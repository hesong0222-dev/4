from __future__ import annotations

import csv
import gzip
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_pdmx_all_orchestra_manifest.py"


class AllArrangementOrchestraManifestTest(unittest.TestCase):
    def test_tiered_selection_and_exact_source_paths(self) -> None:
        fields = [
            "path", "mxl", "pdf", "mid", "tracks", "n_tracks", "n_notes",
            "song_length.bars", "song_length.seconds", "subset:no_license_conflict",
            "subset:all_valid", "subset:deduplicated", "is_best_unique_arrangement",
            "title", "song_name", "subtitle", "composer_name", "artist_name",
            "genres", "groups", "tags", "license", "license_url", "has_paywall",
            "is_draft", "has_lyrics", "has_custom_audio",
        ]

        def row(
            key: str,
            title: str,
            tracks: str,
            *,
            deduplicated: bool = True,
            license_ok: bool = True,
            all_valid: bool = True,
            n_tracks: int | None = None,
        ) -> dict[str, object]:
            programs = tracks.split("-") if tracks else []
            return {
                "path": f"./data/{key}.mscz",
                "mxl": f"./mxl/{key}.mxl",
                "pdf": f"./pdf/{key}.pdf",
                "mid": f"./mid/{key}.mid",
                "tracks": tracks,
                "n_tracks": n_tracks if n_tracks is not None else len(programs),
                "n_notes": 2500,
                "song_length.bars": 80,
                "song_length.seconds": 300,
                "subset:no_license_conflict": license_ok,
                "subset:all_valid": all_valid,
                "subset:deduplicated": deduplicated,
                "is_best_unique_arrangement": deduplicated,
                "title": title,
                "song_name": title,
                "subtitle": "Full Score",
                "composer_name": "Synthetic Composer",
                "artist_name": "",
                "genres": "classical",
                "groups": "orchestra",
                "tags": "full score",
                "license": "publicdomain",
                "license_url": "https://creativecommons.org/publicdomain/mark/1.0/",
                "has_paywall": False,
                "is_draft": False,
                "has_lyrics": False,
                "has_custom_audio": False,
            }

        rows = [
            row("symphony", "Symphony Orchestra", "40-40-41-42-48-68-69-56-57-47"),
            row("opera", "Opera Orchestra Full Score", "40-40-41-42-48-68-56-57-47-52"),
            row("strings", "String Orchestra", "40-40-41-42-43"),
            row("winds", "Wind Orchestra Full Score", "56-56-57-58-64-65-68-69-47"),
            row("chamber-alt", "Chamber Orchestra", "40-41-42-48-68-56", deduplicated=False),
            row("reduction", "Symphony Piano Reduction", "0-0-0-0-40-56"),
            row("rock", "Rock Band Full Score", "24-25-32-33-40-56-68-47"),
            row("conflict", "Orchestra", "40-40-41-42-48-68-56-57-47", license_ok=False),
            row("invalid", "Orchestra", "40-40-41-42-48-68-56-57-47", all_valid=False),
        ]

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "PDMX.csv"
            output = base / "out"
            with source.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)

            completed = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--input", str(source),
                    "--output", str(output),
                    "--minimum-inclusive", "5",
                    "--shard-size", "2",
                    "--source-md5", "synthetic",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertTrue(completed.stdout.strip())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["inclusive_orchestra_score_midi_records"], 5)
            self.assertEqual(summary["strict_records"], 4)
            self.assertEqual(summary["probable_records"], 1)
            self.assertEqual(summary["candidate_records"], 0)
            self.assertEqual(summary["canonical_deduplicated_records"], 4)
            self.assertTrue(summary["validation"]["passed"])
            self.assertEqual(summary["exactness_definition"]["class"], "same_symbolic_source_exact")
            self.assertFalse(summary["exactness_definition"]["human_performance_claim"])
            self.assertEqual(summary["rejection_counts"]["reduction_or_piano_vocal_score"], 1)
            self.assertEqual(summary["rejection_counts"]["explicit_non_orchestral_band"], 1)
            self.assertEqual(summary["rejection_counts"]["license_conflict_or_unknown"], 1)
            self.assertEqual(summary["rejection_counts"]["not_all_formats_valid"], 1)

            with (output / "all_shards.csv").open(encoding="utf-8", newline="") as handle:
                shard_index = list(csv.DictReader(handle))
            self.assertEqual(sum(int(item["rows"]) for item in shard_index), 5)
            with gzip.open(output / "all_records" / shard_index[0]["file"], "rt", encoding="utf-8") as handle:
                first_record = next(csv.DictReader(handle))
            self.assertEqual(first_record["exactness_class"], "same_symbolic_source_exact")
            self.assertTrue(first_record["mxl"] and first_record["pdf"] and first_record["mid"])
            self.assertTrue((output / "SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()
