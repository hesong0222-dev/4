#!/usr/bin/env python3
"""Backfill provenance for runs produced by the pre-provenance trainer.

This never fabricates missing values. Exact timestamps/commits may be supplied
explicitly; otherwise fields remain null or are inferred only where safe.
"""
import argparse
import datetime as dt
import hashlib
import json
import statistics
import subprocess
from pathlib import Path

import torch


def sha256_file(path: Path, chunk_size=1024 * 1024):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def git_commit(path: Path | None):
    if not path:
        return None
    try:
        return subprocess.check_output(["git", "-C", str(path), "rev-parse", "HEAD"], text=True).strip()
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--samples", required=True)
    ap.add_argument("--run-name")
    ap.add_argument("--start-iso")
    ap.add_argument("--end-iso")
    ap.add_argument("--muscriptor-repo")
    ap.add_argument("--muscriptor-commit")
    ap.add_argument("--manifest-sha256")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()

    run = Path(a.run_dir).expanduser().resolve()
    prov_path = run / "provenance.json"
    marker = run / "CHECKPOINT_COMPLETE"
    if prov_path.exists() and not a.force:
        raise RuntimeError(f"provenance already exists: {prov_path}")

    for name in ("model.safetensors", "trainer_state.pt", "train.jsonl"):
        if not (run / name).exists():
            raise FileNotFoundError(run / name)

    logs = [json.loads(x) for x in (run / "train.jsonl").read_text().splitlines() if x.strip()]
    if not logs:
        raise RuntimeError("empty train.jsonl")
    last = logs[-1]
    step_times = [float(r["sec_per_step"]) for r in logs if "sec_per_step" in r]

    ck = torch.load(run / "trainer_state.pt", map_location="cpu", weights_only=False)
    args = ck.get("args", {})
    samples = Path(a.samples).expanduser().resolve()
    actual_manifest_hash = sha256_file(samples)
    if a.manifest_sha256 and actual_manifest_hash != a.manifest_sha256:
        raise RuntimeError(
            f"manifest hash mismatch: expected {a.manifest_sha256}, got {actual_manifest_hash}"
        )

    start_dt = dt.datetime.fromisoformat(a.start_iso) if a.start_iso else None
    end_dt = dt.datetime.fromisoformat(a.end_iso) if a.end_iso else None
    duration = (end_dt - start_dt).total_seconds() if start_dt and end_dt else None

    files = {}
    for name in ("model.safetensors", "trainer_state.pt", "train.jsonl"):
        p = run / name
        files[name] = {"bytes": p.stat().st_size, "sha256": sha256_file(p)}

    commit = a.muscriptor_commit
    if not commit and a.muscriptor_repo:
        commit = git_commit(Path(a.muscriptor_repo).expanduser().resolve())

    prov = {
        "schema_version": 1,
        "run_name": a.run_name or run.name,
        "status": "complete",
        "backfilled": True,
        "wall_clock": {
            "start": a.start_iso,
            "end": a.end_iso,
            "duration_sec": duration,
            "duration_min": duration / 60.0 if duration is not None else None,
        },
        "step_time_sec": {
            "median": statistics.median(step_times) if step_times else None,
            "mean": statistics.fmean(step_times) if step_times else None,
            "count": len(step_times),
        },
        "final_metrics": {
            "step": last.get("step"),
            "loss": last.get("loss"),
            "token_acc": last.get("token_acc"),
            "max_vram_gb": last.get("max_vram_gb"),
        },
        "seed": args.get("seed"),
        "task": args.get("task"),
        "mode": args.get("mode"),
        "base": args.get("base"),
        "precision": args.get("precision"),
        "manifest": {"path": str(samples), "sha256": actual_manifest_hash},
        "muscriptor_commit": commit,
        "checkpoint_files": files,
        "trainer_args": args,
    }
    prov_path.write_text(json.dumps(prov, indent=2, ensure_ascii=False) + "\n")
    marker.write_text(
        json.dumps(
            {
                "status": "complete",
                "step": last.get("step"),
                "completed_at": a.end_iso,
                "provenance_sha256": sha256_file(prov_path),
                "model_sha256": files["model.safetensors"]["sha256"],
                "trainer_state_sha256": files["trainer_state.pt"]["sha256"],
                "train_log_sha256": files["train.jsonl"]["sha256"],
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )
    print(prov_path)
    print(marker)


if __name__ == "__main__":
    main()
