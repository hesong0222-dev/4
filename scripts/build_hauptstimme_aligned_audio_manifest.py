#!/usr/bin/env python3
"""Build an item-level OpenScore Orchestra ↔ human-audio alignment catalog.

Hauptstimme publishes `scores.tsv`, `audios.tsv`, and per-score alignment CSVs.
Only an audio row whose IMSLP number has a concrete `<number>_tstamp` column in
that score's alignment CSV is accepted. This proves musical timeline alignment,
not identity of the printed edition used by the performers.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

SOURCE_REPO = "MarkGotham/Hauptstimme"
SOURCE_TAG = "v4.7.3"
SOURCE_URL = f"https://github.com/{SOURCE_REPO}/tree/{SOURCE_TAG}"
FIELDS = [
    "match_id", "score_id", "score_name", "composer", "collection", "movement",
    "score_path", "mscz_path", "mscz_sha256", "mxl_path", "mxl_sha256",
    "alignment_path", "alignment_sha256", "alignment_rows", "alignment_column",
    "audio_id", "performers", "publisher", "recording_year", "imslp_number",
    "audio_url", "source_repository", "source_tag", "match_class",
    "alignment_claim", "edition_identity_claim", "human_performance",
    "audio_redistributed", "rights_note",
]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def primary_file(folder: Path, suffix: str) -> Path:
    matches = [path for path in folder.glob(f"*{suffix}") if not path.name.endswith(f"_melody{suffix}")]
    if len(matches) != 1:
        raise RuntimeError(f"expected one primary {suffix} in {folder}, found {len(matches)}")
    return matches[0]


def split_score_path(value: str) -> tuple[str, str, str]:
    parts = Path(value).parts
    if len(parts) < 2:
        return value, "", ""
    composer = parts[0].replace("_", " ")
    collection = parts[1].replace("_", " ")
    movement = parts[2] if len(parts) > 2 else ""
    return composer, collection, movement


def build(source_root: Path) -> tuple[list[dict[str, object]], dict[str, object]]:
    data = source_root / "data"
    score_rows = read_tsv(data / "scores.tsv")
    audio_rows = read_tsv(data / "audios.tsv")
    scores = {row["id"]: row for row in score_rows}
    audio_by_score: dict[str, list[dict[str, str]]] = {}
    for row in audio_rows:
        audio_by_score.setdefault(row["score_id"], []).append(row)

    output: list[dict[str, object]] = []
    rejection_counts: Counter[str] = Counter()
    aligned_scores: set[str] = set()
    performers: Counter[str] = Counter()
    years: Counter[str] = Counter()

    for score_id, score in scores.items():
        folder = data / score["path"]
        alignments = list(folder.glob("*_alignment.csv"))
        if not alignments:
            rejection_counts["score_has_no_alignment_table"] += len(audio_by_score.get(score_id, []))
            continue
        if len(alignments) != 1:
            raise RuntimeError(f"expected one alignment CSV in {folder}, found {len(alignments)}")
        alignment = alignments[0]
        with alignment.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle)
            try:
                header = next(reader)
            except StopIteration:
                rejection_counts["empty_alignment_table"] += len(audio_by_score.get(score_id, []))
                continue
            alignment_rows = sum(1 for _ in reader)
        timestamp_columns = {name[:-7]: name for name in header if name.endswith("_tstamp")}
        if not timestamp_columns:
            rejection_counts["alignment_table_has_no_audio_columns"] += len(audio_by_score.get(score_id, []))
            continue
        mscz = primary_file(folder, ".mscz")
        mxl = primary_file(folder, ".mxl")
        composer, collection, movement = split_score_path(score["path"])
        matched_numbers: set[str] = set()
        for audio in audio_by_score.get(score_id, []):
            number = audio["imslp_number"].strip()
            column = timestamp_columns.get(number)
            if not column:
                rejection_counts["audio_metadata_has_no_alignment_column"] += 1
                continue
            if number in matched_numbers:
                rejection_counts["duplicate_imslp_number_within_score"] += 1
                continue
            matched_numbers.add(number)
            aligned_scores.add(score_id)
            performers[audio["performers"]] += 1
            years[audio["year"] or "unknown"] += 1
            key = f"{score_id}:{number}:{audio['id']}"
            output.append({
                "match_id": "hauptstimme-audio-" + hashlib.sha256(key.encode()).hexdigest()[:20],
                "score_id": score_id,
                "score_name": score["name"],
                "composer": composer,
                "collection": collection,
                "movement": movement,
                "score_path": score["path"],
                "mscz_path": str(mscz.relative_to(source_root)).replace("\\", "/"),
                "mscz_sha256": sha256(mscz),
                "mxl_path": str(mxl.relative_to(source_root)).replace("\\", "/"),
                "mxl_sha256": sha256(mxl),
                "alignment_path": str(alignment.relative_to(source_root)).replace("\\", "/"),
                "alignment_sha256": sha256(alignment),
                "alignment_rows": alignment_rows,
                "alignment_column": column,
                "audio_id": audio["id"],
                "performers": audio["performers"],
                "publisher": audio["publisher"],
                "recording_year": audio["year"],
                "imslp_number": number,
                "audio_url": audio["imslp_link"],
                "source_repository": SOURCE_REPO,
                "source_tag": SOURCE_TAG,
                "match_class": "human_performance_note_onset_aligned_strong_match",
                "alignment_claim": "Repository alignment maps score onset positions to timestamps in this specific IMSLP audio file",
                "edition_identity_claim": False,
                "human_performance": True,
                "audio_redistributed": False,
                "rights_note": "Metadata and source URL only; review IMSLP file-page rights before downloading or redistributing audio",
            })
        for number in timestamp_columns:
            if number not in matched_numbers:
                rejection_counts["alignment_column_missing_audio_metadata"] += 1

    output.sort(key=lambda row: (int(str(row["score_id"])), int(str(row["imslp_number"])), int(str(row["audio_id"]))))
    ids = {str(row["match_id"]) for row in output}
    pairs = {(str(row["score_id"]), str(row["imslp_number"])) for row in output}
    summary = {
        "source": "Hauptstimme / OpenScore Orchestra aligned IMSLP audio",
        "source_repository": SOURCE_REPO,
        "source_tag": SOURCE_TAG,
        "source_url": SOURCE_URL,
        "score_metadata_rows": len(score_rows),
        "audio_metadata_rows": len(audio_rows),
        "accepted_aligned_audio_score_pairs": len(output),
        "scores_with_at_least_one_aligned_audio": len(aligned_scores),
        "unique_match_ids": len(ids),
        "unique_score_imslp_pairs": len(pairs),
        "unique_performer_strings": len(performers),
        "recording_year_counts": dict(sorted(years.items())),
        "top_performer_strings": performers.most_common(25),
        "rejection_counts": dict(rejection_counts.most_common()),
        "match_class": "human_performance_note_onset_aligned_strong_match",
        "claim": "A score-audio temporal alignment table exists for each accepted pair.",
        "not_claimed": [
            "the performers used the exact encoded source edition",
            "note-perfect performance without omissions or interpretive changes",
            "permission to mirror the linked audio file",
        ],
        "human_performance": True,
        "audio_redistributed": False,
        "validation": {
            "passed": bool(output) and len(output) == len(ids) == len(pairs),
            "all_have_alignment_columns": all(row["alignment_column"] for row in output),
            "all_have_score_files": all(row["mscz_path"] and row["mxl_path"] for row in output),
            "all_have_audio_urls": all(row["audio_url"] for row in output),
        },
    }
    return output, summary


def write(output_root: Path, rows: list[dict[str, object]], summary: dict[str, object]) -> None:
    output_root.mkdir(parents=True, exist_ok=True)
    manifest = output_root / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    summary["manifest_sha256"] = sha256(manifest)
    (output_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (output_root / "README.md").write_text(
        "# Hauptstimme aligned orchestral performance catalog\n\n"
        f"- accepted score–audio alignment pairs: **{len(rows):,}**\n"
        f"- scores represented: **{summary['scores_with_at_least_one_aligned_audio']:,}**\n"
        "- class: `human_performance_note_onset_aligned_strong_match`\n"
        "- audio binaries mirrored: **no**\n\n"
        "Every accepted audio has a concrete `<IMSLP number>_tstamp` column in the score's alignment CSV. This is stronger than title matching, but it does not prove that the performers read the exact encoded edition.\n",
        encoding="utf-8",
    )
    checksums = []
    for path in sorted(output_root.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            checksums.append(f"{sha256(path)}  {path.name}")
    (output_root / "SHA256SUMS").write_text("\n".join(checksums) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum", type=int, default=1)
    args = parser.parse_args()
    rows, summary = build(args.source_root)
    if len(rows) < args.minimum:
        raise RuntimeError(f"only {len(rows)} aligned pairs found; minimum is {args.minimum}")
    write(args.output, rows, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
