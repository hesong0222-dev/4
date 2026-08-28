from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_hauptstimme_aligned_audio_manifest.py"


class HauptstimmeAlignedAudioManifestTest(unittest.TestCase):
    def test_only_concrete_alignment_columns_are_accepted(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "Hauptstimme"
            data = source / "data"
            score_dir = data / "Composer,_One" / "Symphony_No.1" / "1"
            score_dir.mkdir(parents=True)
            (score_dir / "Symphony_1.mscz").write_bytes(b"mscz")
            (score_dir / "Symphony_1.mxl").write_bytes(b"mxl")
            with (score_dir / "Symphony_1_alignment.csv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle)
                writer.writerow(["score_qstamp", "qstamp", "measure", "beat", "1001_tstamp"])
                writer.writerow([0, 0, 1, 1, 0.5])
                writer.writerow([2, 2, 1, 3, 2.5])
            with (data / "scores.tsv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["id", "path", "name", "set_id", "comments"])
                writer.writerow([1, "Composer,_One/Symphony_No.1/1", "Allegro", 1, ""])
            with (data / "audios.tsv").open("w", encoding="utf-8", newline="") as handle:
                writer = csv.writer(handle, delimiter="\t")
                writer.writerow(["id", "performers", "publisher", "year", "imslp_number", "imslp_link", "score_id"])
                writer.writerow([10, "Test Orchestra", "Public archive", 1950, 1001, "https://example.invalid/a.mp3", 1])
                writer.writerow([11, "Unaligned Orchestra", "Public archive", 1951, 1002, "https://example.invalid/b.mp3", 1])
            output = Path(temp) / "out"
            subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--source-root", str(source),
                    "--output", str(output),
                    "--minimum", "1",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["accepted_aligned_audio_score_pairs"], 1)
            self.assertEqual(summary["scores_with_at_least_one_aligned_audio"], 1)
            self.assertEqual(summary["rejection_counts"]["audio_metadata_has_no_alignment_column"], 1)
            self.assertTrue(summary["validation"]["passed"])
            with (output / "manifest.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(rows[0]["imslp_number"], "1001")
            self.assertEqual(rows[0]["alignment_column"], "1001_tstamp")
            self.assertEqual(rows[0]["match_class"], "human_performance_note_onset_aligned_strong_match")
            self.assertEqual(rows[0]["edition_identity_claim"], "False")
            self.assertEqual(rows[0]["human_performance"], "True")


if __name__ == "__main__":
    unittest.main()
