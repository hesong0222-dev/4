# Score–MIDI / Score–Synth-Audio Catalog

This repository stores **audited manifests, source locators, instrumentation metadata, validation logic and hashes**. It does not mirror the full upstream score/audio binaries.

## Current audited status — 2026-08-28

### 1. PDMX strict per-record symbolic / instrumentation manifest

`data/pdmx-v9-record-instrument-manifest/`

Generated from the pinned PDMX v9 metadata using:

`subset:no_license_conflict AND subset:all_valid AND subset:deduplicated`

Validated output:

- **77,321 unique score records**
- **142,342 sparse `(record_id, GM program)` rows**
- 4 record shards: 20,000 + 20,000 + 20,000 + 17,321
- 3 instrument-long shards
- uniqueness/minimum-count validation: **passed**
- derived family/ensemble classifier: **v2-gm-boundary-corrected**

Each record keeps source title/composer/genre fields, raw zero-based GM-program track counts, family counts, a conservative ensemble class/confidence, same-source MXL/PDF/MID paths, license fields and exactness class.

The raw GM program composition is the primary evidence. Printed staff numbering, Bb/C trumpet identity, divisi, doubling, articulation and MIDI channel-10 drum-kit presence are not fabricated when the PDMX CSV does not expose them.

### 2. Audited PDMX score ↔ synthesized-audio exact pairs

`data/audited-pdmx-score-synthesis/`

Permanently preserved on `main`:

- **24,390 mapped score/synth-audio rows**
- **17,599 eligible exact score→synthesis pairs**

This exactness is **score-to-synthesis exactness**: the synthesized audio is tied to the PDMX symbolic/MIDI source. It is not a claim that a separate human or commercial recording used the identical edition.

The 17,599 rows are not added to the 77,321 symbolic count as new compositions without an explicit join/dedup, because they are mappings against the same PDMX source universe.

## Exactness classes

| Class | Meaning |
|---|---|
| `same_symbolic_source_exact` | PDF/MXL/MIDI representations are associated with the same symbolic source record |
| `score_rendered_audio_exact` | audio is rendered/synthesized from that exact symbolic/MIDI record |
| `performance_midi_audio_exact` | real performance audio and performance MIDI were captured synchronously |
| `score_performance_aligned` | separate score and real performance have explicit alignment annotations |
| `work_identity_match` | title/composer/work identity matches but edition/content exactness is not proven |
| `candidate_unverified` | discovery candidate only |

Do not collapse the lower-confidence classes into `exact`.

## PDMX evidence boundary

PDMX v9 is the bulk symbolic source. This repository distinguishes upstream scale from accepted local manifests.

For the 77,321-record manifest, every row must satisfy:

1. `subset:no_license_conflict == True`
2. `subset:all_valid == True`
3. `subset:deduplicated == True`

The resulting count is therefore a strict symbolic-manifest count, **not** an orchestral-only count. Orchestra, chamber, band, choir, jazz-candidate and other ensemble labels are derived fields and are stored with confidence/evidence notes.

## Counting rule

Every project number should be interpreted at one of these levels:

- `upstream_reported`
- `discovered`
- `candidate`
- `parsed`
- `rights_filtered`
- `deduplicated`
- `accepted_manifest`
- `materialized_binary`
- `rendered`
- `human_reviewed`

The current 77,321 and 17,599 counts are **committed manifest rows**, not claims that all referenced MXL/PDF/MID/WAV binaries are copied into this Git repository.

## Rebuild

The one-shot manifest workflow downloads only the pinned PDMX metadata CSV, verifies its published MD5, runs synthetic validation, builds the strict manifest, applies the v2 GM-boundary classifier, verifies uniqueness/count invariants and commits the generated gzip shards with `[skip ci]`.

The broader cross-domain source/instrument taxonomy is maintained in:

`hesong0222-dev/CodexWorkspace/datasets/music-source-registry/`

See `DATA_LICENSE.md`, `docs/METHODOLOGY.md`, the generated `summary.json`, and `SHA256SUMS` before downstream use or redistribution.
