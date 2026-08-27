from __future__ import annotations

import csv
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "scripts" / "build_manifest.py"
VERIFY = ROOT / "scripts" / "verify_manifest.py"


class PipelineTest(unittest.TestCase):
    def test_synthetic_exact_catalog(self) -> None:
        fields = [
            "path", "mxl", "pdf", "mid", "n_tracks", "tracks",
            "subset:no_license_conflict", "subset:all_valid", "subset:deduplicated",
            "has_paywall", "is_draft", "n_notes", "song_length.bars",
            "song_length.seconds", "song_name", "title", "subtitle", "genres",
            "groups", "tags", "composer_name", "artist_name", "license",
            "license_url", "rating", "n_ratings", "n_views", "is_official",
            "has_annotations", "has_custom_audio",
        ]
        with tempfile.TemporaryDirectory() as temp:
            temp_path = Path(temp)
            source = temp_path / "PDMX.csv"
            rows = []
            orchestra_programs = "40-41-42-43-47-56-57-58-68-69-70-71-72-73"
            for index in range(12):
                rows.append(
                    {
                        "path": f"./data/{index:06d}.mscz",
                        "mxl": f"./mxl/{index:06d}.mxl",
                        "pdf": f"./pdf/{index:06d}.pdf",
                        "mid": f"./mid/{index:06d}.mid",
                        "n_tracks": "14",
                        "tracks": orchestra_programs,
                        "subset:no_license_conflict": "True",
                        "subset:all_valid": "True",
                        "subset:deduplicated": "True",
                        "has_paywall": "False",
                        "is_draft": "False",
                        "n_notes": str(2000 + index),
                        "song_length.bars": "100",
                        "song_length.seconds": "360",
                        "song_name": f"Symphony {index}",
                        "title": f"Symphony {index} Full Score",
                        "subtitle": "",
                        "genres": "classical-orchestral",
                        "groups": "orchestra",
                        "tags": "symphony-fullscore",
                        "composer_name": "Synthetic Composer",
                        "artist_name": "",
                        "license": "publicdomain",
                        "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
                        "rating": "4.8",
                        "n_ratings": "20",
                        "n_views": "1000",
                        "is_official": "False",
                        "has_annotations": "True",
                        "has_custom_audio": "False",
                    }
                )
            # Must be rejected despite containing isolated orchestral programs.
            rows.append(
                {
                    "path": "./data/noise.mscz", "mxl": "./mxl/noise.mxl",
                    "pdf": "./pdf/noise.pdf", "mid": "./mid/noise.mid",
                    "n_tracks": "10", "tracks": "0-0-24-25-32-33-40-48-56-64",
                    "subset:no_license_conflict": "True", "subset:all_valid": "True",
                    "subset:deduplicated": "True", "has_paywall": "False",
                    "is_draft": "False", "n_notes": "1000",
                    "song_length.bars": "50", "song_length.seconds": "200",
                    "song_name": "Rock Band", "title": "Rock Band", "subtitle": "",
                    "genres": "rock", "groups": "band", "tags": "rock-band",
                    "composer_name": "Noise", "artist_name": "",
                    "license": "publicdomain", "license_url": "", "rating": "1",
                    "n_ratings": "0", "n_views": "0", "is_official": "False",
                    "has_annotations": "False", "has_custom_audio": "False",
                }
            )
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            output = temp_path / "data"
            subprocess.run(
                [sys.executable, str(BUILD), "--input", str(source), "--output-dir", str(output), "--target", "10", "--source-md5", "synthetic"],
                check=True,
                capture_output=True,
                text=True,
            )
            subprocess.run(
                [sys.executable, str(VERIFY), "--catalog", str(output / "orchestra_exact_10.csv"), "--stats", str(output / "stats.json"), "--target", "10"],
                check=True,
                capture_output=True,
                text=True,
            )
            stats = json.loads((output / "stats.json").read_text(encoding="utf-8"))
            self.assertEqual(stats["selected_exact_matches"], 10)
            self.assertEqual(stats["qualifying_candidates_before_defensive_dedup"], 12)
            self.assertEqual(stats["rejection_counts"]["not_orchestral_or_too_small"], 1)


if __name__ == "__main__":
    unittest.main()
