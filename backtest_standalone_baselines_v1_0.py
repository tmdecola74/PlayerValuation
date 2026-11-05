"""Chronological standalone component baselines and frozen 2026 forecasts. No holdout outcomes read."""
import argparse,math,json,shutil
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import TARGETS,fit,predict,choose,compose,outcome,finite

FIELDS=['season','player_type','mlbam_id','method','metric','prediction']
def forecasts(rows,components):
 out=[]
 for i,r in enumerate(rows):
  for method in ['historical_baseline','selected_standalone']:
   values=compose(r['player_type'],{t.id:components[t.id][method][i] for t in TARGETS if t.role==r['player_type']})
   for m,v in values.items():out.append(dict(season=r['target_season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],method=method,metric=m,prediction=v))
 return out

def scores(forecast,rows):
 actual={(r['target_season'],r['player_type'],r['mlbam_id'],n[2:]):v for r in rows for n,v in r.items() if n.startswith('y_') and not n.startswith('y_eligible_') and r.get('y_eligible_'+n[2:]) and finite(v)}
 grouped=defaultdict(dict)
 for r in forecast:grouped[r['season'],r['player_type'],r['mlbam_id'],r['metric']][r['method']]=r['prediction']
 summary=defaultdict(list);pairs=[]
 for k,p in sorted(grouped.items()):
  if k not in actual or any(not finite(p.get(m)) for m in ['historical_baseline','selected_standalone']):continue
  a=actual[k];members_hash=hashlib.sha256('|'.join(map(str,k)).encode()).hexdigest()
  pairs.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],metric=k[3],actual=a,baseline=p['historical_baseline'],standalone=p['selected_standalone']))
  for m,v in p.items():summary[k[0],k[1],k[3],m].append((k[2],v-a))
 rowsout=[]
 for (y,role,metric,method),items in sorted(summary.items()):
  e=np.array([v for _,v in items]);rowsout.append(dict(season=y,player_type=role,metric=metric,method=method,n=len(items),mae=float(np.mean(abs(e))),rmse=float(np.sqrt(np.mean(e*e))),bias=float(np.mean(e)),membership_sha256=hashlib.sha256(json.dumps([p for p,_ in items]).encode()).hexdigest(),playing_time_stress_season=y==2020))
 return rowsout,pairs

