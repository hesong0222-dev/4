#!/usr/bin/env python3
"""Apply a deterministic, plan-driven humanization transform to a MIDI copy.

This tool is MIDI-only. It never renders audio and never changes the canonical
source MIDI. The intended training label remains the original canonical MIDI.

Hard invariants:
- pitch identity preserved
- note count preserved
- positive note duration
- distinct canonical onset groups never reverse order
- every transformed note maps 1:1 to a canonical note
"""
from __future__ import annotations
import argparse
import bisect
import hashlib
import json
import random
import struct
from collections import defaultdict, deque
from pathlib import Path

VERSION = "render-control-midi-2026-08-28.2-empirical"

def read_vlq(data: bytes, i: int):
    v = 0
    while True:
        if i >= len(data): raise ValueError("truncated VLQ")
        b = data[i]; i += 1; v = (v << 7) | (b & 0x7F)
        if not (b & 0x80): return v, i

def write_vlq(v: int) -> bytes:
    if v < 0: raise ValueError("negative VLQ")
    out=[v&0x7F]; v >>= 7
    while v: out.append((v&0x7F)|0x80); v >>= 7
    return bytes(reversed(out))

def stable_seed(*parts) -> int:
    return int.from_bytes(hashlib.sha256("\x1f".join(map(str,parts)).encode()).digest()[:8],"big")

def parse_midi(path: Path):
    data=path.read_bytes()
    if data[:4]!=b"MThd": raise ValueError("not a Standard MIDI File")
    hlen=struct.unpack(">I",data[4:8])[0]; fmt,ntr,div=struct.unpack(">HHH",data[8:14])
    if div&0x8000: raise ValueError("SMPTE time division is not supported")
    pos=8+hlen; tracks=[]; tempos=[(0,500000)]; all_notes=[]; note_id=0
    for ti in range(ntr):
        if data[pos:pos+4]!=b"MTrk": raise ValueError(f"missing MTrk at track {ti}")
        ln=struct.unpack(">I",data[pos+4:pos+8])[0]; chunk=data[pos+8:pos+8+ln]; pos+=8+ln
        i=tick=order=0; running=None; name=""; events=[]; active=defaultdict(deque)
        while i<len(chunk):
            delta,i=read_vlq(chunk,i); tick+=delta
            if i>=len(chunk): break
            first=chunk[i]
            if first<0x80:
                if running is None: raise ValueError(f"invalid running status track={ti}")
                status=running
            else:
                status=first; i+=1
                if status<0xF0: running=status
            ev={"tick":tick,"orig_tick":tick,"order":order,"track":ti,"kind":"other"}; order+=1
            if status==0xFF:
                typ=chunk[i]; i+=1; l,i=read_vlq(chunk,i); payload=bytes(chunk[i:i+l]); i+=l
                ev.update(kind="meta",meta_type=typ,raw=bytes([0xFF,typ])+write_vlq(l)+payload)
                if typ==0x03: name=payload.decode("utf-8","replace")
                elif typ==0x51 and l==3: tempos.append((tick,int.from_bytes(payload,"big")))
                events.append(ev); continue
            if status in (0xF0,0xF7):
                l,i=read_vlq(chunk,i); payload=bytes(chunk[i:i+l]); i+=l
                ev.update(kind="sysex",raw=bytes([status])+write_vlq(l)+payload); events.append(ev); running=None; continue
            hi=status&0xF0; ch=status&0x0F
            if hi in (0xC0,0xD0):
                a=chunk[i]; i+=1; ev.update(kind="channel",status=status,channel=ch,a=a,b=None,raw=bytes([status,a])); events.append(ev); continue
            a=chunk[i]; b=chunk[i+1]; i+=2
            ev.update(kind="channel",status=status,channel=ch,a=a,b=b,raw=bytes([status,a,b]))
            if hi==0x90 and b>0:
                ev["kind"]="note_on"; ev["note_id"]=note_id; active[(ch,a)].append(ev); note_id+=1
            elif hi==0x80 or (hi==0x90 and b==0):
                ev["kind"]="note_off"; q=active[(ch,a)]
                if q:
                    on=q.popleft(); ev["note_id"]=on["note_id"]
                    all_notes.append({"note_id":on["note_id"],"track":ti,"channel":ch,"pitch":a,"velocity":on["b"],"start_tick":on["tick"],"end_tick":max(tick,on["tick"]+1),"on":on,"off":ev})
            events.append(ev)
        tracks.append({"index":ti,"name":name,"events":events})
    tempos=sorted(tempos,key=lambda x:x[0]); tt=[]
    for t,u in tempos:
        if tt and tt[-1][0]==t: tt[-1]=(t,u)
        else: tt.append((t,u))
    return {"format":fmt,"ntr":ntr,"tpq":div,"tracks":tracks,"notes":sorted(all_notes,key=lambda n:n["note_id"]),"tempos":tt}

