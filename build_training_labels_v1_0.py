"""Materialize frozen FanGraphs labels with exclusions and physically separate holdout tables."""
from __future__ import annotations
import argparse,csv,hashlib,json,os,shutil,tempfile
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
from decimal import Decimal
import duckdb
from training_label_rules_v1_0 import COUNTS,resolve_label,primitives

VERSION='1.0.0'
KEY=['season','player_type','mlbam_id']
FIELDS=KEY+['metric','label_value','eligible','reasons','case_ids','dependencies','policy_version','purpose','label_source']
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def tree(p):return {str(x.relative_to(p)):sha(x) for x in p.rglob('*') if x.is_file()}
def inside(root,name):
 p=(root/name).resolve()
 if p==root or root not in p.parents:raise ValueError('Manifest path outside register')
 return p
def integer(x,label):
 try:v=Decimal(str(x))
 except ArithmeticError:raise ValueError('Invalid '+label) from None
 if not v.is_finite() or v<0 or v!=int(v):raise ValueError('Invalid '+label)
 return int(v)
def records(db,path,required):
 rel=db.read_parquet(str(path))
 if not set(required)<=set(rel.columns):raise ValueError('Unexpected Parquet schema: '+path.name)
 return rel.project(','.join('"'+x+'"' for x in required)).fetchall()
def reference_rows(reference,policy,config):
 paths=[reference/'actual_counts.parquet',reference/'player_seasons.parquet']
 hashes={p.name:sha(p) for p in paths}
 if hashes!=policy['expected_reference_hashes']:raise ValueError('Frozen reference hash mismatch; no override or reimport is permitted')
 years=set(config['training_seasons'])|{config['holdout_season']};players={};counts=defaultdict(dict);seen=set()
 with duckdb.connect() as db:
  for y,role,pid,split in records(db,paths[1],KEY+['split']):
   y,pid=integer(y,'season'),str(integer(pid,'MLBAM ID'));k=(y,role,pid)
   if pid=='0' or role not in COUNTS or y not in years or k in players:raise ValueError('Invalid or duplicate player-season identity')
   expected='holdout' if y==config['holdout_season'] else 'historical'
   if split!=expected:raise ValueError('Player split contradicts configured season')
   players[k]=split
  for y,role,pid,metric,value,split in records(db,paths[0],KEY+['metric','value','split']):
   k=(integer(y,'season'),role,str(integer(pid,'MLBAM ID')));mk=k+(metric,)
   if k not in players or split!=players[k] or mk in seen or metric not in COUNTS.get(role,set()):raise ValueError('Orphan/duplicate count, unknown primitive or split mismatch')
   seen.add(mk);counts[k][metric]=None if value is None else integer(value,'count')
 if not players or set(counts)!=set(players):raise ValueError('Empty reference or player-season without any counts')
 for role in COUNTS:
  if {k[0] for k in players if k[1]==role}!=years:raise ValueError('Missing requested season/role coverage')
 return players,counts,hashes

