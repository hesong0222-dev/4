#!/usr/bin/env python3
"""Create deterministic per-song/per-track expression plans.

This tool is plan-only: it does not modify MIDI and does not render audio.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path

POLICY_VERSION = "adaptive-humanization-2026-08-28.1"

LEVELS = [
    ("NONE_OR_TIGHT", 0.15, (0.02, 0.16)),
    ("SUBTLE", 0.30, (0.16, 0.38)),
    ("MODERATE", 0.35, (0.38, 0.68)),
    ("STRONG", 0.15, (0.68, 0.92)),
    ("EXPERIMENTAL", 0.05, (0.90, 1.15)),
]

FAMILY = {
    "drums":   {"p": .96, "timing": (.35,.85), "velocity": (.35,.90), "duration": (.00,.10)},
    "bass":    {"p": .92, "timing": (.30,.75), "velocity": (.25,.70), "duration": (.15,.60)},
    "guitar":  {"p": .86, "timing": (.25,.72), "velocity": (.20,.70), "duration": (.15,.55)},
    "keys":    {"p": .84, "timing": (.20,.65), "velocity": (.20,.68), "duration": (.12,.55)},
    "strings": {"p": .72, "timing": (.12,.48), "velocity": (.18,.62), "duration": (.18,.60)},
    "brass":   {"p": .78, "timing": (.16,.55), "velocity": (.25,.75), "duration": (.15,.52)},
    "woodwind":{"p": .72, "timing": (.14,.50), "velocity": (.20,.66), "duration": (.18,.58)},
    "voice":   {"p": .62, "timing": (.12,.45), "velocity": (.15,.55), "duration": (.18,.60)},
    "synth":   {"p": .70, "timing": (.10,.48), "velocity": (.08,.48), "duration": (.12,.52)},
    "unknown": {"p": .55, "timing": (.10,.38), "velocity": (.10,.45), "duration": (.08,.35)},
}

ROLE = {
    "kick":          {"anchor":"RHYTHM_CORE", "timing_scale":.70, "tendency":["centered","slightly_ahead"]},
    "snare":         {"anchor":"BACKBEAT",    "timing_scale":.90, "tendency":["laid_back","centered"]},
    "clap":          {"anchor":"BACKBEAT",    "timing_scale":.90, "tendency":["laid_back","centered"]},
    "hi_hat":        {"anchor":"TIMEKEEPERS", "timing_scale":.82, "tendency":["centered","slightly_ahead"]},
    "ride":          {"anchor":"TIMEKEEPERS", "timing_scale":.82, "tendency":["centered","slightly_ahead"]},
    "electric_bass": {"anchor":"RHYTHM_CORE"},
    "acoustic_bass": {"anchor":"RHYTHM_CORE"},
    "synth_bass":    {"anchor":"RHYTHM_CORE"},
    "piano":         {"anchor":"COMPING"},
    "electric_piano": {"anchor":"COMPING"},
    "organ":         {"anchor":"COMPING", "velocity_scale":.55},
    "rhythm_guitar": {"anchor":"COMPING", "spread":(.25,.85)},
    "acoustic_guitar":{"anchor":"COMPING", "spread":(.40,1.00)},
    "electric_guitar":{"anchor":"COMPING", "spread":(.15,.65)},
    "lead_guitar":   {"anchor":"LEAD_FOLLOW", "spread":(.00,.25)},
    "trumpet":       {"anchor":"HORN_SECTION"},
    "trombone":      {"anchor":"HORN_SECTION"},
    "sax":           {"anchor":"HORN_SECTION"},
    "violin":        {"anchor":"STRING_SECTION"},
    "viola":         {"anchor":"STRING_SECTION"},
    "cello":         {"anchor":"STRING_SECTION"},
    "double_bass":   {"anchor":"STRING_SECTION"},
}

TEMPLATES = {
    "funk": ["FUNK_16","POCKET","LIGHT_HUMAN"],
    "soul": ["POCKET","LAID_BACK_LIGHT","FUNK_16"],
    "rnb": ["LAID_BACK_LIGHT","POCKET","MPC_16_B"],
    "gospel": ["POCKET","FUNK_16","LAID_BACK_LIGHT"],
    "jazz": ["SWING_54","SWING_58","SWING_62","POCKET"],
    "blues": ["SHUFFLE_8","SWING_58","LAID_BACK_LIGHT"],
    "rock": ["PUSH_LIGHT","STRAIGHT_TIGHT","LIGHT_HUMAN"],
    "punk": ["PUSH_LIGHT","STRAIGHT_TIGHT"],
    "metal": ["STRAIGHT_TIGHT","PUSH_LIGHT","LIGHT_HUMAN"],
    "pop": ["LIGHT_HUMAN","POCKET","PUSH_CHORUS","STRAIGHT_TIGHT"],
    "hiphop": ["MPC_16_A","MPC_16_B","LAID_BACK_HEAVY","POCKET"],
    "electronic": ["STRAIGHT_TIGHT","MPC_16_A","MPC_16_B","LIGHT_HUMAN"],
    "worship": ["LIGHT_HUMAN","POCKET","LAID_BACK_LIGHT","PUSH_CHORUS"],
    "classical": ["ORCHESTRA_LOOSE","LIGHT_HUMAN","STRAIGHT_TIGHT"],
    "orchestra": ["ORCHESTRA_LOOSE","LIGHT_HUMAN"],
    "unknown": ["LIGHT_HUMAN","STRAIGHT_TIGHT","POCKET","PUSH_LIGHT","LAID_BACK_LIGHT"],
}

SECTION = {
    "intro":(.70,.90), "verse":(.85,1.00), "pre_chorus":(.95,1.05),
    "chorus":(1.00,1.15), "bridge":(.85,1.10), "solo":(.95,1.15),
    "breakdown":(.65,.90), "outro":(.70,1.00), "unknown":(.88,1.05),
}

def stable_seed(*parts):
    raw = "\x1f".join(map(str, parts)).encode()
    return int.from_bytes(hashlib.sha256(raw).digest()[:8], "big")

def weighted_level(rng):
    x = rng.random()
    total = 0.0
    for name, p, bounds in LEVELS:
        total += p
        if x <= total:
            return name, bounds
    return LEVELS[-1][0], LEVELS[-1][2]

def speed_scale(nps):
    if nps < 4: return 1.0
    if nps < 8: return .75
    if nps < 12: return .45
    if nps < 16: return .25
    return .125

def family_name(track):
    f = str(track.get("family") or "unknown").lower().replace("keyboard","keys")
    if f == "woodwinds": f = "woodwind"
    if f == "string": f = "strings"
    return f if f in FAMILY else "unknown"

def dominant_genre(meta):
    probs = meta.get("genre_probs") or {}
    if probs:
        return str(max(probs.items(), key=lambda kv: float(kv[1]))[0]).lower()
    return str(meta.get("genre") or "unknown").lower()

def build_track(track, song_strength, song_seed):
    tid = str(track.get("id") or track.get("name") or "track")
    fam = family_name(track)
    role = str(track.get("role") or fam).lower().replace(" ","_")
    rng = random.Random(stable_seed(song_seed, tid, role))
    base = FAMILY[fam]
    override = ROLE.get(role,{})
    enabled = rng.random() < float(base["p"])
    nps = float(track.get("peak_notes_per_second") or 0.0)
    ss = speed_scale(nps)
    timing = rng.uniform(*base["timing"]) * song_strength * ss * float(override.get("timing_scale",1.0))
    velocity = rng.uniform(*base["velocity"]) * song_strength * float(override.get("velocity_scale",1.0))
    duration = rng.uniform(*base["duration"]) * song_strength
    spread = rng.uniform(*override.get("spread",(0.0,.35 if fam in {"keys","guitar","strings","brass"} else 0.0))) * song_strength * max(.25,ss)
    tendencies = override.get("tendency", ["centered","slightly_ahead","slightly_behind"])
    if not enabled:
        timing *= .05; velocity *= .05; duration *= .05; spread *= .05
        tendencies = ["centered"]
    return {
        "track_id":tid, "family":fam, "role":role, "enabled":enabled,
        "player_seed":stable_seed(song_seed,tid,"player"),
        "timing_tendency":rng.choice(tendencies),
        "timing_strength":round(min(timing,1.15),4),
        "velocity_strength":round(min(velocity,1.15),4),
        "duration_strength":round(min(duration,1.0),4),
        "chord_spread_strength":round(min(spread,1.0),4),
        "anchor_group":override.get("anchor","NONE"),
        "peak_notes_per_second":nps,
        "fast_passage_timing_multiplier":ss,
        "content_changing_ornaments_enabled":False
    }

def build_plan(meta, seed=None):
    work = str(meta.get("work_id") or "unknown_work")
    arr = str(meta.get("arrangement_id") or "unknown_arrangement")
    seed = int(seed) if seed is not None else stable_seed(work,arr,POLICY_VERSION)
    rng = random.Random(seed)
    level,bounds = weighted_level(rng)
    strength = rng.uniform(*bounds)
    genre = dominant_genre(meta)
    ensemble = str(meta.get("ensemble") or "unknown").lower()
    template_key = "orchestra" if ensemble in {"orchestra","chamber","concert_band"} else genre
    template = rng.choice(TEMPLATES.get(template_key,TEMPLATES["unknown"]))
    if level == "NONE_OR_TIGHT": template = rng.choice(["STRAIGHT_TIGHT","LIGHT_HUMAN"])
    sections=[]
    for i,s in enumerate(meta.get("sections") or [{"id":"whole_song","type":"unknown"}]):
        stype=str(s.get("type") or "unknown").lower().replace("-","_")
        lo,hi=SECTION.get(stype,SECTION["unknown"])
        sections.append({"id":str(s.get("id") or f"section_{i}"),"type":stype,"strength_multiplier":round(rng.uniform(lo,hi),4)})
    tracks=[build_track(t,strength,seed) for t in meta.get("tracks") or []]
    groups={}
    for t in tracks:
        if t["anchor_group"] != "NONE": groups.setdefault(t["anchor_group"],[]).append(t["track_id"])
    groups={g:ids for g,ids in groups.items() if len(ids)>1}
    for t in tracks:
        if t["anchor_group"] not in groups: t["anchor_group"]="NONE"
    return {
        "policy_version":POLICY_VERSION,
        "status":"RENDER_HOLD_PLAN_ONLY",
        "render_audio_enabled":False,
        "work_id":work,"arrangement_id":arr,"song_seed":seed,
        "genre":genre,"ensemble":ensemble,
        "groove_enabled": strength > .10,
        "global_level":level,"template":template,"global_strength":round(strength,4),
        "sections":sections,"anchor_groups":groups,"tracks":tracks,
        "macro_tempo_warp":{"enabled":False,"reason":"separate gated feature"},
        "clean_tier_constraints":{
            "target_is_original_canonical_midi":True,
            "pitch_identity_must_match":True,
            "note_count_must_match":True,
            "event_order_must_not_reverse":True,
            "content_changing_ornaments_enabled":False
        }
    }

def self_test():
    meta={"work_id":"w","arrangement_id":"a","genre":"funk","ensemble":"band","tracks":[
        {"id":"kick","family":"drums","role":"kick","peak_notes_per_second":4},
        {"id":"bass","family":"bass","role":"electric_bass","peak_notes_per_second":8}]}
    a=build_plan(meta,1234); b=build_plan(meta,1234)
    assert a==b and not a["render_audio_enabled"]
    assert a["clean_tier_constraints"]["target_is_original_canonical_midi"]
    assert "RHYTHM_CORE" in a["anchor_groups"]
    print(json.dumps(a,ensure_ascii=False,indent=2,sort_keys=True))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("input",nargs="?",type=Path)
    ap.add_argument("-o","--output",type=Path)
    ap.add_argument("--seed",type=int)
    ap.add_argument("--self-test",action="store_true")
    args=ap.parse_args()
    if args.self_test: self_test(); return
    if not args.input: ap.error("input JSON required unless --self-test")
    plan=build_plan(json.loads(args.input.read_text(encoding="utf-8")),args.seed)
    text=json.dumps(plan,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True); args.output.write_text(text,encoding="utf-8")
    else: print(text,end="")

if __name__=="__main__": main()
