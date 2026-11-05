"""Read-only workload attribution and disclosed evaluation of frozen role/workload forecasts."""
import argparse,hashlib,json,shutil
from collections import defaultdict
from pathlib import Path
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite
from standalone_role_workload_v1_2 import ROLES,DISCLOSURE,actual_role
from role_workload_io_v1_2 import read_labels,verify_join,write_attribution,read_forecasts
from compare_standalone_benchmarks_v1_0 import warehouse_forecasts

ROLE_FIELDS=['season','cohort','method','n','accuracy','balanced_accuracy','brier','logloss','membership_sha256']
def role_scores(role_predictions,rows):
 mapping={(r['target_season'],r['mlbam_id']):r for r in rows if r['player_type']=='pitcher'};groups=defaultdict(list);confusion=defaultdict(int);detail=[];seen=set()
 for r in role_predictions:
  y=int(r['season']);pid=r['mlbam_id'];key=(y,pid);unique=(y,pid,r['method'])
  if unique in seen or key not in mapping:raise ValueError('Duplicate/orphan role prediction')
  seen.add(unique);a=actual_role(mapping[key]);p=np.array([float(r['p_'+role]) for role in ROLES])
  if not np.isfinite(p).all() or min(p)<0 or abs(p.sum()-1)>1e-8 or r['predicted_role'] not in ROLES:raise ValueError('Invalid frozen role forecast')
  d=dict(r);d['actual_role']=a;d['scorable']=a in ROLES;detail.append(d)
  if a not in ROLES:continue
  truth=ROLES.index(a);entry=(pid,a,r['predicted_role'],float(((p-np.eye(3)[truth])**2).sum()),float(-np.log(np.clip(p[truth],1e-15,1))))
  for cohort in ['all']+(['known_prior'] if r['prior_role'] in ROLES else []):groups[y,cohort,r['method']].append(entry)
  confusion[y,r['method'],a,r['predicted_role']]+=1
 scores=[]
 for (y,cohort,method),items in sorted(groups.items()):
  recalls=[np.mean([a==pred for _,a,pred,_,_ in items if a==role]) for role in ROLES if any(a==role for _,a,_,_,_ in items)]
  scores.append(dict(season=y,cohort=cohort,method=method,n=len(items),accuracy=float(np.mean([a==pred for _,a,pred,_,_ in items])),balanced_accuracy=float(np.mean(recalls)),brier=float(np.mean([b for *_,b,l in items])),logloss=float(np.mean([l for *_,b,l in items])),membership_sha256=hashlib.sha256(json.dumps([pid for pid,*_ in items]).encode()).hexdigest()))
 return scores,[dict(season=y,method=m,actual_role=a,predicted_role=p,n=n) for (y,m,a,p),n in sorted(confusion.items())],detail

def workload_benchmarks(predictions,actual,external,available):
 truth=dict(actual)
 for (y,role,pid,metric),a in list(truth.items()):
  if role=='pitcher' and metric=='OUTS':truth[y,role,pid,'IP']=a/3
 pool=defaultdict(dict)
 for r in predictions:
  if r['season']>=2024 and r['metric'] in ['PA','OUTS','IP']:pool[r['season'],r['player_type'],r['mlbam_id'],r['metric']][r['method']]=r['prediction']
 for (y,role,pid,metric,source),(v,record) in external.items():
  if metric in ['PA','OUTS','IP']:pool[y,role,pid,metric][source]=v
 scores=[];pairs=[];coverage=[]
 for y in [2024,2025,2026]:
  sources=sorted(available.get(y,set()));groups=[(source+'_paired',[source]) for source in sources]+([('all_available_sources',sources)] if sources else [])
  for role,metrics in [('hitter',['PA']),('pitcher',['OUTS','IP'])]:
   for metric in metrics:
    keys=sorted(k for k in truth if k[0]==y and k[1]==role and k[3]==metric)
    for group,ss in groups:
     methods=['v1_1','v1_2']+ss;common=[k for k in keys if all(finite(pool[k].get(m)) for m in methods)]
     membership=hashlib.sha256(json.dumps([k[2] for k in common]).encode()).hexdigest()
     for method in methods:
      e=np.array([pool[k][method]-truth[k] for k in common]);scores.append(dict(season=y,player_type=role,metric=metric,comparison_group=group,method=method,n=len(common),mae=float(abs(e).mean()) if len(e) else None,rmse=float(np.sqrt((e*e).mean())) if len(e) else None,bias=float(e.mean()) if len(e) else None,membership_sha256=membership));coverage.append(dict(season=y,player_type=role,metric=metric,comparison_group=group,method=method,eligible_actuals=len(keys),forecasts_with_actuals=sum(finite(pool[k].get(method)) for k in keys),common_pool=len(common)))
      for k in common:pairs.append(dict(season=y,player_type=role,mlbam_id=k[2],metric=metric,comparison_group=group,method=method,prediction=pool[k][method],actual=truth[k],source_record_id=external.get(k+(method,),('', 'FROZEN_STANDALONE'))[1]))
 return scores,pairs,coverage

