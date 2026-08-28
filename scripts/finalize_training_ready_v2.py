#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,re,unicodedata
from collections import Counter,defaultdict
from pathlib import Path

SYNTH='SYNTH_RENDERED_MIDI'; PSEUDO='MODEL_PSEUDO_LABEL'
EVENT_KEEP=[
'duration_seconds','total_note_count','melodic_note_count','drum_note_count','drum_channel_present','distinct_programs','program_note_counts_json','drum_note_counts_json','drum_group_counts_json',
'tempo_event_count','tempo_change_count','initial_bpm','tempo_bpm_min','tempo_bpm_max','tempo_bpm_time_weighted_mean','time_signature_event_count','meter_change_count','primary_meter',
'key_signature_event_count','declared_primary_key','estimated_key','estimated_mode','key_estimation_score','key_estimation_margin','pitch_min','pitch_max','pitch_range_semitones',
'velocity_mean','velocity_std','velocity_p10','velocity_p50','velocity_p90','duration_beats_mean','duration_beats_median','duration_beats_p90','onset_density_notes_per_second',
'polyphony_max','polyphony_time_weighted_mean','polyphony_fraction_time_gt1','unmatched_note_on_count','orphan_note_off_count','symbolic_fingerprint_score','symbolic_fingerprint_with_velocity','symbolic_fingerprint_transposition_invariant'
]

def norm_path(v):
    s=str(v or '').strip().replace('\\','/')
    while s.startswith('./'):s=s[2:]
    return s

def sha(s,n=20): return hashlib.sha256(s.encode()).hexdigest()[:n]
def order(s,ns): return hashlib.sha256(f'{ns}|{s}'.encode()).hexdigest()
def jsonobj(v):
    try:return json.loads(v or '{}')
    except:return {}
def fnum(v,d=0.0):
    try:return float(v)
    except:return d
def inum(v,d=0):
    try:return int(float(v))
    except:return d

