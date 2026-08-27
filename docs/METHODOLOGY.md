# Methodology

## 1. Unit of matching

One catalog row represents one unique PDMX source score. PDMX’s `.mxl`, `.pdf`, and `.mid` paths are associated exports of that source. The catalog’s audio target is a deterministic render of the exact `.mid` referenced by the row.

This is a **same-source score/render match**, not a claim that a separately published commercial recording used an identical edition.

## 2. Mandatory source filters

A record is rejected unless all of the following hold:

1. `subset:no_license_conflict == True`.
2. `subset:all_valid == True`.
3. MXL, PDF, and MIDI paths are non-empty.
4. The score is not paywalled or marked as a draft.
5. It has at least 5 tracks and 200 notes.
6. When duration metadata is present, it has at least 12 bars and 25 seconds.
7. It is not labeled as a piano reduction, vocal score, solo-piano transcription, lead sheet, or a cappella score.

PDMX’s deduplicated/best-arrangement records are ranked before additional source engravings or arrangements. Exact source-path duplicates are always removed.

## 3. Instrument interpretation

PDMX serializes `tracks` as sorted, zero-based General MIDI program numbers joined by hyphens. The pipeline maps them into families:

| GM programs, zero-based | Family |
|---|---|
| 0–23 | keyboard |
| 24–39 | guitar/band bass |
| 40–46, 48–51 | strings |
| 47, 8–15, 112–119 | percussion |
| 52–54 | voice |
| 56–63 | brass |
| 64–79 | woodwinds/reeds/pipes |

The parser also accepts named instruments if a future PDMX export changes the field format.

## 4. Orchestral classes

### Full orchestra

At least 8 tracks, at least 2 string tracks, at least 1 woodwind track, and at least 1 brass track. Guitar/band instrumentation is capped unless explicit orchestra metadata exists.

### String orchestra

At least 3 string tracks, at least 5 total tracks, and at least 50% string-family instrumentation, with no guitar/band tracks and at most one keyboard track. Explicit string-orchestra metadata raises confidence.

### Wind orchestra

At least 6 tracks, at least 2 woodwind and 2 brass tracks, and at least 5 wind/brass/percussion tracks, with little keyboard or guitar/band instrumentation. Explicit wind-orchestra, concert-band, or symphonic-band metadata raises confidence.

### Explicit orchestra

Explicit orchestra metadata, at least 6 tracks, at least two orchestral families, and at least one string track.

### Chamber orchestra

At least 6 tracks, at least 2 string tracks, at least 2 additional orchestral tracks, at least 5 orchestral tracks overall, and an orchestral-family majority.

### Inferred orchestra

At least 9 tracks, multi-track strings, at least three orchestral families, and at least three non-string orchestral tracks, with limits on keyboard and guitar/band dominance.

### Orchestral ensemble

A six-or-more-track score with an orchestral-family majority, at least two orchestral families, and low keyboard/guitar dominance. This is the broadest accepted class and remains confidence tier C.

Explicit big-band, jazz-band, marching-band, pep-band, and rock-band metadata is excluded.

## 5. Confidence tiers

- **A:** explicit orchestra/full-score metadata plus strong orchestral instrumentation, or a strongly supported explicit string/wind orchestra.
- **B:** strong instrumentation evidence without all explicit metadata, or explicit orchestra metadata with moderate instrumentation.
- **C:** conservative inference from a large orchestral General MIDI palette.

Rows are sorted by tier, whether PDMX marks them as the best unique arrangement, quality score, and stable source ID. Selection first caps each PDMX duplicate group at 3 records, then at 10, and uses an unlimited final pass only if still necessary. The reached stage and maximum selected per group are recorded in `stats.json`. The release guarantees unique source paths/IDs, not 10,000 unique compositions.

## 6. Quality score

The score ranks accepted candidates; it does not decide exactness. It rewards confidence tier, track count, orchestral-family breadth, explicit full-score metadata, annotations, rating evidence, views, and note count. It penalizes keyboard-heavy, voice-heavy, or guitar/band-heavy arrangements.

## 7. Verification and reproducibility

The pipeline records:

- source CSV expected and observed MD5;
- source rows scanned;
- accepted candidates before and after defensive deduplication;
- rejection reasons;
- selected class/tier/family counts;
- SHA-256 of canonical CSV and JSONL;
- deduplicated-versus-additional-arrangement counts and duplicate-group cap stage;
- a machine-readable definition stating that no human-performance claim is made.

`verify_manifest.py` aborts on a row-count mismatch, duplicate IDs or MXL paths, missing format paths, missing provenance flags, a wrong exactness label, or a checksum mismatch.

## 8. Known limitations

1. General MIDI programs are an instrumentation abstraction, not a complete orchestration ontology.
2. PDMX’s source exports share provenance, but format conversion can realize repeats, ornaments, or playback directives differently.
3. A SoundFont render is exact with respect to MIDI events, but timbre and expressive timing depend on the chosen renderer and SoundFont.
4. `has_custom_audio` is only source metadata; it is not sufficient evidence of a verified human-orchestra recording.
5. Real-performance edition matching requires content fingerprinting and score-following validation and should be released as a separate tier.
