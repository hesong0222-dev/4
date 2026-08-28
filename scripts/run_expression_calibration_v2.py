#!/usr/bin/env python3
from __future__ import annotations
import bisect, csv, statistics
from collections import defaultdict, Counter
from pathlib import Path
import analyze_expression_corpora as core

def greedy_match(score_notes, perf_notes, score_beats, perf_beats, tol=.22):
    by_pitch=defaultdict(list)
    for i,n in enumerate(perf_notes): by_pitch[n['pitch']].append((n['start'],i,n))
    pitch_times={p:[x[0] for x in arr] for p,arr in by_pitch.items()}
    used=set(); matches=[]
    for sn in sorted(score_notes,key=lambda x:(x['start'],x['pitch'])):
        target=core.interp(score_beats,perf_beats,sn['start'])
        if target is None: continue
        arr=by_pitch.get(sn['pitch'],[]); ts=pitch_times.get(sn['pitch'],[]); j=bisect.bisect_left(ts,target); cand=[]
        for k in (j-2,j-1,j,j+1,j+2):
            if 0<=k<len(arr) and arr[k][1] not in used: cand.append(arr[k])
        if not cand: continue
        best=min(cand,key=lambda x:abs(x[0]-target))
        if abs(best[0]-target)<=tol:
            used.add(best[1]); matches.append((sn,best[2],target))
    return matches

def cluster_attacks(times,tol=.025):
    times=sorted(times)
    if not times:return []
    groups=[[times[0]]]
    for t in times[1:]:
        if t-groups[-1][-1] <= tol: groups[-1].append(t)
        else: groups.append([t])
    return [statistics.median(g) for g in groups]

def analyze_asap(root):
    root=Path(root); meta=root/'metadata.csv'; residual=[]; vel=[]; gate=[]; chord_spread=[]; attack_dens=[]; residual_by_density=defaultdict(list)
    perf_count=aligned_count=matched=score_notes_total=0
    with meta.open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            mp=row.get('midi_performance',''); ms=row.get('midi_score',''); pa=row.get('performance_annotations') or row.get('performance_anotations',''); sa=row.get('midi_score_annotations','')
            if not mp or not ms or not pa or not sa: continue
            pp=root/mp; sp=root/ms; pap=root/pa; sap=root/sa
            if not all(x.exists() for x in [pp,sp,pap,sap]): continue
            perf_count+=1; pb=core.ann_times(pap); sb=core.ann_times(sap)
            if len(pb)<4 or len(pb)!=len(sb): continue
            try: pm=core.parse_midi(pp); sm=core.parse_midi(sp)
            except Exception: continue
            aligned_count+=1; sn=sm['notes']; score_notes_total+=len(sn); msx=greedy_match(sn,pm['notes'],sb,pb); matched+=len(msx)
            # exact canonical score onsets, warped to performance time: chords count once
            attack_times=sorted({round(tgt,6) for _,_,tgt in msx})
            groups=defaultdict(list)
            for s,p,tgt in msx:
                r=(p['start']-tgt)*1000; residual.append(r); vel.append(p['velocity']); d=core.density_at(attack_times,tgt); attack_dens.append(d); residual_by_density[core.density_bin(d)].append(r)
                mapped_end=core.interp(sb,pb,s['end'])
                if mapped_end is not None and mapped_end>tgt and p['end']>p['start']: gate.append((p['end']-p['start'])/(mapped_end-tgt))
                groups[round(s['start'],4)].append(p['start'])
            for g in groups.values():
                if len(g)>=2: chord_spread.append((max(g)-min(g))*1000)
    ad=core.robust(attack_dens)
    return {'source':'ASAP','performances_seen':perf_count,'aligned_performances_used':aligned_count,'score_notes_total':score_notes_total,'matched_notes':matched,'match_rate':matched/max(score_notes_total,1),'density_semantics':'canonical distinct score onsets per second after beat warp; chords count once','microtiming_residual_ms':core.robust(residual),'microtiming_abs_ms':core.robust([abs(x) for x in residual]),'microtiming_residual_ms_by_density':{k:core.robust(v) for k,v in sorted(residual_by_density.items())},'velocity':core.robust(vel),'gate_ratio_performance_over_locally_warped_score':core.robust(gate),'canonical_chord_spread_ms_in_performance':core.robust(chord_spread),'local_attack_density_hz':ad,'local_note_density_hz':ad}

