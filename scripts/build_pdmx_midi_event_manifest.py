#!/usr/bin/env python3
from __future__ import annotations
import argparse, bisect, csv, gzip, hashlib, json, math, os, statistics, re, sys
from collections import Counter, defaultdict, deque
from pathlib import Path
from typing import Any

try:
    import mido
except ImportError as e:
    raise SystemExit('mido is required (pip install mido==1.3.3)') from e

QPPQ = 960
MAJOR_PROFILE = [6.35,2.23,3.48,2.33,4.38,4.09,2.52,5.19,2.39,3.66,2.29,2.88]
MINOR_PROFILE = [6.33,2.68,3.52,5.38,2.60,3.53,2.54,4.75,3.98,2.69,3.34,3.17]
PC_NAMES = ['C','C#','D','D#','E','F','F#','G','G#','A','A#','B']
GM_DRUM_NAMES = {
35:'Acoustic Bass Drum',36:'Bass Drum 1',37:'Side Stick',38:'Acoustic Snare',39:'Hand Clap',40:'Electric Snare',
41:'Low Floor Tom',42:'Closed Hi-Hat',43:'High Floor Tom',44:'Pedal Hi-Hat',45:'Low Tom',46:'Open Hi-Hat',
47:'Low-Mid Tom',48:'Hi-Mid Tom',49:'Crash Cymbal 1',50:'High Tom',51:'Ride Cymbal 1',52:'Chinese Cymbal',
53:'Ride Bell',54:'Tambourine',55:'Splash Cymbal',56:'Cowbell',57:'Crash Cymbal 2',58:'Vibraslap',
59:'Ride Cymbal 2',60:'Hi Bongo',61:'Low Bongo',62:'Mute Hi Conga',63:'Open Hi Conga',64:'Low Conga',
65:'High Timbale',66:'Low Timbale',67:'High Agogo',68:'Low Agogo',69:'Cabasa',70:'Maracas',71:'Short Whistle',
72:'Long Whistle',73:'Short Guiro',74:'Long Guiro',75:'Claves',76:'Hi Wood Block',77:'Low Wood Block',
78:'Mute Cuica',79:'Open Cuica',80:'Mute Triangle',81:'Open Triangle'
}
DRUM_GROUPS = {
    'kick': {35,36}, 'snare': {37,38,40}, 'clap': {39}, 'hihat': {42,44,46},
    'tom': {41,43,45,47,48,50}, 'crash': {49,52,55,57}, 'ride': {51,53,59},
    'aux_percussion': set(range(54,82)) - {55,57,59},
}

FIELDS = [
'record_id','mid_path','parse_ok','parse_error','midi_format','ticks_per_beat','midi_track_count','midi_channel_count',
'duration_ticks','duration_seconds','total_note_count','melodic_note_count','drum_note_count','drum_channel_present',
'distinct_melodic_channels','distinct_programs','program_change_count','program_note_counts_json','drum_note_counts_json','drum_group_counts_json',
'track_names_json','instrument_names_json','tempo_event_count','tempo_change_count','initial_bpm','tempo_bpm_min','tempo_bpm_max','tempo_bpm_median_event','tempo_bpm_time_weighted_mean',
'time_signature_event_count','meter_change_count','primary_meter','meter_sequence_json','key_signature_event_count','declared_primary_key','declared_key_sequence_json',
'estimated_key','estimated_mode','key_estimation_score','key_estimation_margin','pitch_min','pitch_max','pitch_range_semitones','pitch_class_histogram_json',
'velocity_mean','velocity_std','velocity_p10','velocity_p50','velocity_p90','duration_beats_mean','duration_beats_median','duration_beats_p90',
'onset_density_notes_per_second','polyphony_max','polyphony_time_weighted_mean','polyphony_fraction_time_gt1','unmatched_note_on_count','orphan_note_off_count',
'symbolic_fingerprint_score','symbolic_fingerprint_with_velocity','symbolic_fingerprint_transposition_invariant','event_preprocess_version'
]


