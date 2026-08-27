#!/usr/bin/env python3
"""Build a deterministic 10,000-item orchestral score/audio match catalog from PDMX.

The score PDF, MXL and MIDI referenced by every selected row are conversions of the
same source score. Audio is rendered from that exact MIDI, so the MIDI-to-audio event
stream is reproducible rather than inferred from titles.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

TARGET_DEFAULT = 10_000
SOURCE_NAME = "PDMX v9"
SOURCE_DOI = "10.5281/zenodo.15571083"
SOURCE_RECORD_URL = "https://zenodo.org/records/15571083"
SOURCE_CSV_MD5 = "30392ccf38bb63ce70e7afae70f9c88c"

TRUE_VALUES = {"1", "true", "t", "yes", "y"}
FALSE_VALUES = {"0", "false", "f", "no", "n", "", "nan", "na", "n/a", "none"}

FAMILY_TERMS: dict[str, tuple[str, ...]] = {
    "strings": (
        "violin", "viola", "violoncello", "cello", "double bass", "contrabass",
        "contrabasso", "string bass", "string ensemble", "orchestral strings",
        "strings", "harp",
    ),
    "woodwinds": (
        "piccolo", "flute", "oboe", "english horn", "cor anglais", "clarinet",
        "bassoon", "contrabassoon", "saxophone", "soprano sax", "alto sax",
        "tenor sax", "baritone sax", "recorder",
    ),
    "brass": (
        "french horn", "horn in", "horns", "trumpet", "cornet", "flugelhorn",
        "trombone", "euphonium", "baritone horn", "tuba", "brass ensemble",
    ),
    "percussion": (
        "timpani", "percussion", "snare drum", "bass drum", "cymbal", "triangle",
        "tambourine", "glockenspiel", "xylophone", "marimba", "vibraphone",
        "tubular bell", "chimes", "drumset", "drum set", "drums",
    ),
    "keyboard": (
        "piano", "grand piano", "harpsichord", "celesta", "organ", "keyboard",
        "synthesizer", "synth",
    ),
    "voice": (
        "voice", "vocal", "choir", "chorus", "soprano", "alto voice", "tenor voice",
        "baritone voice", "bass voice", "satb",
    ),
    "guitar_band": (
        "guitar", "electric bass", "bass guitar", "ukulele", "mandolin",
    ),
}

ORCHESTRA_TERMS = (
    "orchestra", "orchestral", "full orchestra", "chamber orchestra",
    "string orchestra", "symphony orchestra", "symphonic orchestra",
    "philharmonic", "symphony", "symphonic", "sinfonia", "sinfonietta",
    "orchestre", "orchester", "orquesta", "orquestra", "orkester", "orkest",
    "orkiestra", "orkestr", "оркестр", "オーケストラ", "오케스트라", "관현악",
)

WIND_ORCHESTRA_TERMS = (
    "wind orchestra", "symphonic band", "concert band", "wind ensemble",
    "concert winds", "symphonic winds", "harmonie orchestra", "吹奏楽",
)

STRING_ORCHESTRA_TERMS = (
    "string orchestra", "orchestra of strings", "string ensemble", "strings orchestra",
)

FULL_SCORE_TERMS = (
    "full score", "conductor score", "orchestral score", "partitura completa",
    "partition d'orchestre", "dirigierpartitur", "总谱", "총보",
)

EXCLUDE_TERMS = (
    "piano reduction", "vocal score", "piano score", "solo piano", "easy piano",
    "piano transcription", "lead sheet", "chord chart", "a cappella", "acapella",
)

NON_ORCHESTRAL_BAND_TERMS = (
    "big band", "jazz band", "marching band", "pep band", "rock band",
)

OUTPUT_COLUMNS = [
    "match_id", "source", "source_doi", "source_record_url", "source_record_id",
    "title", "subtitle", "composer", "artist", "license", "license_url",
    "orchestra_class", "confidence_tier", "quality_score", "selection_reason",
    "n_tracks", "instrument_families", "instrument_family_track_counts", "tracks",
    "genres", "groups", "tags", "song_length_seconds", "song_length_bars",
    "n_notes", "rating", "n_ratings", "n_views", "has_custom_audio",
    "mxl_path", "pdf_path", "midi_path", "audio_match_type",
    "audio_render_recipe", "symbolic_match_guarantee",
    "subset_no_license_conflict", "subset_all_valid", "subset_deduplicated",
]


def normalize(value: object) -> str:
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def lower(value: object) -> str:
    return normalize(value).casefold()


def as_bool(value: object) -> bool:
    text = lower(value)
    if text in TRUE_VALUES:
        return True
    if text in FALSE_VALUES:
        return False
    return False


def as_int(value: object, default: int = 0) -> int:
    try:
        text = normalize(value).replace(",", "")
        return int(float(text)) if text else default
    except (TypeError, ValueError):
        return default


def as_float(value: object, default: float = 0.0) -> float:
    try:
        text = normalize(value).replace(",", "")
        return float(text) if text else default
    except (TypeError, ValueError):
        return default


def first(row: Mapping[str, str], *names: str) -> str:
    for name in names:
        if name not in row:
            continue
        value = normalize(row[name])
        if value and value.casefold() not in {"nan", "na", "n/a", "none", "null"}:
            return value
    return ""


def bool_first(row: Mapping[str, str], *names: str) -> bool:
    for name in names:
        if name in row:
            return as_bool(row[name])
    return False


def families_from_text(text: str) -> set[str]:
    t = lower(text)
    return {
        family
        for family, terms in FAMILY_TERMS.items()
        if any(term in t for term in terms)
    }


def parse_midi_programs(tracks: str) -> list[int]:
    """Parse PDMX's hyphen-joined, zero-based General MIDI program list.

    PDMX's source code serializes each track as ``track.program`` and joins the
    sorted values with ``-``. The parser also tolerates commas, JSON-ish lists,
    and future text-bearing track fields.
    """
    return [
        value
        for token in re.findall(r"(?<!\d)\d{1,3}(?!\d)", normalize(tracks))
        if 0 <= (value := int(token)) <= 127
    ]


def family_for_program(program: int) -> str | None:
    # General MIDI Level 1 program numbers are zero-based in PDMX/MusPy.
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


def family_counts_from_tracks(tracks: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for program in parse_midi_programs(tracks):
        family = family_for_program(program)
        if family:
            counts[family] += 1
    # Retain compatibility with any future PDMX export that stores names instead.
    for family in families_from_text(tracks):
        if counts[family] == 0:
            counts[family] = 1
    return counts


def has_any(text: str, terms: Iterable[str]) -> bool:
    t = lower(text)
    return any(term in t for term in terms)


@dataclass(frozen=True)
class Classification:
    orchestra_class: str
    tier: str
    reason: str
    families: tuple[str, ...]
    score: float


def classify(row: Mapping[str, str]) -> Classification | None:
    n_tracks = as_int(row.get("n_tracks"))
    n_notes = as_int(row.get("n_notes"))
    bars = as_float(row.get("song_length.bars"))
    seconds = as_float(row.get("song_length.seconds"))

    title_text = " | ".join(
        first(row, field)
        for field in ("song_name", "title", "subtitle", "genres", "groups", "tags")
    )
    tracks = first(row, "tracks")
    all_text = f"{title_text} | {tracks}"
    family_counts = family_counts_from_tracks(tracks)
    families = set(family_counts)
    core = families & {"strings", "woodwinds", "brass", "percussion"}

    strings_n = family_counts["strings"]
    woodwinds_n = family_counts["woodwinds"]
    brass_n = family_counts["brass"]
    percussion_n = family_counts["percussion"]
    keyboard_n = family_counts["keyboard"]
    guitar_band_n = family_counts["guitar_band"]

    explicit_orchestra = has_any(all_text, ORCHESTRA_TERMS)
    explicit_wind = has_any(all_text, WIND_ORCHESTRA_TERMS)
    explicit_strings = has_any(all_text, STRING_ORCHESTRA_TERMS)
    explicit_full_score = has_any(all_text, FULL_SCORE_TERMS)
    excluded = has_any(all_text, EXCLUDE_TERMS)
    non_orchestral_band = has_any(all_text, NON_ORCHESTRAL_BAND_TERMS)

    # Basic completeness floor. This removes tiny excerpts, exercises and fragments.
    if n_tracks < 5 or n_notes < 200:
        return None
    if bars and bars < 12:
        return None
    if seconds and seconds < 25:
        return None
    if excluded:
        return None

    orchestra_class = ""
    tier = ""
    reason = ""

    strong_full_orchestra = (
        n_tracks >= 8
        and strings_n >= 2
        and woodwinds_n >= 1
        and brass_n >= 1
        and (guitar_band_n <= 2 or explicit_orchestra)
    )
    mostly_strings = strings_n >= 4 and strings_n / max(n_tracks, 1) >= 0.55
    strong_wind = n_tracks >= 8 and woodwinds_n >= 3 and brass_n >= 2
    broad_orchestral_palette = (
        n_tracks >= 9
        and strings_n >= 2
        and len(core) >= 3
        and (woodwinds_n + brass_n + percussion_n) >= 3
        and guitar_band_n <= max(1, n_tracks // 4)
        and keyboard_n <= max(3, n_tracks // 2)
    )

    if strong_full_orchestra:
        orchestra_class = "full_orchestra"
        if explicit_orchestra or explicit_full_score:
            tier = "A"
            reason = (
                "GM instrumentation contains string, woodwind and brass sections; "
                "metadata explicitly identifies an orchestra/full score"
            )
        else:
            tier = "B"
            reason = (
                "GM instrumentation contains multi-track strings plus woodwind "
                "and brass sections"
            )
    elif explicit_strings and mostly_strings:
        orchestra_class = "string_orchestra"
        tier = "A" if explicit_full_score else "B"
        reason = "explicit string-orchestra metadata with at least four string tracks"
    elif mostly_strings and n_tracks >= 6 and guitar_band_n == 0:
        orchestra_class = "string_orchestra"
        tier = "C"
        reason = (
            "inferred string orchestra from a predominantly multi-part string "
            "instrumentation"
        )
    elif explicit_wind and strong_wind:
        orchestra_class = "wind_orchestra"
        tier = "A" if percussion_n >= 1 else "B"
        reason = (
            "explicit wind-orchestra/symphonic-band metadata with woodwind and "
            "brass sections"
        )
    elif explicit_orchestra and n_tracks >= 6 and len(core) >= 2 and strings_n >= 1:
        orchestra_class = "explicit_orchestra"
        tier = "B"
        reason = "explicit orchestra metadata plus multiple orchestral instrument families"
    elif broad_orchestral_palette and not non_orchestral_band:
        orchestra_class = "inferred_orchestra"
        tier = "C"
        reason = "large score with multi-track strings and at least three orchestral GM families"
    else:
        return None

    # Explicit big/jazz/marching/rock-band metadata is outside this catalog even if
    # a user arrangement happens to contain a few orchestral GM programs.
    if non_orchestral_band:
        return None

    rating = as_float(row.get("rating"))
    n_ratings = as_int(row.get("n_ratings"))
    n_views = as_int(row.get("n_views"))
    is_official = as_bool(row.get("is_official"))
    has_annotations = as_bool(row.get("has_annotations"))

    score = 0.0
    score += {"A": 100.0, "B": 70.0, "C": 45.0}[tier]
    score += min(n_tracks, 30) * 0.8
    score += len(core) * 6.0
    score += min(strings_n, 6) * 1.5
    score += min(woodwinds_n, 6) * 1.0
    score += min(brass_n, 6) * 1.0
    score += 8.0 if explicit_full_score else 0.0
    score += 6.0 if is_official else 0.0
    score += 4.0 if has_annotations else 0.0
    score += min(max(rating, 0.0), 5.0) * 2.0
    score += min(math.log10(n_ratings + 1.0) * 2.0, 6.0)
    score += min(math.log10(n_views + 1.0) * 1.5, 9.0)
    score += min(math.log10(n_notes + 1.0) * 2.0, 10.0)
    if keyboard_n > max(2, n_tracks // 3):
        score -= 5.0
    if family_counts["voice"] > 0 and len(core) < 3:
        score -= 4.0
    if guitar_band_n > 0:
        score -= min(guitar_band_n, 4) * 1.5

    return Classification(
        orchestra_class=orchestra_class,
        tier=tier,
        reason=reason,
        families=tuple(
            sorted(family for family, count in family_counts.items() if count > 0)
        ),
        score=round(score, 3),
    )


def verify_source_row(row: Mapping[str, str]) -> tuple[bool, str]:
    no_conflict = bool_first(row, "subset:no_license_conflict")
    all_valid = bool_first(row, "subset:all_valid")
    deduplicated = bool_first(
        row, "subset:deduplicated", "is_best_unique_arrangement"
    )
    paywalled = bool_first(row, "has_paywall")
    draft = bool_first(row, "is_draft")

    if not no_conflict:
        return False, "license_conflict_or_unknown"
    if not all_valid:
        return False, "missing_mxl_pdf_or_midi"
    if not deduplicated:
        return False, "not_deduplicated"
    if paywalled:
        return False, "paywalled"
    if draft:
        return False, "draft"
    if not first(row, "mxl") or not first(row, "pdf") or not first(row, "mid"):
        return False, "missing_paths"
    return True, "ok"


def source_record_id(row: Mapping[str, str]) -> str:
    path = first(row, "path", "mxl", "mid", "pdf")
    stem = Path(path).stem
    if stem:
        return stem
    digest = hashlib.sha256(
        (first(row, "title", "song_name") + "|" + first(row, "tracks")).encode("utf-8")
    ).hexdigest()
    return digest[:20]


def build_output_row(
    row: Mapping[str, str], c: Classification, index: int
) -> dict[str, object]:
    record_id = source_record_id(row)
    midi_path = first(row, "mid")
    safe_mid = midi_path.removeprefix("./")
    return {
        "match_id": f"PDMX-ORCH-{index:05d}",
        "source": SOURCE_NAME,
        "source_doi": SOURCE_DOI,
        "source_record_url": SOURCE_RECORD_URL,
        "source_record_id": record_id,
        "title": first(row, "title", "song_name"),
        "subtitle": first(row, "subtitle"),
        "composer": first(row, "composer_name"),
        "artist": first(row, "artist_name"),
        "license": first(row, "license"),
        "license_url": first(row, "license_url"),
        "orchestra_class": c.orchestra_class,
        "confidence_tier": c.tier,
        "quality_score": c.score,
        "selection_reason": c.reason,
        "n_tracks": as_int(row.get("n_tracks")),
        "instrument_families": "|".join(c.families),
        "instrument_family_track_counts": json.dumps(
            dict(sorted(family_counts_from_tracks(first(row, "tracks")).items())),
            ensure_ascii=False,
            separators=(",", ":"),
        ),
        "tracks": first(row, "tracks"),
        "genres": first(row, "genres"),
        "groups": first(row, "groups"),
        "tags": first(row, "tags"),
        "song_length_seconds": as_float(row.get("song_length.seconds")),
        "song_length_bars": as_float(row.get("song_length.bars")),
        "n_notes": as_int(row.get("n_notes")),
        "rating": as_float(row.get("rating")),
        "n_ratings": as_int(row.get("n_ratings")),
        "n_views": as_int(row.get("n_views")),
        "has_custom_audio": bool_first(row, "has_custom_audio"),
        "mxl_path": first(row, "mxl"),
        "pdf_path": first(row, "pdf"),
        "midi_path": midi_path,
        "audio_match_type": "deterministic_render_from_same_score_midi",
        "audio_render_recipe": (
            f'python scripts/render_audio.py --mid "$PDMX_ROOT/{safe_mid}" '
            f'--out "audio/{record_id}.wav" --soundfont "$SOUNDFONT"'
        ),
        "symbolic_match_guarantee": "exact_same_source_score_conversion",
        "subset_no_license_conflict": True,
        "subset_all_valid": True,
        "subset_deduplicated": True,
    }


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path, help="PDMX.csv")
    parser.add_argument("--output-dir", default=Path("data"), type=Path)
    parser.add_argument("--target", default=TARGET_DEFAULT, type=int)
    parser.add_argument("--source-md5", default="")
    args = parser.parse_args()

    if not args.input.is_file():
        parser.error(f"input file does not exist: {args.input}")
    if args.target < 1:
        parser.error("target must be positive")

    candidates: list[tuple[Classification, dict[str, str]]] = []
    rejection_counts: Counter[str] = Counter()
    source_rows = 0

    with args.input.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        required = {
            "path", "mxl", "pdf", "mid", "n_tracks", "tracks",
            "subset:no_license_conflict", "subset:all_valid",
        }
        missing = sorted(required - set(reader.fieldnames or []))
        if missing:
            raise RuntimeError(f"PDMX.csv is missing required columns: {missing}")

        for row in reader:
            source_rows += 1
            ok, reason = verify_source_row(row)
            if not ok:
                rejection_counts[reason] += 1
                continue
            c = classify(row)
            if c is None:
                rejection_counts["not_orchestral_or_too_small"] += 1
                continue
            candidates.append((c, dict(row)))

    # Stable ordering: confidence first, quality second, record id third.
    tier_rank = {"A": 0, "B": 1, "C": 2}
    candidates.sort(
        key=lambda item: (
            tier_rank[item[0].tier],
            -item[0].score,
            source_record_id(item[1]),
        )
    )

    # Defensive path-level deduplication in addition to PDMX's arrangement flag.
    unique: list[tuple[Classification, dict[str, str]]] = []
    seen_paths: set[str] = set()
    seen_ids: set[str] = set()
    for c, row in candidates:
        path = first(row, "path")
        rid = source_record_id(row)
        if path in seen_paths or rid in seen_ids:
            rejection_counts["defensive_duplicate"] += 1
            continue
        seen_paths.add(path)
        seen_ids.add(rid)
        unique.append((c, row))

    if len(unique) < args.target:
        class_counts = Counter(c.orchestra_class for c, _ in unique)
        tier_counts = Counter(c.tier for c, _ in unique)
        raise RuntimeError(
            "Not enough qualifying unique orchestral scores: "
            f"found={len(unique)}, target={args.target}, "
            f"classes={dict(class_counts)}, tiers={dict(tier_counts)}"
        )

    selected_pairs = unique[: args.target]
    selected = [
        build_output_row(row, c, index)
        for index, (c, row) in enumerate(selected_pairs, start=1)
    ]

    out = args.output_dir
    out.mkdir(parents=True, exist_ok=True)
    catalog_csv = out / f"orchestra_exact_{args.target}.csv"
    catalog_jsonl = out / f"orchestra_exact_{args.target}.jsonl"
    write_csv(catalog_csv, selected)
    write_jsonl(catalog_jsonl, selected)

    shard_dir = out / "shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    shard_size = 1000
    for start in range(0, len(selected), shard_size):
        shard = selected[start : start + shard_size]
        part = start // shard_size + 1
        write_csv(shard_dir / f"part-{part:05d}.csv", shard)

    custom_audio_rows = [row for row in selected if row["has_custom_audio"]]
    write_csv(out / "custom_audio_metadata_candidates.csv", custom_audio_rows)
    write_csv(out / "sample_100.csv", selected[:100])

    class_counts = Counter(str(row["orchestra_class"]) for row in selected)
    tier_counts = Counter(str(row["confidence_tier"]) for row in selected)
    family_counts: Counter[str] = Counter()
    for row in selected:
        family_counts.update(
            filter(None, str(row["instrument_families"]).split("|"))
        )

    stats = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": SOURCE_NAME,
        "source_doi": SOURCE_DOI,
        "source_record_url": SOURCE_RECORD_URL,
        "source_csv_expected_md5": SOURCE_CSV_MD5,
        "source_csv_observed_md5": args.source_md5 or None,
        "source_rows_scanned": source_rows,
        "qualifying_candidates_before_defensive_dedup": len(candidates),
        "qualifying_unique_candidates": len(unique),
        "selected_exact_matches": len(selected),
        "target": args.target,
        "selection_complete": len(selected) == args.target,
        "orchestra_class_counts": dict(sorted(class_counts.items())),
        "confidence_tier_counts": dict(sorted(tier_counts.items())),
        "instrument_family_counts": dict(sorted(family_counts.items())),
        "selected_with_custom_audio_metadata": len(custom_audio_rows),
        "rejection_counts": dict(sorted(rejection_counts.items())),
        "catalog_sha256": sha256_file(catalog_csv),
        "jsonl_sha256": sha256_file(catalog_jsonl),
        "definition": {
            "exact_match": (
                "PDF, MXL and MIDI converted from the same PDMX source score; "
                "audio rendered from that MIDI"
            ),
            "human_performance_claim": False,
            "license_policy": (
                "no-license-conflict + all-valid + deduplicated + "
                "non-paywalled + non-draft"
            ),
        },
    }
    (out / "stats.json").write_text(
        json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    checksums = []
    for path in sorted(out.rglob("*")):
        if path.is_file() and path.name != "SHA256SUMS":
            checksums.append(f"{sha256_file(path)}  {path.relative_to(out)}")
    (out / "SHA256SUMS").write_text(
        "\n".join(checksums) + "\n", encoding="utf-8"
    )

    print(json.dumps(stats, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except BrokenPipeError:
        sys.exit(1)
