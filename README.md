# Verified PDMX score–synthesis pair registry

This repository previously claimed that it already contained **10,000 unique orchestral full-score/audio records**. That claim was not supported by the generated files and has been withdrawn.

## Audited result that actually exists

A successful one-shot run (`33094472148`) produced an artifact named `pdmx-exact-pair-manifest`. Its verified counts are:

| Status | Count | Meaning |
|---|---:|---|
| PDMX rows mapped to the synthesized-audio corpus | 24,390 | Score ID and audio basename map uniquely |
| Eligible exact score–synthesis pairs | **17,599** | No internal/public license conflict, MXL/PDF/MID valid, best unique arrangement, at least two tracks |
| Frozen review subset | 10,000 | Deterministic ranking of the eligible rows |
| Strict band pairs | **0** | The run did not establish a strict band corpus |
| Broad band/ensemble pairs | **0** | The run did not establish a broad band corpus |
| Verified orchestral full-score pairs | **0** | No human or strict machine review established this category |
| Verified jazz pairs | **0** | No jazz-specific manifest has passed validation |

“Exact” here means that the synthesized audio was generated from the corresponding PDMX MIDI. It does **not** mean that an independent human/commercial recording follows the same edition.

## Files preserved in `data/`

The one-shot import workflow preserves the expiring Actions artifact as compressed, checksummed manifests:

- `verified_exact_pairs_17599.csv.gz`
- `verified_exact_pairs_top10000.csv.gz`
- `all_mapped_pairs_24390.csv.gz`
- `hf_audio_index_24390.csv.gz`
- `summary.json`
- `SHA256SUMS`

These are real row-level catalogs. They reference official score/audio sources; they are not placeholder counts and do not pretend that the multi-gigabyte payloads are committed to Git.

## Current scope

This repository is now the **audited PDMX exact-pair registry**. Orchestra, band, jazz, and other field-specific corpora must each be built and validated separately. A field is not reported as complete until:

1. its manifest contains at least 10,000 accepted unique arrangements;
2. each row resolves to an actual symbolic score and an actual score-derived audio object;
3. duplicate groups and train/test leakage are checked;
4. field classification and quality gates pass;
5. a validation report and checksum are committed.

## Provenance

- Score source: PDMX v8/v9 paths and metadata.
- Audio source: `openmusic/pdmx-multi-instrument-synthesized`.
- Artifact run: `33094472148` in this repository.
- Artifact SHA-256: `986b5333074c29a5cc45a4a91e12f367ce338d014937926420f2c8adcf438dae`.

See `TRUTH_STATUS.json`, `docs/METHODOLOGY.md`, and `DATA_LICENSE.md` before using or redistributing the manifests.
