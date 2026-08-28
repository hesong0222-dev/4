# Groove-augmented canonical MIDI training specification

**Status:** AUTHORITATIVE DESIGN / AUDIO RENDER HOLD  
**Recorded:** 2026-08-28  
**Scope:** future score-to-audio training-pair generation, groove augmentation, source selection, fast-passage coverage, ground-truth labeling, split/leakage policy.

This document is authoritative for future implementation unless a later decision explicitly supersedes it.

## 1. Core training pair

The intended future training pair is deliberately **not** `grooved MIDI -> grooved MIDI`.

```text
original_canonical.mid  -------------------------------> TARGET / LABEL
       |
       | copy; original is immutable
       v
render_control.mid
  (DAW-style groove / swing / push-pull / humanize)
       |
       v
future VST render
       |
       v
grooved_audio.flac  ----------------------------------> INPUT AUDIO
```

Therefore:

- **input** = audio rendered from a groove-transformed copy of the MIDI;
- **target** = the original canonical/quantized MIDI;
- **render-control MIDI** = an intermediate control artifact and **must never silently replace the target**.

The learning objective is intentionally groove-invariant/canonicalizing: the model should hear timing deviations in the audio but recover the underlying canonical MIDI grid/score timing.

## 2. Current render state: HOLD

**Do not automatically render new MIDI to audio yet.**

Allowed now:

1. collect and register MIDI sources;
2. parse MIDI events and instrumentation;
3. deduplicate and cluster works/arrangements;
4. measure tempo, meter, key, note density, note duration, velocity, polyphony, drum notes and fast passages;
5. design/test groove transforms on MIDI copies;
6. generate deterministic `render_control.mid` dry-run artifacts if needed for validation;
7. validate that groove transforms preserve the source musical content;
8. prepare manifests, policies and split assignments.

Forbidden until explicit approval:

- new VST/SoundFont/DAW batch audio rendering;
- counting a planned render as a completed audio pair;
- overwriting the original MIDI with a groove-applied MIDI.

The already-audited PDMX synthesized-audio mappings are pre-existing upstream/previous artifacts; they do not mean that a new VST rendering campaign has started.

## 3. Ground-truth classes

Every audio/MIDI pair must carry exactly one provenance/ground-truth class.

| Class | Meaning | Supervised ground truth? |
|---|---|---:|
| `REAL_CAPTURED_MIDI` | MIDI captured synchronously with the real performance | Yes, highest timing provenance |
| `REAL_SCORE_ALIGNED` | separately authored score/MIDI aligned and validated against a real recording | Yes, only after strict alignment gate |
| `SYNTH_EXACT_TIMING_TARGET` | audio rendered directly from the same target MIDI without timing-changing augmentation | Yes |
| `SYNTH_CANONICAL_SCORE_TARGET` | audio rendered from a groove-transformed copy, while the **original canonical MIDI** remains the target | Yes; this is the planned groove-augmentation class |
| `MODEL_PSEUDO_LABEL` | MIDI estimated from audio by an existing transcription model | **No; quarantine only** |

`MODEL_PSEUDO_LABEL` must never be counted as clean supervised ground truth.

## 4. Hard invariants

These are non-negotiable implementation requirements.

1. `original_canonical.mid` is immutable.
2. Groove transformation operates on a copy only.
3. For `SYNTH_CANONICAL_SCORE_TARGET`, the label is always the original canonical MIDI.
4. `render_control.mid` is never used as the target by accident or by convenience.
5. Groove augmentation must not change pitch identity or note count.
6. Per-voice/event ordering must be preserved; timing perturbation may not make a later distinct event overtake an earlier one.
7. Simultaneous chord tones may be deliberately spread, but the chord group must remain associated with the same canonical onset and may not cross the next distinct musical onset.
8. Every transformation is reproducible from `template_id + parameters + seed`.
9. All variants derived from one work/arrangement must inherit the same train/dev/test split.
10. A straight render, swing render, laid-back render and any other render of the same source are **not independent split units**.
11. Source provenance, rights status and hash/ID must remain attached to every derivative.
12. New audio rendering remains disabled until explicitly approved.

## 5. DAW-style groove engine

The groove engine should behave conceptually like a DAW Groove Pool, not like independent per-note white-noise jitter.

A groove template may modify:

- subdivision-relative onset timing;
- swing ratio;
- timing strength;
- velocity/accent strength;
- duration/gate strength;
- limited humanize/random variation around the template;
- per-role push/pull offset;
- intra-chord spread;
- optional pedal/control timing where musically appropriate.

Random selection is allowed and desired, but it must be **seeded and reproducible**. Template selection may be genre-aware; weighting is configurable and must be recorded.

### 5.1 Initial template pool

The following template names are the initial design pool. Exact numeric parameters remain tunable before rendering.

