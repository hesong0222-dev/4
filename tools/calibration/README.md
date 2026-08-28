# Empirical MIDI humanization calibration

This directory stores the one-shot analyzer payload and calibration provenance. The run is MIDI-only: it parses event timing, velocity, duration, note density, chord spread, swing and fast passages; it never invokes a DAW, VST, SoundFont or audio renderer.

The authoritative source registry is `configs/real_midi_calibration_sources.json`, and the methodology is `docs/REAL-MIDI-HUMANIZATION-CALIBRATION.md`.
