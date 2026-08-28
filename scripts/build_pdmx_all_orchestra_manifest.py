#!/usr/bin/env python3
"""Enumerate PDMX full-score/MIDI records with tiered orchestra evidence."""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Mapping

SOURCE = "PDMX v9"
DOI = "10.5281/zenodo.15571083"
URL = "https://zenodo.org/records/15571083"
EXPECTED_MD5 = "30392ccf38bb63ce70e7afae70f9c88c"
TRUE = {"1", "true", "t", "yes", "y"}
NULL = {"", "nan", "na", "n/a", "none", "null"}

ORCH = (
    "orchestra", "orchestral", "orchestration", "symphony", "symphonic",
    "sinfonia", "sinfonietta", "philharmonic", "full score", "conductor score",
    "conducting score", "orchestral score", "orchestre", "orchester", "orquesta",
    "orquestra", "orkester", "orkiestra", "оркестр", "オーケストラ", "管弦楽",
    "交響曲", "오케스트라", "관현악", "교향곡", "총보",
)
STR_ORCH = ("string orchestra", "strings orchestra", "string ensemble", "streichorchester", "현악합주")
WIND_ORCH = ("wind orchestra", "wind ensemble", "concert band", "symphonic band", "symphonic winds", "吹奏楽", "관악합주")
STAGE = ("opera", "operetta", "oratorio", "cantata", "mass", "requiem", "ballet", "choral symphony", "symphonic poem", "tone poem")
REDUCTION = (
    "piano reduction", "piano score", "reduction for piano", "piano transcription",
    "piano arrangement", "solo piano", "piano solo", "piano duet", "four hands",
    "4 hands", "two pianos", "2 pianos", "vocal score", "piano-vocal",
    "piano vocal", "voice and piano", "voices and piano", "klavierauszug",
    "réduction pour piano", "lead sheet", "chord chart", "easy piano",
    "simplified piano", "a cappella", "acapella",
)
NON_ORCH_BAND = ("big band", "jazz band", "marching band", "pep band", "rock band", "pop band", "drum corps", "guitar orchestra")
PART_ONLY = ("individual part", "part only", "separate part", "extracted part", "orchestra part")
REQUIRED = {"path", "mxl", "pdf", "mid", "tracks", "n_tracks", "subset:no_license_conflict", "subset:all_valid"}
FIELDS = [
    "record_id", "source", "source_doi", "source_url", "title", "subtitle",
    "composer", "artist", "license", "license_url", "exactness_class",
    "orchestra_verification_level", "ensemble_class", "confidence_score",
    "classification_basis", "n_tracks", "gm_programs_0based",
    "gm_program_track_counts", "family_track_counts", "orchestral_track_count",
    "orchestral_track_ratio", "orchestral_family_count", "n_notes",
    "song_length_bars", "song_length_seconds", "has_lyrics", "has_custom_audio",
    "subset_deduplicated", "duplicate_group_id", "path", "mxl", "pdf", "mid",
]


def norm(v: object) -> str:
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def first(row: Mapping[str, str], *names: str) -> str:
    for name in names:
        value = norm(row.get(name, ""))
        if value and value.casefold() not in NULL:
            return value
    return ""


def yes(v: object) -> bool:
    return norm(v).casefold() in TRUE


def yes_first(row: Mapping[str, str], *names: str) -> bool:
    return next((yes(row[name]) for name in names if name in row), False)


def num(v: object, integer: bool = False) -> float | int:
    try:
        parsed = float(norm(v).replace(",", ""))
        if not math.isfinite(parsed):
            raise ValueError
        return int(parsed) if integer else parsed
    except (TypeError, ValueError):
        return 0 if integer else 0.0


def has(text: str, terms: tuple[str, ...]) -> bool:
    folded = text.casefold()
    return any(term.casefold() in folded for term in terms)


def programs(v: object) -> list[int]:
    return [int(x) for x in re.findall(r"(?<!\d)\d{1,3}(?!\d)", norm(v)) if 0 <= int(x) <= 127]


