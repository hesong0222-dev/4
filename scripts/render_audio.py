#!/usr/bin/env python3
"""Render one exact-match MIDI to audio using FluidSynth.

Example:
  python scripts/render_audio.py \
    --mid /data/PDMX/mid/foo.mid \
    --out audio/foo.wav \
    --soundfont /soundfonts/GeneralUser-GS.sf2
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mid", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--soundfont", required=True, type=Path)
    parser.add_argument("--sample-rate", type=int, default=44_100)
    parser.add_argument("--gain", type=float, default=0.6)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    fluidsynth = shutil.which("fluidsynth")
    if not fluidsynth:
        parser.error("fluidsynth is not installed or not on PATH")
    if not args.mid.is_file():
        parser.error(f"MIDI not found: {args.mid}")
    if not args.soundfont.is_file():
        parser.error(f"SoundFont not found: {args.soundfont}")
    if args.out.exists() and not args.force:
        print(f"skip existing: {args.out}")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    command = [
        fluidsynth,
        "-ni",
        str(args.soundfont),
        str(args.mid),
        "-F",
        str(args.out),
        "-r",
        str(args.sample_rate),
        "-g",
        str(args.gain),
    ]
    subprocess.run(command, check=True)
    if not args.out.is_file() or args.out.stat().st_size == 0:
        raise RuntimeError(f"FluidSynth produced no output: {args.out}")
    print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