def generic_performance_stats(root,name):
    root=Path(root); mids=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.mid','.midi'}]; velocities=[]; gates=[]; spreads=[]; densities=[]; fastmax=[]; pedal=files=notes_total=0
    for p in mids:
        try:m=core.parse_midi(p)
        except Exception:continue
        if not m['notes']:continue
        files+=1; notes_total+=len(m['notes']); velocities.extend(n['velocity'] for n in m['notes']); gates.extend(max(0,n['end']-n['start']) for n in m['notes']); spreads.extend(core.chord_spreads(m['notes'],.06))
        attacks=cluster_attacks([n['start'] for n in m['notes']],.025); densities.append(len(attacks)/max(m['duration'],1e-6))
        if attacks:fastmax.append(max(core.density_at(attacks,t) for t in attacks))
        pedal+=sum(1 for c in m['cc'] if c['control']==64)
    d=core.robust(densities); mx=core.robust(fastmax)
    return {'source':name,'midi_files_used':files,'notes':notes_total,'density_semantics':'25ms-clustered attack groups per second; advisory approximation','velocity':core.robust(velocities),'note_duration_sec':core.robust(gates),'chord_spread_ms_60ms_group':core.robust(spreads),'whole_file_attack_density_hz':d,'whole_file_note_density_hz':d,'max_local_attack_density_hz':mx,'max_local_note_density_hz':mx,'pedal_cc64_events':pedal}

def analyze_pop909(root):
    root=Path(root); files=[]; base=root/'POP909'
    if base.exists():
        for d in sorted(base.iterdir()):
            if d.is_dir():
                p=d/(d.name+'.mid')
                if p.exists():files.append(p)
    densities=[]; maxdens=[]; velocities=[]; spreads=[]; note_counts=[]; track_names=Counter()
    for p in files:
        try:m=core.parse_midi(p)
        except Exception:continue
        ns=m['notes']; note_counts.append(len(ns)); velocities.extend(n['velocity'] for n in ns)
        attacks=cluster_attacks([n['start'] for n in ns],.002); densities.append(len(attacks)/max(m['duration'],1e-6))
        if attacks:maxdens.append(max(core.density_at(attacks,t) for t in attacks))
        spreads.extend(core.chord_spreads(ns,.01))
        for tr in m['tracks']:
            if tr['name']:track_names[tr['name']]+=1
    d=core.robust(densities); mx=core.robust(maxdens)
    return {'source':'POP909','canonical_songs_used':len(files),'density_semantics':'2ms-clustered canonical onset groups per second; chords count once','notes_per_song':core.robust(note_counts),'whole_file_attack_density_hz':d,'whole_file_note_density_hz':d,'max_local_attack_density_hz':mx,'max_local_note_density_hz':mx,'velocity':core.robust(velocities),'canonical_chord_spread_ms_10ms_group':core.robust(spreads),'track_name_counts':dict(track_names)}

def calibration(gmd,asap,ep,pop):
    out=core.calibration(gmd,asap,ep,pop); out['calibration_version']='empirical-2026-08-28.2-attack-density'
    out['fast_passage_reference']={
      'density_semantics':'attack/onset groups per second; simultaneous chord tones count once',
      'asap_local_attack_density_hz':asap['local_attack_density_hz'],
      'e_piano_max_local_attack_density_hz_advisory':ep['max_local_attack_density_hz'],
      'pop909_max_local_attack_density_hz_structural':pop['max_local_attack_density_hz'],
      'planner_rule':'use empirical piano density bins but also enforce event-order safety cap'
    }
    out['piano']['density_semantics']=asap['density_semantics']
    return out

core.greedy_match=greedy_match
core.analyze_asap=analyze_asap
core.generic_performance_stats=generic_performance_stats
core.analyze_pop909=analyze_pop909
core.calibration=calibration
if __name__=='__main__':core.main()
