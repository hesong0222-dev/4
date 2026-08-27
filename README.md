# Orchestra Score–Audio Exact-Match Catalog (10,000)

A reproducible catalog of **10,000 unique orchestral full-score records** selected from [PDMX v9](https://doi.org/10.5281/zenodo.15571083).

Every accepted record points to a PDF, compressed MusicXML (`.mxl`), and MIDI (`.mid`) exported from the **same PDMX source score**. The accompanying audio recipe renders that exact MIDI with a chosen SoundFont, so the score–audio relationship is deterministic and reproducible rather than inferred from a title search.

## What “exact” means here

| Claim | Status |
|---|---|
| PDF, MXL, and MIDI come from the same source score | Required |
| Audio is rendered from that row’s exact MIDI | Required |
| Source row is valid, non-paywalled, non-draft, and in PDMX’s no-license-conflict subset | Required |
| A human orchestra used the identical printed edition | **Not claimed** |
| Expressive timing of a commercial recording is aligned bar-by-bar | **Not claimed** |

This distinction prevents a common dataset error: calling two files an “exact match” merely because their titles and composers agree.

## Generated data

After the one-time build completes, `data/` contains:

- `orchestra_exact_10000.csv` — canonical catalog.
- `orchestra_exact_10000.jsonl` — equivalent line-delimited JSON.
- `shards/part-00001.csv` … `part-00010.csv` — 1,000 records per shard.
- `sample_100.csv` — small reviewable sample.
- `custom_audio_metadata_candidates.csv` — selected PDMX rows whose metadata reports custom audio; **not automatically treated as verified human performances**.
- `stats.json` — source count, candidate count, class/tier counts, and exactness definition.
- `SHA256SUMS` — integrity hashes.

## Selection rules

A row must pass all provenance and availability filters, then satisfy an orchestral instrumentation rule derived from PDMX’s zero-based General MIDI program list plus score metadata. The catalog distinguishes:

- `full_orchestra`
- `string_orchestra`
- `wind_orchestra`
- `explicit_orchestra`
- `chamber_orchestra`
- `inferred_orchestra`
- `orchestral_ensemble`

Confidence tiers are `A` (explicit and strongly supported), `B` (strong instrumentation evidence), and `C` (conservative inference for large orchestral palettes). See [docs/METHODOLOGY.md](docs/METHODOLOGY.md).

## Reproduce the catalog

```bash
curl -L --fail --retry 5 \
  'https://zenodo.org/records/15571083/files/PDMX.csv?download=1' \
  -o PDMX.csv

echo '30392ccf38bb63ce70e7afae70f9c88c  PDMX.csv' | md5sum -c -

python3 scripts/build_manifest.py \
  --input PDMX.csv \
  --output-dir data \
  --target 10000 \
  --source-md5 30392ccf38bb63ce70e7afae70f9c88c

python3 scripts/verify_manifest.py \
  --catalog data/orchestra_exact_10000.csv \
  --stats data/stats.json \
  --target 10000
```

## Materialize scores and render audio

PDMX distributes the score formats as separate archives. Download `mxl.tar.gz`, `pdf.tar.gz`, and `mid.tar.gz` from the same Zenodo record, then extract only the selected records:

```bash
python3 scripts/extract_selected.py \
  --catalog data/orchestra_exact_10000.csv \
  --archive /path/to/mid.tar.gz \
  --kind mid \
  --output-root materialized
```

Render any selected MIDI to WAV with FluidSynth:

```bash
python3 scripts/render_audio.py \
  --mid materialized/mid/<record>.mid \
  --out audio/<record>.wav \
  --soundfont /path/to/orchestral-soundfont.sf2
```

The repository intentionally stores the catalog and reproducible pipeline rather than tens or hundreds of gigabytes of duplicated score/audio binaries.

## Validation

```bash
make test
make verify
```

The verifier hard-fails unless there are exactly 10,000 unique match IDs, source record IDs, and MXL paths, all provenance flags are valid, duplicate-group IDs are present, and the catalog SHA-256 matches `stats.json`. PDMX’s deduplicated records are ranked first; additional engravings or arrangements are admitted only as needed, with progressive per-group caps recorded in `stats.json`.

## Sources

- Phillip Long et al., **PDMX: A Large-Scale Public Domain MusicXML Dataset for Symbolic Music Processing**, ICASSP 2025, DOI: `10.1109/ICASSP49660.2025.10890217`.
- PDMX v9 dataset record, DOI: `10.5281/zenodo.15571083`.
- PDMX code: `pnlong/PDMX`.

See [DATA_LICENSE.md](DATA_LICENSE.md) before redistributing source score files or rendered audio.
