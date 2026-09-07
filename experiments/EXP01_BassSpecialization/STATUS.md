# EXP01 status

## 2026-09-07 — C1 complete

`C1 General Continued-Training` finished successfully at step 3000.

- Wall clock: 07:25:35 → 08:39:00 KST (73.4 min)
- Median / mean step time: 1.263 / 1.368 s
- Peak VRAM: 3.68 GB
- Final training loss: 0.5627
- Final token accuracy: 0.7844
- Seed: 42
- MuScriptor: `d73147e` (`v0.3.0`)
- Manifest digest as reported in chat: `084defe6...801a7a` (abbreviated; full value is retained in the original run provenance)
- `CHECKPOINT_COMPLETE`: verified at step 3000
- `model.safetensors`, `trainer_state.pt`, `train.jsonl`: SHA256 reverified against backup record
- Physical backup: `~/exp01_c1_backup/` (~1.1 GB)
- Modal provenance: `work/reports/C1_provenance.json`

The exact checkpoint digest strings were not included in the chat message used to generate this GitHub status file, so this document intentionally does **not** invent them. The original provenance JSON is authoritative for those values.

## Scientific interpretation

The C1 training curve is healthy, but C1's loss/token accuracy is **not** directly comparable to M1/M2 because C1 predicts the full multi-instrument target while M1/M2 predict bass-only targets. The key comparison remains identical evaluation-set bass transcription metrics:

- `M1 - M0`: operational bass-specialist benefit
- `M1 - C1`: specialization-specific benefit beyond continued training
- `M2 - M1`: TPCR replacement benefit

## Current queue

- C1: ✅ complete and backed up
- M1: running at the time of the latest report
- M2: queued after M1

## Provenance policy added after C1

Future trainer revisions must:

1. Refuse to modify a directory containing `CHECKPOINT_COMPLETE` unless an explicit dangerous override is supplied.
2. Refuse a non-empty run directory unless `--resume` is used for an incomplete run.
3. On successful completion, write `provenance.json` containing timestamps, runtime statistics, final metrics, seed, manifest/correction hashes, MuScriptor commit, trainer script hash and checkpoint file SHA256 values.
4. Write `CHECKPOINT_COMPLETE` only after final checkpoint and provenance have been safely written.
5. Allow old runs to be backfilled using `scripts/11_write_run_provenance.py` without fabricating unavailable fields.
