#!/usr/bin/env python3
"""Extract only catalog-selected files from a PDMX .tar.gz archive safely."""
from __future__ import annotations

import argparse
import csv
import os
import tarfile
from pathlib import Path, PurePosixPath

COLUMN_BY_KIND = {"mxl": "mxl_path", "pdf": "pdf_path", "mid": "midi_path"}


def normalize_member(path: str) -> str:
    value = path.strip().removeprefix("./")
    pure = PurePosixPath(value)
    if pure.is_absolute() or ".." in pure.parts:
        raise ValueError(f"unsafe archive path: {path}")
    return pure.as_posix()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--kind", required=True, choices=sorted(COLUMN_BY_KIND))
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()

    column = COLUMN_BY_KIND[args.kind]
    with args.catalog.open("r", encoding="utf-8", newline="") as handle:
        wanted = {normalize_member(row[column]) for row in csv.DictReader(handle)}

    args.output_root.mkdir(parents=True, exist_ok=True)
    extracted = 0
    with tarfile.open(args.archive, "r:gz") as archive:
        for member in archive:
            if not member.isfile():
                continue
            normalized = normalize_member(member.name)
            if normalized not in wanted:
                continue
            target = (args.output_root / normalized).resolve()
            root = args.output_root.resolve()
            if os.path.commonpath([root, target]) != str(root):
                raise ValueError(f"path traversal rejected: {member.name}")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = archive.extractfile(member)
            if source is None:
                continue
            with source, target.open("wb") as destination:
                destination.write(source.read())
            extracted += 1

    missing = len(wanted) - extracted
    if missing:
        raise RuntimeError(f"archive missing {missing} selected {args.kind} files")
    print(f"extracted={extracted} kind={args.kind} root={args.output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
