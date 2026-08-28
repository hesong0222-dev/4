#!/usr/bin/env python3
from __future__ import annotations
import argparse, bisect, csv, hashlib, json, math, statistics, struct
from collections import defaultdict, Counter
from pathlib import Path

def vlq(data, i):
    v=0
    while True:
        b=data[i]; i+=1; v=(v<<7)|(b&0x7f)
        if not (b&0x80): return v,i

def parse_midi(path):
    data=Path(path).read_bytes()
    if data[:4]!=b'MThd': raise ValueError(f'not midi: {path}')
    hlen=struct.unpack('>I',data[4:8])[0]
    fmt,ntr,div=struct.unpack('>HHH',data[8:14])
    if div & 0x8000: raise ValueError('SMPTE division unsupported')
    pos=8+hlen; tracks=[]; tempo=[(0,500000)]
    for ti in range(ntr):
        if data[pos:pos+4]!=b'MTrk': raise ValueError('bad track')
        ln=struct.unpack('>I',data[pos+4:pos+8])[0]; chunk=data[pos+8:pos+8+ln]; pos+=8+ln
        i=0; tick=0; running=None; name=''; program={}; active=defaultdict(list); notes=[]; ccs=[]
        while i<len(chunk):
            d,i=vlq(chunk,i); tick+=d
            status=chunk[i]
            if status<0x80:
                if running is None: raise ValueError('bad running status')
                status=running
            else:
                i+=1
                if status<0xf0: running=status
            if status==0xff:
                typ=chunk[i]; i+=1; l,i=vlq(chunk,i); payload=chunk[i:i+l]; i+=l
                if typ==0x03: name=payload.decode('utf-8','replace')
                elif typ==0x51 and l==3: tempo.append((tick,int.from_bytes(payload,'big')))
                continue
            if status in (0xf0,0xf7):
                l,i=vlq(chunk,i); i+=l; running=None; continue
            hi=status&0xf0; ch=status&0x0f
            if hi in (0xc0,0xd0):
                a=chunk[i]; i+=1
                if hi==0xc0: program[ch]=a
                continue
            a=chunk[i]; b=chunk[i+1]; i+=2
            if hi==0x90 and b>0:
                active[(ch,a)].append((tick,b,program.get(ch,0)))
            elif hi==0x80 or (hi==0x90 and b==0):
                key=(ch,a)
                if active[key]:
                    st,vel,pr=active[key].pop(0)
                    notes.append({'track':ti,'channel':ch,'pitch':a,'velocity':vel,'program':pr,'start_tick':st,'end_tick':max(tick,st+1),'track_name':name})
            elif hi==0xb0:
                ccs.append({'track':ti,'channel':ch,'control':a,'value':b,'tick':tick,'track_name':name})
        tracks.append({'index':ti,'name':name,'notes':notes,'cc':ccs})
    tempo=sorted(tempo,key=lambda x:x[0]); tt=[]
    for t,u in tempo:
        if tt and tt[-1][0]==t: tt[-1]=(t,u)
        else: tt.append((t,u))
    ticks=[x[0] for x in tt]; secs=[0.0]*len(tt)
    for j in range(1,len(tt)):
        secs[j]=secs[j-1]+(tt[j][0]-tt[j-1][0])*tt[j-1][1]/1e6/div
    def t2s(t):
        j=bisect.bisect_right(ticks,t)-1
        return secs[j]+(t-ticks[j])*tt[j][1]/1e6/div
    notes=[]; ccs=[]
    for tr in tracks:
        for n in tr['notes']:
            n=dict(n); n['start']=t2s(n['start_tick']); n['end']=t2s(n['end_tick']); notes.append(n)
        for c in tr['cc']:
            c=dict(c); c['time']=t2s(c['tick']); ccs.append(c)
    return {'format':fmt,'tpq':div,'tempo':tt,'notes':notes,'cc':ccs,'tracks':tracks,'duration':max([n['end'] for n in notes] or [0.0])}

def pct(vals,q):
    if not vals:return None
    a=sorted(vals); x=(len(a)-1)*q; lo=int(math.floor(x)); hi=int(math.ceil(x))
    if lo==hi:return a[lo]
    return a[lo]*(hi-x)+a[hi]*(x-lo)

def robust(vals):
    vals=[float(x) for x in vals if x is not None and math.isfinite(float(x))]
    if not vals:return {'n':0}
    med=statistics.median(vals); mad=statistics.median(abs(x-med) for x in vals)
    return {'n':len(vals),'mean':statistics.fmean(vals),'median':med,'mad':mad,'p05':pct(vals,.05),'p10':pct(vals,.10),'p25':pct(vals,.25),'p75':pct(vals,.75),'p90':pct(vals,.90),'p95':pct(vals,.95),'p99':pct(vals,.99)}

