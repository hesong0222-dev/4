#!/usr/bin/env python3
"""Extract planner metadata directly from a canonical MIDI file.

No audio and no MIDI mutation. Simultaneous chord tones count as one attack for
speed estimation.
"""
from __future__ import annotations
import argparse, bisect, hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path
import apply_humanization_v2 as midi

def gm_family(program):
    p=int(program)
    if 0<=p<=23:return "keys"
    if 24<=p<=31:return "guitar"
    if 32<=p<=39:return "bass"
    if 40<=p<=51:return "strings"
    if 52<=p<=55:return "voice"
    if 56<=p<=63:return "brass"
    if 64<=p<=79:return "woodwind"
    if 80<=p<=111:return "synth"
    if 112<=p<=119:return "percussion"
    return "unknown"

def role_from_name(name,family):
    s=re.sub(r"[^a-z0-9]+","_",name.lower()).strip("_")
    checks=[("kick","kick"),("bass_drum","kick"),("snare","snare"),("clap","clap"),("hi_hat","hi_hat"),("hihat","hi_hat"),("ride","ride"),("tom","tom"),("crash","crash"),("electric_bass","electric_bass"),("synth_bass","synth_bass"),("acoustic_bass","acoustic_bass"),("electric_piano","electric_piano"),("rhodes","electric_piano"),("piano","piano"),("organ","organ"),("rhythm_guitar","rhythm_guitar"),("acoustic_guitar","acoustic_guitar"),("lead_guitar","lead_guitar"),("electric_guitar","electric_guitar"),("trumpet","trumpet"),("trombone","trombone"),("sax","sax"),("violin","violin"),("viola","viola"),("cello","cello"),("double_bass","double_bass")]
    for token,role in checks:
        if token in s:return role
    if family=="drums":return "drums_kit"
    if family=="keys":return "piano"
    return family

def programs_for_track(track):
    vals=[]
    for e in sorted(track["events"],key=lambda x:(x["orig_tick"],x["order"])):
        if e.get("kind")=="channel" and (e.get("status",0)&0xF0)==0xC0:vals.append(int(e["a"]))
    return vals

def peak_attack_density(groups,tpq,tempos):
    if not groups:return 0.0,0.0
    secs=[midi.tick_to_sec(t,tpq,tempos) for t in groups];mx=0.0
    for t in secs:mx=max(mx,float(bisect.bisect_right(secs,t+.5)-bisect.bisect_left(secs,t-.5)))
    return mx,len(secs)/max(secs[-1]-secs[0],1e-6)

def infer_family(track,notes):
    channels=Counter(n["channel"] for n in notes)
    if channels and channels[9]>=sum(channels.values())*.5:return "drums"
    name=track["name"].lower();keyword=[("drum","drums"),("percussion","drums"),("bass","bass"),("guitar","guitar"),("piano","keys"),("keyboard","keys"),("rhodes","keys"),("organ","keys"),("violin","strings"),("viola","strings"),("cello","strings"),("string","strings"),("trumpet","brass"),("trombone","brass"),("horn","brass"),("sax","woodwind"),("flute","woodwind"),("clarinet","woodwind"),("oboe","woodwind"),("bassoon","woodwind"),("choir","voice"),("vocal","voice"),("voice","voice"),("synth","synth")]
    for k,f in keyword:
        if k in name:return f
    ps=programs_for_track(track)
    if ps:return Counter(gm_family(p) for p in ps).most_common(1)[0][0]
    return "unknown"

def main():
    ap=argparse.ArgumentParser();ap.add_argument("input_midi",type=Path);ap.add_argument("-o","--output",type=Path,required=True);ap.add_argument("--work-id");ap.add_argument("--arrangement-id");ap.add_argument("--genre",default="unknown");ap.add_argument("--ensemble",default="unknown");args=ap.parse_args()
    parsed=midi.parse_midi(args.input_midi);notes_by_track=defaultdict(list)
    for n in parsed["notes"]:notes_by_track[n["track"]].append(n)
    tracks=[]
    for tr in parsed["tracks"]:
        ns=notes_by_track.get(tr["index"],[])
        if not ns:continue
        fam=infer_family(tr,ns);role=role_from_name(tr["name"],fam);groups=sorted({n["start_tick"] for n in ns});peak,avg=peak_attack_density(groups,parsed["tpq"],parsed["tempos"]);channels=sorted({n["channel"] for n in ns});programs=sorted(set(programs_for_track(tr)))
        tracks.append({"id":tr["name"] or f"track_{tr['index']}","track_index":tr["index"],"track_name":tr["name"],"family":fam,"role":role,"midi_channels":channels,"gm_programs":programs,"note_count":len(ns),"distinct_attack_count":len(groups),"peak_attacks_per_second":round(peak,4),"average_attacks_per_second":round(avg,4)})
    raw=args.input_midi.read_bytes();sha=hashlib.sha256(raw).hexdigest();obj={"schema":"humanization-planner-input-2026-08-28.1","source_midi":str(args.input_midi),"source_midi_sha256":sha,"work_id":args.work_id or f"midi_{sha[:20]}","arrangement_id":args.arrangement_id or f"arr_{sha[:20]}","genre":args.genre,"ensemble":args.ensemble,"speed_metric":"distinct canonical attack/onset groups per second; simultaneous chord tones count once","tracks":tracks,"sections":[{"id":"whole_song","type":"unknown","start_tick":0,"end_tick":max((n["end_tick"] for n in parsed["notes"]),default=0)}],"render_audio_enabled":False}
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps({"tracks":len(tracks),"notes":len(parsed["notes"]),"audio_rendered":False},indent=2))
if __name__=="__main__":main()
