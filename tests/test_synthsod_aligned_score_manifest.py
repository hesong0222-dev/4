from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_synthsod_aligned_score_manifest.py"


def main() -> None:
    with tempfile.TemporaryDirectory() as temp:
        base = Path(temp)
        archive = base / "scores.zip"
        output = base / "out"
        metadata = {
            "songs": {
                "a": {"song_name": "Track_A", "duration": 10.0, "sources": ["Violin_1", "Cello"]},
                "b": {"song_name": "Track_B", "duration": 12.0, "sources": ["Flute", "Horn"]},
            }
        }
        score_a = "start\tend\tpitch\tinstrument\n0.0\t1.0\t60\t40\n1.0\t2.0\t62\t42\n"
        score_b = "0.5\t1.5\t72\t73\n1.5\t3.0\t67\t60\n"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as handle:
            handle.writestr("metadata/train.json", json.dumps(metadata))
            handle.writestr("scores/Track_A.txt", score_a)
            handle.writestr("scores/Track_B.txt", score_b)
            handle.writestr("notes/readme.txt", "not a score")
        completed = subprocess.run(
            [sys.executable, str(SCRIPT), "--archive", str(archive), "--output", str(output), "--minimum", "2"],
            check=True,
            capture_output=True,
            text=True,
        )
        assert completed.stdout.strip()
        summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
        assert summary["enumerated_aligned_score_records"] == 2
        assert summary["unique_score_hashes"] == 2
        assert summary["metadata_song_records"] == 2
        assert summary["score_records_with_metadata_match"] == 2
        assert summary["validation"]["passed"] is True
        with (output / "manifest.csv").open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))
        assert len(rows) == 2
        assert all(row["score_audio_pair_class"] == "midi_derived_note_score_aligned_to_synthetic_orchestra_audio" for row in rows)
        assert all(row["human_performance_claim"] == "False" for row in rows)
        assert all(row["printable_engraved_score_claim"] == "False" for row in rows)
        assert (output / "SHA256SUMS").is_file()


if __name__ == "__main__":
    main()
