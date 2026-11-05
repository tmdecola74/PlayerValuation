"""Evaluate frozen combined forecasts across categories. No training or selection."""
import argparse,csv,json,shutil
from contextlib import ExitStack
from standalone_io_v1_0 import dump,sha,verify,start,finish,load,write
from standalone_combined_v1_4 import *
from category_benchmarks_v1_4 import warehouse_forecasts

def validate_combined(run,c):
 watched=verify(run)
 for n,h in load(run/'freeze_manifest.json').items():
  if sha(run/n)!=h:raise ValueError('Combined freeze mismatch')
 f=load(run/'frozen_composition.json')
 if f['source_v1_3_models_sha256']!=sha(c['source']/'frozen_models.json') or f['source_v1_3_freeze_sha256']!=sha(c['source']/'freeze_manifest.json') or f['final_historical_choices']!=c['choices'][-1]:raise ValueError('Source composition binding mismatch')
 seen=set()
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  last=None;vv=None
  for r in iter_csv(run/name):
   key=(int(r['season']),r['player_type'],r['mlbam_id']);method=r['method'];token=(key,method,r['metric'])
   if key not in c['predictions'] or method not in METHODS or token in seen or (key[0]==2026)!=(name.startswith('frozen')):raise ValueError('Duplicate/orphan combined forecast')
   if key!=last:vv=vectors(c,key);last=key
   value=None if r['prediction']=='' else float(r['prediction'])
   if r['metric'] not in vv[method] or not near(value,vv[method][r['metric']]):raise ValueError('Combined vector differs from frozen policy')
   seen.add(token)
 expected_count=sum(sum(len(v) for v in vectors(c,k).values()) for k in c['predictions'])
 if len(seen)!=expected_count:raise ValueError('Incomplete combined vector domain')
 if sha(run/'classification_and_probability_inputs.csv')!=sha(c['source']/'classification_and_probability_inputs.csv'):raise ValueError('Classification changed')
 return watched

def evaluate(run,source,matrix,baseline,labels,output,backups,warehouse=None):
 print('Verifying frozen composition before reading evaluation labels...',flush=True)
 run=Path(run).resolve();c=context(source,matrix,baseline,labels);c['watched'].update(validate_combined(run,c))
 actual=read_all_labels(c['labels'],'training');actual.update(read_all_labels(c['labels'],'holdout'))
 external,available,issues,watched=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});c['watched'].update(watched)
 output,backups,stage=start(output,backups,[run,source,matrix,baseline,labels]+([warehouse] if warehouse else []))
 try:
  with ExitStack() as stack:
   writers=[]
   for name,fields in [('category_scores.csv',SCORE_FIELDS),('category_coverage.csv',COVERAGE_FIELDS),('category_pairs.csv',PAIR_FIELDS)]:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();writers.append(w)
   counts=score_all(c,actual,*writers,external,available)
  write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  # Compact 5x5 and Yahoo 6x6 summaries, using the same metric-specific common pools.
  fantasy={'hitter':['R','HR','RBI','SB','AVG','OPS'],'pitcher':['W','SV','SO','ERA','WHIP','QS','SV_plus_HLD']}
  summaries=[]
  for r in iter_csv(stage/'category_scores.csv'):
   if r['cohort']=='all_eligible' and r['metric'] in fantasy[r['player_type']]:summaries.append(r)
  write(stage/'fantasy_category_scores.csv',summaries,SCORE_FIELDS)
  report=dict(version='1.4.0',status='FROZEN_COMBINED_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,inputs_unchanged=True,saves_preserved_exactly=True,classification_labels_preserved=True,classification_gate_weakened=False,pitcher_change_used_in_combined=False,**counts,source_availability={str(y):sorted(available.get(y,set())) for y in [2024,2025,2026]},benchmark_run=warehouse is not None,identity_review_rows=len(issues),evaluation_disclosure=DISCLOSURE,limitations=['Common pools are identical across all four standalone methods and each included external source, separately per metric/cohort. Missing/excluded actuals and forecasts are never zero.','No overall winner is inferred by summing errors across categories with different units.','Ratios are evaluated per player, not projected team standings. Actual workload floors are retrospective diagnostics only.','SV_plus_HLD actuals require an explicitly eligible frozen label. Missing labels are never rebuilt. External SV+HLD requires both non-excluded components and no combined-metric exclusion. K is canonical SO.','Pitcher-change forecasts remain a separate research file and cannot drive combined recommendations.','2020 remains a reported stress season; 2026 is previously reviewed evaluation data.','Source date uncertainty, measurement-era differences and unsupported participation remain inherited limitations.'])
  dump(stage/'combined_evaluation_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_combined_v1_4');p.add_argument('--source',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--output',default='outputs/standalone_combined_evaluation_v1_4');p.add_argument('--backup-root',default='backups');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true');a=p.parse_args();print(json.dumps(evaluate(a.run,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
