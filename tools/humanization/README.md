# MIDI-only humanization transformer

This directory preserves the locally validated transformer payload for the adaptive humanization pipeline.

## Status

- **Audio rendering remains HOLD.**
- The transformer only creates `render_control.mid` plus `groove_map.json` from an immutable canonical MIDI and a plan JSON.
- It is designed for the `SYNTH_CANONICAL_SCORE_TARGET` relationship: future input audio may come from the transformed control MIDI, while the target remains the original canonical MIDI.

## Restore source

```bash
base64 --decode tools/humanization/apply_humanization.py.gz.b64 \
  | gzip --decompress > /tmp/apply_humanization.py
```

Requires Python and `mido`.

## Implemented behavior

- seeded groove template timing;
- swing/shuffle timing;
- persistent per-track timing tendency;
- correlated bar drift and anchor-group drift;
- track-specific timing/velocity/duration/chord-spread strengths;
- local fast-passage timing attenuation;
- tempo/density-aware safety bounds;
- chord/strum spreading without crossing the next canonical onset;
- event-order protection;
- one-to-one canonical event mapping;
- canonical SHA-256 provenance;
- explicit `audio_rendered=false` output.

## Clean-tier QA

The tool aborts if its output fails pitch identity, note-count, one-to-one event mapping, positive duration, or distinct-onset ordering checks.

The companion local validation report is `validation_report.json`.