| Template | Character |
|---|---|
| `STRAIGHT_TIGHT` | almost quantized, very small humanization |
| `LIGHT_HUMAN` | small correlated timing/velocity variation |
| `SWING_54` | weak swing |
| `SWING_58` | medium swing |
| `SWING_62` | strong swing/shuffle tendency |
| `LAID_BACK_LIGHT` | modestly behind the grid |
| `LAID_BACK_HEAVY` | clearly behind the grid |
| `PUSH_LIGHT` | modestly ahead of the grid |
| `PUSH_CHORUS` | section-aware forward feel |
| `MPC_16_A` | 16th-note groove template |
| `MPC_16_B` | alternate 16th-note groove/accent map |
| `FUNK_16` | syncopated 16th-note pocket |
| `SHUFFLE_8` | eighth-note shuffle |
| `SHUFFLE_16` | sixteenth-note shuffle/fusion feel |
| `POCKET` | role-dependent push/pull pocket |
| `ORCHESTRA_LOOSE` | low-strength ensemble looseness, not a funk/rock pocket |
| `DRUNK_EXPERIMENTAL` | strongly displaced but correlated experimental timing; low sampling weight |

### 5.2 Role-relative timing

The same groove should not force every instrument to the same absolute offset. A template may use relative role offsets. Example only:

```text
FUNK / POCKET example
kick         -6 ms
bass         -4 ms
hi-hat       +2 ms
snare       +12 ms
piano        +8 ms
guitar       +5 ms
brass        -2 ms
```

These are **illustrative defaults, not final calibrated constants**. Actual values should be tuned from listening tests and/or expressive-MIDI statistics.

For orchestral material, use small correlated ensemble looseness rather than a drum-set pocket.

## 6. Fast passages are mandatory coverage

The corpus must include a non-trivial amount of real fast material. Groove augmentation does **not** create new pitches or fake speed; fast passages should come from the source MIDI or from a separately labeled procedural-coverage generator.

Track/report at least:

- 16th-note runs;
- 16th-note triplet runs;
- 32nd-note bursts;
- scale runs;
- chromatic runs;
- arpeggios/broken chords;
- trills/tremolos;
- guitar-like alternate-picking runs;
- string/woodwind/brass fast lines;
- drum fills.

Recommended reporting bins:

| Local note density | Bin |
|---:|---|
| `< 6 notes/s` | `normal` |
| `6–10 notes/s` | `fast` |
| `10–14 notes/s` | `very_fast` |
| `> 14 notes/s` | `extreme` |

**Provisional coverage target:** roughly 20–30% of augmentation-eligible items should contain at least one meaningful fast passage once the real-source histogram is measured. This is a provisional default, not a fabricated achieved count.

### 6.1 Speed-dependent groove attenuation

Fast runs must not be destroyed by large timing shifts. Initial provisional attenuation schedule:

| Local density | Groove timing-strength multiplier |
|---:|---:|
| `<4 notes/s` | `1.00` |
| `4–8 notes/s` | `0.75` |
| `8–12 notes/s` | `0.45` |
| `12–16 notes/s` | `0.25` |
| `>16 notes/s` | `0.10–0.15` |

Hard constraints still override this table: event order cannot reverse, and a transformed note/chord cannot cross a subsequent distinct onset.

## 7. Chord and strum behavior

Groove augmentation may add an intra-chord spread while preserving the original canonical onset as the target.

Examples:

```text
piano chord:   0, +4, +7, +11 ms
guitar strum:  0, +8, +15, +23, +31, +38 ms
```

Direction and spread can be randomized within a template. The transform must store the exact offsets in metadata. Acoustic-guitar material may use explicit strum-style spreads; the target remains the unspread canonical MIDI.

## 8. File layout for future generated pairs

```text
<item_id>/
  original_canonical.mid     # target, immutable
  render_control.mid         # groove-applied MIDI, not the target
  groove_map.json            # exact transform + seed
  metadata.json
  audio.flac                 # absent while RENDER_HOLD is active
```

When rendering is eventually enabled, `audio.flac` is created from `render_control.mid`.

## 9. Required metadata

Minimum future metadata fields:

```json
{
  "work_id": "...",
  "arrangement_id": "...",
  "variant_id": "...",
  "source_midi": "original_canonical.mid",
  "target_midi": "original_canonical.mid",
  "render_control_midi": "render_control.mid",
  "input_audio": "audio.flac",
  "ground_truth_class": "SYNTH_CANONICAL_SCORE_TARGET",
  "groove": {
    "template_id": "FUNK_16",
    "template_version": "...",
    "seed": 38421,
    "strength": 0.72,
    "timing_strength": 0.81,
    "velocity_strength": 0.55,
    "duration_strength": 0.20,
    "swing_ratio": 0.58,
    "role_offsets_ms": {},
    "event_offsets": []
  },
  "fast_passage": {
    "max_notes_per_second": null,
    "bins_present": []
  },
  "split": "train",
  "source_provenance": {},
  "rights_status": "..."
}
```

