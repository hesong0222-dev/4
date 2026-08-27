# Methodology

## 1. Unit of matching

One catalog row represents one unique PDMX source score. PDMX’s `.mxl`, `.pdf`, and `.mid` paths are associated exports of that source. The catalog’s audio target is a deterministic render of the exact `.mid` referenced by the row.

This is a **same-source score/render match**, not a claim that a separately published commercial recording used an identical edition.

## 2. Mandatory source filters

A record is rejected unless all of the following hold:

1. `subset:no_license_conflict == True`.
2. `subset:all_valid == True`.
3. PDMX’s deduplicated subset flag, or its best-unique-arrangement flag, is true.
4. MXL, PDF, and MIDI paths are non-empty.
5. The score is not paywalled or marked as a draft.
6. It has at least 5 tracks and 200 notes.
7. When duration metadata is present, it has at least 12 bars and 25 seconds.
8. It is not labeled as a piano reduction, vocal score, solo-piano transcription, lead sheet, or a cappella score.

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

At least 4 string tracks and at least 55% of the score’s tracks are string-family programs. Explicit string-orchestra metadata raises confidence.

### Wind orchestra

Explicit wind-orchestra, concert-band, or symphonic-band metadata plus at least 3 woodwind and 2 brass tracks across at least 8 tracks.

### Explicit orchestra

Explicit orchestra metadata, at least 6 tracks, at least two orchestral families, and at least one string track.

### Inferred orchestra

At least 9 tracks, multi-track strings, at least three orchestral families, and at least three non-string orchestral tracks, with limits on keyboard and guitar/band dominance.

Explicit big-band, jazz-band, marching-band, pep-band, and rock-band metadata is excluded.

## 5. Confidence tiers

- **A:** explicit orchestra/full-score metadata plus strong orchestral instrumentation, or a strongly supported explicit string/wind orchestra.
- **B:** strong instrumentation evidence without all explicit metadata, or explicit orchestra metadata with moderate instrumentation.
- **C:** conservative inference from a large orchestral General MIDI palette.

Rows are sorted by tier, quality score, and stable source ID. The first 10,000 unique records form the release.

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
- a machine-readable definition stating that no human-performance claim is made.

`verify_manifest.py` aborts on a row-count mismatch, duplicate IDs or MXL paths, missing format paths, missing provenance flags, a wrong exactness label, or a checksum mismatch.

## 8. Known limitations

1. General MIDI programs are an instrumentation abstraction, not a complete orchestration ontology.
2. PDMX’s source exports share provenance, but format conversion can realize repeats, ornaments, or playback directives differently.
3. A SoundFont render is exact with respect to MIDI events, but timbre and expressive timing depend on the chosen renderer and SoundFont.
4. `has_custom_audio` is only source metadata; it is not sufficient evidence of a verified human-orchestra recording.
5. Real-performance edition matching requires content fingerprinting and score-following validation and should be released as a separate tier.
