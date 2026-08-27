#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--stats", required=True, type=Path)
    parser.add_argument("--target", required=True, type=int)
    args = parser.parse_args()

    with args.catalog.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert len(rows) == args.target, (len(rows), args.target)
    assert len({r["match_id"] for r in rows}) == args.target
    assert len({r["source_record_id"] for r in rows}) == args.target
    assert len({r["mxl_path"] for r in rows}) == args.target
    assert all(r["pdf_path"] and r["midi_path"] and r["mxl_path"] for r in rows)
    assert all(
        r["symbolic_match_guarantee"] == "exact_same_source_score_conversion"
        for r in rows
    )
    assert all(r["subset_no_license_conflict"] == "True" for r in rows)
    assert all(r["subset_all_valid"] == "True" for r in rows)
    assert all(r["subset_deduplicated"] == "True" for r in rows)
    assert set(r["confidence_tier"] for r in rows) <= {"A", "B", "C"}

    stats = json.loads(args.stats.read_text(encoding="utf-8"))
    assert stats["selected_exact_matches"] == args.target
    assert stats["selection_complete"] is True
    assert stats["catalog_sha256"] == sha256_file(args.catalog)

    print(
        json.dumps(
            {
                "verified": True,
                "rows": len(rows),
                "classes": dict(Counter(r["orchestra_class"] for r in rows)),
                "tiers": dict(Counter(r["confidence_tier"] for r in rows)),
                "catalog_sha256": sha256_file(args.catalog),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
