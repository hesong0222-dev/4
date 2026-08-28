#!/usr/bin/env python3
"""Single-pass enumeration of Text2Score's SymphonyNet ABC subset.

The Text2Score code and dataset card identify the subset directory as
`SymphonyNet_Dataset_MXL_abci`. We therefore enumerate that pinned directory
rather than scanning and semantically classifying every source in the 4.73 GB
composite archive. Original SymphonyNet MIDI members are matched by stable
filename tokens and hashed, but MIDI events are not decoded because doing so is
unnecessary for provenance verification.
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
from typing import Iterable

HF_URL = "https://huggingface.co/datasets/emotionwave-company/text2score"
SYMPHONYNET_URL = "https://symphonynet.github.io/"
DRIVE_URL = "https://drive.google.com/file/d/1j9Pvtzaq8k_QIPs8e2ikvCR-BusPluTb/view"
SUBSET_SEGMENT = "symphonynet_dataset_mxl_abci"
DECLARED_ABC = 45_629
DECLARED_MIDI = 46_359
FIELDS = [
    "record_id", "score_member_path", "score_sha256", "score_bytes",
    "title", "composer", "meter", "key", "abc_voice_count",
    "abc_midi_programs", "original_midi_member_path", "original_midi_sha256",
    "original_midi_bytes", "midi_match_method", "source_dataset_card_url",
    "source_midi_collection_url", "source_midi_archive_url", "pair_class",
    "origin_relation", "midi_export_recipe", "pdf_export_recipe",
    "license_claim", "rights_boundary", "human_performance_claim",
    "independent_engraving_claim", "canonical_score_hash",
]


def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical(value: str) -> str:
    name = PurePosixPath(value).name.casefold()
    while PurePosixPath(name).suffix:
        name = PurePosixPath(name).stem
    name = re.sub(r"(?:^|[_\-.])(symphonynet|symphony|midi|mid|score|xml|mxl|abc|abci)(?:[_\-.]|$)", "_", name)
    return re.sub(r"[^a-z0-9]+", "", name)


def path_tokens(value: str) -> set[str]:
    result = {canonical(value)}
    for part in PurePosixPath(value).parts:
        item = canonical(part)
        if len(item) >= 5:
            result.add(item)
    result.update(number.lstrip("0") or "0" for number in re.findall(r"\d{5,}", value))
    return {item for item in result if item}


def is_subset_score(name: str) -> bool:
    folded = name.casefold().replace("-", "_")
    return SUBSET_SEGMENT in folded and PurePosixPath(name).suffix.casefold() in {".abc", ".abci"}


def parse_abc(data: bytes) -> dict[str, object]:
    text = data.decode("utf-8-sig", errors="replace")
    headers: dict[str, str] = {}
    voices: set[str] = set()
    programs: set[int] = set()
    for raw in text.splitlines():
        line = raw.strip()
        header = re.match(r"^([TCMK]):\s*(.*)$", line)
        if header and header.group(1) not in headers:
            headers[header.group(1)] = re.sub(r"\s+", " ", header.group(2)).strip()
        voice = re.match(r"^V:\s*([^\s]+)", line)
        if voice:
            voices.add(voice.group(1))
        voices.update(re.findall(r"\[V:\s*([^\]\s]+)", line))
        for raw_program in re.findall(r"%%MIDI\s+program\s+(\d{1,3})", line, flags=re.I):
            program = int(raw_program)
            if 0 <= program <= 127:
                programs.add(program)
    return {
        "title": headers.get("T", ""),
        "composer": headers.get("C", ""),
        "meter": headers.get("M", ""),
        "key": headers.get("K", ""),
        "voices": len(voices),
        "programs": sorted(programs),
    }


@dataclass(frozen=True)
class MidiMember:
    path: str
    sha256: str
    size: int


def index_midis(path: Path | None) -> tuple[list[MidiMember], dict[str, list[int]]]:
    members: list[MidiMember] = []
    index: dict[str, list[int]] = defaultdict(list)
    if path is None:
        return members, index
    with tarfile.open(path, "r:*") as archive:
        for info in archive:
            if not info.isfile() or PurePosixPath(info.name).suffix.casefold() not in {".mid", ".midi"}:
                continue
            handle = archive.extractfile(info)
            if handle is None:
                continue
            data = handle.read()
            member = MidiMember(info.name, hash_bytes(data), len(data))
            position = len(members)
            members.append(member)
            for token in path_tokens(info.name):
                index[token].append(position)
    return members, index


def match_midi(score_path: str, members: list[MidiMember], index: dict[str, list[int]]) -> tuple[MidiMember | None, str]:
    stem = canonical(score_path)
    exact = [members[position] for position in index.get(stem, []) if canonical(members[position].path) == stem]
    if len(exact) == 1:
        return exact[0], "unique_normalized_basename"
    candidates: Counter[int] = Counter()
    for token in path_tokens(score_path):
        for position in index.get(token, []):
            candidates[position] += 1
    ranked = candidates.most_common()
    if ranked and (len(ranked) == 1 or ranked[0][1] > ranked[1][1]):
        return members[ranked[0][0]], "unique_highest_token_overlap"
    return None, "ambiguous_or_unmatched"


def write_gzip(path: Path, rows: Iterable[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=9) as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader(); writer.writerows(rows)


def write_csv(path: Path, header: list[str], rows: Iterable[Iterable[object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle); writer.writerow(header); writer.writerows(rows)


def build(score_archive: Path, midi_archive: Path | None, output: Path, minimum: int, shard_size: int) -> dict[str, object]:
    midi_members, midi_index = index_midis(midi_archive)
    rows: list[dict[str, object]] = []
    archive_members = 0
    subset_extensions: Counter[str] = Counter()
    match_counts: Counter[str] = Counter()
    with tarfile.open(score_archive, "r:*") as archive:
        for info in archive:
            archive_members += 1
            if not info.isfile() or not is_subset_score(info.name):
                continue
            handle = archive.extractfile(info)
            if handle is None:
                continue
            data = handle.read()
            parsed = parse_abc(data)
            midi, method = match_midi(info.name, midi_members, midi_index)
            match_counts[method] += 1
            subset_extensions[PurePosixPath(info.name).suffix.casefold()] += 1
            score_hash = hash_bytes(data)
            record_id = "text2score-symphonynet-" + hashlib.sha256(info.name.encode()).hexdigest()[:20]
            rows.append({
                "record_id": record_id,
                "score_member_path": info.name,
                "score_sha256": score_hash,
                "score_bytes": len(data),
                "title": parsed["title"],
                "composer": parsed["composer"],
                "meter": parsed["meter"],
                "key": parsed["key"],
                "abc_voice_count": parsed["voices"],
                "abc_midi_programs": json.dumps(parsed["programs"], separators=(",", ":")),
                "original_midi_member_path": midi.path if midi else "",
                "original_midi_sha256": midi.sha256 if midi else "",
                "original_midi_bytes": midi.size if midi else "",
                "midi_match_method": method,
                "source_dataset_card_url": HF_URL,
                "source_midi_collection_url": SYMPHONYNET_URL,
                "source_midi_archive_url": DRIVE_URL,
                "pair_class": "midi_derived_score_renderable_exact",
                "origin_relation": "Text2Score declares this subset as quantized MIDI-to-ABC conversion from SymphonyNet; the ABC is a full symbolic derivative, not an independent edition",
                "midi_export_recipe": "convert ABCI to MusicXML with Text2Score, then export MIDI with MuseScore Studio CLI",
                "pdf_export_recipe": "convert ABCI to MusicXML with Text2Score, then export PDF with MuseScore Studio CLI",
                "license_claim": "Text2Score dataset card identifies the SymphonyNet subset as MIT",
                "rights_boundary": "Underlying composition rights were not independently audited; source binaries are not copied into this repository",
                "human_performance_claim": False,
                "independent_engraving_claim": False,
                "canonical_score_hash": False,
            })
    rows.sort(key=lambda row: (str(row["score_sha256"]), str(row["score_member_path"])))
    seen_hashes: set[str] = set()
    for row in rows:
        score_hash = str(row["score_sha256"])
        row["canonical_score_hash"] = score_hash not in seen_hashes
        seen_hashes.add(score_hash)
    if len(rows) < minimum:
        raise RuntimeError(f"found {len(rows)} SymphonyNet ABC scores, expected at least {minimum}")
    output.mkdir(parents=True, exist_ok=True)
    all_index: list[tuple[str, int, str]] = []
    canonical_rows = [row for row in rows if row["canonical_score_hash"]]
    for name, selected in (("all_records", rows), ("canonical_unique_scores", canonical_rows)):
        index_rows: list[tuple[str, int, str]] = []
        for start in range(0, len(selected), shard_size):
            path = output / name / f"part-{start // shard_size + 1:05d}.csv.gz"
            chunk = selected[start:start + shard_size]
            write_gzip(path, chunk)
            index_rows.append((str(path.relative_to(output)), len(chunk), hash_file(path)))
        write_csv(output / f"{name}_shards.csv", ["file", "rows", "sha256"], index_rows)
        if name == "all_records":
            all_index = index_rows
    write_gzip(output / "sample_100.csv.gz", rows[:100])
    ids = {str(row["record_id"]) for row in rows}
    paths = {str(row["score_member_path"]) for row in rows}
    matched = sum(bool(row["original_midi_member_path"]) for row in rows)
    summary = {
        "source": "Text2Score SymphonyNet subset",
        "source_dataset_card_url": HF_URL,
        "source_collection_url": SYMPHONYNET_URL,
        "dataset_card_declared_scores": DECLARED_ABC,
        "official_symphonynet_declared_midis": DECLARED_MIDI,
        "score_archive_sha256": hash_file(score_archive),
        "midi_archive_sha256": hash_file(midi_archive) if midi_archive else None,
        "composite_archive_members_scanned": archive_members,
        "enumerated_score_records": len(rows),
        "canonical_unique_score_hashes": len(seen_hashes),
        "duplicate_score_records": len(rows) - len(seen_hashes),
        "indexed_original_midi_records": len(midi_members),
        "file_level_original_midi_matches": matched,
        "file_level_original_midi_match_rate": matched / len(rows) if rows else 0,
        "midi_match_method_counts": dict(match_counts.most_common()),
        "subset_extension_counts": dict(subset_extensions.most_common()),
        "pair_class": "midi_derived_score_renderable_exact",
        "claim": "Every row is an ABC score in Text2Score's explicitly named SymphonyNet conversion directory; matching original MIDI files are separately identified where filenames resolve uniquely.",
        "not_claimed": ["independent engraved edition", "human performance", "cross-source unique composition identity"],
        "validation": {
            "passed": len(rows) >= minimum and len(rows) == len(ids) == len(paths),
            "unique_record_ids": len(rows) == len(ids),
            "unique_member_paths": len(rows) == len(paths),
            "all_have_hashes": all(row["score_sha256"] for row in rows),
            "within_declared_count_tolerance": abs(len(rows) - DECLARED_ABC) <= max(25, int(DECLARED_ABC * 0.01)),
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# Text2Score / SymphonyNet MIDI-derived score inventory\n\n"
        f"- enumerated ABC records: **{len(rows):,}**\n"
        f"- unique score-content hashes: **{len(seen_hashes):,}**\n"
        f"- original MIDI filename matches: **{matched:,}**\n"
        f"- dataset-card declared records: **{DECLARED_ABC:,}**\n\n"
        "These are quantized MIDI-derived symbolic scores, not independently engraved editions or human performances.\n",
        encoding="utf-8",
    )
    checksums = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            checksums.append(f"{hash_file(path)}  {path.relative_to(output)}")
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--score-archive", required=True, type=Path)
    parser.add_argument("--midi-archive", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum", type=int, default=40_000)
    parser.add_argument("--shard-size", type=int, default=10_000)
    args = parser.parse_args()
    if not args.score_archive.is_file() or args.minimum < 1 or args.shard_size < 1:
        parser.error("valid archive and positive limits required")
    midi = args.midi_archive if args.midi_archive and args.midi_archive.is_file() else None
    summary = build(args.score_archive, midi, args.output, args.minimum, args.shard_size)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
