#!/usr/bin/env python3
"""Enumerate SymphonyNet-derived ABC full scores in the Text2Score archive.

The resulting rows are not claims of an independently engraved historical score.
Text2Score states that its SymphonyNet subset was produced by quantized MIDI-to-ABC
conversion. Each accepted ABC score can be deterministically converted back to
MusicXML/MIDI, so this is a distinct `midi_derived_score` tier.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import tarfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable, Iterator

HF_REPO = "emotionwave-company/text2score"
HF_ARCHIVE = "ABC_Dataset_only_abci_pkl_json.tar"
HF_URL = f"https://huggingface.co/datasets/{HF_REPO}"
SYMPHONYNET_URL = "https://symphonynet.github.io/"
SYMPHONYNET_DRIVE_ID = "1j9Pvtzaq8k_QIPs8e2ikvCR-BusPluTb"
DATASET_CARD_DECLARED_COUNT = 45_629
OFFICIAL_MIDI_DECLARED_COUNT = 46_359
SOURCE_MARKERS = (
    "symphonynet", "symphony_net", "symphony-net", "symphony midi",
    "symphony_midi", "symphony-midi", "/symphony/", "/symphonies/",
)
SCORE_SUFFIXES = (".abci", ".abc")
MIDI_SUFFIXES = (".mid", ".midi")

FIELDS = [
    "record_id", "source_collection", "source_collection_url",
    "source_dataset_card_url", "source_archive", "score_member_path",
    "score_sha256", "score_bytes", "title", "composer", "meter", "key",
    "abc_voice_count", "abc_midi_programs", "source_detection_method",
    "source_detection_evidence", "source_midi_archive_url",
    "source_midi_member_path", "source_midi_sha256", "source_midi_bytes",
    "source_midi_tracks", "source_midi_note_on_events", "source_midi_programs",
    "source_midi_match_method", "score_midi_pair_class", "origin_relation",
    "midi_materialization_recipe", "pdf_materialization_recipe",
    "license_claim", "underlying_composition_rights", "canonical_score_hash",
]


def normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_token(value: str) -> str:
    value = PurePosixPath(value).name
    while True:
        stem = PurePosixPath(value).stem
        if stem == value:
            break
        value = stem
    value = value.casefold()
    value = re.sub(r"(?:^|[_\-.])(symphonynet|symphony|midi|mid|score|abc|abci)(?:[_\-.]|$)", "_", value)
    return re.sub(r"[^a-z0-9]+", "", value)


def path_tokens(value: str) -> set[str]:
    path = PurePosixPath(value)
    tokens = {canonical_token(path.name)}
    for part in path.parts:
        token = canonical_token(part)
        if len(token) >= 5:
            tokens.add(token)
    for number in re.findall(r"\d{5,}", value):
        tokens.add(number.lstrip("0") or "0")
    return {token for token in tokens if token}


def contains_marker(value: str) -> bool:
    folded = "/" + value.casefold().replace("\\", "/") + "/"
    return any(marker in folded for marker in SOURCE_MARKERS)


def iter_strings(value: Any) -> Iterator[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from iter_strings(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from iter_strings(item)


def source_hint_from_json(data: bytes) -> tuple[bool, str, set[str]]:
    try:
        payload = json.loads(data.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        text = data.decode("utf-8", errors="replace")
        return contains_marker(text), "raw-json-marker" if contains_marker(text) else "", path_tokens(text)
    strings = list(iter_strings(payload))
    joined = "\n".join(strings)
    marker = contains_marker(joined)
    midi_tokens: set[str] = set()
    for text in strings:
        if re.search(r"\.midi?\b", text, flags=re.I):
            midi_tokens.update(path_tokens(text))
    return marker, "json-source-marker" if marker else "", midi_tokens


def parse_abc(data: bytes) -> dict[str, object]:
    text = data.decode("utf-8", errors="replace")
    headers: dict[str, str] = {}
    voices: set[str] = set()
    programs: set[int] = set()
    for raw in text.splitlines():
        line = raw.strip()
        match = re.match(r"^([TCMK]):\s*(.*)$", line)
        if match and match.group(1) not in headers:
            headers[match.group(1)] = normalize(match.group(2))
        voice = re.match(r"^V:\s*([^\s]+)", line)
        if voice:
            voices.add(voice.group(1))
        voices.update(re.findall(r"\[V:\s*([^\]\s]+)", line))
        for program in re.findall(r"%%MIDI\s+program\s+(\d{1,3})", line, flags=re.I):
            number = int(program)
            if 0 <= number <= 127:
                programs.add(number)
    return {
        "title": headers.get("T", ""),
        "composer": headers.get("C", ""),
        "meter": headers.get("M", ""),
        "key": headers.get("K", ""),
        "voice_count": len(voices),
        "programs": sorted(programs),
        "content_marker": contains_marker(text),
    }


def read_varlen(data: bytes, offset: int) -> tuple[int, int]:
    value = 0
    for _ in range(4):
        if offset >= len(data):
            raise ValueError("truncated variable-length integer")
        byte = data[offset]
        offset += 1
        value = (value << 7) | (byte & 0x7F)
        if not byte & 0x80:
            return value, offset
    return value, offset


def parse_midi(data: bytes) -> dict[str, object]:
    if len(data) < 14 or data[:4] != b"MThd":
        return {"tracks": 0, "note_on": 0, "programs": []}
    header_length = int.from_bytes(data[4:8], "big")
    tracks = int.from_bytes(data[10:12], "big")
    offset = 8 + header_length
    note_on = 0
    programs: set[int] = set()
    parsed_tracks = 0
    while offset + 8 <= len(data) and parsed_tracks < tracks:
        if data[offset:offset + 4] != b"MTrk":
            next_track = data.find(b"MTrk", offset + 1)
            if next_track < 0:
                break
            offset = next_track
        length = int.from_bytes(data[offset + 4:offset + 8], "big")
        start = offset + 8
        end = min(len(data), start + length)
        cursor = start
        running: int | None = None
        while cursor < end:
            try:
                _, cursor = read_varlen(data, cursor)
            except ValueError:
                break
            if cursor >= end:
                break
            status = data[cursor]
            if status < 0x80:
                if running is None:
                    break
                status = running
            else:
                cursor += 1
                if status < 0xF0:
                    running = status
            if status == 0xFF:
                if cursor >= end:
                    break
                cursor += 1
                try:
                    size, cursor = read_varlen(data, cursor)
                except ValueError:
                    break
                cursor += size
                running = None
                continue
            if status in (0xF0, 0xF7):
                try:
                    size, cursor = read_varlen(data, cursor)
                except ValueError:
                    break
                cursor += size
                running = None
                continue
            event = status & 0xF0
            channel = status & 0x0F
            data_len = 1 if event in (0xC0, 0xD0) else 2
            if cursor + data_len > end:
                break
            first = data[cursor]
            second = data[cursor + 1] if data_len == 2 else 0
            cursor += data_len
            if event == 0x90 and second > 0:
                note_on += 1
            elif event == 0xC0 and channel != 9:
                programs.add(first)
        parsed_tracks += 1
        offset = end
    return {"tracks": tracks, "note_on": note_on, "programs": sorted(programs)}


@dataclass(frozen=True)
class MidiEntry:
    member: str
    sha256: str
    size: int
    tracks: int
    note_on: int
    programs: tuple[int, ...]


def index_midi_archive(path: Path | None) -> tuple[list[MidiEntry], dict[str, list[int]]]:
    entries: list[MidiEntry] = []
    token_map: dict[str, list[int]] = defaultdict(list)
    if path is None or not path.is_file():
        return entries, token_map
    with tarfile.open(path, "r:*") as archive:
        for member in archive:
            if not member.isfile() or not member.name.casefold().endswith(MIDI_SUFFIXES):
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            parsed = parse_midi(data)
            entry = MidiEntry(
                member=member.name,
                sha256=sha256_bytes(data),
                size=len(data),
                tracks=int(parsed["tracks"]),
                note_on=int(parsed["note_on"]),
                programs=tuple(int(v) for v in parsed["programs"]),
            )
            index = len(entries)
            entries.append(entry)
            for token in path_tokens(member.name):
                token_map[token].append(index)
    return entries, token_map


def pick_midi(score_path: str, hinted_tokens: set[str], entries: list[MidiEntry], token_map: dict[str, list[int]]) -> tuple[MidiEntry | None, str]:
    candidates: Counter[int] = Counter()
    score_token = canonical_token(score_path)
    for token in path_tokens(score_path) | hinted_tokens:
        for index in token_map.get(token, []):
            candidates[index] += 5 if token == score_token else 1
    if not candidates:
        return None, ""
    ranked = candidates.most_common()
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        exact = [index for index, _ in ranked if canonical_token(entries[index].member) == score_token]
        if len(exact) != 1:
            return None, "ambiguous-token-match"
        return entries[exact[0]], "unique-exact-basename"
    return entries[ranked[0][0]], "unique-token-match"


def gzip_csv(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=9) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def plain_csv(path: Path, header: list[str], rows: Iterable[Iterable[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def archive_scan(score_archive: Path, midi_entries: list[MidiEntry], midi_tokens: dict[str, list[int]]) -> tuple[list[dict[str, object]], dict[str, object]]:
    score_members: list[str] = []
    candidate_stems: dict[str, tuple[str, set[str]]] = {}
    prefix_counts: Counter[str] = Counter()
    extension_counts: Counter[str] = Counter()
    json_hints: dict[str, tuple[str, set[str]]] = {}

    with tarfile.open(score_archive, "r:*") as archive:
        for member in archive:
            if not member.isfile():
                continue
            suffix = PurePosixPath(member.name).suffix.casefold()
            extension_counts[suffix or "<none>"] += 1
            parts = PurePosixPath(member.name).parts
            for depth in range(1, min(4, len(parts)) + 1):
                prefix_counts["/".join(parts[:depth])] += 1
            if member.name.casefold().endswith(SCORE_SUFFIXES):
                score_members.append(member.name)
                if contains_marker(member.name):
                    candidate_stems[canonical_token(member.name)] = ("path-marker", set())
                elif any(token in midi_tokens for token in path_tokens(member.name)):
                    candidate_stems[canonical_token(member.name)] = ("midi-name-match", set())
            elif suffix == ".json":
                likely = contains_marker(member.name) or any(token in midi_tokens for token in path_tokens(member.name))
                if not likely:
                    continue
                handle = archive.extractfile(member)
                if handle is None:
                    continue
                marker, method, hinted = source_hint_from_json(handle.read())
                if marker or hinted:
                    json_hints[canonical_token(member.name)] = (method or "json-midi-path", hinted)

    marker_prefixes = {
        prefix for prefix, count in prefix_counts.items()
        if count >= 100 and contains_marker(prefix)
    }
    for name in score_members:
        token = canonical_token(name)
        if token in json_hints:
            method, hinted = json_hints[token]
            candidate_stems[token] = (method, hinted)
        if any(name.startswith(prefix.rstrip("/") + "/") or name == prefix for prefix in marker_prefixes):
            candidate_stems.setdefault(token, ("source-directory-marker", set()))

    rows: list[dict[str, object]] = []
    content_hash_counts: Counter[str] = Counter()
    matched_midi_hashes: Counter[str] = Counter()
    detection_counts: Counter[str] = Counter()
    midi_match_counts: Counter[str] = Counter()
    selected_names = {
        name for name in score_members
        if canonical_token(name) in candidate_stems or contains_marker(name)
    }

    with tarfile.open(score_archive, "r:*") as archive:
        for member in archive:
            if not member.isfile() or member.name not in selected_names:
                continue
            handle = archive.extractfile(member)
            if handle is None:
                continue
            data = handle.read()
            parsed = parse_abc(data)
            token = canonical_token(member.name)
            method, hinted_tokens = candidate_stems.get(token, ("path-marker", set()))
            if parsed["content_marker"] and method not in {"path-marker", "source-directory-marker"}:
                method = "abc-content-marker"
            midi, midi_method = pick_midi(member.name, hinted_tokens, midi_entries, midi_tokens)
            score_hash = sha256_bytes(data)
            content_hash_counts[score_hash] += 1
            if midi:
                matched_midi_hashes[midi.sha256] += 1
            detection_counts[method] += 1
            midi_match_counts[midi_method or "not-file-matched"] += 1
            record_id = "text2score-symphonynet-" + hashlib.sha256(member.name.encode()).hexdigest()[:20]
            rows.append({
                "record_id": record_id,
                "source_collection": "Text2Score / SymphonyNet subset",
                "source_collection_url": SYMPHONYNET_URL,
                "source_dataset_card_url": HF_URL,
                "source_archive": HF_ARCHIVE,
                "score_member_path": member.name,
                "score_sha256": score_hash,
                "score_bytes": len(data),
                "title": parsed["title"],
                "composer": parsed["composer"],
                "meter": parsed["meter"],
                "key": parsed["key"],
                "abc_voice_count": parsed["voice_count"],
                "abc_midi_programs": json.dumps(parsed["programs"], separators=(",", ":")),
                "source_detection_method": method,
                "source_detection_evidence": "archive path/content/sidecar or original MIDI filename token",
                "source_midi_archive_url": f"https://drive.google.com/file/d/{SYMPHONYNET_DRIVE_ID}/view",
                "source_midi_member_path": midi.member if midi else "",
                "source_midi_sha256": midi.sha256 if midi else "",
                "source_midi_bytes": midi.size if midi else "",
                "source_midi_tracks": midi.tracks if midi else "",
                "source_midi_note_on_events": midi.note_on if midi else "",
                "source_midi_programs": json.dumps(midi.programs, separators=(",", ":")) if midi else "",
                "source_midi_match_method": midi_method,
                "score_midi_pair_class": "midi_derived_score_renderable_exact",
                "origin_relation": "Text2Score reports quantized MIDI-to-ABC conversion; ABC can be deterministically converted to MusicXML and MIDI",
                "midi_materialization_recipe": "python text2music/data/batch_abci2xml.py --root_folder <score-dir> && python text2music/data/utils/xml2mid.py --data_dir <score-dir>",
                "pdf_materialization_recipe": "convert ABCI to MusicXML with Text2Score, then export PDF with MuseScore Studio CLI",
                "license_claim": "Text2Score dataset card labels SymphonyNet subset MIT",
                "underlying_composition_rights": "not independently verified; metadata/index only, binaries not redistributed here",
                "canonical_score_hash": content_hash_counts[score_hash] == 1,
            })

    rows.sort(key=lambda row: (str(row["score_sha256"]), str(row["score_member_path"])))
    seen_hashes: set[str] = set()
    for row in rows:
        score_hash = str(row["score_sha256"])
        row["canonical_score_hash"] = score_hash not in seen_hashes
        seen_hashes.add(score_hash)

    inventory = {
        "archive_score_files": len(score_members),
        "selected_symphonynet_score_records": len(rows),
        "unique_score_content_hashes": len(seen_hashes),
        "duplicate_score_records": len(rows) - len(seen_hashes),
        "source_midi_archive_records": len(midi_entries),
        "file_level_source_midi_matches": sum(1 for row in rows if row["source_midi_member_path"]),
        "unique_matched_midi_hashes": len(matched_midi_hashes),
        "source_detection_counts": dict(detection_counts.most_common()),
        "source_midi_match_counts": dict(midi_match_counts.most_common()),
        "archive_extension_counts": dict(extension_counts.most_common()),
        "largest_archive_prefixes": prefix_counts.most_common(100),
        "marker_prefixes": sorted(marker_prefixes),
    }
    return rows, inventory


def write_outputs(output: Path, rows: list[dict[str, object]], inventory: dict[str, object], score_archive: Path, midi_archive: Path | None, shard_size: int) -> dict[str, object]:
    output.mkdir(parents=True, exist_ok=True)
    all_index: list[tuple[str, int, str]] = []
    canonical_rows = [row for row in rows if row["canonical_score_hash"]]
    for start in range(0, len(rows), shard_size):
        chunk = rows[start:start + shard_size]
        path = output / "all_records" / f"part-{start // shard_size + 1:05d}.csv.gz"
        gzip_csv(path, chunk)
        all_index.append((str(path.relative_to(output)), len(chunk), file_sha256(path)))
    canonical_index: list[tuple[str, int, str]] = []
    for start in range(0, len(canonical_rows), shard_size):
        chunk = canonical_rows[start:start + shard_size]
        path = output / "canonical_unique_scores" / f"part-{start // shard_size + 1:05d}.csv.gz"
        gzip_csv(path, chunk)
        canonical_index.append((str(path.relative_to(output)), len(chunk), file_sha256(path)))
    plain_csv(output / "all_shards.csv", ["file", "rows", "sha256"], all_index)
    plain_csv(output / "canonical_shards.csv", ["file", "rows", "sha256"], canonical_index)
    gzip_csv(output / "sample_100.csv.gz", rows[:100])

    total = len(rows)
    canonical = len(canonical_rows)
    summary = {
        "source": "Text2Score SymphonyNet subset",
        "source_dataset_card_url": HF_URL,
        "source_collection_url": SYMPHONYNET_URL,
        "dataset_card_declared_symphonynet_scores": DATASET_CARD_DECLARED_COUNT,
        "official_symphonynet_declared_midis": OFFICIAL_MIDI_DECLARED_COUNT,
        "enumerated_score_records": total,
        "canonical_unique_score_hashes": canonical,
        "duplicate_score_records": total - canonical,
        "file_level_source_midi_matches": inventory["file_level_source_midi_matches"],
        "requested_project_target": 10_000,
        "target_reached_by_this_tier": canonical >= 10_000,
        "target_shortfall_by_this_tier": max(0, 10_000 - canonical),
        "score_archive_sha256": file_sha256(score_archive),
        "source_midi_archive_sha256": file_sha256(midi_archive) if midi_archive and midi_archive.is_file() else None,
        "pair_class": "midi_derived_score_renderable_exact",
        "pair_claim": "The ABC score is a quantized symbolic derivative of SymphonyNet MIDI and can itself be deterministically rendered/exported to MIDI; this is not an independently engraved edition.",
        "human_performance_claim": False,
        "license_boundary": "Dataset card claims MIT for SymphonyNet subset; underlying composition rights are not independently verified. This repository stores metadata only.",
        "inventory": inventory,
        "validation": {
            "unique_record_ids": len({str(row["record_id"]) for row in rows}) == total,
            "unique_score_member_paths": len({str(row["score_member_path"]) for row in rows}) == total,
            "all_score_hashes_present": all(row["score_sha256"] for row in rows),
            "passed": total > 0 and len({str(row["record_id"]) for row in rows}) == total,
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Text2Score / SymphonyNet MIDI-derived score manifest\n\n"
        f"- enumerated ABC scores: **{total:,}**\n"
        f"- unique score-content hashes: **{canonical:,}**\n"
        f"- file-level matches to original SymphonyNet MIDI archive: **{inventory['file_level_source_midi_matches']:,}**\n"
        f"- dataset-card declared SymphonyNet scores: **{DATASET_CARD_DECLARED_COUNT:,}**\n\n"
        "These are quantized MIDI-derived ABC scores, not independently engraved historical editions. "
        "They are stored as metadata paths and reproducible conversion recipes; source binaries are not mirrored.\n",
        encoding="utf-8",
    )
    sums = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            sums.append(f"{file_sha256(path)}  {path.relative_to(output)}")
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-archive", required=True, type=Path)
    parser.add_argument("--midi-archive", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--shard-size", type=int, default=10_000)
    parser.add_argument("--minimum", type=int, default=1)
    args = parser.parse_args()
    if not args.score_archive.is_file():
        parser.error("score archive not found")
    if args.shard_size < 1 or args.minimum < 1:
        parser.error("positive shard size and minimum required")
    midi_archive = args.midi_archive if args.midi_archive and args.midi_archive.is_file() else None
    midi_entries, midi_tokens = index_midi_archive(midi_archive)
    rows, inventory = archive_scan(args.score_archive, midi_entries, midi_tokens)
    summary = write_outputs(args.output, rows, inventory, args.score_archive, midi_archive, args.shard_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    if len(rows) < args.minimum:
        raise RuntimeError(f"enumerated {len(rows)} records, expected at least {args.minimum}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
