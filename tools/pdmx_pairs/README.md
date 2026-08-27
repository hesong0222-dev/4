# PDMX pre-rendered audio index

`build_manifest.py.gz.b64` is a compact, checksummed one-shot builder copied from the validated `data/pdmx-band-pairs-10000` branch. The workflow decodes it to `build_manifest.py`, projects only metadata columns from the public Hugging Face Parquet shards, and emits score/audio rows keyed by the same PDMX source path.

```bash
base64 --decode build_manifest.py.gz.b64 | gzip --decompress > build_manifest.py
python -m pip install -r requirements.txt
TARGET_PAIRS=10000 OUT_DIR=out CACHE_DIR=.cache python build_manifest.py
```

The downstream `scripts/filter_existing_audio.py` applies the repository's orchestral classifier to `out/eligible_exact_pairs.csv`. These audio files are synthesized PDMX renders, not human-orchestra performances.
