"""Disclosed 2026 reporting for frozen coherent-group choices. Never select or fit."""
import argparse,json,shutil
from pathlib import Path
from standalone_io_v1_0 import load,sha,dump,verify,table,csvrows,start,finish
from standalone_diagnostics_v1_16 import checked,emit,comparison_summary
from coherent_skill_groups_v1_19 import VERSION,ARMS,scored,member
from standalone_combined_v1_4 import coherent,METRICS
from statcast_incremental_v1_17 import finite

def evaluate(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 run=Path(a.run).resolve();labels=Path(a.labels).resolve();matrix=Path(a.matrix).resolve();source=Path(a.source_run).resolve();watched=verify(run)
 for n,h in load(run/'forecast_freeze.json').items():
  p=(run/n).resolve()
  if run not in p.parents or sha(p)!=h:raise ValueError('Group freeze mismatch')
 report=load(run/'group_build_report.json')
 if report['version']!=VERSION or report['evaluation_outcomes_read'] or report['selection_max_season']!=2025:raise ValueError('Invalid frozen choices')
 choices=load(run/'frozen_choices_2026.json');digest=__import__('hashlib').sha256(json.dumps(choices,sort_keys=True).encode()).hexdigest()
 if digest!=report['frozen_choices_sha256']:raise ValueError('Choice digest mismatch')
 bindings=load(run/'input_hashes.json');sp=checked(source,'input_hashes.json',watched);lr=checked(labels,'label_build_report.json',watched)
 if any(bindings.get(str(p))!=sha(p) for p in [sp,lr]):raise ValueError('Evaluation source/reference binding mismatch')
 original=load(sp);hp=checked(matrix,'holdout_features.parquet',watched)
 if original.get(str(hp))!=sha(hp):raise ValueError('Evaluation context differs from frozen source')
 lp=checked(labels,'holdout_labels.parquet',watched);actual={};seen=set()
 print('Frozen choices verified. Reading disclosed 2026 outcomes for reporting only...',flush=True)
 for r in table(lp):
  k=int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric']
  if k[0]!=2026 or k[1] not in METRICS or not k[2].isdigit() or int(k[2])<=0 or k in seen or r['eligible'] not in [0,1,False,True]:raise ValueError('Invalid evaluation label')
  seen.add(k)
  if r['eligible'] and (k[3] in METRICS[k[1]] or k[3] in ['G','GS']):
   if not finite(r['label_value']) or r['label_value']<0:raise ValueError('Invalid eligible evaluation value')
   actual[k]=float(r['label_value'])
 features={}
 for r in table(hp):
  k=int(r['target_season']),r['player_type'],str(r['mlbam_id'])
  if k[0]!=2026 or k in features or k[1] not in METRICS or not k[2].isdigit() or int(r['max_source_season'])>=2026 or str(r['source_cutoff'])>='2026-01-01' or any(n.startswith('y_') for n in r):raise ValueError('Invalid evaluation feature chronology')
  features[k]=r
 rows=[];seen=set();vectors={}
 for raw in csvrows(run/'frozen_2026_forecasts.csv'):
  r=dict(raw,season=int(raw['season']),prediction=float(raw['prediction']) if raw['prediction']!='' else None);k=r['season'],r['player_type'],r['mlbam_id'];token=k+(r['method'],r['metric'])
  if k[0]!=2026 or k not in features or r['method'] not in ['accepted_frozen','historical_selected']+ARMS or token in seen:raise ValueError('Invalid frozen forecast')
  seen.add(token);vectors.setdefault(k+(r['method'],),{})[r['metric']]=r['prediction'];rows.append(r)
 for k,v in vectors.items():
  if set(v)!=set(METRICS[k[1]]):raise ValueError('Incomplete frozen vector')
  coherent(k[1],v)
 scores,coverage,outliers=scored(rows,actual,features);support={(int(r['season']),r['player_type'],r['mlbam_id'],r['method']):r for r in csvrows(run/'group_support.csv') if int(r['season'])==2026};fitkeys={k[:3] for k in vectors if all(support[k[:3]+(arm,)]['supported']=='True' and support[k[:3]+(arm,)]['group_models_fitted']=='True' for arm in ARMS)};fs,_,_=scored([r for r in rows if (r['season'],r['player_type'],r['mlbam_id']) in fitkeys],actual,features)
 out,backups,stage=start(a.output,a.backup_root,[run,labels,matrix,source])
 try:
  for n,rr in [('evaluation_scores',scores),('evaluation_comparison_summary',comparison_summary(scores)),('evaluation_fitted_scores',fs),('evaluation_fitted_summary',comparison_summary(fs)),('evaluation_coverage',coverage),('evaluation_outliers',outliers)]:emit(stage/(n+'.csv'),rr)
  result=dict(version=VERSION,status='PREVIOUSLY_REVIEWED_2026_REPORTING_ONLY',choices_changed=False,forecasts_changed=False,models_fitted=False,new_source_promoted=False,frozen_choices_sha256=digest,forecast_freeze_sha256=sha(run/'forecast_freeze.json'),score_rows=len(scores),limitations=['2026 is previously reviewed evaluation data, not independent confirmation.', 'No threshold, group, arm, cap or coefficient selected from these outcomes.', 'Raw frozen v1.17 rates are reused; no external projection system enters either arm.'])
  dump(stage/'group_evaluation_report.json',result);backup=finish(out,backups,stage,watched);return dict(result,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(run='outputs/coherent_skill_groups_v1_19',source_run='outputs/statcast_incremental_v1_17',labels='outputs/training_labels_v1_0',matrix='outputs/standalone_lagged_features_v1_0',output='outputs/coherent_skill_groups_v1_19_evaluation',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(evaluate(p.parse_args()),indent=2))
