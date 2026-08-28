# Ground truth policy

`MODEL_PSEUDO_LABEL` is never supervised ground truth. This corpus is `SYNTH_RENDERED_MIDI`; the score MIDI is the exact synthesis source. `REAL_SCORE_ALIGNED` requires identity lock, chroma/beat + onset-DTW alignment, structural checks and manual audit. `REAL_CAPTURED_MIDI` requires synchronous capture provenance.
