"""UTF-8, manifest integrity and complete-backup helpers."""
import csv,json,hashlib,shutil,tempfile,math
from pathlib import Path
from datetime import datetime,timezone
import duckdb

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def dump(p,v):Path(p).write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def table(p):
 with duckdb.connect() as db:
  rel=db.read_parquet(str(p));cols=rel.columns;return [dict(zip(cols,r)) for r in rel.fetchall()]
def csvrows(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows,fields):
 with Path(p).open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def tree(p):return {str(x.relative_to(p)):sha(x) for x in p.rglob('*') if x.is_file()}
def verify(root):
 root=Path(root).resolve();manifest=load(root/'output_sha256.json');watched={str(root/'output_sha256.json'):sha(root/'output_sha256.json')}
 for n,h in manifest.items():
  p=(root/n).resolve()
  if root not in p.parents or sha(p)!=h:raise ValueError('Manifest path/hash failure: '+n)
  watched[str(p)]=h
 return watched

def start(output,backups,inputs):
 output,backups=Path(output).resolve(),Path(backups).resolve()
 if output.exists():raise FileExistsError('Choose a new output folder')
 for src in map(lambda p:Path(p).resolve(),inputs):
  if output==src or output in src.parents or src in output.parents or backups==src or backups in src.parents or src in backups.parents:raise ValueError('Input/output/backup overlap')
 if output==backups or output in backups.parents or backups in output.parents:raise ValueError('Output/backup overlap')
 output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent));return output,backups,stage

def finish(output,backups,stage,watched):
 backup=backups/(output.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
 try:
  if any(sha(p)!=h for p,h in watched.items()):raise ValueError('Input changed during run')
  dump(stage/'input_hashes.json',watched);dump(stage/'output_sha256.json',tree(stage));backups.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
  if tree(stage)!=tree(backup):raise ValueError('Complete backup failed verification')
  if any(sha(p)!=h for p,h in watched.items()):raise ValueError('Input changed before publication')
  if output.exists():raise FileExistsError(output)
  stage.rename(output);return str(backup)
 except BaseException:
  if backup.exists():shutil.rmtree(backup)
  raise

def validate_features(rows,allow,labels=False,maximum=2025):
 allowed_context={'history_seasons','age_at_target_estimate','has_any_actual_history','has_any_statcast_history'}
 if len(allow)!=len(set(allow)) or any(not(n.startswith(('x_actual_lag','x_statcast_lag','tracking_era_lag','short_season_lag')) or n in allowed_context) or n.startswith('y_') for n in allow):raise ValueError('Unapproved predictor/target leakage')
 seen=set()
 for r in rows:
  y=int(r['target_season']);role=r['player_type'];pid=str(r['mlbam_id']);k=(y,role,pid)
  if y>maximum or role not in ('hitter','pitcher') or not pid.isdigit() or int(pid)<=0 or k in seen:raise ValueError('Invalid/duplicate matrix key or target season')
  seen.add(k)
  if int(r['max_source_season'])>=y or str(r['source_cutoff'])>=str(y)+'-01-01':raise ValueError('Future history/cutoff')
  for lag in [1,2,3]:
   source=r.get('source_season_lag'+str(lag))
   if source is not None and source!=y-lag:raise ValueError('Incorrect lag source year')
   if source is None and any(r.get(n) is not None for n in allow if n.startswith(f'x_actual_lag{lag}_') or n.startswith(f'x_statcast_lag{lag}_')):raise ValueError('Feature with unregistered lag year')
  if any(n not in r for n in allow):raise ValueError('Predictor column missing')
  if labels:
   for n,v in r.items():
    if n.startswith('y_eligible_') and v not in (0,1,False,True):raise ValueError('Invalid eligibility flag')
    if n.startswith('y_') and not n.startswith('y_eligible_'):
     valid=r.get('y_eligible_'+n[2:])
     if (valid and (v is None or not math.isfinite(float(v)))) or (not valid and v is not None):raise ValueError('Label mask/value mismatch')
 return rows
