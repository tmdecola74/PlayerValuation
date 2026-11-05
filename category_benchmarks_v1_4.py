"""Read-only external forecasts, preserving every metric exclusion."""
import json
from collections import defaultdict
from pathlib import Path
import duckdb
from standalone_io_v1_0 import load,sha
from standalone_models_v1_0 import finite
from standalone_combined_v1_4 import METRICS
from compare_standalone_benchmarks_v1_0 import SOURCES,published

def category_values(values,excluded):
 v=published(values,excluded)
 if 'SV_plus_HLD' not in excluded and 'SV_plus_HLD' not in v and all(finite(v.get(m)) and m not in excluded for m in ['SV','HLD']):v['SV_plus_HLD']=v['SV']+v['HLD']
 return v

def warehouse_forecasts(path):
 path=Path(path).resolve();audit=load(path.parent/'migration_audit.json');watched={str(path):sha(path),str(path.parent/'migration_audit.json'):sha(path.parent/'migration_audit.json')}
 if not audit.get('pass'):raise ValueError('Migration audit did not pass')
 for obj in audit['objects']:
  p=(path.parent/obj['parquet_file']).resolve()
  if path.parent not in p.parents or sha(p)!=obj['parquet_sha256']:raise ValueError('Migrated Parquet hash/path mismatch')
  watched[str(p)]=obj['parquet_sha256']
 result={};issues=[];available=defaultdict(set)
 with duckdb.connect(str(path),read_only=True) as db:
  ids=defaultdict(set);owners=defaultdict(set)
  for pid,ns,external in db.execute('SELECT player_id,namespace,external_id FROM player_id_crosswalk').fetchall():
   if str(ns).lower()=='mlbam' and str(external).strip().isdigit() and int(str(external).strip())>0:
    mid=str(int(str(external).strip()));ids[pid].add(mid);owners[mid].add(pid)
  for role in ['hitter','pitcher']:
   name='analytical_'+role+'_projections'
   required={'season','source','player_id','record_id','metrics_json','excluded_metrics_json'};cols={r[0] for r in db.execute('DESCRIBE '+name).fetchall()}
   if not required<=cols:raise ValueError('Analytical projection schema lacks selections/exclusions')
   for y,source,pid,record,raw,excluded in db.execute('SELECT season,source,player_id,record_id,metrics_json,excluded_metrics_json FROM '+name+' WHERE season BETWEEN 2024 AND 2026').fetchall():
    source=SOURCES.get(str(source).lower())
    if source is None:continue
    available[int(y)].add(source)
    mapped=ids[pid]
    if len(mapped)!=1 or len(owners[next(iter(mapped))])!=1:
     issues.append(dict(season=y,player_type=role,source=source,player_id=pid,record_id=record,reason='MISSING_OR_AMBIGUOUS_MLBAM_ID'));continue
    mid=next(iter(mapped));values=category_values(json.loads(raw),set(json.loads(excluded)))
    for m in METRICS[role]:
     if m not in values:continue
     k=(int(y),role,mid,m,source)
     if k in result:raise ValueError('Duplicate analytical source/player/metric')
     result[k]=(values[m],str(record))
 return result,available,issues,watched