def percentile(vals, q):
    if not vals: return 0.0
    s=sorted(vals); pos=(len(s)-1)*q; lo=int(math.floor(pos)); hi=int(math.ceil(pos))
    if lo==hi: return float(s[lo])
    return float(s[lo]*(hi-pos)+s[hi]*(pos-lo))

def corr(a,b):
    ma=sum(a)/len(a); mb=sum(b)/len(b)
    da=[x-ma for x in a]; db=[x-mb for x in b]
    den=math.sqrt(sum(x*x for x in da)*sum(x*x for x in db))
    return 0.0 if den==0 else sum(x*y for x,y in zip(da,db))/den

def rotate_profile(profile, tonic):
    # profile index 0 corresponds tonic; rotate so pitch class tonic receives profile[0]
    out=[0.0]*12
    for i,v in enumerate(profile): out[(i+tonic)%12]=v
    return out

def estimate_key(pc_weights):
    total=sum(pc_weights)
    if total<=0: return ('','',0.0,0.0)
    scores=[]
    for tonic in range(12):
        scores.append((corr(pc_weights, rotate_profile(MAJOR_PROFILE, tonic)), tonic, 'major'))
        scores.append((corr(pc_weights, rotate_profile(MINOR_PROFILE, tonic)), tonic, 'minor'))
    scores.sort(reverse=True)
    s1,pc,mode=scores[0]; s2=scores[1][0]
    name=PC_NAMES[pc] + (' major' if mode=='major' else ' minor')
    return name, mode, round(s1,6), round(s1-s2,6)

def safe_json(v): return json.dumps(v,ensure_ascii=False,separators=(',',':'))
def norm_path(p):
    s=str(p or '').strip().replace('\\','/')
    while s.startswith('./'): s=s[2:]
    return s

def hash_lines(lines):
    h=hashlib.sha256()
    for line in lines:
        h.update(line.encode('utf-8')); h.update(b'\n')
    return h.hexdigest()

def qtick(t, ppq): return int(round(t*QPPQ/max(1,ppq)))

def tempo_segments(tempo_events, end_tick, ppq):
    # list unique tempo changes sorted; last event at same tick wins
    d={0:500000}
    for tick,tempo in tempo_events: d[int(tick)]=int(tempo)
    ev=sorted(d.items())
    seg=[]; cumulative=0.0
    for i,(tick,tempo) in enumerate(ev):
        next_tick = ev[i+1][0] if i+1<len(ev) else end_tick
        if next_tick < tick: continue
        seg.append((tick,cumulative,tempo))
        cumulative += (next_tick-tick)*tempo/1_000_000.0/ppq
    ticks=[x[0] for x in seg]
    def to_seconds(t):
        if not seg: return t*0.5/ppq
        i=bisect.bisect_right(ticks,t)-1; i=max(0,i)
        tick,cum,tempo=seg[i]
        return cum+(t-tick)*tempo/1_000_000.0/ppq
    return seg,to_seconds

def dominant_timeline(events, end_tick, default_value):
    d={0:default_value}
    for tick,val in events: d[int(tick)]=val
    ev=sorted(d.items())
    dur=Counter()
    for i,(tick,val) in enumerate(ev):
        nt=ev[i+1][0] if i+1<len(ev) else end_tick
        if nt>=tick: dur[val]+=nt-tick
    primary=max(dur.items(),key=lambda kv:(kv[1],str(kv[0])))[0] if dur else default_value
    return primary,ev,dur

