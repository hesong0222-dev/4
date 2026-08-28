#!/usr/bin/env python3
"""Create deterministic per-song/per-track expression plans.

Plan-only. It never modifies MIDI and never renders audio.
When empirical calibration is available, GMD drum and ASAP piano statistics
replace the corresponding provisional execution budgets. Other instruments
remain explicitly provisional until direct performance evidence is added.
"""
from __future__ import annotations
import argparse, hashlib, json, random
from pathlib import Path

POLICY_VERSION = "adaptive-humanization-2026-08-28.2-empirical"
DEFAULT_CALIBRATION = Path("data/calibration/humanization-empirical-20260828/humanization_empirical_calibration.json")
LEVELS=[("NONE_OR_TIGHT",.15,(.02,.16)),("SUBTLE",.30,(.16,.38)),("MODERATE",.35,(.38,.68)),("STRONG",.15,(.68,.92)),("EXPERIMENTAL",.05,(.90,1.15))]
FAMILY={
 "drums":{"p":.96,"timing":(.35,.85),"velocity":(.35,.90),"duration":(.00,.10)},
 "bass":{"p":.92,"timing":(.30,.75),"velocity":(.25,.70),"duration":(.15,.60)},
 "guitar":{"p":.86,"timing":(.25,.72),"velocity":(.20,.70),"duration":(.15,.55)},
 "keys":{"p":.84,"timing":(.20,.65),"velocity":(.20,.68),"duration":(.12,.55)},
 "strings":{"p":.72,"timing":(.12,.48),"velocity":(.18,.62),"duration":(.18,.60)},
 "brass":{"p":.78,"timing":(.16,.55),"velocity":(.25,.75),"duration":(.15,.52)},
 "woodwind":{"p":.72,"timing":(.14,.50),"velocity":(.20,.66),"duration":(.18,.58)},
 "voice":{"p":.62,"timing":(.12,.45),"velocity":(.15,.55),"duration":(.18,.60)},
 "synth":{"p":.70,"timing":(.10,.48),"velocity":(.08,.48),"duration":(.12,.52)},
 "unknown":{"p":.55,"timing":(.10,.38),"velocity":(.10,.45),"duration":(.08,.35)}}
ROLE={
 "kick":{"anchor":"RHYTHM_CORE","timing_scale":.70,"tendency":["centered","slightly_ahead"]},
 "snare":{"anchor":"BACKBEAT","timing_scale":.90,"tendency":["laid_back","centered"]},
 "clap":{"anchor":"BACKBEAT","timing_scale":.90,"tendency":["laid_back","centered"]},
 "hi_hat":{"anchor":"TIMEKEEPERS","timing_scale":.82,"tendency":["centered","slightly_ahead"]},
 "hihat":{"anchor":"TIMEKEEPERS","timing_scale":.82,"tendency":["centered","slightly_ahead"]},
 "ride":{"anchor":"TIMEKEEPERS","timing_scale":.82,"tendency":["centered","slightly_ahead"]},
 "tom":{"anchor":"NONE"},"crash":{"anchor":"NONE"},
 "electric_bass":{"anchor":"RHYTHM_CORE"},"acoustic_bass":{"anchor":"RHYTHM_CORE"},"synth_bass":{"anchor":"RHYTHM_CORE"},
 "piano":{"anchor":"COMPING"},"electric_piano":{"anchor":"COMPING"},"organ":{"anchor":"COMPING","velocity_scale":.55},
 "rhythm_guitar":{"anchor":"COMPING","spread":(.25,.85)},"acoustic_guitar":{"anchor":"COMPING","spread":(.40,1.00)},
 "electric_guitar":{"anchor":"COMPING","spread":(.15,.65)},"lead_guitar":{"anchor":"LEAD_FOLLOW","spread":(.00,.25)},
 "trumpet":{"anchor":"HORN_SECTION"},"trombone":{"anchor":"HORN_SECTION"},"sax":{"anchor":"HORN_SECTION"},
 "violin":{"anchor":"STRING_SECTION"},"viola":{"anchor":"STRING_SECTION"},"cello":{"anchor":"STRING_SECTION"},"double_bass":{"anchor":"STRING_SECTION"}}
