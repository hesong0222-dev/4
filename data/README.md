# Preserved verified manifests

This directory is populated from the successful GitHub Actions artifact `pdmx-exact-pair-manifest` created by run `33094472148`.

The files are compressed catalogs, not fabricated placeholders:

- `verified_exact_pairs_17599.csv.gz`: all 17,599 rows that passed the run's exact score-to-synthesis eligibility gates.
- `verified_exact_pairs_top10000.csv.gz`: frozen 10,000-row review subset.
- `all_mapped_pairs_24390.csv.gz`: all 24,390 unique PDMX-to-audio basename mappings before eligibility filtering.
- `hf_audio_index_24390.csv.gz`: source audio index.
- `summary.json`: original counters, definitions, and limitations.
- `SHA256SUMS`: checksums for every preserved file.

A row is not automatically an orchestra, band, or jazz row. Field-specific manifests must be produced separately and must pass their own validation.
