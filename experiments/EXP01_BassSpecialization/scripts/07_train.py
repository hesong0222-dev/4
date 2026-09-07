#!/usr/bin/env python3
import argparse
import contextlib
import datetime as dt
import hashlib
import io
import json
import math
import os
import random
import statistics
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import torch
import torch.nn.functional as F

from amt_pilot.dataset import SampleStore, make_condition
from amt_pilot.model_io import load_tm, save_model


def samplewise_ce_and_acc(logits, labels):
    B, S, V = logits.shape
    raw = F.cross_entropy(
        logits.reshape(-1, V),
        labels.reshape(-1),
        ignore_index=-100,
        reduction="none",
    ).reshape(B, S)
    mask = labels != -100
    per_sample = (raw * mask).sum(1) / mask.sum(1).clamp_min(1)
    loss = per_sample.mean()
    acc = ((logits.argmax(-1) == labels) & mask).sum() / mask.sum().clamp_min(1)
    return loss, acc


class Stream:
    def __init__(self, n, seed):
        self.n = n
        self.r = random.Random(seed)

    def batch(self, b):
        return [self.r.randrange(self.n) for _ in range(b)]

    def state(self):
        return self.r.getstate()

    def restore(self, x):
        self.r.setstate(x)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def git_commit(path: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(path), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except Exception:
        return None


def iso_now() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def write_complete_marker(out: Path, payload: dict) -> None:
    tmp = out / "CHECKPOINT_COMPLETE.tmp"
    final = out / "CHECKPOINT_COMPLETE"
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, final)


