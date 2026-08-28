#!/usr/bin/env python3
import argparse,csv,gzip,hashlib,json,re
from collections import Counter
from pathlib import Path

FAMILY={
 'piano':set(range(0,8)),'keys':set(range(0,24)),'guitar':set(range(24,32)),
 'bass':set(range(32,40)),'strings':set(range(40,50)),'voice':set(range(52,55)),
 'brass':set(range(56,62)),'sax':set(range(64,68)),'woodwind':set(range(64,80)),
 'synth':set(range(50,52))|set(range(54,56))|set(range(62,64))|set(range(80,104)),
 'percussion_program':set(range(8,15))|{47}|set(range(108,120)),'sfx':set(range(120,128)),
}
REQUIRED={'path','tracks','n_tracks','mxl','pdf','mid','subset:no_license_conflict','subset:all_valid','subset:deduplicated'}
FIELDS=['record_id','title','song_name','composer_name','genres','n_tracks','gm_program_track_counts','family_track_counts','distinct_programs','ensemble_primary','ensemble_confidence','classification_basis','drumkit_presence','mxl','pdf','mid','license','license_url','path','exactness_class']
LONG=['record_id','gm_program_0based','track_count']

def truth(v): return str(v).strip().lower() in {'1','true','yes','y','t'}
def intval(v,d=0):
 try:return int(float(v))
 except:return d