def density_at(times,t,window=1.0):
    lo=bisect.bisect_left(times,t-window/2); hi=bisect.bisect_right(times,t+window/2)
    return (hi-lo)/window

def density_bin(d):
    if d<4:return 'lt4'
    if d<8:return '4_8'
    if d<12:return '8_12'
    if d<16:return '12_16'
    return 'ge16'

DRUM_ROLE={}
for p in [35,36]:DRUM_ROLE[p]='kick'
for p in [37,38,40]:DRUM_ROLE[p]='snare'
for p in [42,44,46]:DRUM_ROLE[p]='hihat'
for p in [51,53,59]:DRUM_ROLE[p]='ride'
for p in [41,43,45,47,48,50]:DRUM_ROLE[p]='tom'
for p in [49,52,55,57]:DRUM_ROLE[p]='crash'
def role(p):return DRUM_ROLE.get(p,'other')

def analyze_gmd(root):
    root=Path(root); info=next(iter(root.rglob('info.csv')),None)
    if not info:raise FileNotFoundError('GMD info.csv')
    by_role=defaultdict(list); vel_role=defaultdict(list); by_style_role=defaultdict(list); swing=defaultdict(list)
    file_density=[]; files=0; hits=0; fast_hits=Counter()
    with info.open(encoding='utf-8') as f:
        for row in csv.DictReader(f):
            p=info.parent/row['midi_filename']
            if not p.exists():continue
            m=parse_midi(p); files+=1; bpm=float(row['bpm']); beat=60.0/bpm; step=beat/4
            times=sorted(n['start'] for n in m['notes']); file_density.append(len(times)/max(m['duration'],1e-6)); style=(row.get('style') or 'unknown').split('/')[0]
            for n in m['notes']:
                hits+=1; r=role(n['pitch']); t=n['start']; off=(t-round(t/step)*step)*1000
                if abs(off)<=step*1000*.48:
                    by_role[r].append(off); by_style_role[(style,r)].append(off)
                vel_role[r].append(n['velocity']); d=density_at(times,t); fast_hits[density_bin(d)]+=1
                if r in ('hihat','ride'):
                    phase=(t%beat)/beat
                    if .35<=phase<=.78:swing[style].append(phase)
    return {'source':'Groove MIDI Dataset','files':files,'hits':hits,'timing_offset_ms_by_role':{k:robust(v) for k,v in sorted(by_role.items())},'velocity_by_role':{k:robust(v) for k,v in sorted(vel_role.items())},'timing_offset_ms_by_style_role':{f'{s}/{r}':robust(v) for (s,r),v in sorted(by_style_role.items()) if len(v)>=40},'swing_second_eighth_phase_by_style':{k:robust(v) for k,v in sorted(swing.items()) if len(v)>=30},'file_hit_density_hz':robust(file_density),'hit_density_bins':dict(fast_hits)}

def ann_times(path):
    out=[]
    try:
        for line in Path(path).read_text(encoding='utf-8',errors='replace').splitlines():
            ps=line.split('\t')
            if len(ps)<3:continue
            lab=ps[2].split(',')[0].strip()
            if lab in ('b','db','bR'):out.append(float(ps[0]))
    except Exception:return []
    return out

def interp(xs,ys,x):
    if len(xs)<2:return None
    j=bisect.bisect_right(xs,x)-1; j=max(0,min(j,len(xs)-2)); dx=xs[j+1]-xs[j]
    if dx<=0:return ys[j]
    a=(x-xs[j])/dx; return ys[j]+a*(ys[j+1]-ys[j])

def greedy_match(score_notes,perf_notes,score_beats,perf_beats,tol=.22):
    by_pitch=defaultdict(list)
    for i,n in enumerate(perf_notes):by_pitch[n['pitch']].append((n['start'],i,n))
    used=set(); matches=[]
    for sn in sorted(score_notes,key=lambda x:(x['start'],x['pitch'])):
        target=interp(score_beats,perf_beats,sn['start'])
        if target is None:continue
        arr=by_pitch.get(sn['pitch'],[]); ts=[x[0] for x in arr]; j=bisect.bisect_left(ts,target); cand=[]
        for k in (j-2,j-1,j,j+1,j+2):
            if 0<=k<len(arr) and arr[k][1] not in used:cand.append(arr[k])
        if not cand:continue
        best=min(cand,key=lambda x:abs(x[0]-target))
        if abs(best[0]-target)<=tol:
            used.add(best[1]); matches.append((sn,best[2],target))
    return matches

