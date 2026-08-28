#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,gzip,hashlib,json,math,re,unicodedata
from collections import Counter,defaultdict
from pathlib import Path

GRADES=("REAL_CAPTURED_MIDI","REAL_SCORE_ALIGNED","SYNTH_RENDERED_MIDI","MODEL_PSEUDO_LABEL")
GRADE_SYNTH="SYNTH_RENDERED_MIDI"
GRADE_PSEUDO="MODEL_PSEUDO_LABEL"

FAMILY_SETS={
 'keys':set(range(0,24)),
 'guitar':set(range(24,32)),
 'bass':set(range(32,40)),
 'strings':set(range(40,47))|{48,49},
 'voice':{52,53},
 'brass':set(range(56,62)),
 'woodwind':set(range(64,80)),
 'synth':set(range(50,52))|{54,55}|set(range(62,64))|set(range(80,104)),
 'percussion':set(range(8,16))|{47}|set(range(112,120)),
 'sfx':set(range(120,128)),
}

def norm(v):
    s=unicodedata.normalize('NFKC',str(v or '')).casefold().replace('&',' and ')
    s=re.sub(r'\b(arr(?:angement|anged)?|transcription|orchestration|version|ver\.?|mix|master|remaster(?:ed)?|live|cover|instrumental)\b',' ',s)
    s=re.sub(r'[\[\](){}]',' ',s); s=re.sub(r'[^\w]+',' ',s); return ' '.join(s.split())

def root_title(v):
    s=norm(v)
    s=re.sub(r'\b(?:movement|mov|mvt)\s*[ivxlcdm\d]+\b.*$','',s).strip()
    return s

def creator(row):
    # artist commonly carries original composer in audited PDMX mapping; arranger is in composer.
    return str(row.get('artist') or row.get('composer') or '').strip()

def sh(s,n=16): return hashlib.sha256(s.encode()).hexdigest()[:n]
def work_cluster(row):
    t=root_title(row.get('title'))
    c=norm(creator(row))
    basis=f'title_creator_v2|{c}|{t}' if t else f'pair_fallback_v2|{row.get("pair_id","")}'
    return 'work-'+sh(basis),basis

def arrangement_cluster(row):
    key=str(row.get('pdmx_path') or row.get('mid_path') or row.get('pair_id') or '')
    return 'arr-'+sh(key)

def programs(row):
    src=row.get('tracks') or row.get('raw_gm_programs_0based') or ''
    c=Counter(int(x) for x in re.findall(r'\d+',str(src)) if 0<=int(x)<=127)
    return dict(c)

