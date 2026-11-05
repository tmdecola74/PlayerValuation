"""Disclosed evaluation of separate frozen workload experiments; never refits or retunes."""
import argparse,json,hashlib,shutil
from pathlib import Path
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite
from role_workload_io_v1_2 import read_labels,verify_join
from compare_standalone_benchmarks_v1_0 import warehouse_forecasts
from standalone_workload_experiments_v1_3 import *
from workload_experiments_io_v1_3 import *

def direction_scores(details,rows,truth,s):
 mapping={(r['target_season'],r['player_type'],r['mlbam_id']):r for r in rows};groups=defaultdict(list);predictions=[]
 for d in details:
  key=(int(d['season']),d['player_type'],d['mlbam_id']);r=mapping[key];metric='PA' if key[1]=='hitter' else 'OUTS';a=truth.get(key+(metric,));g=truth.get(key+('G',));anch=anchor(r,s)
  if a is None or g is None or g<=0 or anch is None:continue
  p=float(d['growth_probability']);frequency=float(d['training_growth_frequency']);target=int(a>anch);v2=r.get('x_actual_lag2_'+metric);trend=None
  if finite(v2) and v2>=0:
   v2*=s['source_2020_multiplier'] if r.get('source_season_lag2')==2020 else 1.;trend=int(anch>v2)
  x=dict(season=key[0],player_type=key[1],mlbam_id=key[2],actual_volume=a,normalized_prior_anchor=anch,actual_change=a-anch,actual_growth=target,growth_probability=p,training_growth_frequency=frequency,brier=(p-target)**2,frequency_brier=(frequency-target)**2,model_correct=int((p>=.5)==bool(target)),prior_trend_prediction=trend,prior_trend_correct=None if trend is None else int(trend==target));predictions.append(x);groups[key[:2]].append(x)
 out=[]
 for (year,role),items in sorted(groups.items()):
  tt=[r for r in items if r['prior_trend_prediction'] is not None];out.append(dict(season=year,player_type=role,n=len(items),growth_cases=sum(r['actual_growth'] for r in items),model_brier=float(np.mean([r['brier'] for r in items])),training_frequency_brier=float(np.mean([r['frequency_brier'] for r in items])),model_accuracy=float(np.mean([r['model_correct'] for r in items])),trend_pool_n=len(tt),prior_trend_accuracy=float(np.mean([r['prior_trend_correct'] for r in tt])) if tt else None,model_accuracy_on_trend_pool=float(np.mean([r['model_correct'] for r in tt])) if tt else None))
 return out,predictions

def benchmarks(predictions,truth,external,available):
 scores=[];pairs=[];coverage=[]
 for year in [2024,2025,2026]:
  sources=sorted(available.get(year,set()));groups=[(src+'_paired',[src]) for src in sources]+([('all_available_sources',sources)] if sources else [])
  for role,metrics in [('hitter',['PA']),('pitcher',['OUTS','IP'])]:
   rows=[r for r in predictions if r['season']==year and r['player_type']==role];byid={r['mlbam_id']:r for r in rows}
   for metric in metrics:
    native='OUTS' if metric=='IP' else metric;scale=1/3 if metric=='IP' else 1.;actual={pid:truth[year,role,pid,native]*scale for pid in byid if (year,role,pid,native) in truth}
    for group,ss in groups:
     methods=METHODS+ss
     def value(pid,method):return byid[pid].get(method)*scale if method in METHODS and finite(byid[pid].get(method)) else external.get((year,role,pid,metric,method),(None,None))[0]
     common=sorted(pid for pid in actual if all(finite(value(pid,m)) for m in methods));membership=hashlib.sha256(json.dumps(common).encode()).hexdigest()
     for method in methods:
      e=np.array([value(pid,method)-actual[pid] for pid in common]);scores.append(dict(season=year,player_type=role,metric=metric,comparison_group=group,method=method,n=len(common),mae=float(abs(e).mean()) if len(e) else None,rmse=float(np.sqrt((e*e).mean())) if len(e) else None,bias=float(e.mean()) if len(e) else None,membership_sha256=membership));coverage.append(dict(season=year,player_type=role,metric=metric,comparison_group=group,method=method,candidate_actuals=len(actual),forecasts_with_candidate_actuals=sum(finite(value(pid,method)) for pid in actual),common_pool=len(common)))
      for pid in common:pairs.append(dict(season=year,player_type=role,mlbam_id=pid,metric=metric,comparison_group=group,method=method,prediction=value(pid,method),actual=actual[pid],source_record_id=external.get((year,role,pid,metric,method),('', 'FROZEN_EXPERIMENT'))[1]))
 return scores,pairs,coverage

