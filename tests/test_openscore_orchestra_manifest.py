from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_openscore_orchestra_manifest.py"


class OpenScoreOrchestraManifestTest(unittest.TestCase):
    def test_primary_scores_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "Hauptstimme"
            data = source / "data" / "Composer,_One" / "Symphony_No.1"
            first = data / "01"
            second = data / "02"
            first.mkdir(parents=True)
            second.mkdir(parents=True)
            for folder, stem in ((first, "Work_01"), (second, "Work_02")):
                (folder / f"{stem}.mxl").write_bytes(b"mxl-" + stem.encode())
                (folder / f"{stem}.mscz").write_bytes(b"mscz-" + stem.encode())
                (folder / f"{stem}.mm.json").write_text("{}\n", encoding="utf-8")
                (folder / f"{stem}_melody.mxl").write_bytes(b"melody")
            output = base / "out"
            subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--source-root", str(source),
                    "--output", str(output),
                    "--minimum", "2",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["enumerated_primary_full_scores"], 2)
            self.assertTrue(summary["validation"]["passed"])
            with (output / "manifest.csv").open(encoding="utf-8", newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 2)
            self.assertTrue(all(not row["mxl_path"].endswith("_melody.mxl") for row in rows))
            self.assertTrue(all(row["score_midi_pair_class"] == "encoded_full_score_deterministic_midi_export" for row in rows))
            self.assertTrue(all(row["human_performance_claim"] == "False" for row in rows))
            self.assertTrue((output / "SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()
