#!/usr/bin/env python3
from __future__ import annotations
import argparse, bisect, csv, json, math, re, statistics, xml.etree.ElementTree as ET
from collections import defaultdict, Counter
from difflib import SequenceMatcher
from pathlib import Path

import analyze_expression_corpora as core

# ---------- common ----------
def robust(v): return core.robust(v)
def density_at(t, x): return core.density_at(t, x)
def density_bin(x): return core.density_bin(x)

def cluster_attacks(times, tol=.025):
    a=sorted(float(x) for x in times)
    if not a:return []
    groups=[[a[0]]]
    for t in a[1:]:
        if t-groups[-1][-1] <= tol: groups[-1].append(t)
        else: groups.append([t])
    return [statistics.median(g) for g in groups]

def interp(xs, ys, x):
    if len(xs)<2:return None
    j=bisect.bisect_right(xs,x)-1
    j=max(0,min(j,len(xs)-2)); dx=xs[j+1]-xs[j]
    if dx<=0:return ys[j]
    a=(x-xs[j])/dx
    return ys[j]+a*(ys[j+1]-ys[j])

def nearest_musical_grid_residual(t, beats, max_abs=.055):
    """Residual to local 16th/triplet candidate grid. Reject uncertain events.
    Uses beat interval itself so local tempo variation is removed.
    """
    if len(beats)<2:return None
    j=bisect.bisect_right(beats,t)-1
    if j<0 or j>=len(beats)-1:return None
    a,b=beats[j],beats[j+1]
    dur=b-a
    if dur<=.12 or dur>2.5:return None
    # 16th positions and eighth-triplet positions within a beat.
    phases={0,.25,.5,.75,1/3,2/3}
    cand=[a+p*dur for p in phases]
    best=min(cand,key=lambda q:abs(t-q)); r=t-best
    return r if abs(r)<=max_abs else None

def swing_phase(t, beats):
    if len(beats)<2:return None
    j=bisect.bisect_right(beats,t)-1
    if j<0 or j>=len(beats)-1:return None
    d=beats[j+1]-beats[j]
    if d<=0:return None
    p=(t-beats[j])/d
    return p if .34<=p<=.82 else None

def family_from_program(p, ch=0, name=''):
    n=(name or '').lower()
    if ch==9:return 'drums'
    if re.search(r'vocal|voice|singer|singing|lead vox|melody vocal',n):return 'voice'
    if 0<=p<=23:return 'keys'
    if 24<=p<=31:return 'guitar'
    if 32<=p<=39:return 'bass'
    if 40<=p<=51:return 'strings'
    if 52<=p<=55:return 'voice'
    if 56<=p<=63:return 'brass'
    if 64<=p<=79:return 'woodwinds'
    if 80<=p<=95:return 'synth'
    return 'other'

# ---------- GuitarSet ----------
def _jams_annotations(obj, namespace):
    for ann in obj.get('annotations',[]):
        if ann.get('namespace')==namespace:
            yield ann

def _ann_times(ann):
    out=[]
    for o in ann.get('data',[]):
        try: out.append(float(o.get('time',0)))
        except Exception: pass
    return out