TEMPLATES={
 "funk":["FUNK_16","POCKET","LIGHT_HUMAN"],"soul":["POCKET","LAID_BACK_LIGHT","FUNK_16"],"rnb":["LAID_BACK_LIGHT","POCKET","MPC_16_B"],
 "gospel":["POCKET","FUNK_16","LAID_BACK_LIGHT"],"jazz":["SWING_54","SWING_58","SWING_62","POCKET"],"blues":["SHUFFLE_8","SWING_58","LAID_BACK_LIGHT"],
 "rock":["PUSH_LIGHT","STRAIGHT_TIGHT","LIGHT_HUMAN"],"punk":["PUSH_LIGHT","STRAIGHT_TIGHT"],"metal":["STRAIGHT_TIGHT","PUSH_LIGHT","LIGHT_HUMAN"],
 "pop":["LIGHT_HUMAN","POCKET","PUSH_CHORUS","STRAIGHT_TIGHT"],"hiphop":["MPC_16_A","MPC_16_B","LAID_BACK_HEAVY","POCKET"],
 "electronic":["STRAIGHT_TIGHT","MPC_16_A","MPC_16_B","LIGHT_HUMAN"],"worship":["LIGHT_HUMAN","POCKET","LAID_BACK_LIGHT","PUSH_CHORUS"],
 "classical":["ORCHESTRA_LOOSE","LIGHT_HUMAN","STRAIGHT_TIGHT"],"orchestra":["ORCHESTRA_LOOSE","LIGHT_HUMAN"],
 "unknown":["LIGHT_HUMAN","STRAIGHT_TIGHT","POCKET","PUSH_LIGHT","LAID_BACK_LIGHT"]}
SECTION={"intro":(.70,.90),"verse":(.85,1.00),"pre_chorus":(.95,1.05),"chorus":(1.00,1.15),"bridge":(.85,1.10),"solo":(.95,1.15),"breakdown":(.65,.90),"outro":(.70,1.00),"unknown":(.88,1.05)}
UNCALIBRATED_FAMILIES={"bass","guitar","strings","brass","woodwind","voice","synth","unknown"}

def stable_seed(*parts): return int.from_bytes(hashlib.sha256("\x1f".join(map(str,parts)).encode()).digest()[:8],"big")
def weighted_level(rng):
 x=rng.random(); total=0
 for n,p,b in LEVELS:
  total+=p
  if x<=total:return n,b
 return LEVELS[-1][0],LEVELS[-1][2]
def legacy_speed_scale(nps):
 if nps<4:return 1.0
 if nps<8:return .75
 if nps<12:return .45
 if nps<16:return .25
 return .125
def density_bin(nps):
 if nps<4:return "lt4"
 if nps<8:return "4_8"
 if nps<12:return "8_12"
 if nps<16:return "12_16"
 return "ge16"
def empirical_speed_scale(aps,cal):
 piano=(cal or {}).get("piano",{}); scales=piano.get("timing_scale_by_density",{})
 if scales:
  # empirical residual variance is useful, but an ordering-safety cap must still
  # tighten genuinely fast passages. Never let empirical noise increase at >8 attacks/s.
  empirical=float(scales.get(density_bin(aps),1.0))
  safety=1.0 if aps<8 else (.72 if aps<12 else .50 if aps<16 else .32)
  return max(.12,min(1.0,empirical,safety))
 return legacy_speed_scale(aps)
def family_name(track):
 f=str(track.get("family") or "unknown").lower().replace("keyboard","keys")
 if f=="woodwinds":f="woodwind"
 if f=="string":f="strings"
 return f if f in FAMILY else "unknown"
def dominant_genre(meta):
 probs=meta.get("genre_probs") or {}
 if probs:return str(max(probs.items(),key=lambda kv:float(kv[1]))[0]).lower()
 return str(meta.get("genre") or "unknown").lower()
def load_calibration(path):
 if not path:return None
 p=Path(path)
 if not p.exists():return None
 c=json.loads(p.read_text(encoding="utf-8"))
 if c.get("render_audio_enabled") is not False: raise ValueError("calibration must preserve render HOLD")
 return c

