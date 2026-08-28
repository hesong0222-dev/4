#!/usr/bin/env python3
import argparse,csv,gzip,hashlib,json
from collections import Counter
from pathlib import Path

FAMILY={
 'piano':set(range(0,8)),
 'keys':set(range(0,8))|set(range(16,24)),
 'chromatic_percussion':set(range(8,16)),
 'guitar':set(range(24,32)),'bass':set(range(32,40)),
 'strings':{40,41,42,43,44,45,46,48,49},
 'section_strings':{40,41,42,43,44,45,48,49},
 'voice':{52,53},'brass':set(range(56,62)),'sax':set(range(64,68)),
 'woodwind':set(range(64,80)),
 'synth':{50,51,54,62,63}|set(range(80,104)),
 'percussion_program':set(range(8,15))|{47}|set(range(108,120)),
 'sfx':set(range(120,128)),
}

def parse_counts(s):
 c=Counter()
 for item in str(s or '').split(';'):
  if not item:continue
  a,b=item.split(':',1);c[int(a)]=int(b)
 return c
def count(c,s):return sum(v for k,v in c.items() if k in s)
def family_counts(c):return {k:count(c,s) for k,s in FAMILY.items() if k!='section_strings' and count(c,s)}
def classify(c,row):
 n=sum(c.values());st=count(c,FAMILY['section_strings']);ww=count(c,FAMILY['woodwind']);br=count(c,FAMILY['brass']);sx=count(c,FAMILY['sax']);pi=count(c,FAMILY['piano']);ba=count(c,FAMILY['bass']);gt=count(c,FAMILY['guitar']);vo=count(c,FAMILY['voice']);sy=count(c,FAMILY['synth']);tr=c.get(56,0)+c.get(59,0);tb=c.get(57,0)
 txt=' '.join(str(row.get(k,'') or '').lower() for k in ('title','song_name','genres'))
 if n==4 and c.get(40,0)==2 and c.get(41,0)==1 and c.get(42,0)==1:return 'chamber.string_quartet','high','2 violin+viola+cello GM tracks'
 if st>=5 and ww>=2 and br>=2 and n>=10:return 'orchestra.full.symphonic','high' if any(x in txt for x in ('orchestra','symph','philharmonic','sinfon')) else 'medium',f'section_string={st};woodwind={ww};brass={br}'
 if st>=4 and ww==0 and br==0:return 'orchestra.string','medium',f'section_string={st};no wind/brass'
 if st>=2 and ww+br>=1 and n>=5:return 'orchestra.chamber','medium',f'section_string={st};wind+brass={ww+br}'
 if ww>=5 and br>=3 and st<=1 and n>=8:return 'wind.concert_band_candidate','medium',f'woodwind={ww};brass={br};drumkit unknown'
 if br>=6 and ww<=1 and st<=1:return 'brass_band_candidate','medium',f'brass={br}'
 if sx>=4 and tr>=3 and tb>=2 and n>=10:return 'jazz.big_band_candidate','medium' if ('jazz' in txt or 'big band' in txt) else 'low',f'sax={sx};trumpet={tr};trombone={tb};drumkit unknown'
 if ('jazz' in txt or 'bossa' in txt or 'swing' in txt) and 3<=n<=9 and ba and (pi or gt):return 'jazz.combo_candidate','medium','jazz metadata+bass+piano/guitar'
 if vo>=2:return 'choir.vocal_ensemble','medium' if ('choir' in txt or 'choral' in txt) else 'low',f'acoustic_voice_program_tracks={vo}'
 if vo and pi and n<=4:return 'voice.piano','medium','acoustic voice+piano'
 if n==1 and pi:return 'solo.piano','high','single piano program track'
 if n==1 and gt:return 'solo.guitar','high','single guitar program track'
 if n>=3 and ba and gt and (pi or sy):return 'band.pop_rock_candidate','low','bass+guitar+keys/synth;drumkit unknown'
 if sy>=2 and sy>=max(2,n//2):return 'electronic.synth_ensemble','medium',f'synth={sy}/{n}'
 return 'ensemble.mixed_or_unclassified','low','no canonical pattern proven from GM program list'
def sha(p):
 h=hashlib.sha256()
 with open(p,'rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def rewrite(root):
 root=Path(root);ens=Counter();conf=Counter();total=0;idx=[]
 for p in sorted((root/'records').glob('*.csv.gz')):
  tmp=p.with_suffix(p.suffix+'.tmp')
  with gzip.open(p,'rt',encoding='utf-8',newline='') as src,gzip.open(tmp,'wt',encoding='utf-8',newline='',compresslevel=9) as dst:
   r=csv.DictReader(src);w=csv.DictWriter(dst,fieldnames=r.fieldnames);w.writeheader();rows=0
   for row in r:
    c=parse_counts(row['gm_program_track_counts']);fc=family_counts(c);e,ec,b=classify(c,row)
    row['family_track_counts']=';'.join(f'{k}:{fc[k]}' for k in sorted(fc));row['ensemble_primary']=e;row['ensemble_confidence']=ec;row['classification_basis']=b
    w.writerow(row);rows+=1;total+=1;ens[e]+=1;conf[ec]+=1
  tmp.replace(p);idx.append((p.name,rows,sha(p)))
 with open(root/'record_shards.csv','w',encoding='utf-8',newline='') as f:
  w=csv.writer(f);w.writerow(['file','rows','sha256']);w.writerows(idx)
 with open(root/'ensemble_counts.csv','w',encoding='utf-8',newline='') as f:
  w=csv.writer(f);w.writerow(['ensemble_primary','records','record_fraction']);w.writerows([[k,v,f'{v/total:.8f}'] for k,v in ens.most_common()])
 sp=root/'summary.json';s=json.loads(sp.read_text());s['ensemble_counts']=dict(ens.most_common());s['confidence_counts']=dict(conf);s['classifier_version']='v2-gm-boundary-corrected';s['classifier_corrections']=['GM 47 Timpani excluded from string section and counted as percussion.','GM 46 Harp remains strings-family metadata but excluded from orchestral string-section identity.','GM 52/53 are acoustic choir/voice; GM 54 Synth Voice excluded from choir identity.','GM 8-15 chromatic percussion excluded from keys identity.'];sp.write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
 rp=root/'README.md';txt=rp.read_text();txt+='\n## Classifier version\n\n`v2-gm-boundary-corrected`: ensemble/family fields exclude Timpani from strings, Synth Voice from choir identity, and chromatic percussion from keys identity. Raw `gm_program_track_counts` never changed.\n';rp.write_text(txt,encoding='utf-8')
 sums=[]
 for p in sorted(root.rglob('*')):
  if p.is_file() and p.name!='SHA256SUMS':sums.append(f'{sha(p)}  {p.relative_to(root)}')
 (root/'SHA256SUMS').write_text('\n'.join(sums)+'\n',encoding='utf-8')
 return {'records':total,'ensemble_counts':dict(ens.most_common()),'confidence_counts':dict(conf),'classifier_version':'v2-gm-boundary-corrected'}
if __name__=='__main__':
 a=argparse.ArgumentParser();a.add_argument('--root',required=True);x=a.parse_args();print(json.dumps(rewrite(x.root),indent=2))
