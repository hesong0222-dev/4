#!/usr/bin/env python3
"""Enumerate every full orchestral score in MarkGotham/Hauptstimme.

The OpenScore Orchestra repository stores one primary `.mscz` and `.mxl` pair per
movement. MIDI and PDF are deterministic exports of that exact encoded score.
Melody-only derivative files (`*_melody.mxl`) are excluded.
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
ZENODO_URL = "https://zenodo.org/records/21367032"
FIELDS = [
    "record_id", "composer", "collection", "movement", "source_repository",
    "source_tag", "source_url", "zenodo_url", "mscz_path", "mscz_blob_sha256",
    "mscz_bytes", "mxl_path", "mxl_blob_sha256", "mxl_bytes",
    "measure_map_path", "full_score_format", "midi_available_as_source_file",
    "midi_materialization_recipe", "pdf_materialization_recipe",
    "score_midi_pair_class", "origin_relation", "score_license",
    "annotation_license", "human_performance_claim",
]


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            value.update(block)
    return value.hexdigest()


def slug(value: str) -> str:
    return "-".join(part for part in "".join(ch.casefold() if ch.isalnum() else " " for ch in value).split() if part)


def enumerate_scores(root: Path) -> list[dict[str, object]]:
    data = root / "data"
    if not data.is_dir():
        raise RuntimeError(f"missing OpenScore data directory: {data}")
    rows: list[dict[str, object]] = []
    for mxl in sorted(data.rglob("*.mxl")):
        if mxl.name.endswith("_melody.mxl"):
            continue
        relative = mxl.relative_to(root)
        parts = relative.parts
        if len(parts) < 4 or parts[0] != "data":
            continue
        composer_dir = parts[1]
        collection_dir = parts[2]
        movement = parts[-2] if len(parts) >= 5 else ""
        mscz = mxl.with_suffix(".mscz")
        if not mscz.is_file():
            raise RuntimeError(f"primary MXL has no matching MSCZ: {relative}")
        measure_map = mxl.with_suffix(".mm.json")
        key = "/".join(parts[1:-1])
        record_id = "openscore-orchestra-" + hashlib.sha256(key.encode("utf-8")).hexdigest()[:20]
        mxl_rel = str(relative).replace("\\", "/")
        mscz_rel = str(mscz.relative_to(root)).replace("\\", "/")
        mm_rel = str(measure_map.relative_to(root)).replace("\\", "/") if measure_map.is_file() else ""
        rows.append({
            "record_id": record_id,
            "composer": composer_dir.replace("_", " ").replace(", ", ", "),
            "collection": collection_dir.replace("_", " "),
            "movement": movement,
            "source_repository": SOURCE_REPO,
            "source_tag": SOURCE_TAG,
            "source_url": f"https://github.com/{SOURCE_REPO}/tree/{SOURCE_TAG}/{str(relative.parent).replace(chr(92), '/')}",
            "zenodo_url": ZENODO_URL,
            "mscz_path": mscz_rel,
            "mscz_blob_sha256": digest(mscz),
            "mscz_bytes": mscz.stat().st_size,
            "mxl_path": mxl_rel,
            "mxl_blob_sha256": digest(mxl),
            "mxl_bytes": mxl.stat().st_size,
            "measure_map_path": mm_rel,
            "full_score_format": "MuseScore + compressed MusicXML",
            "midi_available_as_source_file": False,
            "midi_materialization_recipe": f"mscore -o <output>/{slug(record_id)}.mid <checkout>/{mscz_rel}",
            "pdf_materialization_recipe": f"mscore -o <output>/{slug(record_id)}.pdf <checkout>/{mscz_rel}",
            "score_midi_pair_class": "encoded_full_score_deterministic_midi_export",
            "origin_relation": "MIDI is exported from the exact repository MuseScore full score; no title matching is used",
            "score_license": "CC0 1.0 Universal",
            "annotation_license": "CC BY-SA",
            "human_performance_claim": False,
        })
    if not rows:
        raise RuntimeError("no primary OpenScore Orchestra MXL records found")
    return rows


def write(root: Path, rows: list[dict[str, object]], source_root: Path) -> dict[str, object]:
    root.mkdir(parents=True, exist_ok=True)
    manifest = root / "manifest.csv"
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    ids = {str(row["record_id"]) for row in rows}
    mxls = {str(row["mxl_path"]) for row in rows}
    collections = Counter(str(row["collection"]) for row in rows)
    composers = Counter(str(row["composer"]) for row in rows)
    summary = {
        "source": "OpenScore Orchestra / Hauptstimme",
        "source_repository": SOURCE_REPO,
        "source_tag": SOURCE_TAG,
        "source_url": SOURCE_URL,
        "zenodo_url": ZENODO_URL,
        "enumerated_primary_full_scores": len(rows),
        "unique_record_ids": len(ids),
        "unique_mxl_paths": len(mxls),
        "composer_counts": dict(sorted(composers.items())),
        "collection_counts": dict(sorted(collections.items())),
        "manifest_sha256": digest(manifest),
        "pair_class": "encoded_full_score_deterministic_midi_export",
        "exactness_claim": "Each MIDI can be deterministically exported from the exact MSCZ/MXL source score referenced by the row.",
        "midi_files_prepackaged_in_source": False,
        "human_performance_claim": False,
        "licenses": {"scores": "CC0 1.0 Universal", "annotations": "CC BY-SA", "code": "MIT"},
        "source_checkout_sha256_scope": "Per-file SHA-256 values are recorded for each primary MSCZ and MXL at the pinned tag.",
        "validation": {
            "passed": len(rows) == len(ids) == len(mxls),
            "all_have_mscz": all((source_root / str(row["mscz_path"])).is_file() for row in rows),
            "all_have_mxl": all((source_root / str(row["mxl_path"])).is_file() for row in rows),
        },
    }
    (root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# OpenScore Orchestra score–MIDI manifest\n\n"
        f"- primary full-score records: **{len(rows):,}**\n"
        f"- pinned repository tag: `{SOURCE_TAG}`\n"
        "- source formats: MuseScore (`.mscz`) and compressed MusicXML (`.mxl`)\n"
        "- MIDI relation: deterministic export from the exact encoded full score\n"
        "- human-performance claim: none\n\n"
        "The source release does not prepackage a MIDI beside every score. The manifest therefore stores an explicit MuseScore CLI export recipe rather than pretending that an independently supplied MIDI exists.\n",
        encoding="utf-8",
    )
    checksum_lines = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.name != "SHA256SUMS":
            checksum_lines.append(f"{digest(path)}  {path.name}")
    (root / "SHA256SUMS").write_text("\n".join(checksum_lines) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--minimum", type=int, default=90)
    args = parser.parse_args()
    rows = enumerate_scores(args.source_root)
    if len(rows) < args.minimum:
        raise RuntimeError(f"only {len(rows)} primary scores found; expected at least {args.minimum}")
    print(json.dumps(write(args.output, rows, args.source_root), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
