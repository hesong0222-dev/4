# Audited PDMX score ↔ synthesized-audio exact pairs

This directory preserves the already-audited PDMX-derived score/synthesis mapping that was previously stored only on `data/truth-repair-and-import-20260828`.

Counts are intentionally separate from the broader symbolic manifest:

- mapped score/audio rows: **24,390**
- eligible exact score→synthesis pairs: **17,599**
- exactness means the synthesized audio is tied to the PDMX symbolic/MIDI source; it does **not** mean a human/commercial recording is edition-exact.

Files:

- `verified_exact_pairs_17599.csv.gz` — the accepted exact-pair rows.
- `all_mapped_pairs_24390.csv.gz` — all successfully mapped score/audio rows before the strict eligibility gate.
- `hf_audio_index_24390.csv.gz` — corresponding synthesized-audio index.
- `summary.json` — audited counts, definitions and limitations.
- `source_checksums.json`, `artifact-lock.json`, `SHA256SUMS` — provenance/integrity records.

The independent per-record symbolic/instrument manifest is at `../pdmx-v9-record-instrument-manifest/` and currently contains 77,321 unique strict symbolic records.
