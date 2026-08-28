# Instrument-Physics-Constrained AMT

Status: **research idea / experiment specification**  
Project direction: **HarmoScore-MT**  
Date: 2026-08-28

## 1. Core hypothesis

Drums and bass are not only easier because of model/data advantages. They also benefit from a smaller and more structured inference space:

- drums: strong transient timing, small event taxonomy, usually no pitched-note/offset decoding;
- bass: mostly monophonic texture, restricted range, strong harmonic/periodicity structure, relatively smooth pitch-state transitions.

The research hypothesis is:

> Multi-instrument AMT can improve by transferring the *structural advantages* of drum and bass transcription to other instruments through instrument-specific acoustic features, physical/playability constraints, temporal state models, and soft residual conditioning.

This is not a proposal to copy a drum/bass model to every instrument. The goal is to convert each instrument from unconstrained frame-wise note classification into a constrained state-estimation problem.

## 2. Why this is promising

### 2.1 Drums: reduce the time search space

A drum hit is dominated by an onset/transient event. The model can first answer "when did an event occur?" and only then classify the event. This separates timing inference from class inference.

Transferable principle:

`broadband transient evidence -> onset candidates -> instrument/event classification`

Use this for instruments with informative attacks such as piano, guitar, mallet percussion, pizzicato strings, and some brass/woodwind articulations.

### 2.2 Bass: reduce the pitch/state search space

Bass transcription benefits from several priors that are true before any neural prediction:

- low and bounded pitch range;
- usually one active pitch at a time;
- harmonic series consistency;
- periodicity evidence corresponding to F0;
- temporal continuity and limited pitch-jump dynamics.

Transferable principle:

`frequency evidence + periodicity evidence + range/polyphony constraint + temporal continuity -> pitch-state candidates`

PF2N provides direct supporting evidence that frequency-periodicity fusion can improve multi-instrument AMT beyond bass. On Slakh2100, adding PF2N to YMT3 improves onset F1 notably for guitar (+7.2 pp), strings (+6.1 pp), organ (+7.0 pp), pipe (+6.6 pp), reed (+6.9 pp), and other families.

## 3. Proposed architecture

```text
mixture audio
    |
    +--> shared time-frequency encoder
    |
    +--> periodicity / cepstral branch
    |
    +--> transient / onset branch
    |
    +--> instrument-presence / soft-separation branch
    |
    v
instrument-specific experts
    |
    +--> acoustic likelihood
    +--> physical/playability constraints
    +--> temporal state tracking
    |
    v
soft residual / cross-instrument conditioning
    |
    v
music-structure decoder
    |
    +--> performance MIDI head
    +--> canonical score/MIDI head
```

The architecture should remain compatible with the broader HarmoScore-MT direction: harmonic graph reasoning, performance/canonical separation, and later weak-score alignment/EM.

## 4. Instrument-specific constraint library

The constraint layer should not use one rule set for all instruments.

| Instrument/family | Acoustic cue | Physical / structural prior | Decoder emphasis |
|---|---|---|---|
| Drums | transient, broadband attack, spectral fingerprint | finite event classes, no pitched F0 for ordinary drum classes | onset-first event decoder |
| Bass | periodicity, harmonic comb, attack | mostly monophonic, low range, smooth F0 trajectory | constrained F0/state tracker |
| Voice | periodicity, formants | predominantly monophonic lead, continuous F0 | F0 + note segmentation |
| Trumpet / sax / monophonic winds | harmonicity, attack/noise structure | mostly monophonic, instrument range, breathing/phrase continuity | constrained pitch trajectory |
| Violin / solo strings | harmonicity, bow-noise cues | mostly monophonic, continuous pitch, limited simultaneous strings | pitch-first + specialized soft-onset detector |
| Guitar | pluck transient, harmonicity | six-string/fret lattice, bounded polyphony, playable chord shapes | onset + string/fret-aware decoding |
| Piano | strong attack, inharmonic partials, decay | fixed 88-key lattice, high polyphony, sustain-pedal interactions | onset-first polyphonic state decoder |
| String ensemble | harmonic stacks | multiple smooth voices, orchestral ranges, voice continuity | harmonic grouping + voice decomposition |
| Organ | stable harmonics, weak transient | sustained note states, register/timbre combinations | persistent state tracking |
| Pads | weak transient, sustained spectra | long note states, slow changes | frame/state/offset emphasis, not onset-first |

