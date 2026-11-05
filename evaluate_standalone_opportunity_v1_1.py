"""Disclosed evaluation, historical role cohorts, and post-freeze external benchmarking."""
import argparse,hashlib,json,shutil
from pathlib import Path
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite
from standalone_opportunity_v1_1 import role_of,labels,DISCLOSURE
from backtest_standalone_opportunity_v1_1 import scorewrite,actuals,evidence
from compare_standalone_benchmarks_v1_0 import warehouse_forecasts,METRICS

def keyhash(ids):return hashlib.sha256(json.dumps(ids).encode()).hexdigest()
def stat(errors):
 e=np.array(errors);return dict(mae=float(abs(e).mean()) if len(e) else None,rmse=float(np.sqrt((e*e).mean())) if len(e) else None,bias=float(e.mean()) if len(e) else None)

def cohort_scores(predictions,rows):
 truth=actuals(rows);rowmap={(r['target_season'],r['player_type'],str(r['mlbam_id'])):r for r in rows};pred=defaultdict(dict);groups=defaultdict(list)
 for r in predictions:pred[(r['season'],r['player_type'],r['mlbam_id'],r['metric'])][r['method']]=r['prediction']
 for k,v in sorted(pred.items()):
  if k not in truth or not all(finite(v.get(m)) for m in ['v1_0','v1_1']):continue
  y,role,pid,metric=k;r=rowmap[k[:3]];cohorts=['all_eligible'];exp='PA' if role=='hitter' else 'IP';exposure=truth.get(k[:3]+(exp,));prior=r.get('x_actual_lag1_'+('PA' if role=='hitter' else 'OUTS'))
  for floor in ([100,300] if role=='hitter' else [40,100]):
   if finite(exposure) and exposure>=floor:cohorts.append('actual_'+exp+'_ge'+str(floor))
  if finite(prior) and prior>=(300 if role=='hitter' else 120):cohorts.append('prior_exposure_established')
  if role=='pitcher':
   cohorts += ['actual_role_'+role_of(truth.get(k[:3]+('G',)),truth.get(k[:3]+('GS',))),'prior_role_'+role_of(r.get('x_actual_lag1_G'),r.get('x_actual_lag1_GS'))]
   for kind,sv in [('actual',truth.get(k[:3]+('SV',))),('prior',r.get('x_actual_lag1_SV'))]:
    if finite(sv) and sv>=5:cohorts.append(kind+'_saves_ge5')
  for cohort in cohorts:
   for method,p in v.items():groups[y,role,metric,cohort,method].append((pid,p-truth[k]))
 return [dict(season=y,player_type=role,metric=m,cohort=cohort,method=method,n=len(items),membership_sha256=keyhash([p for p,_ in items]),**stat([e for _,e in items])) for (y,role,m,cohort,method),items in sorted(groups.items())]

def benchmark(predictions,rows,external,available):
 truth=actuals(rows);pool=defaultdict(dict)
 for r in predictions:
  if r['season']>=2024:pool[(r['season'],r['player_type'],r['mlbam_id'],r['metric'])][r['method']]=r['prediction']
 for (y,role,pid,m,source),(v,record) in external.items():pool[(y,role,pid,m)][source]=v
 errors=defaultdict(list);pairs=[];coverage=[]
 for y in [2024,2025,2026]:
  sources=sorted(available.get(y,set()));groups=[(s+'_paired',[s]) for s in sources]+([('all_available_sources',sources)] if sources else [])
  for role,metrics in METRICS.items():
   for metric in metrics:
    keys=sorted(k for k in truth if k[0]==y and k[1]==role and k[3]==metric)
    for group,ss in groups:
     methods=['v1_0','v1_1']+ss;common=[k for k in keys if all(finite(pool[k].get(m)) for m in methods)]
     for method in methods:
      coverage.append(dict(season=y,player_type=role,metric=metric,comparison_group=group,method=method,eligible_actuals=len(keys),forecasts_with_actuals=sum(finite(pool[k].get(method)) for k in keys),common_pool=len(common)))
      for k in common:
       v=pool[k][method];errors[y,role,metric,group,method].append((k[2],v-truth[k]));pairs.append(dict(season=y,player_type=role,mlbam_id=k[2],metric=metric,comparison_group=group,method=method,prediction=v,actual=truth[k],source_record_id=external.get(k+(method,),('', 'FROZEN_STANDALONE'))[1]))
 return [dict(season=y,player_type=role,metric=m,comparison_group=group,method=method,n=len(items),membership_sha256=keyhash([p for p,_ in items]),**stat([e for _,e in items])) for (y,role,m,group,method),items in sorted(errors.items())],pairs,coverage

