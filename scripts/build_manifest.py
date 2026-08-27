#!/usr/bin/env python3
"""Build a reproducible orchestral score/audio-render catalog from PDMX v9."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping

SOURCE = "PDMX v9"
DOI = "10.5281/zenodo.15571083"
RECORD_URL = "https://zenodo.org/records/15571083"
EXPECTED_MD5 = "30392ccf38bb63ce70e7afae70f9c88c"
TRUE = {"1", "true", "t", "yes", "y"}
NULLS = {"", "nan", "na", "n/a", "none", "null"}

ORCHESTRA_TERMS = (
    "orchestra", "orchestral", "philharmonic", "symphony", "symphonic",
    "sinfonia", "sinfonietta", "orchestre", "orchester", "orquesta",
    "orquestra", "orkester", "orkest", "orkiestra", "orkestr", "оркестр",
    "オーケストラ", "오케스트라", "관현악",
)
WIND_TERMS = (
    "wind orchestra", "symphonic band", "concert band", "wind ensemble",
    "concert winds", "symphonic winds", "harmonie orchestra", "吹奏楽",
)
STRING_TERMS = ("string orchestra", "orchestra of strings", "string ensemble")
FULL_SCORE_TERMS = (
    "full score", "conductor score", "orchestral score", "partitura completa",
    "partition d'orchestre", "dirigierpartitur", "总谱", "총보",
)
EXCLUDE_TERMS = (
    "piano reduction", "vocal score", "piano score", "solo piano", "easy piano",
    "piano transcription", "lead sheet", "chord chart", "a cappella", "acapella",
)
BAND_EXCLUDE_TERMS = ("big band", "jazz band", "marching band", "pep band", "rock band")

# Text fallback for future PDMX exports that may use instrument names instead of GM programs.
FAMILY_TERMS = {
    "strings": ("violin", "viola", "cello", "violoncello", "contrabass", "double bass", "string", "harp"),
    "woodwinds": ("flute", "piccolo", "oboe", "english horn", "clarinet", "bassoon", "saxophone", "recorder"),
    "brass": ("french horn", "trumpet", "cornet", "trombone", "euphonium", "tuba", "brass"),
    "percussion": ("timpani", "percussion", "snare", "bass drum", "cymbal", "triangle", "glockenspiel", "xylophone", "marimba", "vibraphone", "drums"),
    "keyboard": ("piano", "harpsichord", "celesta", "organ", "keyboard", "synth"),
    "voice": ("voice", "vocal", "choir", "chorus", "soprano", "alto", "tenor", "baritone", "satb"),
    "guitar_band": ("guitar", "electric bass", "bass guitar", "ukulele", "mandolin"),
}

COLUMNS = [
    "match_id", "source", "source_doi", "source_record_url", "source_record_id",
    "title", "subtitle", "composer", "artist", "license", "license_url",
    "orchestra_class", "confidence_tier", "quality_score", "selection_reason",
    "n_tracks", "instrument_families", "instrument_family_track_counts", "tracks",
    "genres", "groups", "tags", "song_length_seconds", "song_length_bars",
    "n_notes", "rating", "n_ratings", "n_views", "has_custom_audio",
    "mxl_path", "pdf_path", "midi_path", "audio_match_type",
    "audio_render_recipe", "symbolic_match_guarantee", "subset_no_license_conflict",
    "subset_all_valid", "subset_deduplicated", "duplicate_group_id",
]


def norm(value: object) -> str:
    return re.sub(r"\s+", " ", str(value)).strip() if value is not None else ""


def first(row: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = norm(row.get(name, ""))
        if value and value.casefold() not in NULLS:
            return value
    return ""


def boolean(value: object) -> bool:
    return norm(value).casefold() in TRUE


def bool_first(row: Mapping[str, str], *names: str) -> bool:
    return next((boolean(row[name]) for name in names if name in row), False)


def number(value: object, integer: bool = False) -> float | int:
    try:
        parsed = float(norm(value).replace(",", ""))
        return int(parsed) if integer else parsed
    except (TypeError, ValueError):
        return 0 if integer else 0.0


def contains(text: str, terms: Iterable[str]) -> bool:
    folded = norm(text).casefold()
    return any(term in folded for term in terms)


def midi_programs(tracks: str) -> list[int]:
    return [int(x) for x in re.findall(r"(?<!\d)\d{1,3}(?!\d)", tracks) if 0 <= int(x) <= 127]


def program_family(program: int) -> str | None:
    if 0 <= program <= 23:
        return "keyboard"
    if 24 <= program <= 39:
        return "guitar_band"
    if 40 <= program <= 46 or 48 <= program <= 51:
        return "strings"
    if program == 47 or 8 <= program <= 15 or 112 <= program <= 119:
        return "percussion"
    if 52 <= program <= 54:
        return "voice"
    if 56 <= program <= 63:
        return "brass"
    if 64 <= program <= 79:
        return "woodwinds"
    return None


def family_counts(tracks: str) -> Counter[str]:
    counts: Counter[str] = Counter(filter(None, (program_family(p) for p in midi_programs(tracks))))
    folded = tracks.casefold()
    for family, terms in FAMILY_TERMS.items():
        if not counts[family] and any(term in folded for term in terms):
            counts[family] = 1
    return counts


@dataclass(frozen=True)
class Classification:
    kind: str
    tier: str
    reason: str
    families: tuple[str, ...]
    score: float


def classify(row: Mapping[str, str]) -> Classification | None:
    n_tracks = int(number(row.get("n_tracks"), True))
    n_notes = int(number(row.get("n_notes"), True))
    bars = float(number(row.get("song_length.bars")))
    seconds = float(number(row.get("song_length.seconds")))
    tracks = first(row, "tracks")
    text = " | ".join(first(row, k) for k in ("song_name", "title", "subtitle", "genres", "groups", "tags"))
    all_text = f"{text} | {tracks}"

    if n_tracks < 5 or n_notes < 200 or (bars and bars < 12) or (seconds and seconds < 25):
        return None
    if contains(all_text, EXCLUDE_TERMS) or contains(all_text, BAND_EXCLUDE_TERMS):
        return None

    counts = family_counts(tracks)
    s, w, b, p = (counts[k] for k in ("strings", "woodwinds", "brass", "percussion"))
    key, guitar, voice = counts["keyboard"], counts["guitar_band"], counts["voice"]
    core = {k for k in ("strings", "woodwinds", "brass", "percussion") if counts[k]}
    orchestral = s + w + b + p
    ratio = orchestral / max(n_tracks, 1)
    non_string = w + b + p
    explicit_orchestra = contains(all_text, ORCHESTRA_TERMS)
    explicit_wind = contains(all_text, WIND_TERMS)
    explicit_strings = contains(all_text, STRING_TERMS)
    full_score = contains(all_text, FULL_SCORE_TERMS)

    strong_full = n_tracks >= 8 and s >= 2 and w >= 1 and b >= 1 and (guitar <= 2 or explicit_orchestra)
    mostly_strings = n_tracks >= 5 and s >= 3 and s / n_tracks >= 0.5 and guitar == 0 and key <= 1
    strong_wind = n_tracks >= 6 and w >= 2 and b >= 2 and w + b + p >= 5 and guitar <= 1 and key <= 2
    chamber = n_tracks >= 6 and s >= 2 and non_string >= 2 and orchestral >= 5 and ratio >= 0.55 and guitar <= 1 and key <= 2
    broad = n_tracks >= 8 and s >= 2 and len(core) >= 3 and non_string >= 3 and ratio >= 0.5 and guitar <= max(1, n_tracks // 4) and key <= max(3, n_tracks // 2)
    ensemble = n_tracks >= 6 and s >= 1 and len(core) >= 2 and orchestral >= 4 and ratio >= 0.5 and guitar <= 1 and key <= 2

    if strong_full:
        kind = "full_orchestra"
        tier = "A" if explicit_orchestra or full_score else "B"
        reason = "string, woodwind and brass sections" + (" with explicit orchestra/full-score metadata" if tier == "A" else "")
    elif mostly_strings:
        kind, tier = "string_orchestra", ("A" if explicit_strings and full_score else "B" if explicit_strings else "C")
        reason = "predominantly multi-part string instrumentation"
    elif strong_wind:
        kind, tier = "wind_orchestra", ("A" if explicit_wind and p else "B" if explicit_wind else "C")
        reason = "dense woodwind, brass and percussion instrumentation"
    elif explicit_orchestra and n_tracks >= 6 and len(core) >= 2 and s >= 1:
        kind, tier, reason = "explicit_orchestra", "B", "explicit orchestra metadata and multiple orchestral families"
    elif chamber:
        kind, tier, reason = "chamber_orchestra", "C", "multi-track strings plus additional orchestral tracks with an orchestral-majority palette"
    elif broad:
        kind, tier, reason = "inferred_orchestra", "C", "large score with multi-track strings and at least three orchestral families"
    elif ensemble:
        kind, tier, reason = "orchestral_ensemble", "C", "six-or-more-track score with an orchestral-majority palette"
    else:
        return None

    rating = float(number(row.get("rating")))
    ratings = int(number(row.get("n_ratings"), True))
    views = int(number(row.get("n_views"), True))
    score = {"A": 100.0, "B": 70.0, "C": 45.0}[tier]
    score += min(n_tracks, 30) * 0.8 + len(core) * 6 + min(s, 6) * 1.5 + min(w, 6) + min(b, 6)
    score += 8 if full_score else 0
    score += 6 if boolean(row.get("is_official")) else 0
    score += 4 if boolean(row.get("has_annotations")) else 0
    score += min(max(rating, 0), 5) * 2 + min(math.log10(ratings + 1) * 2, 6)
    score += min(math.log10(views + 1) * 1.5, 9) + min(math.log10(n_notes + 1) * 2, 10)
    score -= 5 if key > max(2, n_tracks // 3) else 0
    score -= 4 if voice and len(core) < 3 else 0
    score -= min(guitar, 4) * 1.5
    return Classification(kind, tier, reason, tuple(sorted(k for k, v in counts.items() if v)), round(score, 3))


def source_ok(row: Mapping[str, str]) -> tuple[bool, str]:
    if not bool_first(row, "subset:no_license_conflict"):
        return False, "license_conflict_or_unknown"
    if not bool_first(row, "subset:all_valid"):
        return False, "missing_mxl_pdf_or_midi"
    if bool_first(row, "has_paywall"):
        return False, "paywalled"
    if bool_first(row, "is_draft"):
        return False, "draft"
    if not all(first(row, k) for k in ("mxl", "pdf", "mid")):
        return False, "missing_paths"
    return True, "ok"


def record_id(row: Mapping[str, str]) -> str:
    path = first(row, "path", "mxl", "mid", "pdf")
    if path:
        stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(path).stem).strip("-")[:32]
        digest = hashlib.sha256(path.encode()).hexdigest()[:16]
        return f"{stem}-{digest}" if stem else digest
    return hashlib.sha256((first(row, "title", "song_name") + "|" + first(row, "tracks")).encode()).hexdigest()[:20]


def group_id(row: Mapping[str, str]) -> str:
    representative = first(row, "best_unique_arrangement", "best_arrangement", "best_path")
    return hashlib.sha256(representative.encode()).hexdigest()[:20] if representative else record_id(row)


def is_deduplicated(row: Mapping[str, str]) -> bool:
    return bool_first(row, "subset:deduplicated", "is_best_unique_arrangement")


def output_row(row: Mapping[str, str], c: Classification, index: int) -> dict[str, object]:
    rid = record_id(row)
    mid = first(row, "mid")
    return {
        "match_id": f"PDMX-ORCH-{index:05d}", "source": SOURCE, "source_doi": DOI,
        "source_record_url": RECORD_URL, "source_record_id": rid,
        "title": first(row, "title", "song_name"), "subtitle": first(row, "subtitle"),
        "composer": first(row, "composer_name"), "artist": first(row, "artist_name"),
        "license": first(row, "license"), "license_url": first(row, "license_url"),
        "orchestra_class": c.kind, "confidence_tier": c.tier, "quality_score": c.score,
        "selection_reason": c.reason, "n_tracks": int(number(row.get("n_tracks"), True)),
        "instrument_families": "|".join(c.families),
        "instrument_family_track_counts": json.dumps(dict(sorted(family_counts(first(row, "tracks")).items())), separators=(",", ":")),
        "tracks": first(row, "tracks"), "genres": first(row, "genres"),
        "groups": first(row, "groups"), "tags": first(row, "tags"),
        "song_length_seconds": float(number(row.get("song_length.seconds"))),
        "song_length_bars": float(number(row.get("song_length.bars"))),
        "n_notes": int(number(row.get("n_notes"), True)), "rating": float(number(row.get("rating"))),
        "n_ratings": int(number(row.get("n_ratings"), True)), "n_views": int(number(row.get("n_views"), True)),
        "has_custom_audio": bool_first(row, "has_custom_audio"),
        "mxl_path": first(row, "mxl"), "pdf_path": first(row, "pdf"), "midi_path": mid,
        "audio_match_type": "deterministic_render_from_same_score_midi",
        "audio_render_recipe": f'python scripts/render_audio.py --mid "$PDMX_ROOT/{mid.removeprefix("./")}" --out "audio/{rid}.wav" --soundfont "$SOUNDFONT"',
        "symbolic_match_guarantee": "exact_same_source_score_conversion",
        "subset_no_license_conflict": True, "subset_all_valid": True,
        "subset_deduplicated": is_deduplicated(row), "duplicate_group_id": group_id(row),
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output-dir", default=Path("data"), type=Path)
    parser.add_argument("--target", default=10_000, type=int)
    parser.add_argument("--source-md5", default="")
    args = parser.parse_args()
    if not args.input.is_file() or args.target < 1:
        parser.error("valid --input and positive --target are required")

    candidates: list[tuple[Classification, dict[str, str]]] = []
    rejects: Counter[str] = Counter()
    scanned = 0
    with args.input.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"path", "mxl", "pdf", "mid", "n_tracks", "tracks", "subset:no_license_conflict", "subset:all_valid"}
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise RuntimeError(f"PDMX.csv missing columns: {missing}")
        for row in reader:
            scanned += 1
            ok, reason = source_ok(row)
            if not ok:
                rejects[reason] += 1; continue
            classification = classify(row)
            if not classification:
                rejects["not_orchestral_or_too_small"] += 1; continue
            candidates.append((classification, dict(row)))

    rank = {"A": 0, "B": 1, "C": 2}
    candidates.sort(key=lambda x: (rank[x[0].tier], 0 if is_deduplicated(x[1]) else 1, -x[0].score, record_id(x[1])))

    unique: list[tuple[Classification, dict[str, str]]] = []
    paths: set[str] = set(); ids: set[str] = set()
    for c, row in candidates:
        path, rid = first(row, "path"), record_id(row)
        if path in paths or rid in ids:
            rejects["defensive_duplicate"] += 1; continue
        paths.add(path); ids.add(rid); unique.append((c, row))
    if len(unique) < args.target:
        raise RuntimeError(f"Not enough qualifying unique source records: found={len(unique)}, target={args.target}, classes={dict(Counter(c.kind for c, _ in unique))}")

    selected_pairs: list[tuple[Classification, dict[str, str]]] = []
    selected_ids: set[str] = set(); group_counts: Counter[str] = Counter(); cap_stage = "not_reached"
    for cap in (3, 10, None):
        for c, row in unique:
            rid, group = record_id(row), group_id(row)
            if rid in selected_ids or (cap is not None and group_counts[group] >= cap):
                continue
            selected_pairs.append((c, row)); selected_ids.add(rid); group_counts[group] += 1
            if len(selected_pairs) == args.target:
                cap_stage = "unlimited" if cap is None else f"cap_{cap}"; break
        if len(selected_pairs) == args.target:
            break
    if len(selected_pairs) != args.target:
        raise RuntimeError(f"Selection exhausted: {len(selected_pairs)} / {args.target}")

    selected = [output_row(row, c, i) for i, (c, row) in enumerate(selected_pairs, 1)]
    out = args.output_dir; out.mkdir(parents=True, exist_ok=True)
    csv_path = out / f"orchestra_exact_{args.target}.csv"
    jsonl_path = out / f"orchestra_exact_{args.target}.jsonl"
    write_csv(csv_path, selected); write_jsonl(jsonl_path, selected)
    for start in range(0, len(selected), 1000):
        write_csv(out / "shards" / f"part-{start // 1000 + 1:05d}.csv", selected[start:start + 1000])
    custom = [row for row in selected if row["has_custom_audio"]]
    write_csv(out / "custom_audio_metadata_candidates.csv", custom)
    write_csv(out / "sample_100.csv", selected[:100])

    classes = Counter(str(r["orchestra_class"]) for r in selected)
    tiers = Counter(str(r["confidence_tier"]) for r in selected)
    families: Counter[str] = Counter()
    for row in selected:
        families.update(filter(None, str(row["instrument_families"]).split("|")))
    dedup_count = sum(bool(r["subset_deduplicated"]) for r in selected)
    stats = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "source": SOURCE,
        "source_doi": DOI, "source_record_url": RECORD_URL,
        "source_csv_expected_md5": EXPECTED_MD5, "source_csv_observed_md5": args.source_md5 or None,
        "source_rows_scanned": scanned, "qualifying_candidates_before_defensive_dedup": len(candidates),
        "qualifying_unique_candidates": len(unique), "selected_exact_matches": len(selected),
        "target": args.target, "selection_complete": len(selected) == args.target,
        "orchestra_class_counts": dict(sorted(classes.items())),
        "confidence_tier_counts": dict(sorted(tiers.items())),
        "instrument_family_counts": dict(sorted(families.items())),
        "selected_with_custom_audio_metadata": len(custom),
        "selected_deduplicated_records": dedup_count,
        "selected_additional_arrangements": len(selected) - dedup_count,
        "duplicate_group_selection_stage": cap_stage,
        "maximum_selected_per_duplicate_group": max(group_counts.values(), default=0),
        "rejection_counts": dict(sorted(rejects.items())), "catalog_sha256": sha256(csv_path),
        "jsonl_sha256": sha256(jsonl_path),
        "definition": {
            "exact_match": "PDF, MXL and MIDI converted from the same PDMX source score; audio rendered from that MIDI",
            "human_performance_claim": False,
            "license_policy": "no-license-conflict + all-valid + non-paywalled + non-draft; deduplicated records ranked first",
            "uniqueness_claim": "unique source paths and record IDs; not necessarily unique compositions",
        },
    }
    (out / "stats.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [f"{sha256(path)}  {path.relative_to(out)}" for path in sorted(out.rglob("*")) if path.is_file() and path.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
