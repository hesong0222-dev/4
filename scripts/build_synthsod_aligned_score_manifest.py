#!/usr/bin/env python3
"""Enumerate SynthSOD v2 aligned note-event scores without mirroring audio."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath
from typing import Any

DOI = "10.5281/zenodo.15575778"
URL = "https://zenodo.org/records/15575778"
EXPECTED_MD5 = "121bf77f59869ea332e8968d791a3f8c"
FIELDS = [
    "record_id", "track_name", "score_member_path", "score_sha256", "score_bytes",
    "note_events", "instrument_programs", "start_seconds", "end_seconds",
    "metadata_member_paths", "metadata_duration_seconds", "metadata_sources",
    "source", "source_doi", "source_url", "score_representation",
    "origin_relation", "score_audio_pair_class", "human_performance_claim",
    "printable_engraved_score_claim", "audio_binary_mirrored", "rights_note",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def token(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", PurePosixPath(value).stem.casefold())


def finite(value: str) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def parse_score(data: bytes) -> dict[str, Any]:
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text), delimiter="\t")
    note_count = 0
    programs: Counter[int] = Counter()
    starts: list[float] = []
    ends: list[float] = []
    malformed = 0
    for index, row in enumerate(reader):
        if not row or all(not cell.strip() for cell in row):
            continue
        if len(row) < 4:
            malformed += 1
            continue
        start, end = finite(row[0]), finite(row[1])
        try:
            pitch = int(float(row[2])); program = int(float(row[3]))
        except ValueError:
            if index == 0:
                continue
            malformed += 1
            continue
        if start is None or end is None or end < start or not 0 <= pitch <= 127 or not 0 <= program <= 127:
            malformed += 1
            continue
        note_count += 1
        starts.append(start); ends.append(end); programs[program] += 1
    return {
        "note_events": note_count,
        "programs": dict(sorted(programs.items())),
        "start": min(starts) if starts else None,
        "end": max(ends) if ends else None,
        "malformed": malformed,
    }


def extract_songs(payload: Any) -> dict[str, dict[str, Any]]:
    songs: dict[str, dict[str, Any]] = {}
    if isinstance(payload, dict) and isinstance(payload.get("songs"), dict):
        values = payload["songs"].values()
    elif isinstance(payload, dict) and all(isinstance(v, dict) for v in payload.values()):
        values = payload.values()
    elif isinstance(payload, list):
        values = payload
    else:
        return songs
    for item in values:
        if not isinstance(item, dict):
            continue
        name = str(item.get("song_name") or item.get("name") or item.get("track_name") or "").strip()
        if name:
            songs[name] = item
    return songs


def build(archive_path: Path, output: Path, minimum: int) -> dict[str, Any]:
    metadata: dict[str, dict[str, Any]] = {}
    metadata_members_by_song: dict[str, list[str]] = {}
    zip_extensions: Counter[str] = Counter()
    with zipfile.ZipFile(archive_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            suffix = PurePosixPath(info.filename).suffix.casefold() or "<none>"
            zip_extensions[suffix] += 1
            if suffix != ".json":
                continue
            try:
                payload = json.loads(archive.read(info).decode("utf-8-sig"))
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            for name, item in extract_songs(payload).items():
                metadata[name] = item
                metadata_members_by_song.setdefault(name, []).append(info.filename)

        name_by_token: dict[str, str] = {}
        collisions: set[str] = set()
        for name in metadata:
            key = token(name)
            if key in name_by_token and name_by_token[key] != name:
                collisions.add(key)
            else:
                name_by_token[key] = name
        for key in collisions:
            name_by_token.pop(key, None)

        rows: list[dict[str, Any]] = []
        rejection: Counter[str] = Counter()
        seen_paths: set[str] = set()
        for info in archive.infolist():
            if info.is_dir() or PurePosixPath(info.filename).suffix.casefold() not in {".txt", ".tsv"}:
                continue
            data = archive.read(info)
            parsed = parse_score(data)
            if parsed["note_events"] < 1:
                rejection["not_a_valid_note_event_score"] += 1
                continue
            candidate = name_by_token.get(token(info.filename), PurePosixPath(info.filename).stem)
            meta = metadata.get(candidate, {})
            sources = meta.get("sources") or meta.get("instruments") or []
            if isinstance(sources, dict):
                sources = sorted(sources)
            elif not isinstance(sources, list):
                sources = [str(sources)] if sources else []
            path = info.filename
            if path in seen_paths:
                rejection["duplicate_member_path"] += 1
                continue
            seen_paths.add(path)
            record_id = "synthsod-score-" + hashlib.sha256(path.encode()).hexdigest()[:20]
            rows.append({
                "record_id": record_id,
                "track_name": candidate,
                "score_member_path": path,
                "score_sha256": sha(data),
                "score_bytes": len(data),
                "note_events": parsed["note_events"],
                "instrument_programs": json.dumps(parsed["programs"], separators=(",", ":")),
                "start_seconds": "" if parsed["start"] is None else f"{parsed['start']:.6f}",
                "end_seconds": "" if parsed["end"] is None else f"{parsed['end']:.6f}",
                "metadata_member_paths": "|".join(sorted(metadata_members_by_song.get(candidate, []))),
                "metadata_duration_seconds": meta.get("duration", ""),
                "metadata_sources": "|".join(map(str, sources)),
                "source": "SynthSOD aligned scores v2",
                "source_doi": DOI,
                "source_url": URL,
                "score_representation": "tab-separated note events: onset, offset, MIDI pitch, MIDI instrument",
                "origin_relation": "Derived from the original MIDI used to synthesize the SynthSOD audio and aligned to that audio; v2 removes notes absent from the render",
                "score_audio_pair_class": "midi_derived_note_score_aligned_to_synthetic_orchestra_audio",
                "human_performance_claim": False,
                "printable_engraved_score_claim": False,
                "audio_binary_mirrored": False,
                "rights_note": "Metadata only in this repository; source dataset terms apply",
            })
    rows.sort(key=lambda row: (str(row["track_name"]).casefold(), str(row["score_member_path"])))
    ids = {str(row["record_id"]) for row in rows}
    paths = {str(row["score_member_path"]) for row in rows}
    hashes = {str(row["score_sha256"]) for row in rows}
    if len(rows) < minimum:
        raise RuntimeError(f"found {len(rows)} aligned score records, expected at least {minimum}")
    output.mkdir(parents=True, exist_ok=True)
    manifest = output / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
    summary = {
        "source": "SynthSOD aligned scores v2",
        "source_doi": DOI,
        "source_url": URL,
        "source_archive_expected_md5": EXPECTED_MD5,
        "source_archive_observed_md5": md5_file(archive_path),
        "enumerated_aligned_score_records": len(rows),
        "unique_record_ids": len(ids),
        "unique_member_paths": len(paths),
        "unique_score_hashes": len(hashes),
        "duplicate_score_contents": len(rows) - len(hashes),
        "metadata_song_records": len(metadata),
        "score_records_with_metadata_match": sum(bool(row["metadata_member_paths"]) for row in rows),
        "archive_extension_counts": dict(zip_extensions.most_common()),
        "rejection_counts": dict(rejection.most_common()),
        "score_audio_pair_class": "midi_derived_note_score_aligned_to_synthetic_orchestra_audio",
        "claim": "Full-track note-event scores were obtained from the MIDI used to synthesize SynthSOD and aligned to the corresponding synthetic audio.",
        "not_claimed": ["printable engraved full score", "human performance", "independently authored score edition"],
        "validation": {
            "passed": len(rows) >= minimum and len(rows) == len(ids) == len(paths),
            "archive_md5_matches": md5_file(archive_path) == EXPECTED_MD5,
            "all_have_notes": all(int(row["note_events"]) > 0 for row in rows),
        },
    }
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output / "README.md").write_text(
        "# SynthSOD aligned score inventory\n\n"
        f"- aligned full-track note-event scores: **{len(rows):,}**\n"
        f"- unique score-content hashes: **{len(hashes):,}**\n"
        "- relation: original MIDI → SynthSOD render, with score/audio alignment\n"
        "- human performance: no\n"
        "- printable engraved score: no\n\n"
        "The original audio and score archive are not mirrored; the manifest stores record-level paths, hashes, note counts, instrument programs and provenance.\n",
        encoding="utf-8",
    )
    checksums = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            checksums.append(f"{sha(path.read_bytes())}  {path.name}")
    (output / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum", type=int, default=300)
    args = parser.parse_args()
    if not args.archive.is_file() or args.minimum < 1:
        parser.error("valid archive and positive minimum required")
    print(json.dumps(build(args.archive, args.output, args.minimum), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
