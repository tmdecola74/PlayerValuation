"""Post-freeze Steamer/OOPSY comparison using common eligible pools and read-only warehouse access."""
import argparse,math,shutil
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
import duckdb
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite

METRICS={'hitter':['PA','AB','H','HR','R','RBI','SB','AVG','OBP','SLG','OPS'],'pitcher':['OUTS','IP','H','ER','BB','SO','W','SV','HLD','QS','ERA','WHIP']}
SOURCES={'steamer':'Steamer','oopsy':'OOPSY'}
def published(values,excluded):
 v={k:float(x) for k,x in values.items() if finite(x) and k not in excluded}
 def derive(m,deps,fn):
  if m not in v and m not in excluded and all(d in v and d not in excluded for d in deps):
   x=fn()
   if x is not None and finite(x):v[m]=x
 derive('SO',['K'],lambda:v['K']);derive('OUTS',['IP'],lambda:3*v['IP'])
 derive('AVG',['H','AB'],lambda:v['H']/v['AB'] if v['AB']>0 else None)
 derive('ERA',['ER','IP'],lambda:9*v['ER']/v['IP'] if v['IP']>0 else None)
 derive('WHIP',['H','BB','IP'],lambda:(v['H']+v['BB'])/v['IP'] if v['IP']>0 else None)
 derive('OPS',['OBP','SLG'],lambda:v['OBP']+v['SLG'])
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
    mid=next(iter(mapped));values=published(json.loads(raw),set(json.loads(excluded)))
    for m in METRICS[role]:
     if m not in values:continue
     k=(int(y),role,mid,m,source)
     if k in result:raise ValueError('Duplicate analytical source/player/metric')
     result[k]=(values[m],str(record))
 return result,available,issues,watched

def compare(run,labels,warehouse,output,backups):
 run,labels=Path(run).resolve(),Path(labels).resolve();watched=verify(run);watched.update(verify(labels));frozen=load(run/'frozen_models.json');freeze=load(run/'freeze_manifest.json')
 if sha(run/'frozen_models.json')!=freeze['models_sha256'] or sha(run/'frozen_2026_forecasts.csv')!=freeze['forecasts_sha256']:raise ValueError('Model freeze mismatch')
 if load(labels/'label_build_report.json')['reference_sha256']!=frozen['label_reference_sha256']:raise ValueError('Benchmark actuals use different frozen source')
 actual={}
 for name in ['training_labels.parquet','holdout_labels.parquet']:
  for r in table(labels/name):
   if 2024<=r['season']<=2026 and r['eligible'] and finite(r['label_value']):actual[int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric']]=r['label_value']
 forecasts={}
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in csvrows(run/name):
   if r['prediction']=='' or not 2024<=int(r['season'])<=2026:continue
   k=(int(r['season']),r['player_type'],r['mlbam_id'],r['metric'],r['method'])
   if k in forecasts:raise ValueError('Duplicate frozen forecast')
   forecasts[k]=(float(r['prediction']),'FROZEN_STANDALONE')
 external,available,issues,w=warehouse_forecasts(warehouse);watched.update(w);forecasts.update(external)
 groups={}
 for y in [2024,2025,2026]:
  for source in ['Steamer','OOPSY']:
   if source in available[y]:groups[y,source+'_paired']=['historical_baseline','selected_standalone',source]
  if available[y]:groups[y,'all_available_sources']=['historical_baseline','selected_standalone']+sorted(available[y])
 pairs=[];summary=[];coverage=[]
 for (y,group),methods in sorted(groups.items()):
  for role,metrics in METRICS.items():
   for metric in metrics:
    keys=sorted(k for k in actual if k[0]==y and k[1]==role and k[3]==metric)
    common=[k for k in keys if all(k+(m,) in forecasts and finite(forecasts[k+(m,)][0]) for m in methods)]
    membership=sha_keys=hashlib.sha256(json.dumps(common).encode()).hexdigest()
    for method in methods:
     errors=[forecasts[k+(method,)][0]-actual[k] for k in common]
     summary.append(dict(season=y,player_type=role,metric=metric,comparison_group=group,method=method,n=len(common),mae=float(np.mean(abs(np.array(errors)))) if errors else None,rmse=float(np.sqrt(np.mean(np.array(errors)**2))) if errors else None,bias=float(np.mean(errors)) if errors else None,membership_sha256=membership))
     coverage.append(dict(season=y,player_type=role,metric=metric,comparison_group=group,method=method,eligible_actuals=len(keys),method_forecasts_with_actuals=sum(k+(method,) in forecasts for k in keys),common_pool=len(common)))
     for k in common:pairs.append(dict(season=y,player_type=role,mlbam_id=k[2],metric=metric,comparison_group=group,method=method,prediction=forecasts[k+(method,)][0],actual=actual[k],source_record_id=forecasts[k+(method,)][1]))
 output,backups,stage=start(output,backups,[run,labels,warehouse])
 try:
  write(stage/'benchmark_scores.csv',summary,['season','player_type','metric','comparison_group','method','n','mae','rmse','bias','membership_sha256']);write(stage/'benchmark_paired_predictions.csv',pairs,['season','player_type','mlbam_id','metric','comparison_group','method','prediction','actual','source_record_id']);write(stage/'benchmark_coverage.csv',coverage,['season','player_type','metric','comparison_group','method','eligible_actuals','method_forecasts_with_actuals','common_pool']);write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  report=dict(version='1.0.0',status='POST_FREEZE_BENCHMARK_COMPLETE',source_availability={str(y):sorted(available[y]) for y in [2024,2025,2026]},paired_rows=len(pairs),identity_review_rows=len(issues),models_refitted=False,selection_retuned=False,inputs_unchanged=True,models_sha256=freeze['models_sha256'],limitations=['Only common eligible pools support direct accuracy comparisons; source-specific coverage is reported separately.','Sources absent in a season are reported as absent, never zero forecasts.','Analytical warehouse selections and metric exclusions are retained. No name matching.','Projection metrics are scored as published; listed rates are derived only when missing and permitted by available components.','Historical benchmark scope is 2024–2026; OOPSY may be absent in 2024.','Retrospective files and user-confirmed preseason dates are not independently archived as-of vintages.'])
  dump(stage/'benchmark_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_baselines_v1_0');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--output',default='outputs/standalone_benchmarks_v1_0');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(compare(a.run,a.labels,a.warehouse,a.output,a.backup_root),indent=2))
