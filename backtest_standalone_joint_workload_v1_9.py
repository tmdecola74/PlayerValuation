"""Freeze a joint pitcher-workload candidate and descriptive SB-feature audit."""
import argparse,csv,json,shutil,hashlib,math
from pathlib import Path
from collections import defaultdict
from contextlib import ExitStack
from standalone_io_v1_0 import load,dump,sha,start,finish
from standalone_joint_workload_v1_9 import *
from joint_io_v1_9 import context,source_hashes,predictions,replay,emit,forecast,FIELDS,parameter_rows
from joint_scores_v1_9 import summaries,SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS
from standalone_refinements_v1_8 import cohort_names
from standalone_attribution_v1_5 import workload_band
from sb_propensity_audit_v1_9 import freeze_bins,audit

def scores(stage,c,items,actual,maximum=2025,external=None,available=None):
 with ExitStack() as stack:
  ww=[]
  for name,fields in [('category_scores.csv',SCORE_FIELDS),('category_coverage.csv',COVERAGE_FIELDS),('comparison_pairs.csv',PAIR_FIELDS)]:
   f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();ww.append(w)
  return summaries(c,items,actual,*ww,external,available,maximum)

def comparison(c,items,actual,maximum):
 groups=defaultdict(list)
 for k,d in sorted(items.items()):
  if k[1]!='pitcher' or k[0]>maximum:continue
  a=actual.get(k+('OUTS',));vv={'frozen_v1_5':d['baseline'],'research_v1_6':d['research_v1_6'],'research_v1_8':c['items18'][k]['candidate'],'candidate_v1_9':d['candidate'],'selected_v1_9':d['selected']}
  if not finite(a) or not all(finite(v) for v in vv.values()):continue
  cc=cohort_names('pitcher',c['rows'][k],{})+['prior_workload_'+workload_band(c['rows'][k].get('x_actual_lag1_OUTS'),'pitcher')]
  for cohort in cc:groups[k[0],cohort].append((k,a,vv,d['supported']))
 for y in range(2019,maximum+1):groups[y,'all']
 out=[]
 for (y,cc),rr in sorted(groups.items()):
  n=len(rr);member=hashlib.sha256(json.dumps([k for k,a,v,s in rr]).encode()).hexdigest()
  for metric,scale in [('OUTS',1.),('IP',1/3)]:
   for method in ['frozen_v1_5','research_v1_6','research_v1_8','candidate_v1_9','selected_v1_9']:
    ee=[(v[method]-a)*scale for k,a,v,s in rr];out.append(dict(season=y,cohort=cc,method=method,metric=metric,n=n,supported=sum(s for k,a,v,s in rr),RMSE=math.sqrt(sum(e*e for e in ee)/n) if n else None,MAE=sum(abs(e) for e in ee)/n if n else None,bias=sum(ee)/n if n else None,membership_sha256=member,stress_season=y==2020,disclosed_evaluation=y==2026))
 return out

def sb_audit(stage,c,actual,allow,s,bins,maximum):
 tables=audit(c['rows'],actual,allow,s,bins,maximum)
 for name,rr in tables.items():emit(stage,name+'.csv',rr)
 return {name:len(rr) for name,rr in tables.items()}

