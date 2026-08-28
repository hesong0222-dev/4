# Real-MIDI humanization calibration methodology

**Status:** implementation and one-shot empirical calibration; audio rendering remains on hold.

## Objective

Replace provisional humanization constants with distributions measured from real performance MIDI where possible, while using large score/mixed-MIDI collections only for structural coverage.

The future learning relationship remains:

```text
humanized/grooved synthesized audio -> original canonical MIDI target
```

`render_control.mid` is never the target. This calibration job creates neither audio nor render-control MIDI.

## Evidence tiers

1. **High-confidence expressive timing**
   - Groove MIDI Dataset: professionally played electronic-drum MIDI, style and tempo metadata.
   - ASAP performance MIDI: live piano performances with score/beat annotations.
2. **Reference-only expressive timing**
   - International Piano e-Competition aggregation: live-performance MIDI, but underlying file rights are not clearly documented by the mirror. Statistics may be calculated; files remain quarantined.
3. **Structural MIDI only**
   - POP909, Nightingale sorted collection, and game MIDI: used for tempo, meter, instrumentation, note density and fast-passage coverage. They do not automatically define human microtiming priors or supervised labels.

## Event-level measurements

For each parseable MIDI file:

- tempo map and weighted BPM;
- time signature and changes;
- instrument family and role inferred from track names, channels and GM programs;
- note count, duration, velocity and gate ratio;
- local unique-onset density and 1-second peak notes/s;
- straight/triplet grid-family selection;
- signed and absolute onset residual against the selected local grid;
- persistent per-track timing bias;
- bar-level correlated drift and lag-1 correlation;
- residual variation after removing track bias and bar drift;
- chord/strum spread and pitch-direction correlation;
- eighth-note swing ratio where sufficient offbeat evidence exists;
- selected kick/bass, snare/comping and timekeeper offsets in multi-role MIDI;
- raw, performance-sensitive and canonicalized-content fingerprints.

## Hierarchical performer decomposition

The measured model corresponds to:

```text
note timing = song/grid groove
            + persistent track/player bias
            + bar/phrase-correlated drift
            + role tendency
            + event residual
```

The planner reads `data/policies/adaptive_humanization_calibration_v1.json` when present and falls back to the documented design priors only for families/roles lacking sufficient direct evidence.

## Fast-passage calibration

Tracks are binned by peak unique onsets per second:

- `<4`
- `4-8`
- `8-12`
- `12-16`
- `>=16`

The empirical 90th-percentile event residual is converted into a monotonic timing multiplier. Faster bins can never receive more timing movement than slower bins. Pitch identity, note count, positive duration and distinct-onset ordering remain hard invariants.

## Deduplication and provenance

The output records:

- raw SHA-256 duplicates;
- performance-sensitive event fingerprints;
- content fingerprints with beat-normalized onset/duration;
- source snapshot commit or archive checksum;
- source grade, license and rights status.

Rights-uncertain sources remain reference-only regardless of how realistic their MIDI appears.

## Outputs

`data/calibration/real-midi-humanization-v1/` contains compressed per-file and sampled per-track manifests, fast-passage candidates, aggregate distributions, pairwise offsets, source counts, validation results and checksums.

The calibrated planner override is copied to:

`data/policies/adaptive_humanization_calibration_v1.json`

## Hard completion gates

- at least 50,000 parsed MIDI files;
- at least 2,000 expressive-performance MIDI files;
- no audio renderer invoked;
- planner loads the empirical calibration;
- source rights state is preserved;
- malformed MIDI is logged rather than silently counted.
