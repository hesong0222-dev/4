#!/usr/bin/env python3
"""Extend the canonical humanization planner with multi-family empirical priors.

Plan-only: never modifies MIDI and never renders audio. Direct performance
sources override lower-confidence aligned-transcription proxies.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import build_humanization_plan as base

VERSION="adaptive-humanization-2026-08-28.4-multifamily"
CONFIDENCE={
    "REAL_CAPTURED_MIDI":1.0,
    "REAL_PERFORMANCE_NOTE_ANNOTATION_WITH_BEATS":1.0,
    "REAL_SCORE_ALIGNED_PERFORMANCE_MIDI":.95,
    "DIRECT_REAL_PERFORMANCE_NOTE_ANNOTATION":.95,
    "DIRECT_REAL_PERFORMANCE_SCORE_ALIGNED":.93,
    "REAL_SCORE_ALIGNED_DERIVED":.90,
    "MIXED_DIRECT_AND_PROXY":.80,
    "ALIGNED_TRANSCRIPTION_PROXY":.62,
    "UNRESOLVED":0.0,
}

def _timing_fields(rec,song_strength,speed_multiplier):
    t=rec.get('timing') or rec.get('microtiming_residual_ms') or {}
    if not isinstance(t,dict) or not t.get('n'):return None
    mad=float(t.get('mad') or 0); p10=float(t.get('p10') or 0); p90=float(t.get('p90') or 0)
    center=float(t.get('median') or 0)
    return {
      'timing_center_ms':round(center,4),
      'timing_mad_ms':round(mad,4),
      'timing_budget_mad_ms':round(mad*song_strength*speed_multiplier,4),
      'timing_hard_cap_ms':round(max(abs(p10),abs(p90),mad*2.5)*max(.25,song_strength)*speed_multiplier,4),
    }

def _copy_distribution(out,key,rec,src_key=None):
    v=rec.get(src_key or key)
    if isinstance(v,dict) and v.get('n'):
        out[key]={k:v.get(k) for k in ('n','median','mad','p10','p25','p75','p90') if k in v}

def family_empirical(role,fam,cal,song_strength,speed_multiplier):
    if not cal:return {'calibrated':False,'reason':'no calibration loaded'}
    famrec=(cal.get('family_empirical') or {}).get(fam)
    if not isinstance(famrec,dict):return {'calibrated':False,'reason':'no family empirical record'}
    ev=str(famrec.get('evidence') or 'UNRESOLVED'); conf=CONFIDENCE.get(ev,.5)
    tf=_timing_fields(famrec,song_strength,speed_multiplier)
    # A source may still be valuable for gate/articulation even when timing is absent.
    useful=tf is not None or any(isinstance(famrec.get(k),dict) and famrec[k].get('n') for k in ('velocity','gate_ratio','duration','chord_spread'))
    if not useful or conf<=0:return {'calibrated':False,'source':famrec.get('source'),'evidence':ev,'confidence':conf,'reason':famrec.get('reason','insufficient empirical samples')}
    out={'calibrated':True,'source':famrec.get('source'),'evidence':ev,'confidence':conf,'family':fam}
    if tf:out.update(tf)
    _copy_distribution(out,'velocity',famrec)
    _copy_distribution(out,'gate_ratio',famrec)
    _copy_distribution(out,'duration',famrec)
    _copy_distribution(out,'chord_spread_ms',famrec,'chord_spread')
    if isinstance(famrec.get('articulation'),dict):out['articulation']=famrec['articulation']
    if famrec.get('timing_proxy_source'):out['timing_proxy_source']=famrec['timing_proxy_source']
    return out

def empirical_role(role,fam,cal,song_strength,speed_multiplier):
    # Keep the stronger existing role-level calibration for GMD drums and ASAP piano.
    direct=base.empirical_role(role,fam,cal,song_strength,speed_multiplier)
    f=family_empirical(role,fam,cal,song_strength,speed_multiplier)
    if not f.get('calibrated'):return direct
    if not direct.get('calibrated'):return f
    dconf=CONFIDENCE.get(str(direct.get('evidence') or ''),.9)
    fconf=float(f.get('confidence',.5))
    return direct if dconf>=fconf else f

def build(meta,seed=None,calibration=None,calibration_path=None):
    old=base.empirical_role
    try:
        base.empirical_role=empirical_role
        p=base.build_plan(meta,seed,calibration,calibration_path)
    finally:
        base.empirical_role=old
    p['policy_version']=VERSION
    fams={t.get('family') for t in p.get('tracks',[])}
    empirical=sorted({t.get('family') for t in p.get('tracks',[]) if (t.get('empirical_execution') or {}).get('calibrated')})
    direct=[];proxy=[]
    for t in p.get('tracks',[]):
        e=t.get('empirical_execution') or {}
        if not e.get('calibrated'):continue
        if float(e.get('confidence',CONFIDENCE.get(str(e.get('evidence') or ''),.9)))>=.85:direct.append(t.get('family'))
        else:proxy.append(t.get('family'))
    p['calibration']['version']=(calibration or {}).get('calibration_version')
    p['calibration']['automatic_empirical_families']=sorted(set(empirical))
    p['calibration']['direct_or_high_confidence_families']=sorted(set(direct))
    p['calibration']['lower_confidence_proxy_families']=sorted(set(proxy))
    p['calibration']['still_provisional_families']=sorted(x for x in fams if x not in set(empirical))
    return p

def self_test():
    cal={'calibration_version':'v4','render_audio_enabled':False,'family_empirical':{
      'guitar':{'evidence':'DIRECT_REAL_PERFORMANCE_NOTE_ANNOTATION','source':'GuitarSet','timing':{'n':1000,'median':1,'mad':11,'p10':-25,'p90':28},'chord_spread':{'n':500,'median':18,'p75':33,'p90':50}},
      'voice':{'evidence':'ALIGNED_TRANSCRIPTION_PROXY','source':'RWC','timing':{'n':800,'median':0,'mad':14,'p10':-30,'p90':32}},
      'synth':{'evidence':'UNRESOLVED','timing':{'n':0}}}}
    meta={'work_id':'w','arrangement_id':'a','genre':'funk','tracks':[{'id':'g','family':'guitar','role':'rhythm_guitar','peak_attacks_per_second':7}]}
    p=build(meta,seed=42,calibration=cal,calibration_path='x')
    e=p['tracks'][0]['empirical_execution']; assert e['calibrated'] and e['source']=='GuitarSet' and p['render_audio_enabled'] is False
    assert 'synth' not in p['calibration']['automatic_empirical_families']
    print(json.dumps(p,indent=2,sort_keys=True))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input',nargs='?',type=Path); ap.add_argument('-o','--output',type=Path); ap.add_argument('--seed',type=int); ap.add_argument('--calibration',type=Path,default=base.DEFAULT_CALIBRATION); ap.add_argument('--self-test',action='store_true'); a=ap.parse_args()
    if a.self_test:self_test();return
    if not a.input:ap.error('input JSON required')
    cal=base.load_calibration(a.calibration); meta=json.loads(a.input.read_text()); p=build(meta,a.seed,cal,a.calibration); txt=json.dumps(p,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(txt)
    else:print(txt,end='')

if __name__=='__main__':main()