def build(run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels,config,output,backups):
 print('Verifying preserved v1.8 and earlier frozen research...',flush=True);c=context(run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels);config=Path(config).resolve();s=settings_checked(load(config));c['watched'][str(config)]=sha(config);actual=c['actual_training'];items={};history=defaultdict(list);choices=[];models={};members=[];allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist']
 output,backups,stage=start(output,backups,[run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels,config])
 try:
  for y in range(2019,2027):
   print(f'{y}: joint final-workload calibration from earlier OOF forecasts; probabilities fixed',flush=True);model,mm=fit_joint(c['items16'],c['rows'],actual,y,s,c['old16']['settings']);models[str(y)]=model;members+=mm;pp=predictions(c,model,y);choice=dict(season=y,pitcher=selection(history['pitcher'],y,s));choices.append(choice)
   for k,d in pp.items():items[k]=d|dict(selected=d['candidate'] if k[1]=='pitcher' and choice['pitcher']['adopt'] else d['baseline'])
   add_history(y,items,c['rows'],actual,history,s)
  if choices!=replay(c,items,s):raise ValueError('Internal joint gate replay failure')
  emit(stage,'experiment_predictions.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**d) for k,d in sorted(items.items())]);dump(stage/'origin_models.json',models);dump(stage/'rolling_choices.json',choices);dump(stage/'historical_gate_evidence.json',history);emit(stage,'joint_calibration_parameters.csv',parameter_rows(models));emit(stage,'joint_calibration_fit_members.csv',members);emit(stage,'workload_comparison.csv',comparison(c,items,actual,2025))
  emit(stage,'transition_2021.csv',[dict(season=2021,mlbam_id=k[2],prior_role=prior_role(c['rows'][k]),prior_observed_OUTS=c['rows'][k].get('x_actual_lag1_OUTS'),actual_OUTS=actual.get(k+('OUTS',)),research_v1_8=c['items18'][k]['candidate'],**d) for k,d in sorted(items.items()) if k[:2]==(2021,'pitcher')])
  print('Auditing SB propensity changes and freezing predictor-only historical bin boundaries...',flush=True);bins=freeze_bins(c['rows'],allow,s);dump(stage/'sb_frozen_feature_bins.json',bins);auditcounts=sb_audit(stage,c,actual,allow,s,bins,2025);counts=scores(stage,c,items,actual)
  checks=[]
  with ExitStack() as stack:
   writers=[]
   for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();writers.append(w)
   for k,d in sorted(items.items()):
    for method in METHODS:
     v=forecast(c,k,d,method)
     if k[1]=='hitter' and v!=c['base15'][k]:raise ValueError('SB audit changed accepted hitter forecasts')
     checks.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,coherent=True,accepted_saves_holds_preserved=True,SB_preserved=True))
     for m,value in v.items():writers[int(k[0]==2026)].writerow(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,metric=m,prediction=value))
  emit(stage,'preservation_audit.csv',checks);shutil.copyfile(c['run16']/'classification_and_probability_inputs.csv',stage/'classification_and_probability_inputs.csv');frozen=dict(version='1.9.0',settings=s,model=models['2026'],final_choice=choices[-1],source_hashes=source_hashes(c),evaluation_disclosure=DISCLOSURE);dump(stage/'frozen_models.json',frozen);dump(stage/'freeze_manifest.json',{n:sha(stage/n) for n in ['frozen_models.json','origin_models.json','rolling_choices.json','experiment_predictions.csv','historical_forecasts.csv','frozen_2026_forecasts.csv','sb_frozen_feature_bins.json','classification_and_probability_inputs.csv']})
  report=dict(version='1.9.0',status='JOINT_WORKLOAD_FROZEN_SB_AUDIT_ONLY',prior_releases_preserved=True,saves_preserved=True,accepted_holds_preserved=True,accepted_SB_and_hitter_components_preserved=True,pitcher_probabilities_fixed=True,SB_replacement_fitted=False,SB_features_selected=False,evaluation_outcomes_read=False,inputs_unchanged=True,final_historical_choice=choices[-1],final_model_supported=models['2026']['supported'],**counts,SB_audit_tables=auditcounts,evaluation_disclosure=DISCLOSURE,limitations=['Joint multipliers minimize the deployed capped final workload squared error plus a fixed penalty toward (1,1); coordinate descent is deterministic but is not a global optimum guarantee for the piecewise capped objective. Nonconverged pooled fits fall back to accepted v1.5.','Only earlier v1.6 OOF forecast/outcome pairs enter calibration; actual G>0 and known eligible OUTS are required. Nonparticipants or missing actuals are not fabricated zeros.','Prior-role specialists use pooled fallback when sparse or nonconverged. Direction/participation probabilities and source workload anchor remain fixed.','Target 2020 is stress-only, excluded from fit/selection; 2021 remains eligible. No new hyperparameter search or unfavorable-season deletion.','SB associations/bins are descriptive, not a replacement model, predictive validation, significance or causal evidence. Prior-rate/change relationships have mathematical coupling and sampling noise; correlated features and multiple comparisons require caution.','SB bin thresholds use earlier predictor populations, not current outcomes. Only eligible current/prior proxy exposures >=20 enter change analysis; missing/low-exposure cases remain in coverage, so this is not complete cold-start analysis.','Historical sources are retrospective, not archived preseason vintages. 2026 is disclosed, never used to retune choices.'])
  dump(stage/'joint_workload_build_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)

def arguments(evaluation=False):
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in [('run18','standalone_refinements_v1_8'),('run16','standalone_growth_sb_v1_6'),('diagnostics','standalone_magnitude_diagnostics_v1_7'),('run15','standalone_holds_attribution_v1_5'),('run14','standalone_combined_v1_4'),('source','standalone_workload_experiments_v1_3'),('matrix','standalone_lagged_features_v1_0'),('baseline','standalone_role_workload_v1_2'),('labels','training_labels_v1_0')]:p.add_argument('--'+n,default='outputs/'+v)
 p.add_argument('--output',default='outputs/standalone_joint_workload_'+('evaluation_' if evaluation else '')+'v1_9');p.add_argument('--backup-root',default='backups')
 if evaluation:p.add_argument('--run',default='outputs/standalone_joint_workload_v1_9');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true')
 else:p.add_argument('--config',default='config/standalone_joint_workload_v1_9.json')
 return p.parse_args()
if __name__=='__main__':
 a=arguments();print(json.dumps(build(a.run18,a.run16,a.diagnostics,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.config,a.output,a.backup_root),indent=2))
