#!/usr/bin/env python3
"""Multifamily empirical wrapper for build_humanization_plan.
Plan-only; never renders audio and preserves canonical MIDI as target.
"""
from __future__ import annotations
import argparse, json
from pathlib import Path
import build_humanization_plan as base

VERSION='adaptive-humanization-2026-08-28.4-multifamily'
_ORIGINAL_EMPIRICAL_ROLE=base.empirical_role

def _family_key(fam):
    return {'woodwind':'woodwinds','keys':'keys'}.get(fam,fam)

def _confidence(evidence):
    e=str(evidence or '')
    if e.startswith('DIRECT_REAL_CAPTURED'): return 1.0
    if 'DIRECT_REAL_PERFORMANCE' in e: return .90
    if 'DIRECT_REAL_SCORE_ALIGNED' in e: return .90
    if e.startswith('MIXED:'): return .80
    if 'ALIGNED_TRANSCRIPTION_PROXY' in e: return .62
    return 0.0

def empirical_role_v4(role,fam,cal,song_strength,speed_multiplier):
    old=_ORIGINAL_EMPIRICAL_ROLE(role,fam,cal,song_strength,speed_multiplier)
    if old.get('calibrated'): return old
    if not cal: return old
    ent=(cal.get('family_empirical') or {}).get(_family_key(fam)) or {}
    evidence=ent.get('evidence'); weight=_confidence(evidence)
    timing=ent.get('timing') if isinstance(ent.get('timing'),dict) else {}
    if weight<=0 or int(timing.get('n') or 0)<100:
        return {'calibrated':False,'reason':'no sufficient multifamily empirical timing evidence','evidence':evidence}
    med=float(timing.get('median') or 0.0); mad=max(.5,float(timing.get('mad') or 0.0))
    tail=max(abs(float(timing.get('p10') or med)),abs(float(timing.get('p90') or med)),mad*2.5)
    out={
      'calibrated':True,'source':ent.get('source') or ent.get('sources'),'evidence':evidence,
      'confidence_weight':weight,'timing_center_ms':round(med,4),'timing_mad_ms':round(mad,4),
      'timing_budget_mad_ms':round(mad*song_strength*speed_multiplier*weight,4),
      'timing_hard_cap_ms':round(tail*max(.25,song_strength)*speed_multiplier*weight,4),
    }
    cs=ent.get('chord_spread')
    if isinstance(cs,dict) and cs.get('n',0):
        out['chord_spread_ms']={k:cs.get(k) for k in ('median','p25','p75','p90')}
    gate=ent.get('gate_ratio')
    if isinstance(gate,dict) and gate.get('n',0):
        out['gate_ratio']={k:gate.get(k) for k in ('median','p25','p75','p90')}
    vel=ent.get('velocity')
    if isinstance(vel,dict) and vel.get('n',0):
        out['velocity']={k:vel.get(k) for k in ('median','mad','p10','p90')}
    return out

base.empirical_role=empirical_role_v4

def build(meta,seed=None,calibration=None,calibration_path=None):
    plan=base.build_plan(meta,seed=seed,calibration=calibration,calibration_path=calibration_path)
    plan['policy_version']=VERSION
    fam=(calibration or {}).get('family_empirical') or {}
    unresolved=[]; empirical=[]; proxy=[]
    for k,v in sorted(fam.items()):
        ev=str(v.get('evidence') or '')
        if ev=='UNRESOLVED': unresolved.append(k)
        elif 'PROXY' in ev or ev.startswith('MIXED:'): proxy.append(k)
        else: empirical.append(k)
    plan['calibration']['automatic_empirical_families']=empirical
    plan['calibration']['lower_confidence_proxy_families']=proxy
    plan['calibration']['still_provisional_families']=unresolved
    plan['calibration']['direct_overrides_proxy']=True
    return plan

def self_test():
    cal={'calibration_version':'v4','render_audio_enabled':False,'family_empirical':{
      'guitar':{'evidence':'DIRECT_REAL_PERFORMANCE_NOTE_ANNOTATION','source':'GuitarSet','timing':{'n':1000,'median':1,'mad':11,'p10':-25,'p90':28},'chord_spread':{'n':500,'median':18,'p75':33,'p90':50}},
      'voice':{'evidence':'ALIGNED_TRANSCRIPTION_PROXY','source':'RWC','timing':{'n':800,'median':0,'mad':14,'p10':-30,'p90':32}},
      'synth':{'evidence':'UNRESOLVED','timing':{'n':0}}}}
    meta={'work_id':'w','arrangement_id':'a','genre':'funk','tracks':[{'id':'g','family':'guitar','role':'rhythm_guitar','peak_attacks_per_second':7}]}
    p=build(meta,seed=42,calibration=cal,calibration_path='x')
    e=p['tracks'][0]['empirical_execution']; assert e['calibrated'] and e['source']=='GuitarSet' and p['render_audio_enabled'] is False
    assert 'synth' in p['calibration']['still_provisional_families']
    print(json.dumps(p,indent=2,sort_keys=True))

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('input',nargs='?',type=Path); ap.add_argument('-o','--output',type=Path); ap.add_argument('--seed',type=int); ap.add_argument('--calibration',type=Path,default=base.DEFAULT_CALIBRATION); ap.add_argument('--self-test',action='store_true'); a=ap.parse_args()
    if a.self_test:self_test();return
    if not a.input:ap.error('input JSON required')
    cal=base.load_calibration(a.calibration); meta=json.loads(a.input.read_text()); p=build(meta,a.seed,cal,a.calibration); txt=json.dumps(p,ensure_ascii=False,indent=2,sort_keys=True)+'\n'
    if a.output:a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(txt)
    else:print(txt,end='')

if __name__=='__main__':main()