def build(matrix_dir,config,output,backups):
 matrix_dir,config=Path(matrix_dir).resolve(),Path(config).resolve();watched=verify(matrix_dir);watched[str(config)]=sha(config);c=load(config);schema=load(matrix_dir/'feature_schema.json');allow=schema['predictor_allowlist']
 if c['last_training_year']!=2025 or c['holdout_year']!=2026 or c['ridge_alpha']<=0:raise ValueError('Unsupported frozen chronology/config')
 train=validate_features(table(matrix_dir/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix_dir/'holdout_features.parquet'),allow,False,2026)
 if any(r['target_season']!=2026 for r in hold):raise ValueError('Wrong holdout feature season')
 output,backups,stage=start(output,backups,[matrix_dir,config]);history=[];selections=[];all_forecasts=[];fit_audit=[];component_rows=[]
 try:
  for y in range(c['first_inner_origin'],c['last_training_year']+1):
   print(f'Rolling origin {y}: fitting only earlier target years',flush=True);evaluation=[r for r in train if r['target_season']==y];components={}
   for t in TARGETS:
    fitting=[r for r in train if r['player_type']==t.role and r['target_season']<y];model=fit(fitting,t,allow,c);choice=choose([h for h in history if h['season']<y],t,c)
    # Predictions are generated for the complete candidate pool before current outcomes are scored.
    base,ridge=predict(model,evaluation,t,c);selected=ridge if choice['candidate']=='ridge' else base
    components[t.id]={'historical_baseline':base,'selected_standalone':selected}
    selections.append(dict(season=y,target=t.id,**choice));fit_audit.append(dict(season=y,target=t.id,n_fit=model['n_fit'],latest_fit_year=max(model['fit_target_seasons'],default=None),ridge_status=model['ridge_status']))
    paired=[(outcome(r,t)[0],a,b) for r,a,b in zip(evaluation,base,ridge) if r['player_type']==t.role and outcome(r,t) is not None and finite(a) and finite(b)]
    if paired:
     a=np.array(paired);history.append(dict(season=y,target=t.id,n=len(paired),baseline_mse=float(np.mean((a[:,1]-a[:,0])**2)),ridge_mse=float(np.mean((a[:,2]-a[:,0])**2)),baseline_mae=float(np.mean(abs(a[:,1]-a[:,0]))),ridge_mae=float(np.mean(abs(a[:,2]-a[:,0]))),ridge_fitted=model['ridge_status']=='FITTED'))
   if y>=c['first_report_origin']:all_forecasts+=forecasts(evaluation,components)
  print('Freezing final choices and fitting through 2025; no 2026 outcomes read.',flush=True);models={};choices={};components={}
  for t in TARGETS:
   choice=choose(history,t,c);model=fit([r for r in train if r['player_type']==t.role],t,allow,c);choices[t.id]=choice;models[t.id]=model;base,ridge=predict(model,hold,t,c);selected=ridge if choice['candidate']=='ridge' else base
   components[t.id]={'historical_baseline':base,'selected_standalone':selected}
   for i,r in enumerate(hold):
    if r['player_type']==t.role:component_rows.append(dict(season=2026,player_type=t.role,mlbam_id=r['mlbam_id'],component=t.id,baseline=base[i],ridge=ridge[i],selected=selected[i],selected_candidate=choice['candidate']))
  frozen=dict(version='1.0.0',config=c,label_reference_sha256=load(matrix_dir/'label_source_report.json')['reference_sha256'],training_matrix_sha256=sha(matrix_dir/'training_matrix.parquet'),holdout_features_sha256=sha(matrix_dir/'holdout_features.parquet'),feature_schema_sha256=sha(matrix_dir/'feature_schema.json'),models=models,choices=choices,target_specs=[t.__dict__ for t in TARGETS])
  dump(stage/'frozen_models.json',frozen);hold_forecasts=forecasts(hold,components);write(stage/'frozen_2026_forecasts.csv',hold_forecasts,FIELDS);write(stage/'historical_forecasts.csv',all_forecasts,FIELDS)
  write(stage/'holdout_component_forecasts.csv',component_rows,list(component_rows[0]));dump(stage/'historical_component_scores.json',history);dump(stage/'rolling_selections.json',selections);dump(stage/'fit_chronology_audit.json',fit_audit)
  summary,pairs=scores(all_forecasts,train);write(stage/'historical_scores.csv',summary,['season','player_type','metric','method','n','mae','rmse','bias','membership_sha256','playing_time_stress_season']);write(stage/'historical_paired_predictions.csv',pairs,['season','player_type','mlbam_id','metric','actual','baseline','standalone'])
  dump(stage/'freeze_manifest.json',dict(models_sha256=sha(stage/'frozen_models.json'),forecasts_sha256=sha(stage/'frozen_2026_forecasts.csv'),holdout_outcomes_read=False))
  report=dict(version='1.0.0',status='RESEARCH_BASELINES_FROZEN',historical_origins=list(range(c['first_report_origin'],2026)),component_targets=len(TARGETS),selected_ridge_components=sum(v['candidate']=='ridge' for v in choices.values()),holdout_forecast_rows=len(hold_forecasts),holdout_outcomes_read=False,external_projections_used=False,inputs_unchanged=True,models_fitted=True,model_ready=False,limitations=['Fits/evaluation are conditional on supplied eligible actual labels. Missing target outcomes are not zero and non-return participation is not modeled.','Cold-start/prospect players outside the prior-history matrix have no model forecast.','Playing-time targets in 2020 are excluded from fitting/selection; 2020 forecast scores are stress-test reports. Prior 2020 volume predictors scale by fixed 162/60; rate-baseline reliability uses observed exposure.','Rate training floors: 50 PA or 30 AB for hitters, 90 OUTS for pitchers. Actual training exposure is a label/weight only, never a prediction input.','Historical choices use only earlier validation origins. Final 2026 choices use through-2025 origins, never 2026 outcomes.','Point forecasts enforce fixed component coherence; role changes, injuries and team opportunity are not explicitly modeled.','Retrospective data are not archived preseason vintages. No statistical-significance or production-readiness claim.'])
  dump(stage/'standalone_build_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--config',default='config/standalone_baselines_v1_0.json');p.add_argument('--output',default='outputs/standalone_baselines_v1_0');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.matrix,a.config,a.output,a.backup_root),indent=2))
