# Orchestra Score–Audio / Score–MIDI Match Catalog (10,000+)

A reproducible catalog targeting **10,000+ unique orchestral full-score matches**. The project now counts two exact-match classes separately:

1. **real performance ↔ full score** — a human/orchestral recording validated against the score/edition as strongly as the available evidence permits;
2. **full score ↔ MIDI** — MIDI generated from, or distributed with, the exact same symbolic score source.

A MIDI-only record is valid even when no real audio exists. It is never mislabeled as a human performance.

## Exactness classes

| Class | Counted as exact? | Requirement |
|---|---:|---|
| `real_audio_verified_exact` | yes | recording and score validated at work/movement/arrangement/edition-content level |
| `midi_same_source_exact` | yes | PDF/MusicXML/LilyPond/MuseScore score and MIDI share the same source record |
| `real_audio_strong_match` | no, separate tier | strong work/movement match but edition-level identity not proven |
| `midi_score_candidate_unverified` | no | orchestral MIDI exists but the corresponding score source is not yet proven |

## Main exact score–MIDI sources

- **PDMX v9** — 250K+ public-domain MusicXML scores; associated MXL/PDF/MIDI exports when valid. This is the bulk source.
- **Mutopia Project / Orchestra** — curated public-domain/open scores with LilyPond source, PDF and MIDI from the same edition.
- **OpenScore Orchestra** — approximately 100 high-quality transcribed orchestral movements; MIDI can be deterministically exported from the exact MuseScore/MusicXML source.

Discovery-only corpora such as **SymphonyNet** and **SOD** are not counted as exact until a corresponding full score is proven. See [docs/SOURCES.md](docs/SOURCES.md).

## PDMX selection rules

A row must pass provenance/availability checks and an orchestral instrumentation rule derived from PDMX General MIDI programs plus metadata. The catalog distinguishes:

- `full_orchestra`
- `string_orchestra`
- `wind_orchestra`
- `explicit_orchestra`
- `chamber_orchestra`
- `inferred_orchestra`
- `orchestral_ensemble`

Confidence tiers are `A`, `B`, and `C`. Reduction/solo-piano/lead-sheet and explicit non-orchestral band arrangements are rejected. See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Reproduce the PDMX catalog

```bash
curl -L --fail --retry 5 \
  'https://zenodo.org/records/15571083/files/PDMX.csv?download=1' \
  -o PDMX.csv

python3 scripts/build_manifest.py \
  --input PDMX.csv \
  --output-dir data \
  --target 10000

python3 scripts/verify_manifest.py \
  --catalog data/orchestra_exact_10000.csv \
  --stats data/stats.json \
  --target 10000
```

For each accepted PDMX row, the catalog retains the same-source `mxl`, `pdf`, and `mid` paths. MIDI audio rendering is optional and does not change the record’s class from `midi_same_source_exact`.

## Generated data

The build is designed to produce:

- `data/orchestra_exact_10000.csv`
- `data/orchestra_exact_10000.jsonl`
- `data/shards/part-*.csv`
- `data/sample_100.csv`
- `data/custom_audio_metadata_candidates.csv`
- `data/stats.json`
- `data/SHA256SUMS`

The repository stores manifests, source links, validation logic and hashes rather than duplicating hundreds of gigabytes of upstream binaries.

## Important status rule

A target number is not reported as completed until the generated catalog has actually passed uniqueness, path, provenance and checksum validation. Candidate rows and verified rows are always reported separately.

## Sources

- Phillip Long et al., **PDMX: A Large-Scale Public Domain MusicXML Dataset for Symbolic Music Processing**, ICASSP 2025, DOI `10.1109/ICASSP49660.2025.10890217`.
- PDMX v9, DOI `10.5281/zenodo.15571083`.
- Mutopia Project Orchestra catalog.
- OpenScore Orchestra v1.0.1.

See [DATA_LICENSE.md](DATA_LICENSE.md) before redistributing source scores, MIDIs, or rendered audio.
