from __future__ import annotations

import csv
import gzip
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "build_text2score_symphonynet_manifest.py"


def midi_bytes(program: int = 40) -> bytes:
    track = bytes([
        0x00, 0xC0, program,
        0x00, 0x90, 60, 100,
        0x83, 0x60, 0x80, 60, 0,
        0x00, 0xFF, 0x2F, 0x00,
    ])
    return b"MThd" + (6).to_bytes(4, "big") + b"\x00\x01\x00\x01\x01\xE0" + b"MTrk" + len(track).to_bytes(4, "big") + track


def add_bytes(archive: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name)
    info.size = len(data)
    archive.addfile(info, io.BytesIO(data))


class Text2ScoreSymphonyNetManifestTest(unittest.TestCase):
    def test_enumerates_marked_and_midi_matched_scores(self) -> None:
        abc_a = b"X:1\nT:Symphonic Test\nC:Tester\nM:4/4\nK:C\nV:v1\n%%MIDI program 40\n[V:v1] CDEF|\n"
        abc_b = b"X:1\nT:Second Test\nM:3/4\nK:Dm\nV:one\nV:two\n%%MIDI program 68\n[V:one] C2D|\n"
        unrelated = b"X:1\nT:Solo Piano\nM:4/4\nK:C\nCDEF|\n"
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            score_tar = base / "scores.tar"
            midi_tar = base / "midi.tar.gz"
            output = base / "out"
            with tarfile.open(score_tar, "w") as archive:
                add_bytes(archive, "dataset/SymphonyNet/alpha.abci", abc_a)
                add_bytes(archive, "dataset/SymphonyNet/alpha-copy.abci", abc_a)
                add_bytes(archive, "dataset/flat/beta.abci", abc_b)
                add_bytes(archive, "dataset/other/piano.abci", unrelated)
                metadata = json.dumps({"source": "SymphonyNet", "midi": "original/beta.mid"}).encode()
                add_bytes(archive, "dataset/flat/beta.json", metadata)
            with tarfile.open(midi_tar, "w:gz") as archive:
                add_bytes(archive, "original/alpha.mid", midi_bytes(40))
                add_bytes(archive, "original/beta.mid", midi_bytes(68))

            completed = subprocess.run([
                sys.executable, str(SCRIPT),
                "--score-archive", str(score_tar),
                "--midi-archive", str(midi_tar),
                "--output", str(output),
                "--minimum", "3",
                "--shard-size", "2",
            ], check=True, capture_output=True, text=True)
            self.assertTrue(completed.stdout.strip())
            summary = json.loads((output / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["enumerated_score_records"], 3)
            self.assertEqual(summary["canonical_unique_score_hashes"], 2)
            self.assertEqual(summary["duplicate_score_records"], 1)
            self.assertGreaterEqual(summary["file_level_source_midi_matches"], 2)
            self.assertTrue(summary["validation"]["passed"])

            with (output / "all_shards.csv").open(encoding="utf-8", newline="") as handle:
                shards = list(csv.DictReader(handle))
            self.assertEqual(sum(int(row["rows"]) for row in shards), 3)
            records = []
            for shard in shards:
                with gzip.open(output / shard["file"], "rt", encoding="utf-8", newline="") as handle:
                    records.extend(csv.DictReader(handle))
            self.assertTrue(all(row["score_midi_pair_class"] == "midi_derived_score_renderable_exact" for row in records))
            self.assertFalse(any("piano.abci" in row["score_member_path"] for row in records))
            self.assertEqual(sum(row["canonical_score_hash"] == "True" for row in records), 2)
            self.assertTrue((output / "SHA256SUMS").is_file())


if __name__ == "__main__":
    unittest.main()