def parse_midi(path: Path, record_id: str, mid_rel: str):
    base={k:'' for k in FIELDS}; base.update({'record_id':record_id,'mid_path':mid_rel,'parse_ok':0,'event_preprocess_version':'v1-midi-event-full'})
    try:
        mf=mido.MidiFile(path, clip=True)
        if mf.ticks_per_beat <= 0: raise ValueError(f'invalid ticks_per_beat {mf.ticks_per_beat}')
        ppq=mf.ticks_per_beat
        tempo_events=[]; meter_events=[]; key_events=[]; program_changes=0
        track_names=[]; instrument_names=[]; max_tick=0
        # current program is per MIDI channel across file; process tracks independently by absolute tick then sort all events globally
        all_events=[]
        for ti,tr in enumerate(mf.tracks):
            tick=0
            for oi,msg in enumerate(tr):
                tick += msg.time; max_tick=max(max_tick,tick)
                if msg.type=='track_name' and msg.name: track_names.append({'track':ti,'name':msg.name})
                elif msg.type=='instrument_name' and msg.name: instrument_names.append({'track':ti,'name':msg.name})
                elif msg.type=='set_tempo': tempo_events.append((tick,msg.tempo))
                elif msg.type=='time_signature': meter_events.append((tick,f'{msg.numerator}/{msg.denominator}'))
                elif msg.type=='key_signature': key_events.append((tick,msg.key))
                if hasattr(msg,'channel') or msg.type in ('program_change','note_on','note_off'):
                    all_events.append((tick,ti,oi,msg))
        all_events.sort(key=lambda x:(x[0],x[1],x[2]))
        programs=[0]*16; active=defaultdict(deque); notes=[]; orphan_off=0
        channels=set(); melodic_channels=set(); drum_present=False
        prog_note_counts=Counter(); drum_counts=Counter(); pc_weights=[0.0]*12
        for tick,ti,oi,msg in all_events:
            ch=getattr(msg,'channel',None)
            if ch is not None: channels.add(ch)
            if msg.type=='program_change':
                programs[msg.channel]=msg.program; program_changes+=1
                continue
            if msg.type=='note_on' and msg.velocity>0:
                is_drum=(msg.channel==9); drum_present |= is_drum
                if not is_drum: melodic_channels.add(msg.channel)
                active[(msg.channel,msg.note)].append((tick,msg.velocity,programs[msg.channel],ti,is_drum))
            elif msg.type=='note_off' or (msg.type=='note_on' and msg.velocity==0):
                key=(msg.channel,msg.note)
                if active[key]:
                    st,vel,prog,track,is_drum=active[key].popleft()
                    if tick < st: continue
                    notes.append((st,tick,msg.note,vel,prog,msg.channel,track,is_drum))
                    if is_drum: drum_counts[msg.note]+=1
                    else: prog_note_counts[prog]+=1
                else: orphan_off += 1
        unmatched=sum(len(v) for v in active.values())
        seg,to_sec=tempo_segments(tempo_events,max_tick,ppq)
        duration_seconds=to_sec(max_tick)
        durations_beats=[]; velocities=[]; melodic_notes=[]; drum_notes=[]; sweep=[]
        pitch_min=128; pitch_max=-1
        for st,en,pitch,vel,prog,ch,track,is_drum in notes:
            db=(en-st)/ppq; durations_beats.append(db); velocities.append(vel)
            if is_drum: drum_notes.append((st,en,pitch,vel,prog,ch,track,is_drum))
            else:
                melodic_notes.append((st,en,pitch,vel,prog,ch,track,is_drum)); pitch_min=min(pitch_min,pitch); pitch_max=max(pitch_max,pitch)
                pc_weights[pitch%12] += max(db, 1/ppq)
            if en>st: sweep.append((st,1)); sweep.append((en,-1))
        # polyphony, end before start at same tick
        sweep.sort(key=lambda x:(x[0],x[1]))
        cur=0; prev=0; weighted=0; gt1=0; maxpoly=0
        for tick,delta in sweep:
            dt=tick-prev
            if dt>0: weighted += cur*dt; gt1 += (dt if cur>1 else 0)
            cur += delta; maxpoly=max(maxpoly,cur); prev=tick
        poly_mean=weighted/max_tick if max_tick>0 else 0.0; poly_frac=gt1/max_tick if max_tick>0 else 0.0
        # tempo stats
        tempo_dict={0:500000}
        for tick,t in tempo_events: tempo_dict[tick]=t
        tempo_list=sorted(tempo_dict.items())
        bpms=[60_000_000/t for _,t in tempo_list]
        tw_num=0.0; tw_den=0
        for i,(tick,t) in enumerate(tempo_list):
            nt=tempo_list[i+1][0] if i+1<len(tempo_list) else max_tick; dt=max(0,nt-tick)
            tw_num += (60_000_000/t)*dt; tw_den+=dt
        primary_meter,meter_seq,_=dominant_timeline(meter_events,max_tick,'4/4')
        primary_key,key_seq,_=dominant_timeline(key_events,max_tick,'')
        est_key,est_mode,est_score,est_margin=estimate_key(pc_weights)
        # fingerprints normalized to beats; score fingerprint ignores velocity and channel but keeps program/drum identity
        score_lines=[]; vel_lines=[]; trans_lines=[]
        first_pitch = melodic_notes[0][2] if melodic_notes else 0
        for st,en,pitch,vel,prog,ch,track,is_drum in sorted(notes,key=lambda n:(n[0],n[2],n[4],n[5],n[1],n[3])):
            qs,qd=qtick(st,ppq),max(0,qtick(en-st,ppq)); ident=(128+pitch if is_drum else prog)
            score_lines.append(f'{qs},{qd},{pitch},{ident}')
            vel_lines.append(f'{qs},{qd},{pitch},{ident},{vel}')
            if not is_drum: trans_lines.append(f'{qs},{qd},{pitch-first_pitch}')
            else: trans_lines.append(f'{qs},{qd},D{pitch}')
        drum_groups={g:sum(drum_counts[n] for n in ns) for g,ns in DRUM_GROUPS.items() if sum(drum_counts[n] for n in ns)}
        base.update({
            'parse_ok':1,'midi_format':mf.type,'ticks_per_beat':ppq,'midi_track_count':len(mf.tracks),'midi_channel_count':len(channels),
            'duration_ticks':max_tick,'duration_seconds':round(duration_seconds,6),'total_note_count':len(notes),'melodic_note_count':len(melodic_notes),'drum_note_count':len(drum_notes),'drum_channel_present':int(drum_present),
            'distinct_melodic_channels':len(melodic_channels),'distinct_programs':len(prog_note_counts),'program_change_count':program_changes,'program_note_counts_json':safe_json(dict(sorted(prog_note_counts.items()))),
            'drum_note_counts_json':safe_json(dict(sorted(drum_counts.items()))),'drum_group_counts_json':safe_json(drum_groups),'track_names_json':safe_json(track_names),'instrument_names_json':safe_json(instrument_names),
            'tempo_event_count':len(tempo_events),'tempo_change_count':max(0,len(tempo_list)-1),'initial_bpm':round(bpms[0],6) if bpms else 120.0,'tempo_bpm_min':round(min(bpms),6) if bpms else 120.0,'tempo_bpm_max':round(max(bpms),6) if bpms else 120.0,
            'tempo_bpm_median_event':round(statistics.median(bpms),6) if bpms else 120.0,'tempo_bpm_time_weighted_mean':round(tw_num/tw_den,6) if tw_den else (round(bpms[0],6) if bpms else 120.0),
            'time_signature_event_count':len(meter_events),'meter_change_count':max(0,len(meter_seq)-1),'primary_meter':primary_meter,'meter_sequence_json':safe_json(meter_seq),
            'key_signature_event_count':len(key_events),'declared_primary_key':primary_key,'declared_key_sequence_json':safe_json(key_seq),'estimated_key':est_key,'estimated_mode':est_mode,'key_estimation_score':est_score,'key_estimation_margin':est_margin,
            'pitch_min':('' if pitch_max<0 else pitch_min),'pitch_max':('' if pitch_max<0 else pitch_max),'pitch_range_semitones':(0 if pitch_max<0 else pitch_max-pitch_min),'pitch_class_histogram_json':safe_json([round(x,6) for x in pc_weights]),
            'velocity_mean':round(statistics.mean(velocities),6) if velocities else 0.0,'velocity_std':round(statistics.pstdev(velocities),6) if len(velocities)>1 else 0.0,'velocity_p10':round(percentile(velocities,.1),6),'velocity_p50':round(percentile(velocities,.5),6),'velocity_p90':round(percentile(velocities,.9),6),
            'duration_beats_mean':round(statistics.mean(durations_beats),6) if durations_beats else 0.0,'duration_beats_median':round(percentile(durations_beats,.5),6),'duration_beats_p90':round(percentile(durations_beats,.9),6),
            'onset_density_notes_per_second':round(len(notes)/duration_seconds,6) if duration_seconds>0 else 0.0,'polyphony_max':maxpoly,'polyphony_time_weighted_mean':round(poly_mean,6),'polyphony_fraction_time_gt1':round(poly_frac,6),
            'unmatched_note_on_count':unmatched,'orphan_note_off_count':orphan_off,'symbolic_fingerprint_score':hash_lines(score_lines),'symbolic_fingerprint_with_velocity':hash_lines(vel_lines),'symbolic_fingerprint_transposition_invariant':hash_lines(trans_lines)
        })
        return base, prog_note_counts, drum_counts
    except Exception as e:
        base['parse_error']=f'{type(e).__name__}: {e}'[:500]
        return base, Counter(), Counter()

