# Source inventory

This inventory separates **exact same-source score–MIDI pairs** from weaker symbolic/orchestral MIDI corpora.

## Tier M1 — exact full-score + MIDI from the same source record

### PDMX v9

- Scale: over 250,000 public-domain MusicXML scores in the full corpus.
- Per record: MuseScore-derived symbolic score plus attempted MXL, PDF, and MIDI exports.
- Exactness: PDF/MXL/MIDI are generated from the same source score record.
- Orchestra use: filter by instrumentation, tags, groups, title/subtitle, track count, and negative reduction/band rules.
- Required filters: `subset:no_license_conflict`, `subset:all_valid`, deduplication, non-paywall, non-draft.
- Primary role: bulk source for the 10,000+ exact symbolic orchestra target.
- Dataset DOI: https://doi.org/10.5281/zenodo.15571083
- Code: https://github.com/pnlong/PDMX

### Mutopia Project — Orchestra listing

- Scope: curated classical/public-domain and openly licensed scores.
- Orchestra entries expose the score source and MIDI preview/download from the same LilyPond edition; most also expose PDF and LilyPond source.
- Exactness: MIDI is computer-generated from the same LilyPond score source, so score ↔ MIDI is same-source rather than title-inferred.
- Orchestra listing: https://www.mutopiaproject.org/cgibin/make-table.cgi?Instrument=Orchestra
- Examples include orchestral concertos, overtures, symphony movements, opera/oratorio numbers, and string orchestra.
- Primary role: high-confidence independently curated supplemental source and cross-check corpus.

### OpenScore Orchestra

- Scope: approximately 100 transcribed orchestral movements in the first stable OpenScore Orchestra release.
- Native symbolic source: MuseScore/MusicXML.
- MIDI: reproducibly exportable from the exact native score using MuseScore Studio.
- Exactness: MIDI is generated from the exact corpus score; no title matching is required.
- Release: https://zenodo.org/records/15425749
- Primary role: very-high-quality validation/reference subset, not the main source for reaching 10,000.

## Tier M2 — orchestral MIDI corpus without a proven downloadable full score

These are useful for discovery or future score retrieval, but they are **not counted as exact score–MIDI matches until a corresponding full score is located and validated**.

### SymphonyNet

- Large multi-track symphonic MIDI corpus used for symphonic generation research.
- Public project: https://github.com/symphonynet/SymphonyNet
- Some downstream projects report tens of thousands of SymphonyNet MIDI examples.
- Do not count a SymphonyNet MIDI as an exact score pair merely because a work title can be found elsewhere.

### Symbolic Orchestral Database (SOD)

- Symbolic orchestral database supported by MMT preprocessing code.
- Useful as an orchestral MIDI discovery source.
- Not counted as Tier M1 unless a same-edition full score can be tied to the MIDI with sufficient provenance.

## Tier M3 — real-performance score/audio sources

Kept separate from MIDI-only exact pairs. These require a stronger edition/arrangement and musical-content match rather than merely sharing a title and composer.

Examples under investigation include score-video/performance datasets and public-domain score/recording repositories. A real recording is never promoted to exact status solely from metadata similarity.

## Counting policy

A single musical source record can contribute at most one canonical MIDI exact pair. Multiple file mirrors, formats, transpositions, or download URLs for the same underlying arrangement do not increase the count.

The release reports these separately:

1. `real_audio_verified_exact`
2. `real_audio_strong_match`
3. `midi_same_source_exact`
4. `midi_score_candidate_unverified`

Only categories 1 and 3 are considered deterministic/edition-grounded exact pairs.