Constraints can be implemented as:

1. **hard masks**: impossible range/state combinations receive zero probability;
2. **soft penalties**: unlikely but possible states are penalized rather than prohibited;
3. **structured decoder states**: Viterbi/CRF/graph/beam-search states represent legal instrument configurations;
4. **conditioning tokens/features**: instrument identity selects a constraint profile.

## 5. Easy-to-hard residual transcription

Instead of solving every instrument with equal priority at the first decoding step, use high-confidence instruments to reduce ambiguity for harder ones.

Candidate order:

1. drums / percussion events;
2. bass;
3. monophonic vocal or lead instruments;
4. guitar / piano;
5. dense strings, pads, ensembles.

Do **not** subtract a predicted waveform destructively. Early separation/transcription errors would propagate.

Pass the following to later experts instead:

- original mixture representation;
- per-instrument soft masks;
- note/event posterior maps;
- harmonic ownership probabilities;
- residual representation.

Example:

> Energy at 63/126/189 Hz can remain in the mixture while the piano expert receives a high probability that the harmonic stack belongs to bass.

This creates **probabilistic source ownership** rather than irreversible source removal.

## 6. Harmonic ownership graph

A direct extension of HarmoScore-MT is to represent detected spectral components as a graph.

Possible node types:

- spectral peak;
- periodicity/F0 candidate;
- onset candidate;
- note candidate;
- instrument candidate.

Possible edges:

- harmonic relation: `f ~= k*f0`;
- temporal continuation;
- common onset;
- instrument compatibility;
- mutual exclusion;
- shared-note/voice relation.

The graph can answer a key multi-instrument failure mode:

> Which instrument owns this harmonic energy?

Instead of letting every decoder independently explain the same peak, ownership becomes an explicit latent variable.

## 7. Training objectives

A first implementation can combine:

```text
L_total =
    L_note
  + lambda_onset       * L_onset
  + lambda_offset      * L_offset
  + lambda_inst        * L_instrument
  + lambda_periodicity * L_periodicity
  + lambda_owner       * L_harmonic_ownership
  + lambda_phys        * L_physical_constraint
  + lambda_temporal    * L_state_continuity
  + lambda_sep         * L_soft_separation
```

Important: physical constraints should not all be hard-coded as absolute rules. Real performances contain extended techniques, double stops, bends, glissandi, pedal effects, and unusual arrangements. Use hard constraints only where states are physically impossible; use soft constraints for musical conventions.

## 8. Required ablation sequence

Run the experiment incrementally so the gain from each mechanism is measurable.

### A. Baseline

YourMT3+/YMT3/YPTF-class baseline with standard instrument-aware decoding.

### B. + Frequency-periodicity branch

Add PF2N-style frequency/periodicity representation.

Measure whether gains reproduce by instrument family.

### C. + Dedicated transient branch

Separate onset candidate generation from pitched-note decoding.

### D. + Instrument physical constraints

Add range, polyphony, monophony, string/fret, note-state, and playability priors.

### E. + Soft ownership / residual conditioning

Pass instrument/posterior masks to later experts without destructive waveform subtraction.

### F. + Harmonic ownership graph

Resolve shared harmonics explicitly across candidate instruments.

### G. + Musical temporal prior

Add voice leading, rhythmic continuity, phrase/state transitions, and canonical-score prior.

Ablation table template:

