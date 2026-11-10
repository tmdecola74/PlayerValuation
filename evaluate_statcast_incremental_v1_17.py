"""Evaluate already-frozen skill experiments on disclosed 2026 outcomes; never fit."""
import argparse,csv,json,shutil
from pathlib import Path
from standalone_io_v1_0 import load,sha,dump,verify,table,start,finish,csvrows
from standalone_combined_v1_4 import METRICS,coherent
from standalone_diagnostics_v1_16 import checked,score,comparison_summary,emit
from statcast_incremental_v1_17 import VERSION,rate_scores,finite,paired_statistic_scores

def evaluate(a):
 source=Path(a.run).resolve();labels=Path(a.labels).resolve();matrix=Path(a.matrix).resolve();watched=verify(source)
 for n,h in load(source/'forecast_freeze.json').items():
  p=(source/n).resolve()
  if source not in p.parents or sha(p)!=h:raise ValueError('Experiment freeze mismatch')
 report=load(source/'incremental_build_report.json')
 if report['version']!=VERSION or report['evaluation_outcomes_read']:raise ValueError('Require frozen unevaluated build')
 inputs=load(source/'input_hashes.json');hp=checked(matrix,'holdout_features.parquet',watched);lr=checked(labels,'label_build_report.json',watched)
 if any(inputs.get(str(p))!=sha(p) for p in [hp,lr]):raise ValueError('Evaluation reference/features differ from frozen experiment')
 lp=checked(labels,'holdout_labels.parquet',watched);actual={};seen=set()
 for r in table(lp):
  k=int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric']
  if k[0]!=2026 or k[1] not in METRICS or not k[2].isdigit() or k in seen:raise ValueError('Invalid/duplicate disclosed evaluation label')
  seen.add(k)
  if r['eligible'] not in [True,False,0,1]:raise ValueError('Invalid evaluation eligibility')
  if r['eligible'] and (k[3] in METRICS[k[1]] or k[3] in ['G','GS']):
   if not finite(r['label_value']) or r['label_value']<0:raise ValueError('Invalid eligible evaluation component')
   actual[k]=float(r['label_value'])
 features={}
 for r in table(hp):
  k=int(r['target_season']),r['player_type'],str(r['mlbam_id'])
  if k[0]!=2026 or k in features or any(n.startswith('y_') for n in r):raise ValueError('Invalid/duplicate evaluation features')
  features[k]=r
 bank={};vv={}
 with (source/'frozen_2026_forecasts.csv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   k=int(r['season']),r['player_type'],r['mlbam_id'];method=r['method'];m=r['metric'];v=float(r['prediction']) if r['prediction']!='' else None;token=k+(m,'accepted_v1_5' if method=='accepted_frozen' else method)
   if k[0]!=2026 or token in bank:raise ValueError('Invalid frozen evaluation forecast')
   bank[token]=v;vv.setdefault(k+(method,),{})[m]=v
 for k,v in vv.items():coherent(k[1],v)
 rates=[]
 with (source/'frozen_2026_skill_rates.csv').open(encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):
   r=dict(row,season=int(row['season']));
   if r['season']!=2026:raise ValueError('Wrong frozen skill-rate split')
   for n in ['accepted_frozen','standard_skill','statcast_skill','historical_selected']:r[n]=float(row[n]) if row[n]!='' else None
   rates.append(r)
 print('Forecasts and historical choices verified. Reading disclosed 2026 labels for reporting only...',flush=True)
 rs=rate_scores(rates,actual,features);fitted_rs=rate_scores([r for r in rates if r.get('standard_fit_status')=='FITTED' and r.get('statcast_fit_status')=='FITTED'],actual,features);cs,coverage,outliers=score(bank,actual,features);support={(int(r['season']),r['player_type'],r['mlbam_id'],r['method']):r for r in csvrows(source/'composition_support.csv')};keys={k[:3] for k in bank if all(support[k[:3]+(method,)]['accepted_vector_fallback']=='False' and support[k[:3]+(method,)]['all_role_skill_models_fitted']=='True' for method in ['standard_skill','statcast_skill'])};fitted_cs,_,_=score({k:v for k,v in bank.items() if k[:3] in keys},actual,features);out,backups,stage=start(a.output,a.backup_root,[source,labels,matrix])
 try:
  for n,rr in [('evaluation_rate_scores',rs),('evaluation_rate_comparison_summary',comparison_summary(rs)),('evaluation_fitted_rate_scores',fitted_rs),('evaluation_fitted_statistic_scores',fitted_cs),('evaluation_count_and_ratio_scores',cs),('evaluation_paired_statistic_scores',paired_statistic_scores(bank,actual,features)),('evaluation_comparison_summary',comparison_summary(cs)),('evaluation_coverage',coverage),('evaluation_outliers',outliers)]:emit(stage/(n+'.csv'),rr)
  result=dict(version=VERSION,status='DISCLOSED_2026_EVALUATION_ONLY',models_fitted=False,choices_changed=False,forecasts_changed=False,experiment_freeze_sha256=sha(source/'forecast_freeze.json'),rate_score_rows=len(rs),statistic_score_rows=len(cs),limitations=['2026 was previously reviewed; not an untouched holdout.','No decisions, caps or coefficients are selected or retuned here.','No Steamer/OOPSY input enters either arm; external benchmarking remains a separate comparison.'])
  dump(stage/'incremental_evaluation_report.json',result);backup=finish(out,backups,stage,watched);return dict(result,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(run='outputs/statcast_incremental_v1_17',labels='outputs/training_labels_v1_0',matrix='outputs/standalone_lagged_features_v1_0',output='outputs/statcast_incremental_v1_17_evaluation',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(evaluate(p.parse_args()),indent=2))