def read_gz(path):
    with gzip.open(path,'rt',encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write_gz(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',encoding='utf-8',newline='',compresslevel=9) as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)
def file_sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()

class UF:
    def __init__(self):self.p={}
    def find(self,x):
        self.p.setdefault(x,x)
        if self.p[x]!=x:self.p[x]=self.find(self.p[x])
        return self.p[x]
    def union(self,a,b):
        ra,rb=self.find(a),self.find(b)
        if ra!=rb:
            if ra>rb:ra,rb=rb,ra
            self.p[rb]=ra

def load_events(root):
    by_mid={}; by_fp=defaultdict(list)
    for p in sorted((Path(root)/'records').glob('*.csv.gz')):
        for r in read_gz(p):
            if str(r.get('parse_ok','')) not in {'1','True','true'}:continue
            key=norm_path(r.get('mid_path'))
            if key in by_mid: raise RuntimeError(f'duplicate event mid_path {key}')
            by_mid[key]=r
            fp=r.get('symbolic_fingerprint_score','')
            if fp:by_fp[fp].append(key)
    return by_mid,by_fp

def rarity_score(ev,program_presence,n):
    pc=jsonobj(ev.get('program_note_counts_json')); rare=0.0
    for p in pc:
        frac=program_presence.get(int(p),0)/max(1,n); rare=max(rare,-math.log10(max(frac,1/n)))
    meter=ev.get('primary_meter','4/4'); meter_bonus=0.5 if meter not in {'4/4','3/4','2/4','6/8'} else 0.0
    drum=0.35 if inum(ev.get('drum_note_count'))>0 else 0
    keychg=min(0.5,0.1*inum(ev.get('key_signature_event_count')))
    tempo=fnum(ev.get('tempo_bpm_time_weighted_mean'),120); tempo_bonus=0.3 if tempo<55 or tempo>190 else 0
    poly=min(0.8,0.04*max(0,inum(ev.get('polyphony_max'))-10))
    return round(rare+meter_bonus+drum+keychg+tempo_bonus+poly,6)

def allocate(groups,reps,dev,test,rare,review):
    if len(groups)<dev+test+rare+review:raise RuntimeError('not enough final clusters')
    rare_ids=sorted(groups,key=lambda c:(-reps[c]['rarity_score'],order(c,'rare')))[:rare]
    remain=set(groups)-set(rare_ids)
    dev_ids=sorted(remain,key=lambda c:order(c,'dev'))[:dev];remain-=set(dev_ids)
    test_ids=sorted(remain,key=lambda c:order(c,'sealed'))[:test];remain-=set(test_ids)
    review_ids=sorted(remain,key=lambda c:order(c,'review'))[:review];remain-=set(review_ids)
    a={c:'train' for c in remain};a.update({c:'rare_challenge' for c in rare_ids});a.update({c:'strict_dev' for c in dev_ids});a.update({c:'sealed_test' for c in test_ids});a.update({c:'human_review_queue' for c in review_ids})
    return a

def build_source_registry(repo_root,out):
    specs=[
      ('PDMX_SYNTH','PDMX audited score-synthesis','data/audited-pdmx-score-synthesis/summary.json',SYNTH,17599,'READY','same-source MIDI rendered upstream; no new rendering performed'),
      ('SYNTHSOD','SynthSOD aligned scores','data/synthsod-aligned-score-audio/summary.json',SYNTH,484,'SOURCE_VERIFIED_NOT_MATERIALIZED','MIDI-derived note scores aligned to existing synthetic audio'),
      ('ENSEMBLESET','EnsembleSet','data/ensembleset-chamber-score-midi-audio/summary.json',SYNTH,80,'BLOCKED_RESTRICTED_ACCESS','synthetic multitracks from MIDI/MusicXML; academic/RWC access boundary'),
      ('BSED_REAL','BSED real performances','data/bsed-bsd-orchestra-audio/summary.json','REAL_SCORE_ALIGNED',80,'SOURCE_ALIGNMENT_STRONG_NOT_MATERIALIZED','manual verification and note-onset refinement'),
      ('BSED_SYNTH','BSED synthetic','data/bsed-bsd-orchestra-audio/summary.json',SYNTH,20,'SOURCE_VERIFIED_NOT_MATERIALIZED','existing synthetic version; do not re-render'),
      ('BSD_REAL','BSD full movements','data/bsed-bsd-orchestra-audio/summary.json','REAL_SCORE_ALIGNED',415,'BLOCKED_MANUAL_AUDIT','time aligned and structurally verified; weaker than BSED'),
      ('PHENICX','PHENICX-Anechoic','data/phenicx-anechoic-score-audio/summary.json','REAL_SCORE_ALIGNED',4,'SOURCE_ALIGNMENT_STRONG_NOT_MATERIALIZED','manual per-instrument alignment to original MIDI score'),
      ('HAUPTSTIMME','Hauptstimme aligned IMSLP audio','data/hauptstimme-aligned-orchestra-audio/summary.json','REAL_SCORE_ALIGNED',166,'BLOCKED_MANUAL_SPOT_AND_AUDIO_MATERIALIZATION','note-onset alignment exists but exact edition/performance fidelity not claimed'),
      ('RWC_SYNCRWC','RWC Classical / SyncRWC','data/rwc-classical-orchestra-midi-audio/summary.json','REAL_SCORE_ALIGNED',10,'BLOCKED_ALIGNMENT_NOT_GROUND_TRUTH','automatic sync source explicitly warns errors may exist'),
      ('URMP','URMP chamber','data/urmp-chamber-score-midi-audio/summary.json','REAL_SCORE_ALIGNED',44,'BLOCKED_NEEDS_EVENT_ALIGNMENT','score MIDI is reference; not expressive event-for-event ground truth'),
      ('MUTOPIA','Mutopia Orchestra','data/mutopia-orchestra-score-midi/summary.json','SYMBOLIC_ONLY',67,'RENDER_HOLD','same-edition score+MIDI, no paired audio'),
      ('MCTL_S3','S3 Symbolic Symphony Set','data/mctl-symbolic-symphony-set/summary.json','SYMBOLIC_ONLY',16,'RENDER_HOLD','MusicXML/PDF only; deterministic MIDI export possible but audio generation held'),
    ]
    rows=[]
    for sid,name,rel,grade,count,status,note in specs:
        exists=(repo_root/rel).exists(); actual=''
        if exists:
            try: actual=json.loads((repo_root/rel).read_text(encoding='utf-8'))
            except: actual={}
        rows.append({'source_id':sid,'source_name':name,'label_grade':grade,'reported_or_enumerated_rows':count,'status':status if exists else 'SOURCE_SUMMARY_MISSING','supervised_audio_to_midi_eligible':int(status=='READY'),'real_evaluation_eligible_now':0,'new_audio_rendering_allowed':0,'summary_path':rel,'notes':note})
    fields=list(rows[0])
    with (out/'source_ground_truth_registry.csv').open('w',encoding='utf-8',newline='') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    summary={'status':'PASS','rendering_hold':True,'model_pseudo_label_supervised':False,'sources':rows,'real_eval_ready_rows':0,'real_eval_blocker':'real aligned/captured audio binaries + manual audit are not yet materialized in the training-ready workspace'}
    (out/'source_ground_truth_registry.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--v1-manifest',required=True);ap.add_argument('--events-root',required=True);ap.add_argument('--repo-root',default='.');ap.add_argument('--output',required=True);ap.add_argument('--expected',type=int,default=17599);ap.add_argument('--dev',type=int,default=100);ap.add_argument('--sealed',type=int,default=150);ap.add_argument('--rare',type=int,default=50);ap.add_argument('--review',type=int,default=500);args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True); master=read_gz(Path(args.v1_manifest));
    if len(master)!=args.expected:raise RuntimeError(f'input {len(master)} != {args.expected}')
    ev_by_mid,_=load_events(args.events_root)
    # actual note-level program rarity
    prog_presence=Counter()
    joined=[]
    for r in master:
        k=norm_path(r.get('mid_path'));ev=ev_by_mid.get(k)
        if not ev:raise RuntimeError(f'missing parsed MIDI event record for {k}')
        pc=jsonobj(ev.get('program_note_counts_json'))
        for p in pc:prog_presence[int(p)]+=1
        joined.append((r,ev))
    n=len(joined)
    # union existing metadata clusters + exact score fingerprint. transposition fingerprint is audit-only.
    uf=UF(); by_work=defaultdict(list);by_fp=defaultdict(list);by_tfp=defaultdict(list)
    for i,(r,e) in enumerate(joined):
        key=str(i);uf.find(key);by_work[r['work_cluster_id']].append(key);by_fp[e['symbolic_fingerprint_score']].append(key);by_tfp[e['symbolic_fingerprint_transposition_invariant']].append(key)
    for groups in (by_work,by_fp):
        for ids in groups.values():
            for x in ids[1:]:uf.union(ids[0],x)
    members=defaultdict(list)
    for i,(r,e) in enumerate(joined):members[uf.find(str(i))].append(i)
    cluster_ids={root:'cluster-'+sha('|'.join(sorted(joined[i][0]['pair_id'] for i in inds))) for root,inds in members.items()}
    groups={cluster_ids[root]:inds for root,inds in members.items()}
    reps={}
    for cid,inds in groups.items():
        scored=[]
        for i in inds:
            r,e=joined[i];rs=rarity_score(e,prog_presence,n);scored.append((rs,inum(e.get('total_note_count')),r['pair_id'],i))
        _,_,_,idx=max(scored);r,e=joined[idx];reps[cid]={'idx':idx,'rarity_score':rarity_score(e,prog_presence,n)}
    assign=allocate(groups,reps,args.dev,args.sealed,args.rare,args.review)
    output=[]
    for root,inds in members.items():
        cid=cluster_ids[root];cs=assign[cid];repidx=reps[cid]['idx']
        for i in inds:
            r,e=joined[i];x=dict(r)
            x['work_cluster_id_v2']=cid;x['work_cluster_sources']='metadata_title_creator+exact_symbolic_fingerprint';x['symbolic_duplicate_merged']=int(len(by_fp[e['symbolic_fingerprint_score']])>1)
            x['transposition_invariant_candidate_cluster_size']=len(by_tfp[e['symbolic_fingerprint_transposition_invariant']])
            x['cluster_split_v2']=cs;x['split']='train' if cs=='train' else 'holdout'
            if i==repidx:
                x['eval_role_v2']={'strict_dev':'strict_dev','sealed_test':'sealed_test','rare_challenge':'rare_challenge','human_review_queue':'human_review_candidate'}.get(cs,'none')
            else:x['eval_role_v2']='cluster_sibling_holdout' if cs!='train' else 'none'
            x['is_cluster_representative_v2']=int(i==repidx);x['rarity_score_v2']=reps[cid]['rarity_score'] if i==repidx else rarity_score(e,prog_presence,n)
            for k in EVENT_KEEP:x['midi_'+k]=e.get(k,'')
            output.append(x)
    # hard gates
    if any(x.get('label_grade')==PSEUDO or str(x.get('model_pseudo_label')) in {'1','true','True'} for x in output):raise RuntimeError('pseudo label leak')
    # cluster/fingerprint leakage checks
    leaks={}
    for key in ['work_cluster_id_v2','arrangement_cluster_id','audio_variant_cluster_id','midi_symbolic_fingerprint_score']:
        m=defaultdict(set)
        for x in output:m[x[key]].add(x['cluster_split_v2'])
        leaks[key]=sum(1 for v in m.values() if len(v)>1)
    if any(leaks.values()):raise RuntimeError(f'leaks {leaks}')
    output.sort(key=lambda x:(x['work_cluster_id_v2'],x['pair_id']));fields=list(output[0]);write_gz(out/'training_manifest.csv.gz',fields,output)
    roles={'train':[],'dev_100':[],'sealed_test_150':[],'rare_challenge_50':[],'human_review_queue_500':[],'cluster_sibling_holdouts':[]}
    for x in output:
        if x['cluster_split_v2']=='train':roles['train'].append(x)
        elif x['eval_role_v2']=='strict_dev':roles['dev_100'].append(x)
        elif x['eval_role_v2']=='sealed_test':roles['sealed_test_150'].append(x)
        elif x['eval_role_v2']=='rare_challenge':roles['rare_challenge_50'].append(x)
        elif x['eval_role_v2']=='human_review_candidate':roles['human_review_queue_500'].append(x)
        else:roles['cluster_sibling_holdouts'].append(x)
    for name,rows in roles.items():write_gz(out/'splits'/f'{name}.csv.gz',fields,rows)
    expected_counts=(args.dev,args.sealed,args.rare,args.review);actual=(len(roles['dev_100']),len(roles['sealed_test_150']),len(roles['rare_challenge_50']),len(roles['human_review_queue_500']))
    if actual!=expected_counts:raise RuntimeError(f'eval representative count {actual} != {expected_counts}')
    # resolved event coverage
    meters=Counter(x['midi_primary_meter'] for x in output);keys=Counter(x['midi_estimated_key'] for x in output);drums=sum(inum(x['midi_drum_note_count'])>0 for x in output)
    coverage={'status':'PASS_EVENT_LEVEL_SYMBOLIC_PREPROCESS_COMPLETE','records':n,'resolved':['key_distribution','tempo_distribution','meter_distribution','drum_note_distribution','note_duration','velocity','polyphony','program_note_counts','track_names','symbolic_exact_duplicate_fingerprint'],'drum_records':drums,'meter_top':meters.most_common(20),'estimated_key_top':keys.most_common(24),'remaining_not_measurable_without_audio_or_score_semantics':{'audio_master_cover_fingerprint':'REQUIRES_AUDIO_BINARY','same_work_renamed_cover_detection':'REQUIRES_AUDIO_OR_SCORE_SIMILARITY_MODEL','printed_staff_identity_beyond_MIDI_track_names':'REQUIRES_MUSICXML_STAFF_PARSE'},'rendered_audio_created':False}
    (out/'coverage_audit.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
    t_candidates=sum(1 for ids in by_tfp.values() if len(ids)>1); exact_clusters=sum(1 for ids in by_fp.values() if len(ids)>1)
    leakage={'status':'PASS','final_work_clusters':len(groups),'cross_split_leaks':leaks,'exact_symbolic_duplicate_clusters':exact_clusters,'transposition_invariant_candidate_clusters_not_auto_merged':t_candidates,'policy':'exact symbolic fingerprints are unioned with metadata work clusters before split; transposition-invariant collisions are audit-only to avoid false merges','future_real_audio_requirement':'union audio/chroma/acoustic fingerprints before freezing real evaluation'}
    (out/'leakage_audit.json').write_text(json.dumps(leakage,ensure_ascii=False,indent=2)+'\n')
    status={'status':'TRAINING_READY_SYNTHETIC_SYMBOLIC_PREPROCESS_COMPLETE','input_pairs':n,'label_grade':SYNTH,'pseudo_labels_supervised':0,'midi_event_parse_joined':n,'final_work_clusters':len(groups),'strict_eval_representatives':{'dev':args.dev,'sealed_test':args.sealed,'rare_challenge':args.rare},'human_review_queue':args.review,'real_captured_or_real_score_aligned_eval_ready_rows':0,'real_eval_status':'BLOCKED_UNTIL_REAL_BINARY_MATERIALIZATION_AND_MANUAL_AUDIT','new_midi_to_audio_rendering_performed':False,'rendering_hold':True,'validation':{'all_pairs_event_parsed':True,'pseudo_labels_excluded':True,'cluster_leakage_zero':not any(leaks.values()),'eval_counts_exact':actual==expected_counts}}
    status['validation']['passed']=all(status['validation'].values());(out/'preprocessing_status.json').write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n')
    render_policy={'status':'HOLD','new_midi_to_audio_rendering_allowed':False,'reason':'explicit user hold; preprocessing only','existing_upstream_synthetic_audio_may_be_indexed':True,'audio_generation_commands_in_workflow':False};(out/'RENDERING_HOLD.json').write_text(json.dumps(render_policy,ensure_ascii=False,indent=2)+'\n')
    build_source_registry(Path(args.repo_root),out)
    # quarantine pseudo placeholder
    write_gz(out/'quarantine/model_pseudo_labels.csv.gz',['record_id','reason'],[])
    with (out/'SHA256SUMS').open('w') as f:
        for p in sorted(out.rglob('*')):
            if p.is_file() and p.name!='SHA256SUMS':f.write(f'{file_sha(p)}  {p.relative_to(out)}\n')
    print(json.dumps(status,ensure_ascii=False,indent=2))
    if not status['validation']['passed']:raise SystemExit(2)
if __name__=='__main__':main()