Do not omit the distinction between `target_midi` and `render_control_midi`.

## 10. Split/leakage policy

Split by work/arrangement cluster before creating groove variants.

All of the following must remain in the same split:

- same MIDI under different groove templates;
- same MIDI rendered by different plugins/presets;
- same arrangement with straight vs humanized timing;
- same arrangement transcribed/exported in another container format;
- near-duplicate MIDI with metadata-only changes;
- future audio re-encodes of the same render.

For broader real-music data, also cluster covers, alternate masters and structurally equivalent arrangements where detectable. File hash alone is insufficient.

## 11. MIDI source strategy

Prefer real compositions/arrangements as the canonical musical content. Procedural data is for controlled coverage gaps, not the dominant musical prior.

### 11.1 Canonical/score-like MIDI sources

| Source | Observed scale/content | Intended role | Caveat |
|---|---|---|---|
| PDMX v9 | current project has 77,321 strict symbolic records; 17,599 previously audited same-source synthesized-audio mappings | bulk canonical score MIDI | instrumentation detail sometimes only GM-level; current audio mappings are a separate existing tier |
| SymphonyNet | 46,359 multi-track MIDI reported by official project | orchestral multi-track source/candidate pool | provenance/rights and per-piece score equivalence tracked separately |
| POP909 | 909 pop-song arrangement MIDI; `MELODY`, `BRIDGE`, `PIANO`, plus alternate versions | high-value real-pop structure and accompaniment | only three symbolic roles; repository license and song-level rights must remain explicit |
| nightingale-ai/midi-data | 221,599 MIDI total; 57,765 genre-sorted; e.g. rock 7,775, pop 5,491, metal 2,812, jazz 1,458 | very large real-song candidate/distribution pool | repository states files were freely available online but does not own them; no clean dataset license -> rights quarantine until reviewed |
| ryanrudes/game-midis | video-game MIDI collection | fast/complex arrangement candidate pool | no clear data license; do not promote directly to clean ground truth |

### 11.2 Expressive/performance MIDI references

These are valuable for measuring timing/velocity/pedal distributions and learning realistic groove-template priors, but they are not automatically canonical score targets.

| Source | Observed content | Intended role | Caveat |
|---|---|---|---|
| ASAP (`fosfrancesco/asap-dataset`) | 236 scores, 1,067 MIDI performances; score MIDI + performance MIDI + alignment annotations | expressive timing/rubato/fast-passage reference; real aligned evaluation candidate | piano only; CC BY-NC-SA 4.0; use alignment quality flags |
| International Piano e-Competition mirrors | live-performance MIDI from 2002–2018 competition material | expressive timing, velocity, pedal and virtuosic-speed reference | data-license status unclear in mirrors -> rights quarantine/reference only until resolved |

### 11.3 Excluded/misleading repository

`Hvdogra/jazz-midi-dataset` was inspected and its tracked training files are primarily `.txt` representations rather than raw `.mid/.midi` files. Do not count it as a raw-MIDI source without an independently verified MIDI origin.

## 12. Existing 17,599-pair corpus vs future groove corpus

Do not conflate the existing PDMX audited pair set with the future groove-augmentation set.

- Existing audited set: `SYNTH_EXACT_TIMING_TARGET` conceptually; audio is tied to the same source MIDI timing.
- Future groove-augmented set: `SYNTH_CANONICAL_SCORE_TARGET`; audio timing is intentionally displaced but the target remains canonical.

Both can coexist, but the ground-truth class must make the distinction explicit.

## 13. Future rendering procedure after HOLD is lifted

Only after explicit approval:

```text
source MIDI QA
  -> immutable canonical target
  -> seeded groove transform
  -> render_control MIDI QA
  -> VST/preset selection
  -> audio render
  -> latency/tail compensation
  -> audio QA
  -> pair manifest
```

The renderer must log plugin, preset/state hash, sample rate, latency, gain/pan, groove template/version and random seed.

## 14. Open decisions that are not yet hard-coded

The following remain tunable and must not be represented as completed facts:

- exact probability of each groove template;
- exact number of groove variants per source MIDI;
- final timing/velocity/duration ranges per genre and instrument;
- final fast-passage quota after real-corpus distribution analysis;
- final VST/preset mapping;
- final audio rendering start date/run size;
- whether pedal timing is augmented for each source class;
- training loss/tolerance details for canonical onset recovery.

Until these are fixed, implementations should expose them as configuration rather than silently choosing permanent constants.
