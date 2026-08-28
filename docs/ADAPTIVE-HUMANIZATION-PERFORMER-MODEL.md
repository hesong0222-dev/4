# Adaptive Humanization & Performer Model

**Status:** AUTHORITATIVE DESIGN / `RENDER_HOLD`  
**Parent spec:** `docs/GROOVE-AUGMENTATION-TRAINING-SPEC.md`  
**Purpose:** make future synthetic audio behave more like real musicians while keeping the **original canonical MIDI as the training target**.

## 0. Non-negotiable target relationship

```text
original_canonical.mid  -----------------------------> target MIDI
       |
       | immutable copy
       v
adaptive humanization / groove / performer model
       v
render_control.mid
       |
       | FUTURE ONLY — currently HOLD
       v
grooved / humanized audio ---------------------------> model input
```

The system must never train against `render_control.mid` when the row is `SYNTH_CANONICAL_SCORE_TARGET`.

## 1. Main principle: humanization is hierarchical, not one global knob

Whether groove is applied, what kind of groove is used, and how much is applied must vary at **five levels**:

1. **song** — some songs remain nearly straight; others use strong pocket/swing;
2. **section** — intro/verse/chorus/bridge/solo/outro can have different intensity;
3. **instrument family** — drums, bass, guitar, keys, strings, brass, winds behave differently;
4. **individual part/player** — each track receives a persistent performer tendency;
5. **event** — small residual variation is added after all correlated structure.

Do not apply the same random offset to the entire song and do not use IID `±N ms` noise as the primary humanization mechanism.

A useful timing model is:

```text
Δt(event) =
    song_groove(subdivision)
  + section_offset(section)
  + anchor_group_offset(group, bar)
  + performer_bias(track)
  + phrase_drift(track, phrase)
  + role_offset(instrument_role)
  + event_residual(event)
```

The components are correlated and bounded. This is intentionally closer to several people playing together than independent random jitter.

## 2. Song-level groove gate and amount

Every canonical MIDI receives a deterministic seeded **expression plan** before any transformation.

### 2.1 Provisional global intensity mixture

Initial defaults, to be calibrated later from listening tests and expressive-MIDI statistics:

| Level | Approx. initial probability | Meaning |
|---|---:|---|
| `NONE_OR_TIGHT` | 0.15 | almost no groove; only minimal execution variation |
| `SUBTLE` | 0.30 | light timing/velocity/duration humanization |
| `MODERATE` | 0.35 | clearly audible but natural groove |
| `STRONG` | 0.15 | strong pocket/swing/laid-back/push behavior |
| `EXPERIMENTAL` | 0.05 | exaggerated but still constraint-safe |

These are **provisional sampling priors**, not achieved corpus statistics.

### 2.2 Genre/ensemble modifiers

The base mixture must be shifted by genre/ensemble evidence.

- **classical / orchestra / chamber:** low random jitter, low swing probability, larger phrase/dynamic shaping, small ensemble looseness;
- **jazz:** higher swing/push-pull probability, rhythm-section coupling, stronger articulation variance;
- **funk / soul / R&B / gospel:** strong pocket probability, kick↔bass coupling, snare/comping laid-back options;
- **rock / punk / metal:** tighter drums, possible forward drive, fast-passage protection, less swing unless explicitly detected;
- **pop:** mostly subtle/moderate, section-aware chorus lift, moderate pocket;
- **hip-hop / electronic:** MPC-style groove templates allowed, strong velocity/accent patterns, drums may be much tighter than keys/bass;
- **worship:** moderate pocket, section-level energy growth, pad/keys timing softened, rhythm section tighter;
- **march/concert band:** low swing unless detected, section attack spread and breath modeling more important than random pocket.

If genre confidence is low, use conservative `SUBTLE`/`MODERATE` priors rather than forcing a genre-specific groove.

## 3. DAW-style groove controls

The engine models the same conceptual dimensions used by DAW groove systems such as Ableton Live Groove Pool: base resolution, quantize amount, timing amount, random amount and velocity amount. Ableton also explicitly notes that individual drum voices can benefit from different groove treatment (for example, a snare behind the beat while another voice stays tighter).

Reference: https://www.ableton.com/en/live-manual/12/using-grooves/

