# BSED / BSD orchestral score–audio catalog

This directory records the verified scope of the 2026 Beethoven Symphony Excerpt Dataset (BSED) and Beethoven Symphonies Dataset (BSD), DOI `10.5281/zenodo.20344500`.

## BSED

- 20 orchestral score excerpts.
- 5 synchronized audio versions per excerpt: 4 concert recordings and 1 synthetic rendition.
- 100 score–audio pairs in total, including 80 human-performance pairs.
- PDF, MusicXML, Sibelius, MIDI and CSV note-event scores.
- Robust alignment followed by manual verification and note-onset refinement.

`bsed_excerpts.csv` enumerates all 20 excerpt definitions. These are **not full-score records**, so the 100 pairs are reported separately from the full-score/MIDI target.

## BSD

- 415 recordings of complete Beethoven symphony movements.
- Approximately 63 hours of public-domain orchestral audio.
- Note-level annotations aligned from digital scores and structurally verified.
- The large-scale BSD alignments did not receive the same manual refinement as BSED.

The source paper supplies the 415-recording count. The 34.3 GB archive is not mirrored here. Item-level BSD archive enumeration remains separate from the source-level count.

## Claims and boundaries

Both datasets provide genuine score–audio alignment. This repository does **not** claim that performers used the exact printed edition represented by the digital score, and it does not redistribute the source audio binaries.