def build(reference,register_dir,config_path,output,backup_root):
 reference,register_dir,config_path,output,backup_root=map(lambda p:Path(p).resolve(),(reference,register_dir,config_path,output,backup_root))
 if output.exists():raise FileExistsError('Choose a new output folder')
 for a,b in [(output,reference),(output,register_dir),(output,backup_root),(backup_root,reference),(backup_root,register_dir)]:
  if a==b or a in b.parents or b in a.parents:raise ValueError('Overlapping input/output/backup paths')
 config=load(config_path);policy=load(register_dir/'modeling_label_policy.json');register=load(register_dir/'discrepancy_register.json');rreport=load(register_dir/'build_report.json')
 manifest=load(register_dir/'output_sha256.json')
 for name,h in manifest.items():
  if sha(inside(register_dir,name))!=h:raise ValueError('Register manifest hash mismatch: '+name)
 for name in ['modeling_label_policy.json','discrepancy_register.json','build_report.json']:
  if name not in manifest:raise ValueError('Incomplete register manifest')
 if policy['primary_season_label_source']!='FROZEN_FANGRAPHS_ACTUALS' or policy['cross_source_component_substitution'] or policy['disputed_metric_action']!='EXCLUDE_METRIC_AND_DEPENDENT_LABELS':raise ValueError('Unsupported primary-label policy')
 if policy['version']!='1.0.0' or config['holdout_season']!=policy['holdout_season'] or max(config['training_seasons'])!=policy['training_max_season'] or any(y>=config['holdout_season'] for y in config['training_seasons']):raise ValueError('Training/holdout policy mismatch')
 if len(set(config['training_seasons']))!=len(config['training_seasons']):raise ValueError('Duplicate training seasons')
 if len(register)!=rreport['baseline_discrepancy_rows']:raise ValueError('Register count mismatch')
 if sha(Path(__file__).with_name('training_label_rules_v1_0.py'))!=config['rules_sha256']:raise ValueError('Label resolver code differs from pinned implementation')
 if set(config['metrics'])!=set(COUNTS) or set(config['joint_bundles'])!=set(COUNTS):raise ValueError('Both roles must have explicit targets and bundles')
 for role,metrics in config['metrics'].items():
  if role not in COUNTS or len(metrics)!=len(set(metrics)):raise ValueError('Invalid target list')
  for m in metrics:primitives(role,m)
  if not set(config['joint_bundles'][role])<=set(metrics):raise ValueError('Bundle member not in configured label targets')
 watched=[config_path,register_dir/'output_sha256.json']+[inside(register_dir,n) for n in manifest]+[reference/'actual_counts.parquet',reference/'player_seasons.parquet']
 fingerprints={str(p):sha(p) for p in watched}
 print('Verifying frozen FanGraphs reference and register...',flush=True)
 players,counts,hashes=reference_rows(reference,policy,config)
 regkeys=set();case_ids=set()
 for r in register:
  k=(int(r['season']),r['player_type'],str(r['mlbam_id']));rk=k+(r['metric'],)
  if rk in regkeys or r['case_id'] in case_ids:raise ValueError('Duplicate register key or case ID')
  regkeys.add(rk);case_ids.add(r['case_id'])
  if k not in counts or counts[k].get(r['metric'])!=integer(r['fangraphs_actual'],'registered reference value'):raise ValueError('Register case absent or baseline count differs from frozen reference')
 # Index the register once; per-label lookups need only the player's cases.
 by_player=defaultdict(list)
 for r in register:by_player[(int(r['season']),r['player_type'],str(r['mlbam_id']))].append(r)
 output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent));opened=[];backup=None
 try:
  writers={};totals=Counter();reason_counts=Counter();coverage=Counter();bundles=[]
  for split in ['training','holdout']:
   for kind in ['labels','label_audit']:
    f=(stage/f'{split}_{kind}.csv').open('w',newline='',encoding='utf-8');opened.append(f);w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();writers[split,kind]=w
  for i,(k,source_split) in enumerate(sorted(players.items()),1):
   y,role,pid=k;split='holdout' if source_split=='holdout' else 'training';purpose='holdout_evaluation' if split=='holdout' else 'training';decisions={}
   for metric in config['metrics'][role]:
    d=resolve_label(y,role,pid,metric,counts[k],by_player[k],policy,hashes['actual_counts.parquet'],purpose);decisions[metric]=d
    row=dict(zip(KEY,k));row.update(metric=metric,label_value=d['value'],eligible=d['eligible'],reasons=json.dumps(d['reasons']),case_ids=json.dumps(d['case_ids']),dependencies=json.dumps(d['dependencies']),policy_version=policy['version'],purpose=purpose,label_source=d['source'])
    writers[split,'label_audit'].writerow(row);totals[split+'_audit']+=1;coverage[y,role,metric,'eligible' if d['eligible'] else 'excluded']+=1
    if d['eligible']:writers[split,'labels'].writerow(row);totals[split+'_eligible']+=1
    else:
     totals[split+'_excluded']+=1
     for reason in d['reasons']:reason_counts[split,reason]+=1
   members=config['joint_bundles'][role];valid=all(decisions[m]['eligible'] for m in members)
   bundles.append(dict(zip(KEY,k))|dict(split=split,bundle_eligible=valid,excluded_members=json.dumps([m for m in members if not decisions[m]['eligible']]),bundle_values=json.dumps({m:decisions[m]['value'] for m in members}) if valid else None,policy_version=policy['version']))
   if i%2000==0:print(f'{i:,}/{len(players):,} player-seasons processed',flush=True)
  for f in opened:f.close()
  opened=[]
  for split in ['training','holdout']:
   with (stage/(split+'_joint_bundles.csv')).open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=list(bundles[0]));w.writeheader();w.writerows(r for r in bundles if r['split']==split)
  with (stage/'label_coverage.csv').open('w',newline='',encoding='utf-8') as f:
   w=csv.writer(f);w.writerow(['season','player_type','metric','status','rows']);w.writerows([list(k)+[v] for k,v in sorted(coverage.items())])
  types={**{x:'VARCHAR' for x in FIELDS},'season':'INTEGER','label_value':'DOUBLE','eligible':'BOOLEAN'}
  print('Writing Parquet tables and checking split isolation...',flush=True)
  with duckdb.connect() as db:
   for split in ['training','holdout']:
    for kind in ['labels','label_audit']:
     name=split+'_'+kind;rel=db.read_csv(str(stage/(name+'.csv')),header=True,columns=types);rel.create_view(name)
     bad=db.execute(f'SELECT count(*) FROM {name} WHERE season '+('>=?' if split=='training' else '<>?'),[config['holdout_season']]).fetchall()[0][0]
     if bad:raise ValueError('Holdout contamination')
     if kind=='labels' and db.execute(f'SELECT count(*) FROM {name} WHERE NOT eligible OR label_value IS NULL').fetchall()[0][0]:raise ValueError('Masked label leaked into usable labels')
     rel.write_parquet(str(stage/(name+'.parquet')),compression='zstd')
   if db.execute('SELECT count(*) FROM training_labels t JOIN holdout_labels h USING(season,player_type,mlbam_id,metric)').fetchall()[0][0]:raise ValueError('Overlapping split keys')
  for name in ['modeling_label_policy.json','discrepancy_register.json','build_report.json']:
   dest=stage/'register_snapshot'/name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(register_dir/name,dest)
  shutil.copyfile(config_path,stage/'training_labels_config.json');shutil.copyfile(Path(__file__).with_name('training_label_rules_v1_0.py'),stage/'training_label_rules_snapshot.py')
  dump(stage/'input_hashes.json',fingerprints)
  report=dict(version=VERSION,status='LABEL_TABLES_BUILT_NOT_FULL_MODEL_APPROVAL',training_seasons=config['training_seasons'],holdout_season=config['holdout_season'],player_seasons=len(players),player_seasons_by_split=dict(Counter('holdout' if v=='holdout' else 'training' for v in players.values())),rows=dict(totals),exclusion_reasons=[dict(split=k[0],reason=k[1],rows=v) for k,v in sorted(reason_counts.items())],registered_disputed_metrics=len(register),reference_sha256=hashes,primary_source=policy['primary_season_label_source'],source_counts_modified=False,inputs_unchanged=True,holdout_physically_separate=True,models_fitted=False,model_ready=False,notes=['Eligibility applies to the frozen-label policy only; coverage, historical measurements and feature chronology retain separate readiness gates.','Same-season actual counts are targets/target denominators, never preseason features.','2026 holdout labels are evaluation-only; no fit or model selection is performed.','2020 is retained as observed; season-length normalization belongs to later modeling.','No replacement of excluded components by MLB or Statcast values.'])
  dump(stage/'label_build_report.json',report)
  if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Inputs changed during build')
  backup=backup_root/(output.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'));report['backup']=str(backup);dump(stage/'label_build_report.json',report)
  dump(stage/'output_sha256.json',tree(stage));backup_root.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
  if tree(stage)!=tree(backup):raise ValueError('Complete backup verification failed')
  if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Input changed before publication')
  if output.exists():raise FileExistsError('Output created during run')
  stage.rename(output);return report
 finally:
  for f in opened:f.close()
  if stage.exists():
   shutil.rmtree(stage)
   if backup is not None and backup.exists():shutil.rmtree(backup)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reference',default='data/actuals_reference_v1_0_min0ip');p.add_argument('--register',default='outputs/discrepancy_register_v1_0_utf8');p.add_argument('--config',default='config/training_labels_v1_0.json');p.add_argument('--output',default='outputs/training_labels_v1_0');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.reference,a.register,a.config,a.output,a.backup_root),indent=2))
if __name__=='__main__':main()