def write_provenance(*, out, args, started_at, ended_at, duration_sec, step_times, final_rec, muscriptor_repo):
    checkpoint_files = {}
    for name in ("model.safetensors", "trainer_state.pt", "train.jsonl"):
        path = out / name
        if path.exists():
            checkpoint_files[name] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}

    samples_path = Path(args.samples).expanduser().resolve()
    corrections_path = Path(args.corrections).expanduser().resolve()
    source_path = Path(__file__).resolve()
    prov = {
        "schema_version": 1,
        "run_name": out.name,
        "status": "complete",
        "wall_clock": {
            "start": started_at,
            "end": ended_at,
            "duration_sec": duration_sec,
            "duration_min": duration_sec / 60.0,
        },
        "step_time_sec": {
            "median": statistics.median(step_times) if step_times else None,
            "mean": statistics.fmean(step_times) if step_times else None,
            "count": len(step_times),
        },
        "final_metrics": {
            "step": final_rec.get("step"),
            "loss": final_rec.get("loss"),
            "token_acc": final_rec.get("token_acc"),
            "max_vram_gb": final_rec.get("max_vram_gb"),
        },
        "seed": args.seed,
        "task": args.task,
        "mode": args.mode,
        "base": args.base,
        "precision": args.precision,
        "hyperparameters": {
            "steps": args.steps,
            "batch_size": args.batch_size,
            "grad_accum": args.grad_accum,
            "effective_batch": args.batch_size * args.grad_accum,
            "learning_rate": args.lr,
            "save_every": args.save_every,
            "workers": args.workers,
            "max_samples": args.max_samples,
        },
        "inputs": {
            "samples_manifest": str(samples_path),
            "samples_manifest_sha256": sha256_file(samples_path),
            "corrections": str(corrections_path),
            "corrections_sha256": sha256_file(corrections_path),
        },
        "code": {
            "train_script": str(source_path),
            "train_script_sha256": sha256_file(source_path),
            "muscriptor_commit": git_commit(muscriptor_repo) if muscriptor_repo else None,
        },
        "checkpoint_files": checkpoint_files,
        "command": " ".join(sys.argv),
    }
    path = out / "provenance.json"
    path.write_text(json.dumps(prov, indent=2, ensure_ascii=False) + "\n")
    return prov


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", required=True)
    ap.add_argument("--corrections", required=True)
    ap.add_argument("--task", choices=["general", "bass"], required=True)
    ap.add_argument("--mode", choices=["normal", "tpcr"], default="normal")
    ap.add_argument("--base", default="small")
    ap.add_argument("--out", required=True)
    ap.add_argument("--steps", type=int, default=3000)
    ap.add_argument("--batch-size", type=int, default=2)
    ap.add_argument("--grad-accum", type=int, default=8)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--seed", type=int, default=20260905)
    ap.add_argument("--precision", choices=["fp32", "bf16"], default="bf16")
    ap.add_argument("--save-every", type=int, default=500)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--max-samples", type=int)
    ap.add_argument("--resume", action="store_true")
    ap.add_argument("--allow-overwrite-complete", action="store_true")
    ap.add_argument("--muscriptor-repo", default=None)
    a = ap.parse_args()

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA required")

    out = Path(a.out).expanduser().resolve()
    complete_marker = out / "CHECKPOINT_COMPLETE"
    if complete_marker.exists() and not a.allow_overwrite_complete:
        raise RuntimeError(
            f"Refusing to modify completed run: {out}. Use a new --out directory. "
            "Only use --allow-overwrite-complete intentionally."
        )
    out.mkdir(parents=True, exist_ok=True)

    state_path = out / "trainer_state.pt"
    model_path = out / "model.safetensors"
    if not a.resume and (state_path.exists() or model_path.exists() or (out / "train.jsonl").exists()):
        raise RuntimeError(
            f"Run directory is not empty: {out}. Use --resume for an incomplete run or choose a new --out directory."
        )

    started_wall = time.time()
    started_at = iso_now()
    model_source = str(model_path) if a.resume and model_path.exists() else a.base
    torch.manual_seed(a.seed)
    random.seed(a.seed)
    tm = load_tm(model_source, "cuda", "float32")
    model = tm._model
    model.train()
    tok = tm._tokenizer

    store = SampleStore(a.samples, a.corrections, a.task, a.mode)
    store.rows = [r for r in store.rows if r["split"] == "train"]
    if a.max_samples:
        store.rows = store.rows[: a.max_samples]
    stream = Stream(len(store), a.seed)

    decay, nodec = [], []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        (nodec if p.ndim < 2 or name.endswith(".bias") or "norm" in name.lower() else decay).append(p)

    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 0.01}, {"params": nodec, "weight_decay": 0.0}],
        lr=a.lr,
        betas=(0.9, 0.95),
    )
    warm = max(1, int(a.steps * 0.05))
    sch = torch.optim.lr_scheduler.LambdaLR(
        opt,
        lambda s: max(1e-3, s / warm)
        if s < warm
        else 0.5 * (1 + math.cos(math.pi * (s - warm) / max(1, a.steps - warm))),
    )
    start = 0
    if a.resume:
        if not state_path.exists():
            raise FileNotFoundError(state_path)
        ck = torch.load(state_path, map_location="cpu", weights_only=False)
        opt.load_state_dict(ck["optimizer"])
        sch.load_state_dict(ck["scheduler"])
        stream.restore(ck["stream_state"])
        torch.set_rng_state(ck["torch_rng"])
        torch.cuda.set_rng_state_all(ck["cuda_rng"])
        start = int(ck["step"])
        print("RESUME step", start)

    log = open(out / "train.jsonl", "a" if a.resume else "w")
    pool = ThreadPoolExecutor(max_workers=a.workers)
    bf = a.precision == "bf16" and torch.cuda.is_bf16_supported()
    step_times = []
    final_rec = {}

    try:
        for step in range(start + 1, a.steps + 1):
            t0 = time.time()
            ls = 0.0
            acs = 0.0
            opt.zero_grad(set_to_none=True)
            for _ in range(a.grad_accum):
                batch = list(pool.map(lambda i: store.get(i, tok), stream.batch(a.batch_size)))
                labs = [x[1] for x in batch]
                S = max(t.numel() for t in labs)
                B = len(labs)
                inp = torch.full((B, S), model.zero_token_id, dtype=torch.long, device="cuda")
                lab = torch.full((B, S), -100, dtype=torch.long, device="cuda")
                attrs = []
                for i, (audio, t, cond, _) in enumerate(batch):
                    t = t.cuda()
                    L = t.numel()
                    inp[i, 0] = model.initial_token_id
                    lab[i, :L] = t
                    if L > 1:
                        inp[i, 1:L] = t[:-1]
                    attrs.append(make_condition(audio.cuda(), cond))
                prepared = model.condition_provider.tokenize(attrs)
                with contextlib.redirect_stdout(io.StringIO()):
                    conds = model.condition_provider(prepared)
                with torch.autocast("cuda", dtype=torch.bfloat16, enabled=bf):
                    raw_loss, acc = samplewise_ce_and_acc(model(inp, conds, first_step=True), lab)
                    loss = raw_loss / a.grad_accum
                if not torch.isfinite(loss):
                    raise RuntimeError("non-finite loss")
                loss.backward()
                ls += float(loss.item())
                acs += float(acc.item()) / a.grad_accum

            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
            sch.step()
            sec = time.time() - t0
            step_times.append(sec)
            rec = {
                "step": step,
                "loss": ls,
                "token_acc": acs,
                "lr": sch.get_last_lr()[0],
                "sec_per_step": sec,
                "max_vram_gb": torch.cuda.max_memory_allocated() / 1e9,
            }
            final_rec = rec
            log.write(json.dumps(rec) + "\n")
            log.flush()
            if step == 1 or step % 20 == 0:
                print(rec, flush=True)
            if step % a.save_every == 0 or step == a.steps:
                save_model(model, out)
                torch.save(
                    {
                        "step": step,
                        "optimizer": opt.state_dict(),
                        "scheduler": sch.state_dict(),
                        "stream_state": stream.state(),
                        "torch_rng": torch.get_rng_state(),
                        "cuda_rng": torch.cuda.get_rng_state_all(),
                        "args": vars(a),
                    },
                    state_path,
                )
    finally:
        pool.shutdown()
        log.close()

    ended_at = iso_now()
    duration_sec = time.time() - started_wall
    repo = Path(a.muscriptor_repo).expanduser().resolve() if a.muscriptor_repo else None
    prov = write_provenance(
        out=out,
        args=a,
        started_at=started_at,
        ended_at=ended_at,
        duration_sec=duration_sec,
        step_times=step_times,
        final_rec=final_rec,
        muscriptor_repo=repo,
    )
    write_complete_marker(
        out,
        {
            "status": "complete",
            "step": final_rec.get("step"),
            "completed_at": ended_at,
            "provenance_sha256": sha256_file(out / "provenance.json"),
            "model_sha256": prov.get("checkpoint_files", {}).get("model.safetensors", {}).get("sha256"),
            "trainer_state_sha256": prov.get("checkpoint_files", {}).get("trainer_state.pt", {}).get("sha256"),
            "train_log_sha256": prov.get("checkpoint_files", {}).get("train.jsonl", {}).get("sha256"),
        },
    )
    print("RUN COMPLETE; provenance and checksums written to", out, flush=True)


if __name__ == "__main__":
    main()