def iter_records(root: Path):
    for p in sorted((root/'records').glob('*.csv.gz')):
        with gzip.open(p,'rt',encoding='utf-8-sig',newline='') as f:
            yield from csv.DictReader(f)

def write_shard(outdir, idx, rows):
    p=outdir/f'part-{idx:05d}.csv.gz'
    with gzip.open(p,'wt',encoding='utf-8',newline='',compresslevel=9) as f:
        w=csv.DictWriter(f,fieldnames=FIELDS,extrasaction='ignore'); w.writeheader(); w.writerows(rows)
    return p

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--records-root',required=True); ap.add_argument('--midi-root',required=True); ap.add_argument('--output',required=True); ap.add_argument('--shard-size',type=int,default=20000); ap.add_argument('--expected-records',type=int,default=77321)
    args=ap.parse_args(); root=Path(args.records_root); midi_root=Path(args.midi_root); out=Path(args.output); rec_out=out/'records'; rec_out.mkdir(parents=True,exist_ok=True)
    rows=[]; index=[]; total=ok=0; parse_errors=[]; program_records=Counter(); program_notes=Counter(); drum_records=Counter(); drum_notes=Counter(); meter_counts=Counter(); declared_key_counts=Counter(); estimated_key_counts=Counter(); tempo_bins=Counter(); fp_groups=defaultdict(list); trans_groups=defaultdict(list)
    def flush():
        nonlocal rows
        if not rows: return
        p=write_shard(rec_out,len(index)+1,rows); index.append((p.name,len(rows),sha256(p))); rows=[]
    for src in iter_records(root):
        total+=1; rid=src.get('record_id',''); rel=norm_path(src.get('mid','') or src.get('mid_path',''))
        # records manifest field is 'mid'; training manifest field is 'mid_path'.
        path=midi_root/rel
        if not path.exists() and rel.startswith('mid/'):
            path=midi_root/rel[4:]
        parsed,pc,dc=parse_midi(path,rid,rel) if path.exists() else ({**{k:'' for k in FIELDS},'record_id':rid,'mid_path':rel,'parse_ok':0,'parse_error':'FileNotFoundError: MIDI asset missing','event_preprocess_version':'v1-midi-event-full'},Counter(),Counter())
        if parsed['parse_ok']:
            ok+=1
            for p,c in pc.items(): program_records[p]+=1; program_notes[p]+=c
            for n,c in dc.items(): drum_records[n]+=1; drum_notes[n]+=c
            meter_counts[str(parsed['primary_meter'])]+=1
            if parsed['declared_primary_key']: declared_key_counts[str(parsed['declared_primary_key'])]+=1
            if parsed['estimated_key']: estimated_key_counts[str(parsed['estimated_key'])]+=1
            try:
                bpm=float(parsed['tempo_bpm_time_weighted_mean']); lo=int(bpm//10*10); tempo_bins[f'{lo}-{lo+9}']+=1
            except: pass
            fp_groups[str(parsed['symbolic_fingerprint_score'])].append(rid); trans_groups[str(parsed['symbolic_fingerprint_transposition_invariant'])].append(rid)
        else: parse_errors.append({'record_id':rid,'mid_path':rel,'error':parsed['parse_error']})
        rows.append(parsed)
        if len(rows)>=args.shard_size: flush()
    flush()
    if total!=args.expected_records: raise RuntimeError(f'record count {total} != expected {args.expected_records}')
    # indexes and distributions
    with (out/'record_shards.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow(['file','rows','sha256']); w.writerows(index)
    def write_counter(name, headers, counter, extra=None):
        with (out/name).open('w',encoding='utf-8',newline='') as f:
            w=csv.writer(f); w.writerow(headers)
            for k,v in sorted(counter.items(),key=lambda kv:(-kv[1],str(kv[0]))): w.writerow([k,v] if extra is None else extra(k,v))
    write_counter('meter_distribution.csv',['meter','records'],meter_counts)
    write_counter('declared_key_distribution.csv',['key','records'],declared_key_counts)
    write_counter('estimated_key_distribution.csv',['key','records'],estimated_key_counts)
    write_counter('tempo_distribution_10bpm.csv',['bpm_bin','records'],tempo_bins)
    with (out/'program_note_distribution.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow(['gm_program_0based','records_present','note_count'])
        for p,v in sorted(program_records.items(),key=lambda kv:(-kv[1],kv[0])): w.writerow([p,v,program_notes[p]])
    with (out/'drum_note_distribution.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow(['midi_note','gm_drum_name','records_present','note_count'])
        for n,v in sorted(drum_records.items(),key=lambda kv:(-kv[1],kv[0])): w.writerow([n,GM_DRUM_NAMES.get(n,'non-GM/extended'),v,drum_notes[n]])
    with (out/'parse_errors.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['record_id','mid_path','error']); w.writeheader(); w.writerows(parse_errors)
    dup=[(h,ids) for h,ids in fp_groups.items() if h and len(ids)>1]; tdup=[(h,ids) for h,ids in trans_groups.items() if h and len(ids)>1]
    with (out/'symbolic_duplicate_clusters.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow(['fingerprint','cluster_size','record_ids']);
        for h,ids in sorted(dup,key=lambda x:(-len(x[1]),x[0])): w.writerow([h,len(ids),';'.join(sorted(ids))])
    with (out/'transposition_invariant_candidate_clusters.csv').open('w',encoding='utf-8',newline='') as f:
        w=csv.writer(f); w.writerow(['fingerprint','cluster_size','record_ids','auto_merge']);
        for h,ids in sorted(tdup,key=lambda x:(-len(x[1]),x[0])): w.writerow([h,len(ids),';'.join(sorted(ids)),0])
    summary={
      'source':'PDMX v9 strict symbolic manifest + official mid.tar.gz','input_records':total,'parsed_ok':ok,'parse_failures':total-ok,'parse_success_fraction':round(ok/total,8) if total else 0,
      'midi_event_fields_resolved':['key_signature','estimated_key','tempo_map','time_signature','channel_10_drums','note_count','note_duration','velocity','polyphony','track_names','program_note_counts','symbolic_fingerprints'],
      'rendered_audio_created':False,'rendering_prohibited_in_this_workflow':True,
      'exact_symbolic_duplicate_clusters':len(dup),'exact_symbolic_duplicate_records':sum(len(x[1]) for x in dup),'transposition_invariant_candidate_clusters':len(tdup),
      'validation':{'record_count_exact':total==args.expected_records,'all_midi_parsed':ok==total,'zero_parse_errors':not parse_errors,'shard_rows_sum':sum(x[1] for x in index)==total}
    }
    summary['validation']['passed']=all(summary['validation'].values())
    (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    # hashes
    with (out/'SHA256SUMS').open('w',encoding='utf-8') as f:
        for p in sorted(out.rglob('*')):
            if p.is_file() and p.name!='SHA256SUMS': f.write(f'{sha256(p)}  {p.relative_to(out)}\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    if not summary['validation']['passed']: raise SystemExit(2)

if __name__=='__main__': main()