Our engine extends that model with instrument-role offsets, section variation, correlated player drift, duration/gate, chord spread, pedal/CC planning and speed-aware protection.

## 4. Groove template selection

A song may receive no template, one dominant template, or a small compatible combination. Selection is seeded and recorded.

Initial template vocabulary:

- `STRAIGHT_TIGHT`
- `LIGHT_HUMAN`
- `SWING_54`
- `SWING_58`
- `SWING_62`
- `LAID_BACK_LIGHT`
- `LAID_BACK_HEAVY`
- `PUSH_LIGHT`
- `PUSH_CHORUS`
- `MPC_16_A`
- `MPC_16_B`
- `FUNK_16`
- `SHUFFLE_8`
- `SHUFFLE_16`
- `POCKET`
- `ORCHESTRA_LOOSE`
- `DRUNK_EXPERIMENTAL` with a very small prior

The template controls grid-relative timing shape. Instrument/player models then scale and offset that template rather than copying it identically to all tracks.

## 5. Instrument-specific performer models

All ranges below are design ranges, not hard constants. The planner chooses within them per song/track and stores the exact result.

### 5.1 Drum kit

Drums should be split at least into kick, snare, closed/open/pedal hi-hat, ride, crash, toms and auxiliary percussion when MIDI channel/note data is available.

**Kick**
- usually relatively tight;
- can sit slightly ahead in rock/funk or close to grid in electronic material;
- strongly coupled to bass anchors;
- timing randomization reduced at double-kick/high-density passages.

**Snare / clap**
- may be deliberately behind the beat in laid-back styles;
- backbeat consistency should be high across bars;
- velocity alternation and section energy should matter more than IID timing noise.

**Hi-hat / ride**
- primary carrier of swing/subdivision feel;
- alternating velocity/accent patterns;
- can remain tighter than snare;
- open-hat duration changes may be allowed if they do not alter note identity.

**Toms / fills**
- phrase-aware accelerando/drag may be small;
- event ordering protected aggressively at high density.

**Main clean tier rule:** do not invent extra ghost notes, flams or drags that are absent in the canonical target. Content-changing drum embellishments belong to a separately labeled nuisance/robustness tier, disabled by default.

### 5.2 Bass

- anchor group with kick when rhythm section exists;
- per-song player can be `ahead`, `centered`, or `laid_back`;
- note lengths/gates may vary by style;
- legato overlap can be modest for electric/synth bass;
- staccato separation can increase in funk;
- velocity tracks section energy and kick relationship;
- very fast runs receive low timing perturbation.

### 5.3 Piano / electric piano / organ / keys

- chord tones may receive controlled intra-chord spread;
- left/right register groups may have slightly different timing tendencies;
- comping can sit behind or around the snare depending on style;
- lead/solo lines use lower chord spread and more phrase-level dynamics;
- sustain/pedal planning is allowed only if the target representation does not require the modified controller as ground truth; otherwise preserve canonical CC;
- organ generally uses less velocity realism and more gate/phrase/CC shaping than piano.

### 5.4 Acoustic guitar

- chord onset becomes a controlled strum spread, preserving one canonical target onset;
- choose down/up direction from rhythmic context or deterministic alternation;
- spread is shortened as tempo/density increases;
- repeated strums should have correlated but non-identical velocity and duration;
- impossible note-order reversals are forbidden.

### 5.5 Electric guitar

- chord/power-chord spread smaller than acoustic by default;
- lead lines use pick-like microtiming and duration variation;
- high-gain fast passages stay tight;
- palm-mute/legato/bend-like rendering controls may be planned only where supported and must not alter the target pitch/note identity in the clean tier.

### 5.6 Strings — solo

- phrase-level rubato/energy more important than beat-pocket swing;
- small attack delay/advance relative to ensemble;
- legato overlap and note duration shaping;
- fast scales/runs strongly attenuate jitter;
- vibrato/expression CC belongs to render-expression metadata, not target note identity.

### 5.7 Strings — section / ensemble

- use a **shared section offset + small per-player residual** concept;
- avoid every section member attacking at exactly the same millisecond;
- section attack spread increases for slow sustained chords and decreases for rhythmic ostinati/fast runs;
- Violin I/II, viola, cello, bass sections may each have separate persistent biases;
- ensemble texture should be correlated, not randomly scattered.