def analyze_guitarset(root):
    root=Path(root); jams=list(root.rglob('*.jams'))
    residual=[]; duration=[]; spreads=[]; density=[]; max_density=[]; phases=[]
    styles=defaultdict(list); file_resid=defaultdict(list); notes_total=0; files=0
    for p in jams:
        try: obj=json.loads(p.read_text(encoding='utf-8'))
        except Exception: continue
        beats=[]
        for ns in ('beat_position','beat'):
            for ann in _jams_annotations(obj,ns): beats.extend(_ann_times(ann))
        beats=sorted(set(round(x,6) for x in beats))
        if len(beats)<4: continue
        notes=[]
        for ann in _jams_annotations(obj,'note_midi'):
            for o in ann.get('data',[]):
                try:
                    t=float(o['time']); d=float(o.get('duration',0)); val=o.get('value')
                    if isinstance(val,dict): pitch=val.get('midi') or val.get('note') or val.get('pitch')
                    else: pitch=val
                    notes.append((t,d,float(pitch) if pitch is not None else None))
                except Exception: continue
        if not notes: continue
        files+=1; notes_total+=len(notes)
        attacks=cluster_attacks([x[0] for x in notes],.018)
        density.extend(density_at(attacks,t) for t in attacks)
        if attacks:max_density.append(max(density_at(attacks,t) for t in attacks))
        for t,d,_ in notes:
            r=nearest_musical_grid_residual(t,beats,.050)
            if r is not None:
                ms=r*1000; residual.append(ms); file_resid[p.stem].append(ms)
            if d>0:duration.append(d)
            ph=swing_phase(t,beats)
            if ph is not None:phases.append(ph)
        # strum spread: cluster string-note attacks into likely chords; exclude wide arpeggios.
        for g in _groups([x[0] for x in notes],.075):
            if len(g)>=2: spreads.append((max(g)-min(g))*1000)
        # style from filename and metadata sandbox, best-effort only.
        style='unknown'
        txt=(p.stem+' '+json.dumps(obj.get('sandbox',{}),ensure_ascii=False)).lower()
        for s in ('funk','jazz','rock','bossa','singer','ss','comp','solo'):
            if s in txt: style=s; break
        for t,_,_ in notes:
            r=nearest_musical_grid_residual(t,beats,.050)
            if r is not None: styles[style].append(r*1000)
    file_mads=[]
    for v in file_resid.values():
        if len(v)>=12:
            m=statistics.median(v); file_mads.append(statistics.median(abs(x-m) for x in v))
    return {
      'source':'GuitarSet','evidence':'REAL_PERFORMANCE_NOTE_ANNOTATION_WITH_BEATS','files':files,'notes':notes_total,
      'microtiming_residual_ms':robust(residual),'per_file_microtiming_mad_ms':robust(file_mads),
      'note_duration_sec':robust(duration),'strum_chord_spread_ms':robust(spreads),
      'local_attack_density_hz':robust(density),'max_local_attack_density_hz':robust(max_density),
      'offbeat_phase':robust(phases),'microtiming_by_style':{k:robust(v) for k,v in sorted(styles.items()) if len(v)>=100},
      'timing_method':'nearest local 16th/triplet candidate using annotated beats; >50ms residual rejected to avoid treating rhythmic content as performance error'
    }

def _groups(times,tol):
    a=sorted(times)
    if not a:return []
    g=[[a[0]]]
    for t in a[1:]:
        if t-g[-1][-1]<=tol:g[-1].append(t)
        else:g.append([t])
    return g

# ---------- IDMT bass ----------
def analyze_idmt_bass(root):
    root=Path(root); mids=[p for p in root.rglob('*') if p.is_file() and p.suffix.lower() in {'.mid','.midi'}]
    durations=[]; densities=[]; maxdens=[]; velocities=[]; notes_total=0; files=0
    for p in mids:
        try:m=core.parse_midi(p)
        except Exception:continue
        ns=m['notes']
        if not ns:continue
        files+=1; notes_total+=len(ns); velocities.extend(n['velocity'] for n in ns); durations.extend(max(0,n['end']-n['start']) for n in ns)
        att=cluster_attacks([n['start'] for n in ns],.018); densities.append(len(att)/max(m['duration'],1e-6))
        if att:maxdens.append(max(density_at(att,t) for t in att))
    # Generic XML note annotation discovery for real onset/offset values; no timing residual without beat/score alignment.
    xml_durs=[]; xml_onsets=[]; xml_records=0
    for p in root.rglob('*.xml'):
        try:tree=ET.parse(p)
        except Exception:continue
        for elem in tree.iter():
            vals={}
            for c in list(elem):
                tag=c.tag.split('}')[-1].lower(); text=(c.text or '').strip()
                if text:vals[tag]=text
            onset=_first_float(vals,['onset','start','starttime','onsettime','onset_sec','onsetsec'])
            offset=_first_float(vals,['offset','end','endtime','offsettime','offset_sec','offsetsec'])
            dur=_first_float(vals,['duration','duration_sec','durationsec'])
            if onset is not None and (offset is not None or dur is not None):
                xml_records+=1; xml_onsets.append(onset)
                dd=(offset-onset) if offset is not None else dur
                if dd is not None and dd>0:xml_durs.append(dd)
    return {
      'source':'IDMT-SMT-Bass-Single-Track','evidence':'REAL_BASS_NOTE_ANNOTATION_ARTICULATION; TIMING_GRID_NOT_DIRECTLY_AVAILABLE',
      'midi_files':files,'midi_notes':notes_total,'midi_note_duration_sec':robust(durations),'midi_velocity':robust(velocities),
      'midi_whole_file_attack_density_hz':robust(densities),'midi_max_local_attack_density_hz':robust(maxdens),
      'xml_note_records_detected':xml_records,'xml_note_duration_sec':robust(xml_durs),
      'timing_calibration_allowed':False,
      'reason':'dataset supplies real bass note onset/offset annotations, but no reliable canonical beat grid was assumed; use for gate/density/articulation, not microtiming offset'
    }