| Variant | Onset F1 | Onset+Offset F1 | Frame F1 | Instr. F1 | Leakage | Pitch errors | Per-family delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| A baseline | | | | | | | |
| B + periodicity | | | | | | | |
| C + transient | | | | | | | |
| D + physics | | | | | | | |
| E + soft residual | | | | | | | |
| F + ownership graph | | | | | | | |
| G + music prior | | | | | | | |

## 9. Evaluation requirements

Do not rely on a single aggregate F1.

Report at least:

- note onset F1;
- onset+offset F1;
- frame F1;
- pitch-only errors;
- instrument assignment errors;
- instrument leakage / duplicate ownership;
- false polyphony rate;
- range-violation rate;
- note fragmentation rate;
- per-instrument-family metrics;
- dense-mixture vs sparse-mixture slices;
- fast-passage slice;
- soft-attack vs hard-attack slice;
- groove/timing-deviation slices when those datasets become available.

The key research question is not merely whether average F1 increases, but **which ambiguity class is removed by each transferred structural prior**.

## 10. Falsifiable hypotheses

### H1 — Periodicity transfer

Frequency-periodicity fusion will improve pitched families with overlapping harmonics more than drums and other strongly transient/non-pitched classes.

### H2 — Onset transfer

A dedicated transient branch will help piano/guitar/plucked instruments more than pads/legato strings.

### H3 — Physical-state constraints

Instrument-specific range/polyphony/playability priors will reduce false positives and instrument leakage without materially reducing recall.

### H4 — Soft residual conditioning

Soft ownership conditioning will outperform destructive waveform subtraction because it does not propagate early separation mistakes irreversibly.

### H5 — Harmonic ownership

Explicit harmonic ownership will produce the largest gains in dense mixtures where multiple instruments share partials and octave relationships.

### H6 — Search-space reduction

The largest relative gains will appear in instrument families whose unconstrained decoder currently admits many physically or musically invalid states.

## 11. Relation to current dataset strategy

This idea should use the existing data-quality tiers rather than treating all MIDI/audio pairs as equivalent:

- `REAL_CAPTURED_MIDI`: strongest supervision for performance timing and note states;
- `REAL_SCORE_ALIGNED`: weak supervision for canonical structure and cross-version consistency;
- exact source/render pairs: controlled acoustic/structural experiments;
- groove-augmented pairs: later robustness experiments for microtiming and fast passages;
- MIDI-only corpora: symbolic/playability/voice-leading priors;
- unlabeled audio: representation or consistency objectives.

**Current execution constraint:** this document records the research design only. It does not authorize starting MIDI-to-audio rendering. Rendering remains a separate later step.

## 12. Immediate implementation priority

Recommended first experiment:

1. reproduce a strong multi-instrument baseline;
2. add a PF2N-like periodicity branch;
3. implement a small constraint registry for bass, drums, piano, guitar, strings, brass/woodwinds;
4. evaluate per-instrument error slices;
5. only then add soft ownership/residual conditioning;
6. add the full harmonic graph after the simpler mechanisms are quantified.

This ordering minimizes architectural complexity before proving that the central hypothesis is real.

## 13. References / evidence

1. Kim, T.; Kim, M.-J.; Ahn, C.W. **PF2N: Periodicity–Frequency Fusion Network for Multi-Instrument Music Transcription.** Mathematics 2025, 13(11), 1708. DOI: `10.3390/math13111708`.  
   https://doi.org/10.3390/math13111708

2. Cheuk, K.W. et al. **Jointist: Simultaneous Improvement of Multi-instrument Transcription and Music Source Separation via Joint Training.** arXiv:2302.00286.  
   https://arxiv.org/abs/2302.00286

3. Jointist official implementation.  
   https://github.com/KinWaiCheuk/Jointist

## 14. One-line research statement

> Learn the acoustics with neural networks, but let instrument physics, harmonic ownership, and musical state constraints determine which explanations are actually plausible.