### 5.8 Brass

- attacks may be slightly later than percussive rhythm-section instruments;
- staccato/accent notes tighter; sustained chords may have small section spread;
- breath-related phrase gaps can shorten note-offs without adding notes;
- trumpet/trombone/horn/tuba sections get separate player/section biases;
- fast jazz/fanfare lines reduce timing randomness;
- falls/doits/shakes that change pitch content are disabled in the clean tier unless they already exist in the source/controller data.

### 5.9 Woodwinds

- breath phrase boundaries and note-off shortening;
- tongued repeated notes tighter than lyrical legato;
- small section/solo onset variation;
- fast runs protected similarly to strings/brass;
- flute/clarinet/sax/oboe/bassoon families may use different attack/gate tendencies.

### 5.10 Choir / voice-like synth parts

- small onset spread for ensemble choir patches;
- phrase-level swell and release variation;
- consonant timing is not modeled unless real phoneme/lyric alignment exists;
- do not invent note pitches absent from the canonical target.

### 5.11 Orchestral percussion

- timpani and struck percussion remain relatively tight;
- rolls/tremolo event ordering protected;
- cymbal release/tail is primarily a renderer/timbre issue rather than MIDI-note timing augmentation.

## 6. Anchor groups and musician interaction

Real players listen to each other. Tracks therefore form shared timing groups.

Recommended groups:

- `RHYTHM_CORE`: kick + bass;
- `BACKBEAT`: snare/clap + selected comping parts;
- `COMPING`: piano/EP/organ + rhythm guitar;
- `HORN_SECTION`: trumpet/trombone/sax section figures;
- `STRING_SECTION`: related orchestral string sections;
- `ORCHESTRA_SECTION`: family-level shared offsets;
- `LEAD_FOLLOW`: lead line plus supportive accompaniment where detected.

Each group receives a bar/phrase shared offset process. Individual tracks add smaller performer residuals. This preserves pocket and prevents the ensemble from sounding like unrelated jittered MIDI tracks.

## 7. Persistent performer identity

Every track gets a seeded performer profile that stays stable across the song, for example:

```json
{
  "timing_tendency": "laid_back",
  "timing_bias_ms": 7.2,
  "consistency": 0.82,
  "velocity_variance": 0.18,
  "gate_tendency": "slightly_short",
  "section_response": 0.65,
  "fast_passage_tightening": 0.78
}
```

A player should not randomly alternate between far ahead and far behind on every note unless the template explicitly calls for an experimental effect.

## 8. Section-aware variation

Humanization intensity must not remain constant for four minutes.

When section labels exist, use them. Otherwise infer rough boundaries from repeated patterns, note density, instrumentation changes and silence/change points.

Provisional section multipliers:

| Section | Groove/dynamic multiplier |
|---|---:|
| intro | `0.70–0.90` |
| verse | `0.85–1.00` |
| pre-chorus | `0.95–1.05` |
| chorus | `1.00–1.15` |
| bridge | `0.85–1.10` |
| instrumental solo | `0.95–1.15` |
| breakdown | `0.65–0.90` |
| outro | `0.70–1.00` |

These values are provisional configuration ranges. Section transitions should be smoothed rather than causing a one-note discontinuity.

## 9. Phrase-level timing and dynamics

Within a section, add low-frequency correlated variation:

- slight phrase arrival delay/advance;
- small bar-to-bar drift with mean reversion;
- phrase-end relaxation;
- pickup/anacrusis push where detected;
- dynamic arc across 2/4/8-bar phrases;
- chorus or climax energy lift;
- repeated identical patterns receive subtle variations but retain recognizability.

Implement drift as a bounded correlated process (for example an AR(1)-like process), not a fresh independent draw for every note.

## 10. Speed-aware protection and mandatory fast material

Fast source material is required for corpus coverage. Humanization must preserve it.

Local density bins:

- `<6 notes/s`: `normal`
- `6–10`: `fast`
- `10–14`: `very_fast`
- `>14`: `extreme`

Initial timing-strength multipliers:

- `<4 notes/s`: `1.00`
- `4–8`: `0.75`
- `8–12`: `0.45`
- `12–16`: `0.25`
- `>16`: `0.10–0.15`