def empirical_role(role,fam,cal,song_strength,speed_multiplier):
 if not cal:return {"calibrated":False}
 if fam=="drums":
  key={"hi_hat":"hihat","clap":"snare"}.get(role,role); d=cal.get("drums",{}).get(key)
  if d:
   # GMD global grid medians include actual style/swing structure. Preserve them as
   # evidence but do not blindly shift every genre by the global median.
   return {"calibrated":True,"source":"GMD","evidence":d.get("evidence"),
     "raw_grid_center_ms":round(float(d["timing_median_ms"]),4),
     "timing_mad_ms":round(float(d["timing_mad_ms"]),4),
     "timing_budget_mad_ms":round(float(d["timing_mad_ms"])*song_strength*speed_multiplier,4),
     "timing_hard_cap_ms":round(float(d["timing_p90_abs_proxy_ms"])*max(.25,song_strength)*speed_multiplier,4),
     "velocity_median":d.get("velocity_median"),"velocity_mad":d.get("velocity_mad")}
 if fam=="keys" and role in {"piano","electric_piano","keys"}:
  p=cal.get("piano",{}); t=p.get("microtiming_residual_ms",{}); cs=p.get("chord_spread_ms",{}); v=p.get("velocity",{}); g=p.get("gate_ratio",{})
  if t.get("n",0):
   return {"calibrated":True,"source":"ASAP","evidence":p.get("evidence"),
    "timing_center_ms":round(float(t.get("median",0)),4),"timing_mad_ms":round(float(t.get("mad",0)),4),
    "timing_budget_mad_ms":round(float(t.get("mad",0))*song_strength*speed_multiplier,4),
    "timing_hard_cap_ms":round(max(abs(float(t.get("p10",0))),abs(float(t.get("p90",0))))*max(.25,song_strength)*speed_multiplier,4),
    "chord_spread_ms":{"median":cs.get("median"),"p75":cs.get("p75"),"p90":cs.get("p90")},
    "velocity":{"median":v.get("median"),"mad":v.get("mad"),"p10":v.get("p10"),"p90":v.get("p90")},
    "gate_ratio":{"median":g.get("median"),"p25":g.get("p25"),"p75":g.get("p75"),"p90":g.get("p90")}}
 return {"calibrated":False,"reason":"no direct calibrated performance evidence for this role"}

def build_track(track,song_strength,song_seed,cal):
 tid=str(track.get("id") or track.get("name") or "track"); fam=family_name(track); role=str(track.get("role") or fam).lower().replace(" ","_"); rng=random.Random(stable_seed(song_seed,tid,role)); base=FAMILY[fam]; override=ROLE.get(role,{})
 enabled=rng.random()<float(base["p"])
 aps=float(track.get("peak_attacks_per_second") or track.get("peak_onsets_per_second") or track.get("peak_notes_per_second") or 0.0)
 ss=empirical_speed_scale(aps,cal)
 timing=rng.uniform(*base["timing"])*song_strength*ss*float(override.get("timing_scale",1)); velocity=rng.uniform(*base["velocity"])*song_strength*float(override.get("velocity_scale",1)); duration=rng.uniform(*base["duration"])*song_strength
 spread=rng.uniform(*override.get("spread",(0,.35 if fam in {"keys","guitar","strings","brass"} else 0)))*song_strength*max(.25,ss); tendencies=override.get("tendency",["centered","slightly_ahead","slightly_behind"])
 if not enabled: timing*=.05;velocity*=.05;duration*=.05;spread*=.05;tendencies=["centered"]
 emp=empirical_role(role,fam,cal,song_strength,ss)
 return {"track_id":tid,"family":fam,"role":role,"enabled":enabled,"player_seed":stable_seed(song_seed,tid,"player"),"timing_tendency":rng.choice(tendencies),
  "timing_strength":round(min(timing,1.15),4),"velocity_strength":round(min(velocity,1.15),4),"duration_strength":round(min(duration,1),4),"chord_spread_strength":round(min(spread,1),4),
  "anchor_group":override.get("anchor","NONE"),"peak_attacks_per_second":aps,"fast_passage_timing_multiplier":round(ss,4),"empirical_execution":emp,
  "calibration_status":"EMPIRICAL" if emp.get("calibrated") else "PROVISIONAL","content_changing_ornaments_enabled":False}

