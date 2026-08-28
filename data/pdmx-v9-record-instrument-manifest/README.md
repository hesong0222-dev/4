# PDMX v9 strict per-record instrumentation manifest

Strict filter: `subset:no_license_conflict && subset:all_valid && subset:deduplicated`.

- records: **77,321**
- sparse `(record, GM-program)` rows: **142,342**
- evidence: PDMX per-track zero-based GM program list
- exactness: same symbolic source MXL/PDF/MID only; **not** a human-recording exactness claim

`records/*.csv.gz` is one row per score. `record_instruments/*.csv.gz` is the normalized long form. `program_counts.csv` and `ensemble_counts.csv` are aggregate indexes.

Important: drum-kit presence, printed staff numbering, transposing-instrument key, divisi, doubles and articulation are not fabricated from GM programs; they remain unknown until direct MusicXML/MuseScore/MIDI parsing.

## Classifier version

`v2-gm-boundary-corrected`: ensemble/family fields exclude Timpani from strings, Synth Voice from choir identity, and chromatic percussion from keys identity. Raw `gm_program_track_counts` never changed.
