"""Back up migrated warehouse and compare four SQLite/DuckDB evaluator stages."""
import argparse,csv,importlib,json,math,shutil,time
from pathlib import Path
from datetime import datetime,timezone
from warehouse_readonly_v1_0 import sha,open_warehouse

STAGES=[('accuracy','evaluate_historical_projection_accuracy','evaluate','accuracy_evaluation.json'),('consensus','build_consensus_projections','build','consensus_projections.json'),('consensus_backtest','backtest_consensus_projections','run','consensus_backtesting.json'),('blend_backtest','backtest_projection_blends','backtest','blend_backtesting.json')]
IGNORED={'built_at_utc','built_at','generated_at','warehouse','warehouse_sha256','output'}

def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items() if k not in IGNORED}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,str):
  try:
   x=json.loads(v)
   if isinstance(x,(dict,list)):return clean(x)
  except (ValueError,TypeError):pass
 return v

def compare(a,b,path='$',differences=None):
 differences=[] if differences is None else differences
 if isinstance(a,dict) and isinstance(b,dict):
  if set(a)!=set(b):differences.append({'path':path,'reason':'keys','sqlite':sorted(a),'duckdb':sorted(b)})
  for k in sorted(set(a)&set(b)):compare(a[k],b[k],path+'.'+k,differences)
 elif isinstance(a,list) and isinstance(b,list):
  if len(a)!=len(b):differences.append({'path':path,'reason':'length','sqlite':len(a),'duckdb':len(b)})
  for i,(x,y) in enumerate(zip(a,b)):compare(x,y,f'{path}[{i}]',differences)
 elif a!=b:
  try:
   # Integer-valued IDs/sample fields remain exact. Tolerance only float values.
   numeric=('.' in str(a) or 'e' in str(a).lower() or '.' in str(b) or 'e' in str(b).lower())
   if numeric and math.isclose(float(a),float(b),rel_tol=1e-10,abs_tol=1e-12):return differences
  except (ValueError,TypeError):pass
  if len(differences)<100:differences.append({'path':path,'reason':'value','sqlite':a,'duckdb':b})
 return differences

def load(path):
 if path.suffix=='.csv':
  with path.open(encoding='utf-8-sig',newline='') as f:
   reader=csv.DictReader(f);headers=reader.fieldnames or [];rows=[clean(r) for r in reader]
  rows.sort(key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))
  return {'headers':sorted(headers),'rows':rows}
 if path.suffix=='.jsonl':
  rows=[clean(json.loads(s)) for s in path.read_text(encoding='utf-8').splitlines() if s.strip()]
  return sorted(rows,key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))
 value=clean(json.loads(path.read_text(encoding='utf-8')))
 if isinstance(value,list):value.sort(key=lambda r:json.dumps(r,sort_keys=True,ensure_ascii=False))
 return value

def compare_outputs(left,right):
 def files(root):return {p.relative_to(root).as_posix():p for p in root.rglob('*') if p.is_file() and p.suffix in ('.csv','.json','.jsonl')}
 a=files(left);b=files(right);checks=[]
 if not a or not b:return [{'file':'*','pass':False,'reason':'empty output set'}]
 for name in sorted(set(a)|set(b)):
  if name not in a or name not in b:checks.append({'file':name,'pass':False,'reason':'missing file'});continue
  differences=compare(load(a[name]),load(b[name]))
  checks.append({'file':name,'pass':not differences,'differences':differences})
 return checks

def fingerprints(path):
 path=Path(path)
 if path.suffix=='.duckdb':
  audit=json.loads((path.parent/'migration_audit.json').read_text(encoding='utf-8'))
  paths=sorted(p for p in path.parent.rglob('*') if p.is_file())
 else:paths=[path]
 return {str(p):sha(p) for p in paths}

def run(project,sqlite,duckdb,output,backup=None):
 project=Path(project).resolve();sqlite=Path(sqlite).resolve();duckdb=Path(duckdb).resolve();output=Path(output).resolve()
 if output.exists():raise ValueError('Comparison output must not exist')
 if output==project or output in project.parents:raise ValueError('Output cannot contain project')
 for db in (sqlite,duckdb):
  if not db.is_file():raise FileNotFoundError(db)
  if output==db.parent or output in db.parents or db.parent in output.parents:raise ValueError('Keep comparison output outside database directories')
 backup=Path(backup).resolve() if backup else project/'backups'/('historical_duckdb_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f'))
 if backup==duckdb.parent or duckdb.parent in backup.parents or backup in duckdb.parents:raise ValueError('Backup must be outside migrated directory')
 # No database writes occur. Caller must close any other warehouse writers.
 audit=json.loads((duckdb.parent/'migration_audit.json').read_text(encoding='utf-8'))
 if sha(sqlite)!=audit['source_sha256']:raise ValueError('SQLite reference differs from migration source; rebuild/resolve before comparison')
 before={**fingerprints(sqlite),**fingerprints(duckdb)}
 backup.parent.mkdir(parents=True,exist_ok=True)
 print('Backing up complete migrated folder to '+str(backup),flush=True)
 shutil.copytree(duckdb.parent,backup)
 for original,hash_value in fingerprints(duckdb).items():
  copied=backup/Path(original).relative_to(duckdb.parent)
  if sha(copied)!=hash_value:raise ValueError('Backup hash mismatch')
 with_read=open_warehouse(duckdb)
 try:with_read.execute('PRAGMA integrity_check').fetchone()
 finally:with_read.close()
 output.mkdir(parents=True)
 checks=[];timings={}
 for label,module,function,config_name in STAGES:
  config=project/'config'/config_name
  for backend,db in [('sqlite',sqlite),('duckdb',duckdb)]:
   print(label+': running '+backend,flush=True);start=time.perf_counter()
   name=module+('_duckdb_v1_0' if backend=='duckdb' else '_v1_0')
   fn=getattr(importlib.import_module(name),function)
   fn(config,output/backend/label,db)
   timings[label+'_'+backend]=round(time.perf_counter()-start,3)
  stage_checks=compare_outputs(output/'sqlite'/label,output/'duckdb'/label)
  for check in stage_checks:check['stage']=label
  checks.extend(stage_checks)
  print(label+': '+('PASS' if all(r['pass'] for r in stage_checks) else 'DIFFERENCES FOUND'),flush=True)
 unchanged=before=={**fingerprints(sqlite),**fingerprints(duckdb)}
 report={'pass':unchanged and bool(checks) and all(r['pass'] for r in checks),'inputs_unchanged':unchanged,'backup':str(backup),'timings_seconds':timings,'checks':checks,'ignored_metadata_keys':sorted(IGNORED),'numeric_relative_tolerance':1e-10,'numeric_absolute_tolerance':1e-12,'notes':['CSV/JSON/JSONL compared; Markdown presentation reports excluded.','Row order ignored for top-level record lists; duplicates retained.','Reference outputs freshly recomputed with unchanged original SQLite scripts. Existing outputs untouched.']}
 (output/'backend_comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print(json.dumps({k:report[k] for k in ('pass','inputs_unchanged','backup','timings_seconds')},indent=2))
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--sqlite',required=True);p.add_argument('--duckdb',required=True);p.add_argument('--output',required=True);p.add_argument('--project',default='.');p.add_argument('--backup')
 a=p.parse_args();r=run(a.project,a.sqlite,a.duckdb,a.output,a.backup)
 raise SystemExit(0 if r['pass'] else 1)
if __name__=='__main__':main()
