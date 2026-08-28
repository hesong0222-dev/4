# Orchestra full-score + MIDI source registry

This registry distinguishes **enumerated same-source pairs** from collections that are only discovery candidates. “Same source” means the downloadable or derivable score and MIDI are produced from one encoded score record; it does not imply a matching human-orchestra recording.

## A. Enumerated or directly enumerable exact symbolic sources

| Source | Score and MIDI relation | Scope used here | Rights / validation boundary | Import state |
|---|---|---|---|---|
| PDMX v9 | A valid row links MXL, PDF and MIDI exports from the same MuseScore source record | All `no_license_conflict + all_valid` rows; alternate arrangements retained; orchestra evidence tiered | Per-row license fields retained; `strict/probable/candidate` refers only to orchestra membership | Fully automated and committed as sharded manifests |
| Mutopia Project | LilyPond source generates the item’s PDF and MIDI | Orchestra-tagged entries and full/conductor-score LilyPond projects | Item-level Public Domain/Creative Commons terms; deduplicate movements and alternate output files | Source repository identified; item harvester is a separate adapter |
| OpenScore Orchestra / Hauptstimme | Native MuseScore/MusicXML corpus can export matching MIDI and PDF | Approximately 100 transcribed orchestral movements | Release-specific license and corpus metadata | High-quality reference source; adapter required |
| MuseData / CCARH | Encoded score data can be translated to printable scores and MIDI | Symphonies, concertos, operas, oratorios, cantatas and related full scores | Work/edition and repository-level audit required | Collection inventory source; adapter required |

## B. Symbolic orchestral sources not yet counted as exact full-score + MIDI pairs

| Source | Why it is useful | Why it is not yet promoted |
|---|---|---|
| SymphonyNet | Tens of thousands of multi-track symphonic MIDI records | The MIDI corpus does not itself establish a downloadable same-edition full score for every record |
| Symbolic Orchestral Database / LOP | Orchestral MIDI/MusicXML material and orchestration research pairs | Record-level score/MIDI provenance and redistribution terms must be normalized |
| KernScores / Humdrum collections | Very large symbolic classical corpus; many files are renderable | Collection/file licenses and full-score identity vary; a MIDI export alone is not proof of an originally paired MIDI release |
| IMSLP | Extremely broad public-domain score discovery | Mostly scanned PDFs; symbolic encoding and edition-exact MIDI are usually absent |

## C. Counting rules

1. One PDMX source row is one record; mirrors and format links do not create extra records.
2. Alternate engravings and arrangements are retained in the inclusive manifest and separately labeled with PDMX deduplication metadata.
3. `same_symbolic_source_exact` applies only to score/MIDI provenance.
4. `strict`, `probable`, and `candidate` apply only to orchestra classification.
5. MIDI-only corpora are not counted as score–MIDI pairs until a same-edition score is proven.
6. Human recordings remain a separate validation track and are never inferred from title/composer equality.