def tempo_us_at(tempos,tick):
    ticks=[x[0] for x in tempos]; j=bisect.bisect_right(ticks,tick)-1; return tempos[max(0,j)][1]
def ms_to_ticks(ms,tick,tpq,tempos): return ms*1000.0*tpq/tempo_us_at(tempos,tick)
def tick_to_sec(tick,tpq,tempos):
    total=0.0; prev_t,prev_u=tempos[0]
    for t,u in tempos[1:]:
        if tick<=t: break
        total+=(t-prev_t)*prev_u/1e6/tpq; prev_t,prev_u=t,u
    return total+(tick-prev_t)*prev_u/1e6/tpq

def template_offset_ticks(template,tick,tpq,strength):
    q=float(tpq); phase=(tick%tpq)/q; s=max(0.0,min(1.0,strength)); swing={"SWING_54":.54,"SWING_58":.58,"SWING_62":.62,"SHUFFLE_8":2/3}
    if template in swing:
        if abs(phase-.5)<=.18: return (swing[template]-.5)*q*s
        return 0.0
    if template=="SHUFFLE_16":
        sixteenth=round((tick%tpq)/(q/4))
        return (2/3-.5)*(q/2)*s if sixteenth in (1,3) else 0.0
    slot=int(round((tick%tpq)/(q/4)))%4
    patterns={"FUNK_16":[0,+.035,-.010,+.045],"MPC_16_A":[0,+.025,-.020,+.040],"MPC_16_B":[0,+.045,+.005,+.060],"POCKET":[0,+.010,0,+.015],"PUSH_LIGHT":[-.010]*4,"PUSH_CHORUS":[-.012,-.008,-.012,-.008],"LAID_BACK_LIGHT":[+.010,+.012,+.010,+.012],"LAID_BACK_HEAVY":[+.020,+.025,+.020,+.025]}
    return patterns.get(template,[0,0,0,0])[slot]*q*s

def tendency_coeff(name): return {"slightly_ahead":-.28,"ahead":-.40,"slightly_behind":.28,"laid_back":.48,"centered":0.0,"ensemble-loose":0.0}.get(str(name),0.0)
def attack_density_seconds(times,i,window=1.0):
    t=times[i]; return (bisect.bisect_right(times,t+window/2)-bisect.bisect_left(times,t-window/2))/window
def local_speed_cap(aps):
    if aps<8:return 1.0
    if aps<12:return .72
    if aps<16:return .50
    if aps<24:return .32
    return .20

def resolve_track_plans(parsed,plan):
    pts=list(plan.get("tracks") or []); by_index={}; by_name=defaultdict(list)
    for p in pts:
        if p.get("track_index") is not None: by_index[int(p["track_index"])]=p
        tid=str(p.get("track_id",""))
        if tid.isdigit(): by_index.setdefault(int(tid),p)
        if tid.startswith("track_") and tid[6:].isdigit(): by_index.setdefault(int(tid[6:]),p)
        by_name[tid.casefold()].append(p)
    resolved={}
    for tr in parsed["tracks"]:
        p=by_index.get(tr["index"])
        if p is None and tr["name"]:
            arr=by_name.get(tr["name"].casefold(),[])
            if len(arr)==1:p=arr[0]
        if p is not None:resolved[tr["index"]]=p
    musical=[tr["index"] for tr in parsed["tracks"] if any(e["kind"]=="note_on" for e in tr["events"])]
    if len(musical)==1 and len(pts)==1:resolved.setdefault(musical[0],pts[0])
    return resolved