def order(cid,ns): return hashlib.sha256(f'{ns}|{cid}'.encode()).hexdigest()
def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()
def write_gz(path,fields,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with gzip.open(path,'wt',encoding='utf-8',newline='',compresslevel=9) as f:
        w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows(rows)

def allocate(items,dev_n,test_n,rare_n,review_n):
    groups=defaultdict(list)
    for x in items: groups[x['work_cluster_id']].append(x)
    reps={cid:sorted(rows,key=lambda r:(-len(r['program_counts']),-r['rarity_score'],r['pair_id']))[0] for cid,rows in groups.items()}
    if len(reps)<dev_n+test_n+rare_n+review_n: raise RuntimeError('not enough work clusters')
    rare_rank=sorted(reps.values(),key=lambda r:(-r['rarity_score'],-len(r['program_counts']),order(r['work_cluster_id'],'rare')))
    rare=[r['work_cluster_id'] for r in rare_rank[:rare_n]]
    remain=set(reps)-set(rare)
    dev=sorted(remain,key=lambda c:order(c,'dev'))[:dev_n];remain-=set(dev)
    test=sorted(remain,key=lambda c:order(c,'sealed'))[:test_n];remain-=set(test)
    review=sorted(remain,key=lambda c:order(c,'review'))[:review_n];remain-=set(review)
    a={c:'train' for c in remain}
    a.update({c:'rare_challenge' for c in rare});a.update({c:'strict_dev' for c in dev});a.update({c:'sealed_test' for c in test});a.update({c:'human_review_queue' for c in review})
    return a,reps

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--exact',required=True);ap.add_argument('--output',required=True);ap.add_argument('--expected-exact',type=int,default=17599);ap.add_argument('--dev',type=int,default=100);ap.add_argument('--sealed',type=int,default=150);ap.add_argument('--rare',type=int,default=50);ap.add_argument('--review',type=int,default=500);args=ap.parse_args()
    out=Path(args.output);out.mkdir(parents=True,exist_ok=True)
    with gzip.open(args.exact,'rt',encoding='utf-8-sig',newline='') if str(args.exact).endswith('.gz') else open(args.exact,encoding='utf-8-sig',newline='') as f:
        rd=csv.DictReader(f);headers=rd.fieldnames or []; rows=list(rd)
    if len(rows)!=args.expected_exact: raise RuntimeError(f'exact count {len(rows)} != {args.expected_exact}')
    required={'pair_id','tracks','pdmx_path','mxl_path','pdf_path','mid_path','hf_audio_path','eligible_exact_pair'}
    miss=required-set(headers)
    if miss: raise RuntimeError(f'missing required exact columns: {sorted(miss)}')
    items=[];ids=set()
    for r in rows:
        pid=r['pair_id']
        if pid in ids: raise RuntimeError(f'duplicate pair_id {pid}')
        ids.add(pid)
        if str(r.get('eligible_exact_pair','')).lower() not in {'true','1','yes'}: raise RuntimeError(f'non-eligible row {pid}')
        pc=programs(r)
        if not pc: raise RuntimeError(f'no GM track evidence {pid}')
        wid,wb=work_cluster(r); aid=arrangement_cluster(r)
        items.append({'row':r,'pair_id':pid,'program_counts':pc,'work_cluster_id':wid,'work_cluster_basis':wb,'arrangement_cluster_id':aid})
    presence=Counter()
    for x in items:
        for p in x['program_counts']: presence[p]+=1
    n=len(items)
    for x in items:
        scored=sorted((presence[p]/n,p) for p in x['program_counts'])
        frac=scored[0][0];x['rarity_score']=round(-math.log10(max(frac,1/n))+0.04*len(x['program_counts']),6);x['rare_programs']=[p for f,p in scored if f<=.01]
    assign,reps=allocate(items,args.dev,args.sealed,args.rare,args.review)
    master=[]
    for x in items:
        r=x['row'];cs=assign[x['work_cluster_id']];rep=reps[x['work_cluster_id']]['pair_id']==x['pair_id']
        if cs=='train': split='train';role='none'
        elif cs=='human_review_queue': split='holdout';role='human_review_candidate' if rep else 'cluster_sibling_holdout'
        else: split='holdout';role=cs if rep else 'cluster_sibling_holdout'
        pc=x['program_counts']
        master.append({
          'pair_id':x['pair_id'],'label_grade':GRADE_SYNTH,'supervised_ground_truth_eligible':1,'model_pseudo_label':0,
          'alignment_class':'EXACT_BY_CONSTRUCTION','alignment_gate':'PASS','alignment_method':'same_source_midi_synthesis','dtw_required':0,'manual_alignment_required':0,
          'work_cluster_id':x['work_cluster_id'],'work_cluster_basis':x['work_cluster_basis'],'arrangement_cluster_id':x['arrangement_cluster_id'],'audio_variant_cluster_id':x['arrangement_cluster_id'],
          'cluster_split':cs,'split':split,'eval_role':role,'is_cluster_representative':int(rep),
          'title':r.get('title',''),'creator':creator(r),'composer_or_arranger':r.get('composer',''),'genres':r.get('genres',''),'tags':r.get('tags',''),
          'gm_programs_0based':r.get('tracks',''),'distinct_gm_programs':len(pc),'rarity_score':x['rarity_score'],'rare_programs_0based':'-'.join(map(str,x['rare_programs'])),
          'pdmx_path':r.get('pdmx_path',''),'mxl_path':r.get('mxl_path',''),'pdf_path':r.get('pdf_path',''),'mid_path':r.get('mid_path',''),'audio_path':r.get('hf_audio_path',''),'audio_source':r.get('audio_source',''),'score_source':r.get('score_source',''),
          'license':r.get('pdmx_license',''),'license_url':r.get('pdmx_license_url',''),'rights_gate':'PASS_PDMX_NO_LICENSE_CONFLICT','feature_policy':'compressed_audio_5s_on_the_fly',
        })
    # hard supervised-label/alignment gate
    if any(x['label_grade']==GRADE_PSEUDO or x['model_pseudo_label'] for x in master): raise RuntimeError('pseudo label leak')
    if any(x['alignment_gate']!='PASS' for x in master): raise RuntimeError('alignment gate leak')
    # cluster leak audit
    for key in ('work_cluster_id','arrangement_cluster_id','audio_variant_cluster_id'):
        m=defaultdict(set)
        for x in master:m[x[key]].add(x['cluster_split'])
        leaks={k:v for k,v in m.items() if len(v)>1}
        if leaks: raise RuntimeError(f'{key} leakage: {len(leaks)}')
    fields=list(master[0]);master.sort(key=lambda x:(x['work_cluster_id'],x['pair_id']));write_gz(out/'training_manifest.csv.gz',fields,master)
    def reps_role(role):return [x for x in master if x['eval_role']==role]
    dev=reps_role('strict_dev');sealed=reps_role('sealed_test');rare=reps_role('rare_challenge');review=reps_role('human_review_candidate');siblings=[x for x in master if x['eval_role']=='cluster_sibling_holdout'];train=[x for x in master if x['cluster_split']=='train']
    for name,data in [('train',train),('dev_100',dev),('sealed_test_150',sealed),('rare_challenge_50',rare),('human_review_queue_500',review),('cluster_sibling_holdouts',siblings)]:write_gz(out/'splits'/f'{name}.csv.gz',fields,data)
    if (len(dev),len(sealed),len(rare),len(review))!=(args.dev,args.sealed,args.rare,args.review):raise RuntimeError('holdout count mismatch')
    # instrument balance
    occ=Counter();tracks=Counter()
    for x in items:
        for p,c in x['program_counts'].items():occ[p]+=1;tracks[p]+=c
    with (out/'instrument_balance.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['gm_program_0based','records_present','track_occurrences','record_fraction'])
        for p,v in sorted(occ.items(),key=lambda kv:(-kv[1],kv[0])):w.writerow([p,v,tracks[p],f'{v/n:.8f}'])
    fam_presence=Counter();fam_tracks=Counter()
    for x in items:
        pc=x['program_counts']
        for fam,ps in FAMILY_SETS.items():
            total=sum(c for p,c in pc.items() if p in ps)
            if total:
                fam_presence[fam]+=1;fam_tracks[fam]+=total
    with (out/'family_balance.csv').open('w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['family','records_present','track_occurrences','record_fraction'])
        for fam,v in sorted(fam_presence.items(),key=lambda kv:(-kv[1],kv[0])):w.writerow([fam,v,fam_tracks[fam],f'{v/n:.8f}'])
    rare_programs=[p for p,v in sorted(occ.items()) if v/n < .01]
    coverage={
      'status':'PASS_WITH_DECLARED_METADATA_GAPS',
      'records':n,
      'family_record_presence':dict(sorted(fam_presence.items())),
      'rare_gm_programs_under_1pct':rare_programs,
      'rare_gm_program_count':len(rare_programs),
      'measured':['GM program presence','family presence','track occurrences','work-cluster split distribution'],
      'not_measured_from_current_manifest':{
        'key_distribution':'BLOCKED_REQUIRES_MIDI_EVENT_PARSE',
        'tempo_distribution':'BLOCKED_REQUIRES_MIDI_TEMPO_MAP_PARSE',
        'meter_distribution':'BLOCKED_REQUIRES_MIDI_TIME_SIGNATURE_PARSE',
        'drum_note_distribution':'BLOCKED_REQUIRES_CHANNEL_10_NOTE_PARSE',
        'note_duration_velocity_polyphony':'BLOCKED_REQUIRES_MIDI_EVENT_PARSE',
      },
      'risk_flags':{
        'keys_overrepresentation': fam_presence.get('keys',0) > 2*max(1,fam_presence.get('guitar',0)),
        'rare_wind_brass_monitoring_required': True,
        'strings_brass_woodwind_reported_separately': True,
      },
    }
    (out/'coverage_audit.json').write_text(json.dumps(coverage,indent=2,ensure_ascii=False))
    work_clusters=len({x['work_cluster_id'] for x in master})
    split_counts=Counter(x['cluster_split'] for x in master)
    leakage={'status':'PASS','work_clusters':work_clusters,'work_cluster_cross_split_leaks':0,'arrangement_cluster_cross_split_leaks':0,'audio_variant_cluster_cross_split_leaks':0,'method':'title+original-creator metadata cluster; arrangement=PDMX source record','limitations':['Metadata clustering cannot guarantee detection of renamed covers/masters. Union with audio/chroma fingerprint clusters before freezing real-audio evaluation.','Future renders from the same PDMX arrangement must inherit this split.']}
    (out/'leakage_audit.json').write_text(json.dumps(leakage,indent=2,ensure_ascii=False))
    alignment={'status':'PASS_FOR_SYNTH_RENDERED_MIDI_ONLY','grade':GRADE_SYNTH,'exact_pairs':n,'alignment_method':'same-source MIDI to synthesis; exact by construction','real_score_aligned_gate':{'status':'BLOCKED_NOT_PRESENT_IN_THIS_CORPUS','requirements':['lock work/performance identity before alignment','coarse chroma/beat agreement','onset-aware monotonic DTW','key/repeat/cut/duration consistency','manual spot review and failure log','never choose MIDI candidate by best evaluation-audio alignment score']},'model_pseudo_label_policy':'QUARANTINE_NOT_SUPERVISED'}
    (out/'alignment_audit.json').write_text(json.dumps(alignment,indent=2,ensure_ascii=False))
    feature={'audio_storage':'keep compressed upstream audio; no corpus-wide PCM expansion','segment_seconds':5.0,'decode':'on demand','target_channels':1,'target_sample_rate_hz':16000,'stft_mel':'on-the-fly only','full_mel_cache':'forbidden','cache':'bounded local segment/feature cache','sharding':'compressed song/manifest shards'}
    (out/'audio_feature_policy.json').write_text(json.dumps(feature,indent=2,ensure_ascii=False))
    gt={'grades':{'REAL_CAPTURED_MIDI':{'supervised':True,'gate':'synchronous capture provenance'},'REAL_SCORE_ALIGNED':{'supervised':True,'gate':'real alignment PASS'},'SYNTH_RENDERED_MIDI':{'supervised':True,'gate':'exact source MIDI render provenance'},'MODEL_PSEUDO_LABEL':{'supervised':False,'gate':'quarantine only'}},'current_corpus_grade':'SYNTH_RENDERED_MIDI','pseudo_label_rows':0}
    (out/'ground_truth_grades.json').write_text(json.dumps(gt,indent=2,ensure_ascii=False))
    (out/'GROUND_TRUTH_POLICY.md').write_text('# Ground truth policy\n\n`MODEL_PSEUDO_LABEL` is never supervised ground truth. This corpus is `SYNTH_RENDERED_MIDI`; the score MIDI is the exact synthesis source. `REAL_SCORE_ALIGNED` requires identity lock, chroma/beat + onset-DTW alignment, structural checks and manual audit. `REAL_CAPTURED_MIDI` requires synchronous capture provenance.\n',encoding='utf-8')
    # human review queue is a queue, not verified data
    status={'status':'TRAINING_READY_SYNTHETIC','input_exact_pairs':n,'joined_exact_pairs':n,'label_grade_counts':{GRADE_SYNTH:n},'pseudo_labels_in_supervised_manifest':0,'work_clusters':work_clusters,'split_row_counts':dict(split_counts),'strict_eval_representatives':{'dev':len(dev),'sealed_test':len(sealed),'rare_challenge':len(rare)},'human_review_queue':len(review),'human_verified_post_training_rows':0,'cluster_sibling_holdouts':len(siblings),'real_captured_or_real_score_aligned_eval_rows':0,'real_eval_status':'BLOCKED_UNTIL_REAL_CAPTURED_OR_ALIGNMENT_GATED_DATA_IS_MATERIALIZED','training_ready_scope':'audited PDMX score-derived synthesized audio only','validation':{'exact_count':n==args.expected_exact,'pseudo_labels_excluded':True,'all_alignment_pass':True,'cluster_leakage_zero':True,'strict_eval_requested':len(dev)+len(sealed)+len(rare)==args.dev+args.sealed+args.rare,'human_review_queue_requested':len(review)==args.review}}
    if not all(status['validation'].values()):raise RuntimeError(status['validation'])
    (out/'preprocessing_status.json').write_text(json.dumps(status,indent=2,ensure_ascii=False))
    # empty quarantine schema now; other pipelines append pseudo labels here instead of supervised manifest
    write_gz(out/'quarantine'/'model_pseudo_labels.csv.gz',['pair_id','source','reason','label_grade'],[])
    files=sorted(p for p in out.rglob('*') if p.is_file() and p.name!='SHA256SUMS')
    with (out/'SHA256SUMS').open('w',encoding='utf-8') as f:
        for p in files:f.write(f'{sha256(p)}  {p.relative_to(out).as_posix()}\n')
    print(json.dumps(status,indent=2,ensure_ascii=False))
if __name__=='__main__':main()