def _first_float(d,keys):
    for k in keys:
        if k in d:
            try:return float(re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?',d[k])[0])
            except Exception:pass
    return None

# ---------- URMP ----------
URMP_GM={'vn':40,'va':41,'vc':42,'db':43,'fl':73,'ob':68,'cl':71,'sax':65,'bn':70,'tpt':56,'hn':60,'tbn':57,'tba':58}
URMP_FAM={'vn':'strings','va':'strings','vc':'strings','db':'bass','fl':'woodwinds','ob':'woodwinds','cl':'woodwinds','sax':'woodwinds','bn':'woodwinds','tpt':'brass','hn':'brass','tbn':'brass','tba':'brass'}

def _freq_pitch(f):
    if f<=0:return None
    return int(round(69+12*math.log2(f/440.0)))

def _read_urmp_notes(p):
    out=[]
    for line in p.read_text(errors='replace').splitlines():
        nums=re.findall(r'[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?',line)
        if len(nums)<3:continue
        try:on,f,d=map(float,nums[:3]); pitch=_freq_pitch(f)
        except Exception:continue
        if pitch is not None and d>=0:out.append({'start':on,'end':on+d,'pitch':pitch})
    return out

def _score_tracks_by_program(m):
    d=defaultdict(list)
    for n in m['notes']:d[(n['track'],n['program'])].append(n)
    return d

def _best_score_part(m, code, part_no, actual):
    candidates=_score_tracks_by_program(m); target=URMP_GM.get(code)
    ap=[n['pitch'] for n in actual]
    best=None
    for (tr,pr),ns in candidates.items():
        sp=[n['pitch'] for n in sorted(ns,key=lambda x:(x['start'],x['pitch']))]
        if len(sp)<4:continue
        ratio=SequenceMatcher(None,sp,ap,autojunk=False).ratio()
        program_bonus=.15 if target is not None and abs(pr-target)<=1 else 0
        index_bonus=.05 if tr in (part_no,part_no-1,part_no+1) else 0
        score=ratio+program_bonus+index_bonus
        if best is None or score>best[0]:best=(score,ns,ratio,tr,pr)
    return best

def _align_pitch_blocks(score,actual):
    ss=sorted(score,key=lambda n:(n['start'],n['pitch'])); aa=sorted(actual,key=lambda n:(n['start'],n['pitch']))
    sm=SequenceMatcher(None,[n['pitch'] for n in ss],[n['pitch'] for n in aa],autojunk=False)
    pairs=[]
    for b in sm.get_matching_blocks():
        for k in range(b.size): pairs.append((ss[b.a+k],aa[b.b+k]))
    return pairs

def analyze_urmp(root):
    root=Path(root); note_files=list(root.rglob('Notes_*.txt')); piece_parts=defaultdict(list)
    rx=re.compile(r'Notes_(\d+)_([A-Za-z]+)_(\d+)_')
    for p in note_files:
        m=rx.search(p.name)
        if not m:continue
        part=int(m.group(1)); code=m.group(2).lower(); pid=m.group(3)
        if code in URMP_FAM:piece_parts[(pid,p.parent)].append((part,code,p))
    fam_res=defaultdict(list); fam_gate=defaultdict(list); fam_density=defaultdict(list); inst_res=defaultdict(list)
    matched_by_fam=Counter(); total_by_fam=Counter(); pieces=0; part_matches=[]
    for (pid,parent),parts in piece_parts.items():
        mids=[p for p in parent.glob('*.mid')]+[p for p in parent.glob('*.midi')]
        if not mids:
            # occasional parent nesting
            mids=[p for p in parent.parent.glob('*.mid')]+[p for p in parent.parent.glob('*.midi')]
        if not mids:continue
        # choose largest score MIDI as likely full score
        mp=max(mids,key=lambda p:p.stat().st_size)
        try:mm=core.parse_midi(mp)
        except Exception:continue
        aligned=[]
        for part,code,np in parts:
            actual=_read_urmp_notes(np); fam=URMP_FAM[code]; total_by_fam[fam]+=len(actual)
            if len(actual)<4:continue
            best=_best_score_part(mm,code,part,actual)
            if not best:continue
            _,score,ratio,tr,pr=best; pairs=_align_pitch_blocks(score,actual)
            if len(pairs)<max(4,min(len(actual),len(score))*.20):continue
            part_matches.append({'piece':pid,'instrument':code,'sequence_ratio':ratio,'matches':len(pairs),'actual_notes':len(actual),'score_track':tr,'program':pr})
            matched_by_fam[fam]+=len(pairs); aligned.append((code,fam,pairs))
        if not aligned:continue
        # Ensemble-shared warp anchors: canonical onset -> median actual onset across all parts.
        anchor=defaultdict(list)
        for code,fam,pairs in aligned:
            for s,a in pairs:anchor[round(s['start'],3)].append(a['start'])
        xs=[];ys=[]
        for x,v in sorted(anchor.items()):
            if v:xs.append(x);ys.append(statistics.median(v))
        if len(xs)<4:continue
        pieces+=1
        for code,fam,pairs in aligned:
            score_att=sorted(set(round(s['start'],6) for s,_ in pairs))
            for s,a in pairs:
                target=interp(xs,ys,s['start'])
                if target is None:continue
                r=(a['start']-target)*1000
                if abs(r)<=250: fam_res[fam].append(r); inst_res[code].append(r)
                mapped_end=interp(xs,ys,s['end'])
                if mapped_end is not None and mapped_end>target and a['end']>a['start']:
                    q=(a['end']-a['start'])/(mapped_end-target)
                    if 0<q<8:fam_gate[fam].append(q)
                fam_density[fam].append(density_at(score_att,s['start']))
    return {
      'source':'URMP','evidence':'REAL_SEPARATELY_RECORDED_PERFORMANCE_NOTE_ANNOTATION_ALIGNED_TO_SCORE_MIDI_BY_PITCH_SEQUENCE_AND_SHARED_ENSEMBLE_WARP',
      'pieces_used':pieces,'note_files_seen':len(note_files),'matched_notes_by_family':dict(matched_by_fam),'annotated_notes_by_family':dict(total_by_fam),
      'microtiming_residual_ms_by_family':{k:robust(v) for k,v in sorted(fam_res.items())},
      'microtiming_residual_ms_by_instrument':{k:robust(v) for k,v in sorted(inst_res.items())},
      'gate_ratio_by_family':{k:robust(v) for k,v in sorted(fam_gate.items())},
      'canonical_attack_density_hz_by_family':{k:robust(v) for k,v in sorted(fam_density.items())},
      'part_match_summary':{'parts':len(part_matches),'median_sequence_ratio':statistics.median([x['sequence_ratio'] for x in part_matches]) if part_matches else None},
      'alignment_method':'monotonic pitch SequenceMatcher per part; all parts jointly define a shared piece tempo warp; residual is player-relative onset deviation after that shared warp'
    }

# ---------- RWC aligned MIDI ----------
def _read_beats_csv(p):
    out=[]
    try:
        with p.open(encoding='utf-8-sig') as f:
            r=csv.DictReader(f,delimiter=';')
            for row in r:
                try:out.append(float(row.get('t') or row.get('time')))
                except Exception:pass
    except Exception:return []
    return sorted(out)

def analyze_rwc(root):
    root=Path(root); midi_root=root/'01_annotations_preprocessed'/'MIDI_aligned'; beat_root=root/'01_annotations_preprocessed'/'beats'
    fam_res=defaultdict(list); fam_vel=defaultdict(list); fam_dur=defaultdict(list); fam_density=defaultdict(list); fam_files=defaultdict(set); fam_notes=Counter(); style_fam=defaultdict(list)
    files=0
    for mp in midi_root.rglob('*.mid'):
        rel=mp.relative_to(midi_root); bp=beat_root/rel.with_suffix('.csv')
        if not bp.exists():continue
        beats=_read_beats_csv(bp)
        if len(beats)<4:continue
        try:m=core.parse_midi(mp)
        except Exception:continue
        files+=1; style=rel.parts[0] if rel.parts else 'unknown'
        # family attack times for local density
        byfam=defaultdict(list)
        for n in m['notes']:
            fam=family_from_program(int(n.get('program',0)),int(n.get('channel',0)),str(n.get('track_name','')))
            if fam in {'other','drums'}:continue
            byfam[fam].append(n['start'])
        attacks={k:cluster_attacks(v,.012) for k,v in byfam.items()}
        for n in m['notes']:
            fam=family_from_program(int(n.get('program',0)),int(n.get('channel',0)),str(n.get('track_name','')))
            if fam in {'other','drums'}:continue
            r=nearest_musical_grid_residual(n['start'],beats,.050)
            if r is not None:
                fam_res[fam].append(r*1000); style_fam[(style,fam)].append(r*1000)
            fam_vel[fam].append(n['velocity']); fam_dur[fam].append(max(0,n['end']-n['start'])); fam_notes[fam]+=1; fam_files[fam].add(str(rel))
            if attacks.get(fam): fam_density[fam].append(density_at(attacks[fam],n['start']))
    return {
      'source':'RWC Music Database annotations','evidence':'REAL_SCORE_ALIGNED_PROFESSIONAL_TRANSCRIPTION; LOWER_CONFIDENCE_THAN_DIRECT_CAPTURE',
      'midi_files_with_beats':files,'notes_by_family':dict(fam_notes),'files_by_family':{k:len(v) for k,v in fam_files.items()},
      'microtiming_residual_ms_by_family':{k:robust(v) for k,v in sorted(fam_res.items())},
      'velocity_by_family':{k:robust(v) for k,v in sorted(fam_vel.items())},
      'duration_sec_by_family':{k:robust(v) for k,v in sorted(fam_dur.items())},
      'attack_density_hz_by_family':{k:robust(v) for k,v in sorted(fam_density.items())},
      'microtiming_by_collection_family':{f'{s}/{f}':robust(v) for (s,f),v in sorted(style_fam.items()) if len(v)>=500},
      'timing_method':'aligned MIDI onset residual to annotated beat-local 16th/triplet candidates; >50ms residual rejected',
      'usage':'proxy/cross-check, including voice/synth if sufficient program/name evidence; does not override stronger direct-performance sources'
    }

# ---------- combine ----------
def build_family_calibration(base, guitar, bass, urmp, rwc):
    out={}
    # Preserve direct GMD + ASAP evidence already in base.
    out['drums']={'evidence':'DIRECT_REAL_CAPTURED_MIDI','source':'GMD','roles':base.get('drums',{})}
    out['keys']={'evidence':'DIRECT_REAL_SCORE_ALIGNED_PERFORMANCE_MIDI','source':'ASAP','piano':base.get('piano',{})}
    if guitar.get('notes',0)>=1000:
        out['guitar']={'evidence':'DIRECT_REAL_PERFORMANCE_NOTE_ANNOTATION','source':'GuitarSet','timing':guitar.get('microtiming_residual_ms',{}),'duration':guitar.get('note_duration_sec',{}),'chord_spread':guitar.get('strum_chord_spread_ms',{}),'attack_density':guitar.get('local_attack_density_hz',{})}
    # Bass: direct IDMT controls articulation; use RWC for lower-confidence timing if available.
    br=rwc.get('microtiming_residual_ms_by_family',{}).get('bass',{})
    out['bass']={'evidence':'MIXED: DIRECT_REAL_BASS_ARTICULATION + ALIGNED_TRANSCRIPTION_TIMING_PROXY','sources':['IDMT-SMT-Bass-Single-Track','RWC'], 'timing':br if br.get('n',0)>=500 else {'n':0},'duration':bass.get('xml_note_duration_sec') if bass.get('xml_note_duration_sec',{}).get('n',0) else bass.get('midi_note_duration_sec',{}),'attack_density':rwc.get('attack_density_hz_by_family',{}).get('bass',{})}
    for fam in ('strings','brass','woodwinds'):
        u=urmp.get('microtiming_residual_ms_by_family',{}).get(fam,{})
        if u.get('n',0)>=100:
            out[fam]={'evidence':'DIRECT_REAL_PERFORMANCE_NOTE_ANNOTATION_DERIVED_SCORE_ALIGNMENT','source':'URMP','timing':u,'gate_ratio':urmp.get('gate_ratio_by_family',{}).get(fam,{}),'attack_density':urmp.get('canonical_attack_density_hz_by_family',{}).get(fam,{})}
        else:
            r=rwc.get('microtiming_residual_ms_by_family',{}).get(fam,{})
            out[fam]={'evidence':'ALIGNED_TRANSCRIPTION_PROXY' if r.get('n',0) else 'UNRESOLVED','source':'RWC' if r.get('n',0) else None,'timing':r}
    for fam in ('voice','synth'):
        r=rwc.get('microtiming_residual_ms_by_family',{}).get(fam,{})
        out[fam]={'evidence':'ALIGNED_TRANSCRIPTION_PROXY' if r.get('n',0)>=500 else 'UNRESOLVED','source':'RWC' if r.get('n',0)>=500 else None,'timing':r if r.get('n',0)>=500 else {'n':0},'velocity':rwc.get('velocity_by_family',{}).get(fam,{}),'duration':rwc.get('duration_sec_by_family',{}).get(fam,{}),'attack_density':rwc.get('attack_density_hz_by_family',{}).get(fam,{})}
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--base',required=True,type=Path); ap.add_argument('--guitarset',required=True,type=Path); ap.add_argument('--bass',required=True,type=Path); ap.add_argument('--urmp',required=True,type=Path); ap.add_argument('--rwc',required=True,type=Path); ap.add_argument('--output',required=True,type=Path); a=ap.parse_args()
    base=json.loads(a.base.read_text()); g=analyze_guitarset(a.guitarset); b=analyze_idmt_bass(a.bass); u=analyze_urmp(a.urmp); r=analyze_rwc(a.rwc)
    out=a.output; out.mkdir(parents=True,exist_ok=True)
    for name,obj in [('guitarset.json',g),('idmt_bass.json',b),('urmp.json',u),('rwc.json',r)]: (out/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    fam=build_family_calibration(base,g,b,u,r)
    final=dict(base); final['calibration_version']='empirical-2026-08-28.4-multifamily'; final['render_audio_enabled']=False; final['family_empirical']=fam
    final['evidence_policy']={'direct_preferred_over_proxy':True,'no_audio_rendered':True,'unresolved_is_not_fabricated':True}
    (out/'humanization_empirical_calibration_v4.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    (out/'humanization_empirical_calibration.json').write_text(json.dumps(final,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    status={k:v.get('evidence') for k,v in fam.items()}
    summary={'status':'PASS','audio_rendered':False,'families':status,'guitarset_files':g.get('files',0),'bass_files':b.get('midi_files',0),'urmp_pieces':u.get('pieces_used',0),'rwc_files':r.get('midi_files_with_beats',0)}
    (out/'additional_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