def programs(v):return [int(x) for x in re.findall(r'\d+',str(v or '')) if 0<=int(x)<=127]
def count(c,s):return sum(v for k,v in c.items() if k in s)
def family_counts(c):return {k:count(c,s) for k,s in FAMILY.items() if count(c,s)}
def rid(row):return 'pdmx-'+re.sub(r'[^a-z0-9]+','',Path(str(row['path'])).stem.lower())
def classify(c,row):
 n=sum(c.values());f=family_counts(c);st=f.get('strings',0);ww=f.get('woodwind',0);br=f.get('brass',0);sx=f.get('sax',0);pi=f.get('piano',0);ba=f.get('bass',0);gt=f.get('guitar',0);vo=f.get('voice',0);sy=f.get('synth',0);tr=c.get(56,0)+c.get(59,0);tb=c.get(57,0)
 txt=' '.join(str(row.get(k,'') or '').lower() for k in ('title','song_name','genres','tags','groups'))
 if n==4 and c.get(40,0)==2 and c.get(41,0)==1 and c.get(42,0)==1:return 'chamber.string_quartet','high','2 violin+viola+cello GM tracks'
 if st>=5 and ww>=2 and br>=2 and n>=10:return 'orchestra.full.symphonic','high' if any(x in txt for x in ('orchestra','symph','philharmonic','sinfon')) else 'medium',f'string={st};woodwind={ww};brass={br}'
 if st>=4 and ww==0 and br==0:return 'orchestra.string','medium',f'string={st};no wind/brass'
 if st>=2 and ww+br>=1 and n>=5:return 'orchestra.chamber','medium',f'string={st};wind+brass={ww+br}'
 if ww>=5 and br>=3 and st<=1 and n>=8:return 'wind.concert_band_candidate','medium',f'woodwind={ww};brass={br};drumkit unknown'
 if br>=6 and ww<=1 and st<=1:return 'brass_band_candidate','medium',f'brass={br}'
 if sx>=4 and tr>=3 and tb>=2 and n>=10:return 'jazz.big_band_candidate','medium' if ('jazz' in txt or 'big band' in txt) else 'low',f'sax={sx};trumpet={tr};trombone={tb};drumkit unknown'
 if ('jazz' in txt or 'bossa' in txt or 'swing' in txt) and 3<=n<=9 and ba and (pi or gt):return 'jazz.combo_candidate','medium','jazz metadata+bass+piano/guitar'
 if vo>=2:return 'choir.vocal_ensemble','medium' if ('choir' in txt or 'choral' in txt) else 'low',f'voice_program_tracks={vo}'
 if vo and pi and n<=4:return 'voice.piano','medium','voice+piano'
 if n==1 and pi:return 'solo.piano','high','single piano program track'
 if n==1 and gt:return 'solo.guitar','high','single guitar program track'
 if n>=3 and ba and gt and (pi or sy):return 'band.pop_rock_candidate','low','bass+guitar+keys/synth;drumkit unknown'
 if sy>=2 and sy>=max(2,n//2):return 'electronic.synth_ensemble','medium',f'synth={sy}/{n}'
 return 'ensemble.mixed_or_unclassified','low','no canonical pattern proven from GM program list'

def sha256(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def gz_writer(path,fields):
 f=gzip.open(path,'wt',encoding='utf-8',newline='',compresslevel=9);w=csv.DictWriter(f,fieldnames=fields);w.writeheader();return f,w

def build(src,out,shard_size=20000,min_records=10000):
 out=Path(out);(out/'records').mkdir(parents=True,exist_ok=True);(out/'record_instruments').mkdir(exist_ok=True)
 seen=set();records=[];long=[];rec_index=[];long_index=[];prog_records=Counter();prog_tracks=Counter();ens=Counter();conf=Counter();total=0;long_total=0;rp=lp=0
 def flush_records():
  nonlocal records,rp
  if not records:return
  rp+=1;p=out/'records'/f'part-{rp:05d}.csv.gz';f,w=gz_writer(p,FIELDS);w.writerows(records);f.close();rec_index.append((p.name,len(records),sha256(p)));records=[]
 def flush_long():
  nonlocal long,lp
  if not long:return
  lp+=1;p=out/'record_instruments'/f'part-{lp:05d}.csv.gz';f,w=gz_writer(p,LONG);w.writerows(long);f.close();long_index.append((p.name,len(long),sha256(p)));long=[]
 with open(src,encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f);missing=REQUIRED-set(r.fieldnames or [])
  if missing:raise RuntimeError('missing columns: '+str(sorted(missing)))
  for row in r:
   if not(truth(row.get('subset:no_license_conflict')) and truth(row.get('subset:all_valid')) and truth(row.get('subset:deduplicated'))):continue
   record_id=rid(row)
   if record_id in seen:raise RuntimeError('duplicate id '+record_id)
   seen.add(record_id);ps=programs(row.get('tracks'));c=Counter(ps);fc=family_counts(c);e,ec,basis=classify(c,row)
   rec={'record_id':record_id,'title':row.get('title',''),'song_name':row.get('song_name',''),'composer_name':row.get('composer_name',''),'genres':row.get('genres',''),'n_tracks':intval(row.get('n_tracks')),'gm_program_track_counts':';'.join(f'{k}:{c[k]}' for k in sorted(c)),'family_track_counts':';'.join(f'{k}:{fc[k]}' for k in sorted(fc)),'distinct_programs':len(c),'ensemble_primary':e,'ensemble_confidence':ec,'classification_basis':basis,'drumkit_presence':'unknown_from_pdmx_program_list','mxl':row.get('mxl',''),'pdf':row.get('pdf',''),'mid':row.get('mid',''),'license':row.get('license',''),'license_url':row.get('license_url',''),'path':row.get('path',''),'exactness_class':'same_symbolic_source_exact'}
   records.append(rec);total+=1;ens[e]+=1;conf[ec]+=1
   for p,v in sorted(c.items()):
    long.append({'record_id':record_id,'gm_program_0based':p,'track_count':v});long_total+=1;prog_records[p]+=1;prog_tracks[p]+=v
   if len(records)>=shard_size:flush_records()
   if len(long)>=shard_size*3:flush_long()
 flush_records();flush_long()
 if total<min_records:raise RuntimeError(f'only {total} records; expected >= {min_records}')
 def write_csv(name,header,rows):
  with open(out/name,'w',encoding='utf-8',newline='') as f:w=csv.writer(f);w.writerow(header);w.writerows(rows)
 write_csv('program_counts.csv',['gm_program_0based','records_present','track_occurrences','record_fraction'],[[p,prog_records[p],prog_tracks[p],f'{prog_records[p]/total:.8f}'] for p in sorted(prog_records,key=lambda p:(-prog_records[p],p))])
 write_csv('ensemble_counts.csv',['ensemble_primary','records','record_fraction'],[[k,v,f'{v/total:.8f}'] for k,v in ens.most_common()])
 write_csv('record_shards.csv',['file','rows','sha256'],rec_index);write_csv('instrument_shards.csv',['file','rows','sha256'],long_index)
 summary={'source':'PDMX v9 / Zenodo 15571083','input_sha256':sha256(src),'filter':'no_license_conflict AND all_valid AND deduplicated','records':total,'unique_record_ids':len(seen),'record_instrument_rows':long_total,'record_shards':len(rec_index),'instrument_shards':len(long_index),'ensemble_counts':dict(ens.most_common()),'confidence_counts':dict(conf),'validation':{'minimum_records':min_records,'minimum_passed':total>=min_records,'unique_ids':len(seen)==total,'passed':total>=min_records and len(seen)==total},'limitations':['GM program list is track-level evidence, not exact printed staff names.','PDMX CSV does not prove MIDI channel-10 drum-kit presence.','Bb/C trumpet, divisi, instrument doubling and articulations require direct score parsing.']}
 (out/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
 (out/'README.md').write_text(f'''# PDMX v9 strict per-record instrumentation manifest\n\nStrict filter: `subset:no_license_conflict && subset:all_valid && subset:deduplicated`.\n\n- records: **{total:,}**\n- sparse `(record, GM-program)` rows: **{long_total:,}**\n- evidence: PDMX per-track zero-based GM program list\n- exactness: same symbolic source MXL/PDF/MID only; **not** a human-recording exactness claim\n\n`records/*.csv.gz` is one row per score. `record_instruments/*.csv.gz` is the normalized long form. `program_counts.csv` and `ensemble_counts.csv` are aggregate indexes.\n\nImportant: drum-kit presence, printed staff numbering, transposing-instrument key, divisi, doubles and articulation are not fabricated from GM programs; they remain unknown until direct MusicXML/MuseScore/MIDI parsing.\n''',encoding='utf-8')
 sums=[]
 for p in sorted(out.rglob('*')):
  if p.is_file() and p.name!='SHA256SUMS':sums.append(f'{sha256(p)}  {p.relative_to(out)}')
 (out/'SHA256SUMS').write_text('\n'.join(sums)+'\n',encoding='utf-8')
 return summary

if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--input',required=True);a.add_argument('--output',required=True);a.add_argument('--shard-size',type=int,default=20000);a.add_argument('--min-records',type=int,default=10000);x=a.parse_args();print(json.dumps(build(x.input,x.output,x.shard_size,x.min_records),indent=2))