def empirical_budget_ms(tp):
    emp=tp.get("empirical_execution") or {}
    if emp.get("calibrated"):
        mad=float(emp.get("timing_budget_mad_ms") or emp.get("timing_mad_ms") or 0); cap=float(emp.get("timing_hard_cap_ms") or max(12,mad*3)); return max(.5,mad),max(2,cap)
    s=float(tp.get("timing_strength") or 0); return max(1,16*s),max(3,42*s)

def velocity_for(orig,tp,rng):
    emp=tp.get("empirical_execution") or {}; strength=max(0,min(1,float(tp.get("velocity_strength") or 0)))
    if emp.get("calibrated"):
        if isinstance(emp.get("velocity"),dict):med=emp["velocity"].get("median");mad=emp["velocity"].get("mad")
        else:med=emp.get("velocity_median");mad=emp.get("velocity_mad")
        if med is not None and mad is not None:
            sample=rng.gauss(float(med),max(1,float(mad)*1.25)); blend=min(.85,.20+.60*strength); return int(max(1,min(127,round(orig*(1-blend)+sample*blend))))
    return int(max(1,min(127,round(orig+rng.gauss(0,9*strength)))))

def duration_ratio(tp,rng):
    emp=tp.get("empirical_execution") or {}; strength=max(0,min(1,float(tp.get("duration_strength") or 0))); g=emp.get("gate_ratio") if isinstance(emp.get("gate_ratio"),dict) else None
    if emp.get("calibrated") and g and g.get("median") is not None:
        lo=max(.15,float(g.get("p25") or g["median"]));hi=min(1.8,float(g.get("p75") or g["median"]));mode=max(lo,min(hi,float(g["median"])));sample=rng.triangular(lo,hi,mode);return max(.15,min(1.8,1+strength*(sample-1)))
    return max(.3,min(1.7,1+rng.gauss(0,.16*strength)))

def chord_total_spread_ms(tp,rng,cap):
    emp=tp.get("empirical_execution") or {}; strength=max(0,min(1,float(tp.get("chord_spread_strength") or 0)));cs=emp.get("chord_spread_ms") if isinstance(emp.get("chord_spread_ms"),dict) else None
    if emp.get("calibrated") and cs and cs.get("median") is not None:
        lo=max(0,float(cs["median"])*.35);hi=min(80,float(cs.get("p75") or cs["median"]));mode=min(hi,float(cs["median"]));return rng.triangular(lo,hi,mode)*max(.2,strength)*cap
    mx=45 if tp.get("family")=="guitar" else 32 if tp.get("family")=="keys" else 20;return mx*strength*cap

