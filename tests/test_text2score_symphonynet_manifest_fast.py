from __future__ import annotations

import csv
import gzip
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_text2score_symphonynet_manifest_fast.py"


def add(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name); info.size = len(data); archive.addfile(info, io.BytesIO(data))


def midi(program: int) -> bytes:
    track = bytes([0, 0xC0, program, 0, 0x90, 60, 100, 1, 0x80, 60, 0, 0, 0xFF, 0x2F, 0])
    return b"MThd" + (6).to_bytes(4, "big") + b"\x00\x01\x00\x01\x01\xE0" + b"MTrk" + len(track).to_bytes(4, "big") + track


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp); scores = root / "scores.tar"; midis = root / "midis.tar.gz"; output = root / "out"
        abc_a = b"X:1\nT:Alpha\nC:Tester\nM:4/4\nK:C\nV:one\n%%MIDI program 40\n[V:one] CDEF|\n"
        abc_b = b"X:2\nT:Beta\nM:3/4\nK:Dm\nV:one\nV:two\n%%MIDI program 68\n[V:one] C2D|\n"
        with tarfile.open(scores, "w") as archive:
            add(archive, "ABC_Dataset/SymphonyNet_Dataset_MXL_abci/alpha.abci", abc_a)
            add(archive, "ABC_Dataset/SymphonyNet_Dataset_MXL_abci/beta.abci", abc_b)
            add(archive, "ABC_Dataset/PDMX_MXL_abci/ignore.abci", abc_a)
        with tarfile.open(midis, "w:gz") as archive:
            add(archive, "SymphonyNet/alpha.mid", midi(40))
            add(archive, "SymphonyNet/beta.mid", midi(68))
        subprocess.run([
            sys.executable, str(SCRIPT), "--score-archive", str(scores), "--midi-archive", str(midis),
            "--output", str(output), "--minimum", "2", "--shard-size", "1",
        ], check=True, capture_output=True, text=True)
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        assert summary["enumerated_score_records"] == 2
        assert summary["canonical_unique_score_hashes"] == 2
        assert summary["file_level_original_midi_matches"] == 2
        assert summary["validation"]["passed"] is True
        with (output / "all_records_shards.csv").open(encoding="utf-8", newline="") as handle:
            shards = list(csv.DictReader(handle))
        rows = []
        for shard in shards:
            with gzip.open(output / shard["file"], "rt", encoding="utf-8", newline="") as handle:
                rows.extend(csv.DictReader(handle))
        assert len(rows) == 2
        assert all(row["pair_class"] == "midi_derived_score_renderable_exact" for row in rows)
        assert all(row["human_performance_claim"] == "False" for row in rows)


if __name__ == "__main__":
    main()