Also tighten chord/strum spread as inter-onset interval decreases. No transformed event may overtake the next distinct canonical onset.

## 11. Density- and tempo-aware scaling

The same `20 ms` is not equivalent at 60 BPM and 220 BPM. Use a normalized maximum based on local inter-onset interval and beat duration.

A safe bound should be computed as the minimum of:

- style/template max milliseconds;
- a fraction of local beat/subdivision duration;
- a fraction of the nearest distinct onset gap;
- instrument-specific max;
- fast-passage attenuation.

This makes the system naturally tighter at high tempo/density.

## 12. Chord and ensemble attack spread

Treat simultaneous canonical onsets as groups.

- preserve canonical group ID;
- choose spread direction/order by instrument;
- apply deterministic offsets to members;
- never let the group cross the next canonical onset;
- store every event offset in `groove_map.json`.

Typical relative behavior:

- acoustic guitar: largest strum spread;
- piano: small/medium rolled-chord spread;
- electric guitar: small spread;
- brass/string sections: small section attack spread;
- synth pads: very small MIDI spread; apparent attack softness belongs mainly to the patch envelope.

## 13. Velocity realism

Velocity is not simple independent noise.

Use:

- metrical accent hierarchy;
- groove-template accent pattern;
- section energy;
- phrase arc;
- repeated-note alternation;
- instrument response profile;
- player consistency;
- small event residual.

For instruments where MIDI velocity poorly represents loudness (organ, some synth pads), reduce velocity augmentation and prefer future expression/CC/timbre controls.

## 14. Note duration / gate realism

Duration transforms must be instrument-aware.

- bass: style-dependent separation/overlap;
- piano: pedal-aware note-off treatment;
- guitar: strum/comping gate patterns;
- staccato brass/woodwind: preserve short articulation;
- legato strings/winds: modest overlap allowed;
- drums: most note-off duration is semantically weak; avoid meaningless edits;
- pads: allow longer overlap if source semantics permit.

Minimum positive duration is enforced, and a transformed note may not create pathological overlaps with unrelated same-pitch notes.

## 15. Pedal / CC / expression planning

Future renderer realism can also come from controller data:

- CC64 sustain;
- CC1 modulation where appropriate;
- CC11 expression;
- CC7 volume only where renderer policy permits;
- aftertouch/pitch-bend only in an explicitly supported render-expression tier.

**Ground-truth caveat:** if the model target includes controller transcription, do not modify a controller while keeping the unmodified controller as the target. In that case either preserve the original controller or create a separately defined canonicalization target policy.

## 16. Articulation realism without label corruption

The clean canonical-target tier may alter **how** a canonical note is rendered, but not what note exists.

Allowed examples:

- same MIDI note rendered with legato/staccato articulation selected from canonical duration/context;
- bow/attack variation;
- drum sample round-robin;
- guitar pick/strum articulation;
- brass attack style;
- velocity-layer/round-robin variation.

Not allowed in the clean tier:

- adding grace notes, ghost notes, flams, fills or ornaments absent from the target;
- pitch-changing falls/doits/bends that materially create unlabeled notes;
- deleting canonical notes.

Those may later exist only in a separately labeled robustness/nuisance tier with an explicit target policy.

## 17. Optional macro-tempo expression — separate gated feature

Phrase-level tempo warping can make a render much more human, but it also changes audio↔canonical-time alignment substantially.

Therefore:

- `macro_tempo_warp.enabled = false` by default while the target representation is not formally confirmed beat-relative/canonicalizing;
- microtiming groove is allowed in dry-run planning now;
- phrase ritardando/accelerando rubato becomes a separate future opt-in tier after target/loss semantics are verified.

Do not silently introduce large tempo-map changes into the current canonical-target pipeline.

## 18. Humanization plan schema

Each future item should store a deterministic plan similar to:

```json
{
  "song_seed": 918223,
  "groove_enabled": true,
  "global_level": "MODERATE",
  "template": "FUNK_16",
  "global_strength": 0.68,
  "sections": [
    {"id":"verse_1", "strength_multiplier":0.92},
    {"id":"chorus_1", "strength_multiplier":1.08}
  ],
  "anchor_groups": {
    "RHYTHM_CORE": ["kick", "bass"]
  },
  "tracks": {
    "bass": {
      "enabled": true,
      "player_seed": 812,
      "timing_tendency": "slightly_ahead",
      "timing_strength": 0.52,
      "velocity_strength": 0.34,
      "duration_strength": 0.20,
      "anchor_group": "RHYTHM_CORE"
    },
    "snare": {
      "enabled": true,
      "timing_tendency": "laid_back",
      "timing_strength": 0.64
    }
  }
}
```

The final `groove_map.json` additionally stores event-level canonical IDs and exact transformed values.

## 19. Automatic song analysis before plan generation

Before choosing humanization, compute as much as available:

- tempo and tempo changes;
- meter;
- key/key changes;
- genre probabilities;
- ensemble type;
- track/instrument roles;
- gridness/quantization confidence;
- note density per track and local window;
- syncopation estimate;
- onset histogram by subdivision;
- chord/simultaneous-onset groups;
- repeated patterns;
- phrase/section boundaries;
- drum pattern type;
- bass↔kick coincidence;
- polyphony;
- register;
- duration/gate distribution;
- velocity distribution;
- pedal/CC presence;
- fast-passage locations and max notes/s.

If the source is not sufficiently grid-like, do not automatically treat it as a canonical target. Performance MIDI belongs in performance/reference tiers unless a score/canonical counterpart exists.

## 20. Source-specific behavior

### Score/canonical MIDI

PDMX, score exports and similarly quantized symbolic sources are primary candidates for `SYNTH_CANONICAL_SCORE_TARGET` groove augmentation.

### Performance MIDI

ASAP performance MIDI and Piano e-Competition live MIDI are primarily **reference distributions** for timing, velocity, pedal and fast-passage behavior. They should not be re-labeled as canonical grid targets unless paired with a canonical score MIDI.

### Unknown web MIDI

Large collections such as `nightingale-ai/midi-data` need a `gridness + provenance + instrumentation + duplicate` audit first. Classify each file as:

- `CANONICAL_GRID_MIDI`
- `LIKELY_SCORE_MIDI`
- `PERFORMANCE_MIDI`
- `MIXED_OR_EDITED_MIDI`
- `UNKNOWN_MIDI`

Only the first two are automatically eligible as canonical targets after QA.

## 21. QA gates for every transformed MIDI

A dry-run `render_control.mid` must fail if any of the following occurs:

1. pitch multiset differs from canonical MIDI in the clean tier;
2. note count differs;
3. canonical event ID cannot be mapped one-to-one;
4. a distinct event ordering reverses;
5. chord/strum spread crosses the next distinct canonical onset;
6. note duration becomes non-positive;
7. same-pitch overlap becomes invalid/pathological;
8. timing displacement exceeds local safety bound;
9. fast-passage attenuation was not applied where required;
10. split/work/arrangement identity is missing;
11. transform seed/template/version is missing;
12. canonical MIDI file hash changed.

Also report per-track statistics:

- mean/median/std timing offset;
- p95/max absolute offset;
- velocity delta stats;
- duration delta stats;
- fast-region vs normal-region offsets;
- anchor-group correlation;
- number of simultaneous groups spread;
- percentage of untouched notes.

## 22. Diversity without unrealistic chaos

Dataset variation should come from several controlled axes:

- some songs completely straight;
- same genre with different pocket strengths;
- same groove family with different player identities;
- instruments opting out independently;
- section-level strength changes;
- multiple groove variants for a subset of songs;
- realistic timbre/preset diversity later;
- fast and slow passages receiving different treatment.

Do not maximize randomness. The goal is **plausible variation**, not entropy.

## 23. Initial implementation order while rendering remains HOLD

1. parse MIDI event-level statistics;
2. classify canonical/grid vs performance MIDI;
3. infer track roles and anchor groups;
4. detect sections/phrases and fast passages;
5. generate seeded per-song/per-track expression plans;
6. apply plans to MIDI copies only;
7. run invariant/QA checks;
8. inspect displacement reports and a small number of MIDI-only examples;
9. calibrate distributions using ASAP/real performance MIDI statistics;
10. only after explicit approval, connect the validated control MIDI to VST rendering.

No audio rendering is authorized by this document.