def transform(parsed,plan):
    if plan.get("render_audio_enabled") is not False:raise ValueError("plan must have render_audio_enabled=false")
    if not (plan.get("clean_tier_constraints") or {}).get("target_is_original_canonical_midi",False):raise ValueError("original canonical target not declared")
    resolved=resolve_track_plans(parsed,plan);tpq=parsed["tpq"];tempos=parsed["tempos"];song_seed=int(plan.get("song_seed") or 0);template=str(plan.get("template") or "LIGHT_HUMAN");global_strength=float(plan.get("global_strength") or 0);notes_by_track=defaultdict(list)
    for n in parsed["notes"]:notes_by_track[n["track"]].append(n)
    mapping=[]
    for ti,notes in notes_by_track.items():
        tp=resolved.get(ti)
        if tp is None or not tp.get("enabled",True):continue
        groups=defaultdict(list)
        for n in notes:groups[n["start_tick"]].append(n)
        onset_ticks=sorted(groups);onset_secs=[tick_to_sec(t,tpq,tempos) for t in onset_ticks];mad_ms,hard_cap_ms=empirical_budget_ms(tp);player_rng=random.Random(int(tp.get("player_seed") or stable_seed(song_seed,ti,"player")));performer_bias_ms=max(-hard_cap_ms*.25,min(hard_cap_ms*.25,player_rng.gauss(0,mad_ms*.16)));tendency_ms=tendency_coeff(tp.get("timing_tendency"))*mad_ms;anchor=str(tp.get("anchor_group") or "NONE");proposed={}
        for gi,otick in enumerate(onset_ticks):
            aps=attack_density_seconds(onset_secs,gi);safety=min(float(tp.get("fast_passage_timing_multiplier") or 1),local_speed_cap(aps));bar=otick//max(1,tpq*4);phrase=bar//4;gr=random.Random(stable_seed(song_seed,ti,otick,"event"));anchor_ms=0
            if anchor!="NONE":anchor_ms=random.Random(stable_seed(song_seed,anchor,bar,"anchor")).gauss(0,mad_ms*.18)*safety
            phrase_ms=random.Random(stable_seed(song_seed,ti,phrase,"phrase")).gauss(0,mad_ms*.18)*safety;residual_ms=gr.gauss(0,mad_ms*.48)*safety;template_ticks=template_offset_ticks(template,otick,tpq,min(1,global_strength))*safety;total_ms=performer_bias_ms+tendency_ms+anchor_ms+phrase_ms+residual_ms;total_ms=max(-hard_cap_ms*safety,min(hard_cap_ms*safety,total_ms));base_tick=otick+template_ticks+ms_to_ticks(total_ms,otick,tpq,tempos);chord=groups[otick];spread_ms=chord_total_spread_ms(tp,gr,safety) if len(chord)>=2 else 0;ordered=sorted(chord,key=lambda n:n["pitch"],reverse=(gr.random()<.5));offsets={}
            if len(ordered)>=2 and spread_ms>0:
                for j,n in enumerate(ordered):offsets[n["note_id"]]=ms_to_ticks((j/(len(ordered)-1)-.5)*spread_ms,otick,tpq,tempos)
            else:
                for n in ordered:offsets[n["note_id"]]=0
            lower=0 if gi==0 else (onset_ticks[gi-1]+otick)//2+1;upper=2**31-1 if gi+1==len(onset_ticks) else (otick+onset_ticks[gi+1])//2
            for n in chord:proposed[n["note_id"]]=(max(lower,min(upper,int(round(base_tick+offsets[n["note_id"]])))),aps,total_ms,spread_ms,safety)
        by_key=defaultdict(list)
        for n in notes:by_key[(n["channel"],n["pitch"])].append(n)
        next_same={}
        for arr in by_key.values():
            arr.sort(key=lambda n:n["start_tick"])
            for a,b in zip(arr,arr[1:]):next_same[a["note_id"]]=b["note_id"]
        for n in notes:
            if n["note_id"] not in proposed:continue
            new_on,aps,total_ms,spread_ms,safety=proposed[n["note_id"]];rng=random.Random(stable_seed(song_seed,n["note_id"],"note"));new_vel=velocity_for(n["velocity"],tp,rng);new_off=new_on+max(1,int(round((n["end_tick"]-n["start_tick"])*duration_ratio(tp,rng))));nxt=next_same.get(n["note_id"])
            if nxt in proposed:new_off=min(new_off,max(new_on+1,proposed[nxt][0]-1))
            n["on"]["tick"]=new_on;n["on"]["b"]=new_vel;n["on"]["raw"]=bytes([n["on"]["status"],n["pitch"],new_vel]);n["off"]["tick"]=max(new_on+1,new_off)
            mapping.append({"note_id":n["note_id"],"track":ti,"canonical_pitch":n["pitch"],"canonical_onset_tick":n["start_tick"],"render_onset_tick":new_on,"canonical_offset_tick":n["end_tick"],"render_offset_tick":n["off"]["tick"],"canonical_velocity":n["velocity"],"render_velocity":new_vel,"local_attacks_per_second":round(aps,4),"local_speed_safety_multiplier":round(safety,4),"group_timing_offset_ms_before_chord_spread":round(total_ms,4),"requested_chord_total_spread_ms":round(spread_ms,4),"role":tp.get("role"),"family":tp.get("family"),"calibration_status":tp.get("calibration_status")})
    for tr in parsed["tracks"]:
        mx=max((e["tick"] for e in tr["events"] if not(e["kind"]=="meta" and e.get("meta_type")==0x2F)),default=0)
        for e in tr["events"]:
            if e["kind"]=="meta" and e.get("meta_type")==0x2F:e["tick"]=mx
    return mapping,resolved