def build_plan(meta,seed=None,calibration=None,calibration_path=None):
 work=str(meta.get("work_id") or "unknown_work");arr=str(meta.get("arrangement_id") or "unknown_arrangement");seed=int(seed) if seed is not None else stable_seed(work,arr,POLICY_VERSION);rng=random.Random(seed);level,bounds=weighted_level(rng);strength=rng.uniform(*bounds);genre=dominant_genre(meta);ensemble=str(meta.get("ensemble") or "unknown").lower();template_key="orchestra" if ensemble in {"orchestra","chamber","concert_band"} else genre;template=rng.choice(TEMPLATES.get(template_key,TEMPLATES["unknown"]));
 if level=="NONE_OR_TIGHT":template=rng.choice(["STRAIGHT_TIGHT","LIGHT_HUMAN"])
 sections=[]
 for i,s in enumerate(meta.get("sections") or [{"id":"whole_song","type":"unknown"}]):
  stype=str(s.get("type") or "unknown").lower().replace("-","_");lo,hi=SECTION.get(stype,SECTION["unknown"]);sections.append({"id":str(s.get("id") or f"section_{i}"),"type":stype,"strength_multiplier":round(rng.uniform(lo,hi),4)})
 tracks=[build_track(t,strength,seed,calibration) for t in meta.get("tracks") or []];groups={}
 for t in tracks:
  if t["anchor_group"]!="NONE":groups.setdefault(t["anchor_group"],[]).append(t["track_id"])
 groups={g:ids for g,ids in groups.items() if len(ids)>1}
 for t in tracks:
  if t["anchor_group"] not in groups:t["anchor_group"]="NONE"
 return {"policy_version":POLICY_VERSION,"status":"RENDER_HOLD_PLAN_ONLY","render_audio_enabled":False,"work_id":work,"arrangement_id":arr,"song_seed":seed,"genre":genre,"ensemble":ensemble,"groove_enabled":strength>.10,"global_level":level,"template":template,"global_strength":round(strength,4),"sections":sections,"anchor_groups":groups,"tracks":tracks,
  "calibration":{"used":bool(calibration),"version":(calibration or {}).get("calibration_version"),"path":str(calibration_path) if calibration_path else None,"automatic_roles":["drums.*","keys.piano"] if calibration else [],"still_provisional_families":sorted(UNCALIBRATED_FAMILIES)},
  "speed_metric":"peak distinct attack/onset groups per second; simultaneous chord tones count once","macro_tempo_warp":{"enabled":False,"reason":"separate gated feature"},
  "clean_tier_constraints":{"target_is_original_canonical_midi":True,"pitch_identity_must_match":True,"note_count_must_match":True,"event_order_must_not_reverse":True,"content_changing_ornaments_enabled":False}}

def self_test():
 fake={"calibration_version":"test","render_audio_enabled":False,"drums":{"kick":{"timing_median_ms":-5,"timing_mad_ms":10,"timing_p90_abs_proxy_ms":30,"velocity_median":80,"velocity_mad":8,"evidence":"REAL_CAPTURED_MIDI"}},"piano":{"evidence":"REAL_SCORE_ALIGNED_PERFORMANCE_MIDI","timing_scale_by_density":{"lt4":1,"4_8":.9,"8_12":.7,"12_16":.5,"ge16":.3},"microtiming_residual_ms":{"n":100,"median":0,"mad":8,"p10":-20,"p90":20},"chord_spread_ms":{"median":12,"p75":24,"p90":40},"velocity":{"median":67,"mad":12,"p10":40,"p90":90},"gate_ratio":{"median":.7,"p25":.4,"p75":1,"p90":1.3}}}
 meta={"work_id":"w","arrangement_id":"a","genre":"funk","ensemble":"band","tracks":[{"id":"kick","family":"drums","role":"kick","peak_attacks_per_second":4},{"id":"piano","family":"keys","role":"piano","peak_attacks_per_second":18},{"id":"bass","family":"bass","role":"electric_bass","peak_attacks_per_second":9}]}
 a=build_plan(meta,1234,fake,"fake.json");b=build_plan(meta,1234,fake,"fake.json");assert a==b and not a["render_audio_enabled"] and "RHYTHM_CORE" in a["anchor_groups"];assert a["tracks"][0]["calibration_status"]=="EMPIRICAL";assert a["tracks"][1]["fast_passage_timing_multiplier"]<=.32;assert a["tracks"][2]["calibration_status"]=="PROVISIONAL";print(json.dumps(a,ensure_ascii=False,indent=2,sort_keys=True))
def main():
 ap=argparse.ArgumentParser();ap.add_argument("input",nargs="?",type=Path);ap.add_argument("-o","--output",type=Path);ap.add_argument("--seed",type=int);ap.add_argument("--calibration",type=Path,default=DEFAULT_CALIBRATION);ap.add_argument("--no-calibration",action="store_true");ap.add_argument("--self-test",action="store_true");args=ap.parse_args()
 if args.self_test:self_test();return
 if not args.input:ap.error("input JSON required unless --self-test")
 cal=None if args.no_calibration else load_calibration(args.calibration);plan=build_plan(json.loads(args.input.read_text(encoding="utf-8")),args.seed,cal,None if args.no_calibration else args.calibration);text=json.dumps(plan,ensure_ascii=False,indent=2,sort_keys=True)+"\n"
 if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text,encoding="utf-8")
 else:print(text,end="")
if __name__=="__main__":main()