def evaluate(run,matrix,output,backups,warehouse=None):
 run,matrix=Path(run).resolve(),Path(matrix).resolve();watched=verify(run);watched.update(verify(matrix));freeze=load(run/'freeze_manifest.json');frozen=load(run/'frozen_models.json')
 if sha(run/'frozen_models.json')!=freeze['models_sha256'] or sha(run/'frozen_2026_forecasts.csv')!=freeze['forecasts_sha256'] or sha(matrix/'holdout_features.parquet')!=frozen['holdout_features_sha256'] or sha(matrix/'training_matrix.parquet')!=frozen['training_matrix_sha256']:raise ValueError('Frozen models/forecasts/matrix mismatch')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];training=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_matrix.parquet'),allow,True,2026)
 if any(r['target_season']!=2026 for r in hold):raise ValueError('Wrong evaluation target season')
 if (run/'participation_evidence_snapshot').exists():ew,_=evidence(run/'participation_evidence_snapshot',training);watched.update(ew)
 rows=training+hold;predictions=[]
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in csvrows(run/name):r['season']=int(r['season']);r['prediction']=float(r['prediction']) if r['prediction']!='' else None;predictions.append(r)
 rowmap={(r['target_season'],r['player_type'],str(r['mlbam_id'])):r for r in labels(rows)};diagnostics=csvrows(run/'opportunity_diagnostics.csv');rolechecks=[];participation=[];savechecks=[]
 for d in diagnostics:
  key=(int(d['season']),d['player_type'],d['mlbam_id']);r=rowmap[key]
  if d['player_type']=='pitcher':
   g=r.get('y_G') if r.get('y_eligible_G') else None;gs=r.get('y_GS') if r.get('y_eligible_GS') else None;actual_role=role_of(g,gs);rolechecks.append(dict(season=key[0],mlbam_id=key[2],actual_role=actual_role,predicted_role=d['predicted_role'],actual_G=g,actual_GS=gs,predicted_G=d['G'],predicted_GS=d['GS'],scorable=actual_role!='UNKNOWN' and d['predicted_role']!='UNKNOWN'))
   sv=r.get('y_SV') if r.get('y_eligible_SV') else None
   if finite(g) and g>0 and finite(sv) and d['save_probability_given_active']!='':
    p=float(d['save_probability_given_active']);a=int(sv>0);savechecks.append(dict(season=key[0],mlbam_id=key[2],probability=p,actual=a,brier=(p-a)**2))
  if d['participation_supported']=='True' and r['y_eligible_ACTIVE'] and d['participation_probability']!='':
   p=float(d['participation_probability']);a=r['y_ACTIVE'];participation.append(dict(season=key[0],player_type=key[1],mlbam_id=key[2],probability=p,actual=a,brier=(p-a)**2))
 role_scores=[];save_scores=[];part_scores=[]
 for y in sorted({int(d['season']) for d in diagnostics}):
  rr=[r for r in rolechecks if r['season']==y and r['scorable']];role_scores.append(dict(season=y,n=len(rr),correct=sum(r['actual_role']==r['predicted_role'] for r in rr),accuracy=sum(r['actual_role']==r['predicted_role'] for r in rr)/len(rr) if rr else None,G_rmse=stat([float(r['predicted_G'])-r['actual_G'] for r in rr if r['predicted_G']!=''])['rmse'],GS_rmse=stat([float(r['predicted_GS'])-r['actual_GS'] for r in rr if r['predicted_GS']!=''])['rmse']))
  ss=[r for r in savechecks if r['season']==y];save_scores.append(dict(season=y,n=len(ss),positive_save_seasons=sum(r['actual'] for r in ss),brier=float(np.mean([r['brier'] for r in ss])) if ss else None,scope='ANY_SAVE_CONDITIONAL_ON_OBSERVED_APPEARANCE'))
  for role in ['hitter','pitcher']:
   pp=[r for r in participation if r['season']==y and r['player_type']==role];part_scores.append(dict(season=y,player_type=role,n=len(pp),nonappearance_rows=sum(r['actual']==0 for r in pp),brier=float(np.mean([r['brier'] for r in pp])) if pp else None))
 external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});watched.update(w);bs,bp,bc=benchmark(predictions,rows,external,available);output,backups,stage=start(output,backups,[run,matrix]+([warehouse] if warehouse else []))
 try:
  n=scorewrite(stage,[r for r in predictions if r['season']==2026],hold,'evaluation_2026')
  write(stage/'cohort_scores.csv',cohort_scores(predictions,rows),['season','player_type','metric','cohort','method','n','mae','rmse','bias','membership_sha256']);write(stage/'pitcher_role_predictions.csv',rolechecks,['season','mlbam_id','actual_role','predicted_role','actual_G','actual_GS','predicted_G','predicted_GS','scorable']);write(stage/'role_scores.csv',role_scores,['season','n','correct','accuracy','G_rmse','GS_rmse']);confusion=defaultdict(int)
  for r in rolechecks:
   if r['scorable']:confusion[r['season'],r['actual_role'],r['predicted_role']]+=1
  write(stage/'role_confusion.csv',[dict(season=y,actual_role=a,predicted_role=p,n=n) for (y,a,p),n in sorted(confusion.items())],['season','actual_role','predicted_role','n']);write(stage/'saves_hurdle_scores.csv',save_scores,['season','n','positive_save_seasons','brier','scope']);write(stage/'saves_hurdle_predictions.csv',savechecks,['season','mlbam_id','probability','actual','brier']);write(stage/'participation_predictions.csv',participation,['season','player_type','mlbam_id','probability','actual','brier']);write(stage/'participation_scores.csv',part_scores,['season','player_type','n','nonappearance_rows','brier']);write(stage/'benchmark_scores.csv',bs,['season','player_type','metric','comparison_group','method','n','mae','rmse','bias','membership_sha256']);write(stage/'benchmark_paired_predictions.csv',bp,['season','player_type','mlbam_id','metric','comparison_group','method','prediction','actual','source_record_id']);write(stage/'benchmark_coverage.csv',bc,['season','player_type','metric','comparison_group','method','eligible_actuals','forecasts_with_actuals','common_pool']);write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  report=dict(version='1.1.0',status='DISCLOSED_EVALUATION_COMPLETE',evaluation_disclosure=DISCLOSURE,models_refitted=False,selection_retuned=False,inputs_unchanged=True,models_sha256=freeze['models_sha256'],paired_2026_metric_rows=n,benchmark_rows=len(bp),identity_review_rows=len(issues),participation_scored_rows=len(participation),participation_scope='Observed matrix labels plus frozen confirmed historical nonappearance evidence if supplied; absent 2026 outcomes remain unknown.',source_availability={str(y):sorted(v) for y,v in available.items()},limitations=['Actual-exposure and actual-role cohorts are retrospective diagnostics; prior-role cohorts use only lagged G/GS.','Clipped ridge probabilities are not calibrated probabilities. Unsupported participation models receive no Brier score.','2026 was reviewed before v1.1 design and is not a fresh untouched holdout.','Steamer/OOPSY enter post-freeze benchmarking only. Common eligible pools vary by source group/metric.'])
  dump(stage/'opportunity_evaluation_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_opportunity_v1_1');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--output',default='outputs/standalone_opportunity_evaluation_v1_1');p.add_argument('--backup-root',default='backups');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true');a=p.parse_args();print(json.dumps(evaluate(a.run,a.matrix,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