def analyze_asap(root):
    root=Path(root); meta=root/'metadata.csv'; residual=[]; vel=[]; gate=[]; chord_spread=[]; dens=[]; residual_by_density=defaultdict(list)
    perf_count=0; aligned_count=0; matched=0; score_notes_total=0
    with meta.open(encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            mp=row.get('midi_performance',''); ms=row.get('midi_score',''); pa=row.get('performance_annotations') or row.get('performance_anotations',''); sa=row.get('midi_score_annotations','')
            if not mp or not ms or not pa or not sa:continue
            pp=root/mp; sp=root/ms; pap=root/pa; sap=root/sa
            if not all(x.exists() for x in [pp,sp,pap,sap]):continue
            perf_count+=1; pb=ann_times(pap); sb=ann_times(sap)
            if len(pb)<4 or len(pb)!=len(sb):continue
            try:pm=parse_midi(pp); sm=parse_midi(sp)
            except Exception:continue
            aligned_count+=1; pn=pm['notes']; sn=sm['notes']; score_notes_total+=len(sn); ptimes=sorted(n['start'] for n in pn); msx=greedy_match(sn,pn,sb,pb); matched+=len(msx); groups=defaultdict(list)
            for s,p,tgt in msx:
                r=(p['start']-tgt)*1000; residual.append(r); vel.append(p['velocity']); d=density_at(ptimes,p['start']); dens.append(d); residual_by_density[density_bin(d)].append(r); mapped_end=interp(sb,pb,s['end'])
                if mapped_end is not None and mapped_end>tgt and p['end']>p['start']:gate.append((p['end']-p['start'])/(mapped_end-tgt))
                groups[round(s['start'],3)].append(p['start'])
            for g in groups.values():
                if len(g)>=2:chord_spread.append((max(g)-min(g))*1000)
    return {'source':'ASAP','performances_seen':perf_count,'aligned_performances_used':aligned_count,'score_notes_total':score_notes_total,'matched_notes':matched,'match_rate':matched/max(score_notes_total,1),'microtiming_residual_ms':robust(residual),'microtiming_abs_ms':robust([abs(x) for x in residual]),'microtiming_residual_ms_by_density':{k:robust(v) for k,v in sorted(residual_by_density.items())},'velocity':robust(vel),'gate_ratio_performance_over_locally_warped_score':robust(gate),'canonical_chord_spread_ms_in_performance':robust(chord_spread),'local_note_density_hz':robust(dens)}

def chord_spreads(notes,tol=.003):
    notes=sorted(notes,key=lambda n:n['start']); out=[]; i=0
    while i<len(notes):
        j=i+1
        while j<len(notes) and notes[j]['start']-notes[i]['start']<=tol:j+=1
        if j-i>=2:out.append((max(n['start'] for n in notes[i:j])-min(n['start'] for n in notes[i:j]))*1000)
        i=j
    return out

def generic_performance_stats(root,name):
    root=Path(root); mids=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.mid','.midi'}]; velocities=[]; gates=[]; spreads=[]; densities=[]; fastmax=[]; pedal=0; files=0; notes_total=0
    for p in mids:
        try:m=parse_midi(p)
        except Exception:continue
        if not m['notes']:continue
        files+=1; notes_total+=len(m['notes']); velocities.extend(n['velocity'] for n in m['notes']); gates.extend(max(0,n['end']-n['start']) for n in m['notes']); spreads.extend(chord_spreads(m['notes'],.06)); times=sorted(n['start'] for n in m['notes']); densities.append(len(times)/max(m['duration'],1e-6))
        if times:fastmax.append(max(density_at(times,t) for t in times))
        pedal+=sum(1 for c in m['cc'] if c['control']==64)
    return {'source':name,'midi_files_used':files,'notes':notes_total,'velocity':robust(velocities),'note_duration_sec':robust(gates),'chord_spread_ms_60ms_group':robust(spreads),'whole_file_note_density_hz':robust(densities),'max_local_note_density_hz':robust(fastmax),'pedal_cc64_events':pedal}

def analyze_pop909(root):
    root=Path(root); files=[]; base=root/'POP909'
    if base.exists():
        for d in sorted(base.iterdir()):
            if d.is_dir():
                p=d/(d.name+'.mid')
                if p.exists():files.append(p)
    densities=[]; maxdens=[]; velocities=[]; spreads=[]; note_counts=[]; track_names=Counter()
    for p in files:
        try:m=parse_midi(p)
        except Exception:continue
        ns=m['notes']; note_counts.append(len(ns)); velocities.extend(n['velocity'] for n in ns); times=sorted(n['start'] for n in ns); densities.append(len(ns)/max(m['duration'],1e-6))
        if times:maxdens.append(max(density_at(times,t) for t in times))
        spreads.extend(chord_spreads(ns,.01))
        for tr in m['tracks']:
            if tr['name']:track_names[tr['name']]+=1
    return {'source':'POP909','canonical_songs_used':len(files),'notes_per_song':robust(note_counts),'whole_file_note_density_hz':robust(densities),'max_local_note_density_hz':robust(maxdens),'velocity':robust(velocities),'canonical_chord_spread_ms_10ms_group':robust(spreads),'track_name_counts':dict(track_names)}

def calibration(gmd,asap,ep,pop):
    drum={}
    for r,s in gmd['timing_offset_ms_by_role'].items():
        if s.get('n',0)>=100:
            v=gmd['velocity_by_role'].get(r,{})
            drum[r]={'timing_median_ms':s['median'],'timing_mad_ms':s['mad'],'timing_p90_abs_proxy_ms':max(abs(s['p10']),abs(s['p90'])),'velocity_median':v.get('median'),'velocity_mad':v.get('mad'),'source':'GMD','evidence':'REAL_CAPTURED_MIDI'}
    bins=asap['microtiming_residual_ms_by_density']; base=[]
    for k in ('lt4','4_8'):
        if bins.get(k,{}).get('n',0):base.append(bins[k]['mad'])
    base_mad=statistics.fmean(base) if base else max(asap['microtiming_residual_ms'].get('mad',1),1); scale={}
    for k in ('lt4','4_8','8_12','12_16','ge16'):
        s=bins.get(k,{})
        if s.get('n',0)>=100:scale[k]=max(.12,min(1.25,s['mad']/max(base_mad,1e-6)))
    return {'calibration_version':'empirical-2026-08-28.1','render_audio_enabled':False,'automatic_calibration_sources':['GMD','ASAP'],'advisory_only_sources':['International Piano e-Competition mirror','POP909'],'drums':drum,'piano':{'microtiming_residual_ms':asap['microtiming_residual_ms'],'microtiming_abs_ms':asap['microtiming_abs_ms'],'chord_spread_ms':asap['canonical_chord_spread_ms_in_performance'],'velocity':asap['velocity'],'gate_ratio':asap['gate_ratio_performance_over_locally_warped_score'],'timing_scale_by_density':scale,'source':'ASAP','evidence':'REAL_SCORE_ALIGNED_PERFORMANCE_MIDI'},'fast_passage_reference':{'asap_local_note_density_hz':asap['local_note_density_hz'],'e_piano_max_local_note_density_hz_advisory':ep['max_local_note_density_hz'],'pop909_max_local_note_density_hz_structural':pop['max_local_note_density_hz'],'planner_rule':'timing variance must not increase with local density; preserve distinct-onset ordering'},'rights_notes':{'GMD':'CC BY 4.0','ASAP':'CC BY-NC-SA 4.0; research/non-commercial calibration tier','e_piano':'underlying MIDI license unclear; aggregate advisory statistics only','POP909':'repository MIT but underlying popular-song rights require separate treatment; structural advisory statistics only'}}

def write_json(path,obj):
    Path(path).parent.mkdir(parents=True,exist_ok=True); Path(path).write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--gmd',required=True); ap.add_argument('--asap',required=True); ap.add_argument('--epiano',required=True); ap.add_argument('--pop909',required=True); ap.add_argument('--output',required=True); a=ap.parse_args(); out=Path(a.output); out.mkdir(parents=True,exist_ok=True)
    g=analyze_gmd(a.gmd); write_json(out/'gmd.json',g); s=analyze_asap(a.asap); write_json(out/'asap.json',s); e=generic_performance_stats(a.epiano,'International Piano e-Competition mirror'); write_json(out/'epiano.json',e); p=analyze_pop909(a.pop909); write_json(out/'pop909.json',p); cal=calibration(g,s,e,p); write_json(out/'humanization_empirical_calibration.json',cal)
    summary={'status':'PASS' if g['files']>=1000 and s['aligned_performances_used']>=900 and p['canonical_songs_used']>=900 else 'PARTIAL','audio_rendered':False,'sources':{'gmd':{'files':g['files'],'hits':g['hits']},'asap':{'aligned_performances':s['aligned_performances_used'],'matched_notes':s['matched_notes'],'match_rate':s['match_rate']},'epiano':{'files':e['midi_files_used'],'advisory_only':True},'pop909':{'songs':p['canonical_songs_used'],'structural_only':True}},'automatic_defaults_calibrated_from':['GMD drums','ASAP piano'],'not_calibrated_due_to_missing_direct_performance_evidence':['bass','guitar','strings','brass','woodwinds','voice','synth'],'render_hold':True}
    write_json(out/'summary.json',summary); files=[x for x in out.iterdir() if x.is_file() and x.name!='SHA256SUMS']; lines=[hashlib.sha256(x.read_bytes()).hexdigest()+'  '+x.name for x in sorted(files)]; (out/'SHA256SUMS').write_text('\n'.join(lines)+'\n'); print(json.dumps(summary,indent=2))
if __name__=='__main__':main()