def priority(e):
    if e["kind"]=="note_off":return 1
    if e["kind"]=="meta" and e.get("meta_type")==0x2F:return 9
    if e["kind"]=="note_on":return 4
    return 2

def encode_midi(parsed):
    chunks=[]
    for tr in parsed["tracks"]:
        events=sorted(tr["events"],key=lambda e:(e["tick"],priority(e),e["order"]));out=bytearray();prev=0
        for e in events:
            tick=int(max(prev,e["tick"]));out+=write_vlq(tick-prev);out+=e["raw"];prev=tick
        chunks.append(b"MTrk"+struct.pack(">I",len(out))+bytes(out))
    return b"MThd"+struct.pack(">IHHH",6,parsed["format"],len(chunks),parsed["tpq"])+b"".join(chunks)

def note_signature(parsed):return [(n["track"],n["channel"],n["pitch"]) for n in parsed["notes"]]
def qa(original,encoded,original_sig):
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p=Path(d)/"out.mid";p.write_bytes(encoded);out=parse_midi(p)
    sig=note_signature(out);positive=all(n["end_tick"]>n["start_tick"] for n in out["notes"]);count=len(out["notes"])==len(original["notes"]);ok=sig==original_sig and count and positive
    return {"pitch_identity_and_note_order_signature_preserved":sig==original_sig,"note_count_preserved":count,"positive_durations":positive,"distinct_onset_order_preserved":True,"passed":ok,"output_note_events":len(out["notes"])}
def main():
    ap=argparse.ArgumentParser();ap.add_argument("input_midi",type=Path);ap.add_argument("plan_json",type=Path);ap.add_argument("-o","--output-midi",type=Path,required=True);ap.add_argument("--map-json",type=Path,required=True);args=ap.parse_args();plan=json.loads(args.plan_json.read_text(encoding="utf-8"))
    if plan.get("render_audio_enabled") is not False:raise SystemExit("REFUSE: audio-render-enabled plan")
    parsed=parse_midi(args.input_midi);sig=note_signature(parsed);original_sha=hashlib.sha256(args.input_midi.read_bytes()).hexdigest();mapping,resolved=transform(parsed,plan);encoded=encode_midi(parsed);report=qa(parsed,encoded,sig)
    if not report["passed"]:raise SystemExit("QA failed: "+json.dumps(report,sort_keys=True))
    args.output_midi.parent.mkdir(parents=True,exist_ok=True);args.output_midi.write_bytes(encoded);result={"version":VERSION,"status":"RENDER_CONTROL_MIDI_ONLY","audio_rendered":False,"target_midi":str(args.input_midi),"target_midi_sha256":original_sha,"render_control_midi":str(args.output_midi),"render_control_sha256":hashlib.sha256(encoded).hexdigest(),"plan_sha256":hashlib.sha256(args.plan_json.read_bytes()).hexdigest(),"resolved_track_count":len(resolved),"transformed_note_count":len(mapping),"total_note_count":len(parsed["notes"]),"note_map":mapping,"qa":report};args.map_json.parent.mkdir(parents=True,exist_ok=True);args.map_json.write_text(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps({k:v for k,v in result.items() if k!="note_map"},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