def evaluate(run,matrix,baseline,labels_root,output,backups,warehouse=None):
 run,matrix,baseline,labels_root=map(lambda p:Path(p).resolve(),(run,matrix,baseline,labels_root));watched={}
 for root in [run,matrix,baseline,labels_root]:watched.update(verify(root))
 frozen=load(run/'frozen_models.json');freeze=load(run/'freeze_manifest.json')
 for filename,digest in freeze.items():
  if sha(run/filename)!=digest:raise ValueError('Experiment freeze mismatch')
 for root,filename,key in [(matrix,'training_matrix.parquet','training_matrix_sha256'),(matrix,'holdout_features.parquet','holdout_features_sha256'),(matrix,'feature_schema.json','feature_schema_sha256'),(labels_root,'training_labels.parquet','training_labels_sha256')]:
  if sha(root/filename)!=frozen[key]:raise ValueError('Frozen matrix/training-label mismatch')
 if sha(baseline/'frozen_models.json')!=frozen['source_v1_2_model_sha256'] or sha(baseline/'role_predictions.csv')!=frozen['source_role_probabilities_sha256'] or load(labels_root/'label_build_report.json')['reference_sha256']!=frozen['label_reference_sha256']:raise ValueError('Frozen source-release/reference mismatch')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];rows=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_matrix.parquet'),allow,True,2026)
 if any(r['target_season']!=2026 for r in hold):raise ValueError('Wrong evaluation target year')
 rows+=hold;truth=read_labels(labels_root,'training');truth.update(read_labels(labels_root,'holdout'));verify_join(rows,truth);bank=probability_bank(baseline,rows,load(baseline/'freeze_manifest.json'));original=read_baseline(baseline);predictions=[];seen=set()
 for r in iter_csv(run/'workload_predictions.csv'):
  r['season']=int(r['season']);key=(r['season'],r['player_type'],r['mlbam_id'])
  if key in seen or key not in original:raise ValueError('Duplicate/orphan workload prediction')
  seen.add(key)
  for method in METHODS:
   r[method]=float(r[method]) if r[method]!='' else None
   if r[method] is not None and not finite(r[method]):raise ValueError('Nonfinite workload forecast')
  for name in ['change_supported','probability_supported']:r[name]=r[name]=='True'
  predictions.append(r)
 bykey={(r['season'],r['player_type'],r['mlbam_id']):r for r in predictions};last=None;expected=None
 for filename in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in iter_csv(run/filename):
   key=(int(r['season']),r['player_type'],r['mlbam_id']);method=r['method'];token=(key,method)
   if key not in bykey or method not in ['frozen_v1_2','selected_probability_experiment','selected_change_experiment']:raise ValueError('Invalid full projection experiment')
   if token!=last:expected=volume_overlay(original[key],bykey[key][method],key[1]);last=token
   value=float(r['prediction']) if r['prediction']!='' else None;e=expected.get(r['metric'])
   if (value is None)!=(e is None) or (value is not None and abs(value-e)>1e-9*max(1,abs(e))):raise ValueError('Full projections differ from frozen workload scaling or saves')
 labels=csvrows(run/'classification_and_probability_inputs.csv');cs=set()
 for r in labels:
  key=(int(r['season']),r['mlbam_id']);source=bank[key]['prior_role']
  if key in cs or r['classification_label']!=source['predicted_role'] or r['prior_role']!=source['prior_role']:raise ValueError('Frozen prior-role classification changed')
  cs.add(key)
 expected_classes={(y,pid) for y,role,pid in bykey if role=='pitcher'}
 if cs!=expected_classes:raise ValueError('Incomplete classification preservation audit')
 ds,dp=direction_scores(csvrows(run/'change_predictions.csv'),rows,truth,frozen['settings']);external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});watched.update(w);bs,bp,bc=benchmarks(predictions,truth,external,available);output,backups,stage=start(output,backups,[run,matrix,baseline,labels_root]+([warehouse] if warehouse else []))
 try:
  summary=write_scores(stage,predictions,rows,truth,'evaluation');write(stage/'growth_direction_scores.csv',ds,['season','player_type','n','growth_cases','model_brier','training_frequency_brier','model_accuracy','trend_pool_n','prior_trend_accuracy','model_accuracy_on_trend_pool']);write(stage/'growth_direction_predictions.csv',dp,['season','player_type','mlbam_id','actual_volume','normalized_prior_anchor','actual_change','actual_growth','growth_probability','training_growth_frequency','brier','frequency_brier','model_correct','prior_trend_prediction','prior_trend_correct']);write(stage/'workload_benchmark_scores.csv',bs,['season','player_type','metric','comparison_group','method','n','mae','rmse','bias','membership_sha256']);write(stage/'workload_benchmark_pairs.csv',bp,['season','player_type','mlbam_id','metric','comparison_group','method','prediction','actual','source_record_id']);write(stage/'workload_benchmark_coverage.csv',bc,['season','player_type','metric','comparison_group','method','candidate_actuals','forecasts_with_candidate_actuals','common_pool']);write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  report=dict(version='1.3.0',status='SEPARATE_EXPERIMENTS_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,inputs_unchanged=True,saves_preserved_exactly=True,classification_labels_preserved=True,classification_gate_weakened=False,evaluation_disclosure=DISCLOSURE,models_sha256=sha(run/'frozen_models.json'),workload_score_rows=len(summary),growth_direction_score_rows=len(ds),benchmark_pair_rows=len(bp),identity_review_rows=len(issues),limitations=['Experiments are separate; no combined ensemble or production promotion is inferred from 2026.','Growth means actual exposure greater than normalized prior-year exposure; exact ties are non-growth. Actual-growth cohorts are retrospective diagnostics only.','Direction and magnitude fits condition on observed appearance; absent outcomes are unknown, not zero.','Common source pools vary by metric and source group. Probability estimates are not claimed calibrated.','2026 was previously reviewed and cannot establish fresh independent holdout evidence.'])
  dump(stage/'workload_experiments_evaluation_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--output',default='outputs/standalone_workload_experiments_evaluation_v1_3');p.add_argument('--backup-root',default='backups');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true');a=p.parse_args();print(json.dumps(evaluate(a.run,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