def evaluate(run,matrix,labels_root,baseline,output,backups,warehouse=None):
 run,matrix,labels_root,baseline=map(lambda p:Path(p).resolve(),(run,matrix,labels_root,baseline));watched=verify(run);watched.update(verify(matrix));watched.update(verify(labels_root));watched.update(verify(baseline));frozen=load(run/'frozen_models.json');freeze=load(run/'freeze_manifest.json')
 for filename,key in [('frozen_models.json','models_sha256'),('frozen_2026_forecasts.csv','forecasts_sha256'),('role_predictions.csv','role_predictions_sha256')]:
  if sha(run/filename)!=freeze[key]:raise ValueError('v1.2 freeze mismatch')
 for root,filename,key in [(matrix,'feature_schema.json','feature_schema_sha256'),(matrix,'training_matrix.parquet','training_matrix_sha256'),(matrix,'holdout_features.parquet','holdout_features_sha256'),(labels_root,'training_labels.parquet','training_labels_sha256')]:
  if sha(root/filename)!=frozen[key]:raise ValueError('Frozen feature/training-label mismatch')
 if load(labels_root/'label_build_report.json')['reference_sha256']!=frozen['label_reference_sha256'] or sha(baseline/'frozen_models.json')!=frozen['v1_1_models_sha256']:raise ValueError('v1.1/actual-reference mismatch')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];training=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_matrix.parquet'),allow,True,2026)
 if any(r['target_season']!=2026 for r in hold):raise ValueError('Incorrect evaluation season')
 truth=read_labels(labels_root,'training');truth.update(read_labels(labels_root,'holdout'));rows=training+hold;verify_join(rows,truth);old=read_forecasts(baseline);predictions=[]
 for filename in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in csvrows(run/filename):
   r['season']=int(r['season']);r['prediction']=float(r['prediction']) if r['prediction']!='' else None;k=(r['season'],r['player_type'],r['mlbam_id'])
   if k not in old:raise ValueError('Orphan frozen forecast')
   if r['metric']=='SV' and r['prediction']!=old[k].get('SV'):raise ValueError('v1.1 saves preservation failed')
   if r['player_type']=='hitter' and r['prediction']!=old[k].get(r['metric']):raise ValueError('Hitter forecast preservation failed')
   predictions.append(r)
 scores,confusion,detail=role_scores(csvrows(run/'role_predictions.csv'),rows);external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});watched.update(w);bs,bp,bc=workload_benchmarks(predictions,truth,external,available);output,backups,stage=start(output,backups,[run,matrix,labels_root,baseline]+([warehouse] if warehouse else []))
 try:
  workload_scores=write_attribution(stage,predictions,rows,truth);write(stage/'role_scores.csv',scores,ROLE_FIELDS);write(stage/'role_confusion.csv',confusion,['season','method','actual_role','predicted_role','n']);fields=['season','mlbam_id','prior_role','method','predicted_role','p_STARTER','p_RELIEVER','p_SWING','latest_fit_year','actual_role','scorable'];write(stage/'role_predictions_with_actuals.csv',detail,fields);write(stage/'workload_benchmark_scores.csv',bs,['season','player_type','metric','comparison_group','method','n','mae','rmse','bias','membership_sha256']);write(stage/'workload_benchmark_pairs.csv',bp,['season','player_type','mlbam_id','metric','comparison_group','method','prediction','actual','source_record_id']);write(stage/'workload_benchmark_coverage.csv',bc,['season','player_type','metric','comparison_group','method','eligible_actuals','forecasts_with_actuals','common_pool']);write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  report=dict(version='1.2.0',status='DISCLOSED_ROLE_WORKLOAD_EVALUATION_COMPLETE',evaluation_disclosure=DISCLOSURE,models_refitted=False,selection_retuned=False,saves_preserved_exactly=True,hitter_forecasts_preserved=True,inputs_unchanged=True,models_sha256=freeze['models_sha256'],workload_score_rows=len(workload_scores),role_score_rows=len(scores),benchmark_pair_rows=len(bp),identity_review_rows=len(issues),source_availability={str(y):sorted(v) for y,v in available.items()},limitations=['Actual-role/exposure/change cohorts are retrospective attribution only. Prior-role cohorts use strictly previous-season G/GS.','Missing actuals remain unknown and are excluded from accuracy pools; no absence-to-zero inference.','Role probabilities are conditional on an observed appearance/known role label; participation remains inherited from v1.1.','Benchmarks here cover PA/OUTS/IP only. External projection systems are not training or selection inputs.','2026 is previously reviewed, not independent untouched-holdout evidence.'])
  dump(stage/'role_workload_evaluation_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_role_workload_v1_2');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--baseline',default='outputs/standalone_opportunity_v1_1');p.add_argument('--output',default='outputs/standalone_role_workload_evaluation_v1_2');p.add_argument('--backup-root',default='backups');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true');a=p.parse_args();print(json.dumps(evaluate(a.run,a.matrix,a.labels,a.baseline,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