def family(p: int) -> str:
    if p <= 7: return "piano"
    if p <= 15: return "chromatic_percussion"
    if p <= 23: return "organ_keyboard"
    if p <= 31: return "guitar"
    if p <= 39: return "band_bass"
    if p <= 45 or 48 <= p <= 49: return "bowed_strings"
    if p == 46: return "harp"
    if p == 47: return "timpani"  # zero-based GM 48
    if p <= 51: return "synth_strings"
    if p <= 54: return "voice"
    if p == 55: return "orchestra_hit"
    if p <= 61: return "brass"
    if p <= 63: return "synth_brass"
    if p <= 67: return "saxophone"
    if p <= 79: return "woodwind"
    if p <= 103: return "synth"
    if p <= 111: return "ethnic"
    if p <= 119: return "orchestral_percussion"
    return "sound_effect"


def classify(row: Mapping[str, str]) -> tuple[dict[str, object] | None, str]:
    n_tracks = int(num(row.get("n_tracks"), True)); n_notes = int(num(row.get("n_notes"), True))
    bars = float(num(row.get("song_length.bars"))); seconds = float(num(row.get("song_length.seconds")))
    text = " | ".join(first(row, k) for k in ("song_name", "title", "subtitle", "genres", "groups", "tags")).casefold()
    if n_tracks < 4: return None, "too_few_tracks"
    if n_notes and n_notes < 120: return None, "too_few_notes"
    if bars and bars < 8: return None, "too_few_bars"
    if seconds and seconds < 15: return None, "too_short"
    if has(text, REDUCTION): return None, "reduction_or_piano_vocal_score"
    if has(text, PART_ONLY): return None, "individual_part"

    pc = Counter(programs(first(row, "tracks"))); fc = Counter()
    for p, count in pc.items(): fc[family(p)] += count
    strings, harp, timpani = fc["bowed_strings"], fc["harp"], fc["timpani"]
    ww, brass, sax = fc["woodwind"], fc["brass"], fc["saxophone"]
    perc = timpani + fc["chromatic_percussion"] + fc["orchestral_percussion"]
    voice = fc["voice"]; keys = fc["piano"] + fc["organ_keyboard"]
    guitar, bass = fc["guitar"], fc["band_bass"]
    orch_tracks = strings + harp + ww + brass + perc
    ratio = orch_tracks / max(n_tracks, 1)
    families = sum(v > 0 for v in (strings + harp, ww, brass, perc))
    explicit = has(text, ORCH); explicit_string = has(text, STR_ORCH); explicit_wind = has(text, WIND_ORCH)
    full_score = has(text, ("full score", "conductor score", "conducting score", "orchestral score", "总谱", "총보"))
    non_orch = has(text, NON_ORCH_BAND)
    band_dominant = guitar + bass >= max(3, n_tracks // 3)
    key_dominant = keys >= max(4, math.ceil(n_tracks * 0.55))

    def accept(level: str, cls: str, base: int, basis: str) -> tuple[dict[str, object], str]:
        score = base + (8 if full_score else 0) + (5 if explicit or explicit_string or explicit_wind else 0) + min(n_tracks, 30) // 3 + min(families, 4) * 2
        score -= (8 if non_orch else 0) + min(guitar + bass, 5) + (4 if key_dominant else 0)
        return {
            "level": level, "class": cls, "score": max(0, min(100, score)), "basis": basis,
            "pc": pc, "fc": fc, "orch_tracks": orch_tracks, "ratio": ratio, "families": families,
        }, "accepted"

    if n_tracks >= 9 and strings >= 3 and ww >= 1 and brass >= 1 and orch_tracks >= 7 and ratio >= .55 and not band_dominant and not non_orch:
        cls = "orchestra.full.vocal_stage" if voice and has(text, STAGE) else "orchestra.full.symphonic"
        return accept("strict", cls, 84, f"tracks={n_tracks};strings={strings};woodwind={ww};brass={brass};percussion={perc};ratio={ratio:.3f}")
    if n_tracks >= 5 and strings >= 4 and (strings + harp) / n_tracks >= .60 and ww + brass + sax == 0 and guitar == 0 and bass <= 1 and keys <= 1 and not non_orch:
        return accept("strict", "orchestra.string", 82, f"tracks={n_tracks};strings={strings};harp={harp};string_ratio={(strings+harp)/n_tracks:.3f}")
    if explicit_wind and n_tracks >= 8 and ww + sax >= 3 and brass >= 3 and guitar <= 1 and bass <= 1 and not has(text, ("jazz", "big band", "marching", "pep band")):
        return accept("strict", "orchestra.wind", 80, f"explicit wind ensemble;tracks={n_tracks};woodwind+sax={ww+sax};brass={brass};percussion={perc}")
    if voice and n_tracks >= 9 and strings >= 3 and ww >= 1 and brass >= 1 and ratio >= .45 and not band_dominant:
        return accept("strict", "orchestra.full.vocal_stage", 79, f"voice={voice};strings={strings};woodwind={ww};brass={brass}")
    if n_tracks >= 6 and strings >= 2 and families >= 2 and orch_tracks >= 5 and ratio >= .50 and guitar <= 1 and bass <= 1 and keys <= 2 and not non_orch:
        return accept("probable", "orchestra.chamber", 68, f"tracks={n_tracks};orchestral_tracks={orch_tracks};families={families};ratio={ratio:.3f}")
    if explicit and n_tracks >= 6 and orch_tracks >= 4 and families >= 2 and not non_orch and not band_dominant and not key_dominant:
        return accept("probable", "orchestra.explicit_metadata", 66, f"tracks={n_tracks};orchestral_tracks={orch_tracks};families={families}")
    if explicit_string and n_tracks >= 5 and strings >= 3 and guitar <= 1 and keys <= 2 and not non_orch:
        return accept("probable", "orchestra.string", 65, f"explicit string orchestra;tracks={n_tracks};strings={strings}")
    if explicit_wind and n_tracks >= 7 and ww + sax >= 2 and brass >= 2 and not has(text, ("jazz", "big band", "marching", "pep band")):
        return accept("probable", "orchestra.wind", 64, f"tracks={n_tracks};woodwind+sax={ww+sax};brass={brass}")
    if n_tracks >= 8 and orch_tracks >= 5 and families >= 2 and ratio >= .38 and guitar + bass <= max(2, n_tracks // 4) and keys <= max(3, n_tracks // 2) and not non_orch:
        return accept("candidate", "orchestra.large_palette_candidate", 50, f"tracks={n_tracks};orchestral_tracks={orch_tracks};families={families};ratio={ratio:.3f}")
    if explicit and n_tracks >= 5 and orch_tracks >= 3 and not non_orch and not band_dominant and not key_dominant:
        return accept("candidate", "orchestra.explicit_candidate", 48, f"explicit orchestra text;tracks={n_tracks};orchestral_tracks={orch_tracks}")
    if has(text, STAGE) and n_tracks >= 8 and strings >= 2 and orch_tracks >= 4 and families >= 2 and not key_dominant:
        return accept("candidate", "orchestra.vocal_stage_candidate", 46, f"stage work;tracks={n_tracks};voice={voice};orchestral_tracks={orch_tracks}")
    if full_score and n_tracks >= 6 and orch_tracks >= 2 and not non_orch and not band_dominant:
        return accept("candidate", "orchestra.full_score_text_candidate", 44, f"full-score text;tracks={n_tracks};orchestral_tracks={orch_tracks}")
    if non_orch: return None, "explicit_non_orchestral_band"
    if key_dominant: return None, "keyboard_dominant"
    if band_dominant: return None, "guitar_or_band_bass_dominant"
    return None, "insufficient_orchestra_evidence"


def source_ok(row: Mapping[str, str]) -> tuple[bool, str]:
    if not yes_first(row, "subset:no_license_conflict"): return False, "license_conflict_or_unknown"
    if not yes_first(row, "subset:all_valid"): return False, "not_all_formats_valid"
    if yes_first(row, "has_paywall"): return False, "paywalled"
    if yes_first(row, "is_draft"): return False, "draft"
    if not all(first(row, k) for k in ("path", "mxl", "pdf", "mid")): return False, "missing_required_path"
    return True, "ok"


def record(row: Mapping[str, str], d: Mapping[str, object]) -> dict[str, object]:
    path = first(row, "path"); stem = re.sub(r"[^a-z0-9]+", "", Path(path).stem.casefold())[:28]
    rid = f"pdmx-{stem}-" + hashlib.sha256(path.encode()).hexdigest()[:16]
    rep = first(row, "best_unique_arrangement", "best_arrangement", "best_path")
    group = "pdmx-group-" + hashlib.sha256(rep.encode()).hexdigest()[:20] if rep else rid
    pc: Counter[int] = d["pc"]  # type: ignore[assignment]
    fc: Counter[str] = d["fc"]  # type: ignore[assignment]
    return {
        "record_id": rid, "source": SOURCE, "source_doi": DOI, "source_url": URL,
        "title": first(row, "title", "song_name"), "subtitle": first(row, "subtitle"),
        "composer": first(row, "composer_name"), "artist": first(row, "artist_name"),
        "license": first(row, "license"), "license_url": first(row, "license_url"),
        "exactness_class": "same_symbolic_source_exact",
        "orchestra_verification_level": d["level"], "ensemble_class": d["class"],
        "confidence_score": d["score"], "classification_basis": d["basis"],
        "n_tracks": int(num(row.get("n_tracks"), True)), "gm_programs_0based": first(row, "tracks"),
        "gm_program_track_counts": json.dumps({str(k): pc[k] for k in sorted(pc)}, separators=(",", ":")),
        "family_track_counts": json.dumps({k: fc[k] for k in sorted(fc)}, separators=(",", ":")),
        "orchestral_track_count": d["orch_tracks"], "orchestral_track_ratio": f"{float(d['ratio']):.6f}",
        "orchestral_family_count": d["families"], "n_notes": int(num(row.get("n_notes"), True)),
        "song_length_bars": float(num(row.get("song_length.bars"))), "song_length_seconds": float(num(row.get("song_length.seconds"))),
        "has_lyrics": yes_first(row, "has_lyrics"), "has_custom_audio": yes_first(row, "has_custom_audio"),
        "subset_deduplicated": yes_first(row, "subset:deduplicated", "is_best_unique_arrangement"),
        "duplicate_group_id": group, "path": path, "mxl": first(row, "mxl"), "pdf": first(row, "pdf"), "mid": first(row, "mid"),
    }


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def write_gz(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="", compresslevel=9) as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader(); w.writerows(rows)


def shards(root: Path, rows: list[dict[str, object]], size: int) -> list[tuple[str, int, str]]:
    result = []
    for start in range(0, len(rows), size):
        path = root / f"part-{start // size + 1:05d}.csv.gz"; chunk = rows[start:start + size]
        write_gz(path, chunk); result.append((path.name, len(chunk), digest(path)))
    return result


def plain(path: Path, header: list[str], rows: list[tuple[object, ...]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(header); w.writerows(rows)


def build(src: Path, out: Path, minimum: int, shard_size: int, source_md5: str) -> dict[str, object]:
    accepted: list[dict[str, object]] = []; rejects: Counter[str] = Counter(); ids = set(); paths = set(); scanned = eligible = 0
    with src.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f); missing = REQUIRED - set(reader.fieldnames or [])
        if missing: raise RuntimeError(f"missing PDMX columns: {sorted(missing)}")
        for row in reader:
            scanned += 1; ok, reason = source_ok(row)
            if not ok: rejects[reason] += 1; continue
            eligible += 1; decision, reason = classify(row)
            if decision is None: rejects[reason] += 1; continue
            item = record(row, decision); rid, path = str(item["record_id"]), str(item["path"])
            if rid in ids or path in paths: rejects["defensive_duplicate_record"] += 1; continue
            ids.add(rid); paths.add(path); accepted.append(item)
    rank = {"strict": 0, "probable": 1, "candidate": 2}
    accepted.sort(key=lambda x: (rank[str(x["orchestra_verification_level"])], -int(x["confidence_score"]), 0 if x["subset_deduplicated"] else 1, str(x["record_id"])))
    if len(accepted) < minimum: raise RuntimeError(f"inclusive orchestra records {len(accepted)} < {minimum}; eligible={eligible}; rejects={dict(rejects)}")
    groups = {
        "all": accepted,
        "strict": [x for x in accepted if x["orchestra_verification_level"] == "strict"],
        "probable": [x for x in accepted if x["orchestra_verification_level"] == "probable"],
        "candidate": [x for x in accepted if x["orchestra_verification_level"] == "candidate"],
        "canonical": [x for x in accepted if x["subset_deduplicated"]],
    }
    out.mkdir(parents=True, exist_ok=True)
    for name, rows in groups.items():
        index = shards(out / ("all_records" if name == "all" else name), rows, shard_size)
        plain(out / f"{name}_shards.csv", ["file", "rows", "sha256"], index)
    levels = Counter(str(x["orchestra_verification_level"]) for x in accepted); classes = Counter(str(x["ensemble_class"]) for x in accepted)
    plain(out / "verification_level_counts.csv", ["level", "records", "fraction"], [(k, v, f"{v/len(accepted):.8f}") for k, v in sorted(levels.items())])
    plain(out / "ensemble_counts.csv", ["ensemble_class", "records", "fraction"], [(k, v, f"{v/len(accepted):.8f}") for k, v in classes.most_common()])
    write_gz(out / "sample_200.csv.gz", accepted[:200])
    summary = {
        "source": SOURCE, "source_doi": DOI, "source_url": URL,
        "source_csv_expected_md5": EXPECTED_MD5, "source_csv_observed_md5": source_md5 or None,
        "source_rows_scanned": scanned, "source_rows_rights_and_formats_eligible": eligible,
        "inclusive_orchestra_score_midi_records": len(accepted), "strict_records": len(groups["strict"]),
        "probable_records": len(groups["probable"]), "candidate_records": len(groups["candidate"]),
        "canonical_deduplicated_records": len(groups["canonical"]), "unique_record_ids": len(ids),
        "minimum_inclusive_required": minimum, "minimum_inclusive_passed": len(accepted) >= minimum,
        "verification_level_counts": dict(sorted(levels.items())), "ensemble_class_counts": dict(classes.most_common()),
        "rejection_counts": dict(rejects.most_common()),
        "exactness_definition": {"class": "same_symbolic_source_exact", "claim": "MXL, PDF and MIDI are associated exports of one PDMX source record", "human_performance_claim": False, "orchestra_membership": "tiered GM-program/metadata evidence; direct score review is separate"},
        "counting_policy": {"all": "distinct PDMX source records, including alternate arrangements/engravings", "canonical": "PDMX deduplicated subset", "strict": "strong automated orchestra evidence, not human staff-by-staff review"},
        "validation": {"passed": len(accepted) >= minimum and len(ids) == len(accepted) and len(paths) == len(accepted), "unique_ids": len(ids) == len(accepted), "unique_paths": len(paths) == len(accepted), "required_paths_present": True},
    }
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (out / "README.md").write_text(f"# PDMX v9 all-arrangement orchestra score–MIDI manifest\n\n- inclusive: **{len(accepted):,}**\n- strict: **{len(groups['strict']):,}**\n- probable: **{len(groups['probable']):,}**\n- candidate: **{len(groups['candidate']):,}**\n- canonical deduplicated: **{len(groups['canonical']):,}**\n\nEvery row has same-source MXL/PDF/MIDI provenance. Orchestra evidence tiers do not imply human review or a human recording.\n", encoding="utf-8")
    sums = [f"{digest(p)}  {p.relative_to(out)}" for p in sorted(out.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__); p.add_argument("--input", required=True, type=Path); p.add_argument("--output", required=True, type=Path)
    p.add_argument("--minimum-inclusive", type=int, default=10_000); p.add_argument("--shard-size", type=int, default=20_000); p.add_argument("--source-md5", default="")
    a = p.parse_args()
    if not a.input.is_file() or a.minimum_inclusive < 1 or a.shard_size < 1: p.error("valid input and positive limits are required")
    print(json.dumps(build(a.input, a.output, a.minimum_inclusive, a.shard_size, a.source_md5), ensure_ascii=False, indent=2, sort_keys=True)); return 0


if __name__ == "__main__":
    raise SystemExit(main())
