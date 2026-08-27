# Orchestra Score–Audio / Score–MIDI Match Catalog

This repository is a reproducible orchestral **source/candidate catalog pipeline**. It does **not** currently contain 10,000 materialized score/audio binaries, and the latest strict main-branch build did not complete successfully.

## Current audited status — 2026-08-28

- A one-shot PDMX workflow on branch `data/pdmx-band-pairs-10000` completed successfully with target `10,000` and produced a temporary GitHub Actions manifest artifact.
- The later stricter main-branch workflow failed at `Build and verify exactly 10,000 rows`; its generated-catalog commit step was skipped.
- Therefore the earlier 10k artifact is **provisional candidate-manifest evidence**, not a claim that 10,000 final verified pairs are stored in this repository.
- `materialized MXL/PDF/MIDI`, `rendered audio`, and `human-reviewed` counts are separate metrics and must never be inferred from a target number, workflow name, README title, or temporary artifact.

The broader, cross-domain source audit now lives in `hesong0222-dev/CodexWorkspace/datasets/music-source-registry/`.

## Exactness classes

| Class | Meaning |
|---|---|
| `same_symbolic_source_exact` | PDF/MusicXML/LilyPond/MuseScore representation and MIDI share the same source record |
| `score_rendered_audio_exact` | audio is rendered directly from that exact symbolic/MIDI record |
| `performance_midi_audio_exact` | real performance MIDI and audio were captured synchronously |
| `score_performance_aligned` | separate score and real performance have explicit alignment annotations |
| `work_identity_match` | title/composer/work identity matches but edition/content exactness is not proven |
| `candidate_unverified` | discovery candidate only |

Do not relabel the lower-confidence classes as `exact`.

## Primary symbolic source

**PDMX v9** is the bulk source because it supplies MusicXML-derived records and, when valid, associated MXL/PDF/MID exports. Preferred filtering is:

1. `subset:no_license_conflict == True`
2. `subset:all_valid == True`
3. work/arrangement deduplication
4. orchestral instrumentation classification
5. strict path/provenance/uniqueness verification

PDMX reports 222,856 songs in `no_license_conflict`; that is an upstream source-pool number, not an orchestral count.

## Counting rule

Every number reported by this project must include one of these levels:

- `upstream_reported`
- `discovered`
- `candidate`
- `parsed`
- `rights_cleared`
- `deduplicated`
- `accepted`
- `materialized`
- `rendered`
- `human_reviewed`

If the level is omitted, the number is not publication-ready.

## Reproduce the PDMX candidate build

```bash
python3 scripts/build_manifest.py \
  --input PDMX.csv \
  --output-dir data \
  --target 10000

python3 scripts/verify_manifest.py \
  --catalog data/orchestra_exact_10000.csv \
  --stats data/stats.json \
  --target 10000
```

A successful run must commit or otherwise persist its generated manifest and validation report before it can be called complete.

## Storage boundary

The repository intentionally stores source links, manifests, validation logic, metadata and hashes rather than duplicating hundreds of gigabytes of upstream score/audio binaries.

See `DATA_LICENSE.md` and `docs/METHODOLOGY.md` for provenance and classification rules.
