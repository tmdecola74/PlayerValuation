"""Preserve v1.1; freeze categorical roles and role-specific workloads using historical folds."""
import argparse,copy,json,shutil,hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite
from standalone_role_workload_v1_2 import *
from role_workload_io_v1_2 import read_labels,verify_join,read_forecasts,write_attribution,FIELDS

PROB_FIELDS=['season','mlbam_id','prior_role','method','predicted_role','p_STARTER','p_RELIEVER','p_SWING','latest_fit_year','actual_role']
def check_settings(s):
 if s['holdout_year']!=2026 or s['first_report_origin']!=2019 or s['softmax_penalty']<=0 or not 0<s['prior_role_probability_mass']<1:raise ValueError('Unsupported chronology/model settings')

def build(matrix,baseline,labels_root,config,output,backups):
 matrix,baseline,labels_root,config=map(lambda p:Path(p).resolve(),(matrix,baseline,labels_root,config));watched=verify(matrix);watched.update(verify(baseline));watched.update(verify(labels_root));watched[str(config)]=sha(config);s=load(config);check_settings(s);oldfrozen=load(baseline/'frozen_models.json');freeze=load(baseline/'freeze_manifest.json');labelreport=load(labels_root/'label_build_report.json')
 if sha(baseline/'frozen_models.json')!=freeze['models_sha256'] or sha(baseline/'frozen_2026_forecasts.csv')!=freeze['forecasts_sha256']:raise ValueError('v1.1 freeze mismatch')
 if labelreport['reference_sha256']!=oldfrozen['label_reference_sha256'] or labelreport.get('primary_source')!='FROZEN_FANGRAPHS_ACTUALS':raise ValueError('Frozen label reference differs from v1.1')
 for filename,key in [('training_matrix.parquet','training_matrix_sha256'),('holdout_features.parquet','holdout_features_sha256')]:
  if sha(matrix/filename)!=oldfrozen[key]:raise ValueError('v1.1 matrix/features mismatch')
 schema_hashes={h for name,h in load(baseline/'input_hashes.json').items() if name.replace('\\','/').endswith('/feature_schema.json')}
 if schema_hashes!={sha(matrix/'feature_schema.json')}:raise ValueError('Feature schema differs from frozen v1.1 input')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];rows=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_features.parquet'),allow,False,2026)
 if any(r['target_season']!=2026 or any(k.startswith('y_') for k in r) for r in hold):raise ValueError('Evaluation features contain outcomes or wrong year')
 actual=verify_join(rows,read_labels(labels_root,'training'));baseconfig=copy.deepcopy(oldfrozen['models']['config']);old=read_forecasts(baseline);participation={}
 for r in csvrows(baseline/'opportunity_diagnostics.csv'):
  k=(int(r['season']),r['player_type'],r['mlbam_id'])
  if k in participation:raise ValueError('Duplicate frozen participation row')
  p=float(r['participation_probability']) if r['participation_probability']!='' else None
  if p is not None and (not finite(p) or not 0<=p<=1):raise ValueError('Invalid frozen participation probability')
  participation[k]=p
 output,backups,stage=start(output,backups,[matrix,baseline,labels_root,config]);role_history=[];role_choices=[];role_predictions=[];oof=[];lineage=[];role_audit=[]
 try:
  # Each target year's role probabilities are made before that year's labels are scored.
  start_year=min(int(r['target_season']) for r in rows)
  for year in range(start_year,2027):
   print(f'{year}: categorical roles fit on target seasons before {year}',flush=True);fitting=[r for r in rows if r['target_season']<year];testing=[r for r in (hold if year==2026 else rows) if r['target_season']==year and r['player_type']=='pitcher'];model=fit_roles(fitting,allow,baseconfig,s);choice=choose_role(role_history,year,s);b,bc,cat,cc=predict_roles(model,testing,s);selected=cat if choice['candidate']=='categorical' else b;selected_classes=cc if choice['candidate']=='categorical' else bc;latest=max(model['fit_target_seasons'],default=None)
   if latest is not None and latest>=year:raise ValueError('Role chronology violation')
   role_choices.append(dict(season=year,**choice));role_audit.append(dict(origin=year,n_fit=model['n_fit'],class_counts=model['class_counts'],fit_years=model['fit_target_seasons'],status=model['status'],iterations=model['iterations']))
   enhanced=with_probabilities(testing,selected)
   for r in enhanced:
    r['role_prediction_latest_fit_year']=latest;r['role_prediction_target_season']=year
   if year<2026:oof+=enhanced
   else:hold_enhanced=enhanced;final_role=model;final_role_choice=choice
   for i,r in enumerate(testing):
    lineage.append(dict(target_season=year,mlbam_id=r['mlbam_id'],latest_role_fit_year=latest,role_choice=choice['candidate'],selection_validation_seasons=json.dumps({k:v['validation_seasons'] for k,v in choice['gates'].items()})))
    for method,probs,classes in [('prior_role',b,bc),('categorical',cat,cc),('selected_role',selected,selected_classes)]:role_predictions.append(dict(season=year,mlbam_id=r['mlbam_id'],prior_role=prior_role(r),method=method,predicted_role=classes[i],p_STARTER=float(probs[i,0]),p_RELIEVER=float(probs[i,1]),p_SWING=float(probs[i,2]),latest_fit_year=latest,actual_role=actual_role(r) if year<2026 else 'NOT_READ'))
   if year<2026:
    for cohort in ['all','known_prior']:role_history.append(dict(season=year,cohort=cohort,model_fitted=model['status']=='FITTED',**probability_metrics(testing,b,bc,cat,cc,cohort)))
  workload_history=[];workload_choices=[];workload_audit=[];predictions=[];expert_predictions=[]
  for year in range(2019,2027):
   print(f'{year}: workload experts use chronological role predictions',flush=True);fitting=[r for r in oof if r['target_season']<year];testing=hold_enhanced if year==2026 else [r for r in oof if r['target_season']==year]
   for r in fitting+testing:
    latest=r['role_prediction_latest_fit_year']
    if r['role_prediction_target_season']!=r['target_season'] or (latest is not None and latest>=r['target_season']):raise ValueError('Workload role features are not chronological OOF predictions')
   bundle=fit_workload(fitting,allow,baseconfig,s);pooled=bundle['pooled']
   if any(y>=year for y in pooled['fit_target_seasons']):raise ValueError('Pooled workload chronology violation')
   workload_audit.append(dict(origin=year,expert='POOLED',status=pooled['ridge_status'],n_fit=pooled['n_fit'],fit_years=pooled['fit_target_seasons'],uses_pooled=False))
   choice=choose_workload(workload_history,year,s);workload_choices.append(dict(season=year,**choice));mixture,experts=predict_workload(bundle,testing);candidate={}
   for name,expert in bundle['experts'].items():
    years=expert['model']['fit_target_seasons'];workload_audit.append(dict(origin=year,expert=name,status=expert['status'],n_fit=expert['model']['n_fit'],fit_years=years,uses_pooled=expert['use_pooled']))
    if any(y>=year for y in years):raise ValueError('Workload chronology violation')
   for i,r in enumerate(testing):
    key=(year,'pitcher',r['mlbam_id']);p=participation.get(key);conditional=mixture[i];expected=None if p is None or conditional is None else p*conditional;candidate[key]=expected;expert_predictions.append(dict(season=year,mlbam_id=r['mlbam_id'],participation_probability=p,conditional_OUTS=conditional,candidate_OUTS=expected,starter_OUTS=experts['STARTER'][i],reliever_OUTS=experts['RELIEVER'][i],swing_OUTS=experts['SWING'][i],workload_overlay_adopted=choice['adopt'],workload_application_supported=finite(expected) and key in old and finite(old[key].get('OUTS')) and old[key]['OUTS']>0))
   targetrows=[r for r in (hold if year==2026 else rows) if r['target_season']==year];errors=defaultdict(list)
   for r in targetrows:
    key=(year,r['player_type'],r['mlbam_id'])
    if key not in old:raise ValueError('Missing frozen v1.1 candidate')
    original=old[key];new=overlay(original,candidate.get(key),choice['adopt']) if r['player_type']=='pitcher' else dict(original)
    if new.get('SV')!=original.get('SV'):raise ValueError('Frozen v1.1 saves changed')
    for method,v in [('v1_1',original),('v1_2',new)]:
     for metric,value in v.items():predictions.append(dict(season=year,player_type=r['player_type'],mlbam_id=r['mlbam_id'],method=method,metric=metric,prediction=value))
    if year<2026 and r['player_type']=='pitcher':
     a=actual.get(key+('OUTS',));v=candidate.get(key);den=original.get('OUTS')
     if a is not None and finite(v) and finite(den):
      v=v if den>0 else den;err=(den-a,v-a);errors['all'].append((r['mlbam_id'],*err))
      if prior_role(r)=='STARTER':errors['prior_starter'].append((r['mlbam_id'],*err))
   for cohort,items in errors.items():
    e=np.array([(a,b) for pid,a,b in items]);workload_history.append(dict(season=year,cohort=cohort,n=len(e),membership_sha256=hashlib.sha256(json.dumps([pid for pid,a,b in items]).encode()).hexdigest(),baseline_mse=float((e[:,0]**2).mean()),candidate_mse=float((e[:,1]**2).mean()),baseline_mae=float(abs(e[:,0]).mean()),candidate_mae=float(abs(e[:,1]).mean())))
   if year==2026:final_workload=bundle;final_workload_choice=choice
  hist=[r for r in predictions if r['season']<2026];evaluation=[r for r in predictions if r['season']==2026];write(stage/'historical_forecasts.csv',hist,FIELDS);write(stage/'frozen_2026_forecasts.csv',evaluation,FIELDS);write(stage/'role_predictions.csv',role_predictions,PROB_FIELDS);write(stage/'role_probability_lineage.csv',lineage,['target_season','mlbam_id','latest_role_fit_year','role_choice','selection_validation_seasons']);write(stage/'workload_expert_predictions.csv',expert_predictions,['season','mlbam_id','participation_probability','conditional_OUTS','candidate_OUTS','starter_OUTS','reliever_OUTS','swing_OUTS','workload_overlay_adopted','workload_application_supported']);write_attribution(stage,hist,rows,actual)
  dump(stage/'role_candidate_scores.json',role_history);dump(stage/'role_choices.json',role_choices);dump(stage/'role_fit_audit.json',role_audit);dump(stage/'workload_candidate_scores.json',workload_history);dump(stage/'workload_choices.json',workload_choices);dump(stage/'workload_fit_audit.json',workload_audit)
  frozen=dict(version='1.2.0',settings=s,role_model=final_role,role_choice=final_role_choice,workload_model=final_workload,workload_choice=final_workload_choice,v1_1_models_sha256=freeze['models_sha256'],feature_schema_sha256=sha(matrix/'feature_schema.json'),training_matrix_sha256=sha(matrix/'training_matrix.parquet'),holdout_features_sha256=sha(matrix/'holdout_features.parquet'),training_labels_sha256=sha(labels_root/'training_labels.parquet'),label_reference_sha256=labelreport['reference_sha256'],evaluation_disclosure=DISCLOSURE)
  dump(stage/'frozen_models.json',frozen);dump(stage/'freeze_manifest.json',dict(models_sha256=sha(stage/'frozen_models.json'),forecasts_sha256=sha(stage/'frozen_2026_forecasts.csv'),role_predictions_sha256=sha(stage/'role_predictions.csv'),evaluation_outcomes_read=False))
  report=dict(version='1.2.0',status='ROLE_WORKLOAD_MODELS_FROZEN_RESEARCH_ONLY',v1_1_preserved=True,saves_preserved_exactly=True,hitter_forecasts_preserved=True,inputs_unchanged=True,evaluation_outcomes_read=False,evaluation_disclosure=DISCLOSURE,final_role_choice=final_role_choice,final_workload_choice=final_workload_choice,training_actuals_join='FROZEN_FANGRAPHS_ELIGIBLE_PA_OUTS_G_GS',limitations=['Conditional appearance modeling inherited from v1.1; no new nonappearance evidence or preseason roster universe.','Categorical role probabilities are not guaranteed calibrated; evaluate Brier/log loss as well as class accuracy.','Experts use actual role only as a training label/cohort; all role probability predictors are generated from earlier seasons.','Low-support experts use a pooled fallback. Rejected workload changes retain exact v1.1 forecasts.','2020 excluded from role/workload fitting and selection; historical stress-test reporting retained.','Hitters and saves remain exact v1.1 forecasts. Prior-role UNKNOWN uses fold-only population probabilities.','2026 has already been reviewed, so it cannot establish a new untouched-holdout claim.'])
  dump(stage/'role_workload_build_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_opportunity_v1_1');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--config',default='config/standalone_role_workload_v1_2.json');p.add_argument('--output',default='outputs/standalone_role_workload_v1_2');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.matrix,a.baseline,a.labels,a.config,a.output,a.backup_root),indent=2))
