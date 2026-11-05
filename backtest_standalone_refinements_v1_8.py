"""Freeze separate magnitude-calibration and direct SB-propensity experiments."""
import argparse,csv,json,shutil
from pathlib import Path
from collections import defaultdict
from contextlib import ExitStack
from standalone_io_v1_0 import load,dump,sha,start,finish,write
from standalone_refinements_v1_8 import *
from refinement_io_v1_8 import context,source_hashes,predictions,forecast,FIELDS,emit,parameter_rows,replay
from standalone_growth_sb_v1_6 import FULL_METHODS
from refinement_scores_v1_8 import summaries,SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS

def scores(stage,c,items,actual,maximum=2025,external=None,available=None):
 with ExitStack() as stack:
  ww=[]
  for name,fields in [('category_scores.csv',SCORE_FIELDS),('category_coverage.csv',COVERAGE_FIELDS),('comparison_pairs.csv',PAIR_FIELDS)]:
   f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();ww.append(w)
  return summaries(c,items,actual,*ww,external,available,maximum)

def comparison(c,items,actual,maximum):
 groups=defaultdict(list)
 for k,d in sorted(items.items()):
  if k[0]>maximum:continue
  a=actual.get(k+(d['metric'],));vv={'frozen_v1_5':d['baseline'],'research_v1_6':d['uncalibrated_candidate'],'candidate_v1_8':d['candidate'],'selected_v1_8':d['selected']}
  if not finite(a) or not all(finite(v) for v in vv.values()):continue
  for cc in cohort_names(k[1],c['rows'][k],c['settings18']):groups[k[0],k[1],d['metric'],cc].append((k,a,vv,d['supported']))
 out=[]
 import hashlib,math
 for (y,role,metric,cc),rr in sorted(groups.items()):
  n=len(rr);member=hashlib.sha256(json.dumps([k for k,a,v,s in rr]).encode()).hexdigest()
  for method in rr[0][2]:
   e=[v[method]-a for k,a,v,s in rr];out.append(dict(season=y,player_type=role,metric=metric,cohort=cc,method=method,n=n,supported=sum(s for k,a,v,s in rr),RMSE=math.sqrt(sum(x*x for x in e)/n),MAE=sum(abs(x) for x in e)/n,bias=sum(e)/n,membership_sha256=member,stress_season=y==2020,disclosed_evaluation=y==2026))
 return out

def build(run16,diagnostics,run15,run14,source,matrix,baseline,labels,config,output,backups):
 print('Verifying v1.6/v1.7 research evidence and accepted forecasts...',flush=True);c=context(run16,diagnostics,run15,run14,source,matrix,baseline,labels);config=Path(config).resolve();s=settings_checked(load(config));c['settings18']=s;c['watched'][str(config)]=sha(config);old=c['old16']['settings'];rows=prepared(c,old);allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist'];base=load(c['baseline']/'frozen_models.json')['workload_model']['config'];actual=c['actual_training'];items={};history=defaultdict(list);choices=[];models={};members=[]
 output,backups,stage=start(output,backups,[run16,diagnostics,run15,run14,source,matrix,baseline,labels,config])
 try:
  for year in range(2019,2027):
   print(f'{year}: calibrating earlier OOF magnitudes and fitting prior-season SB propensity',flush=True);pitch,mm=fit_calibration(c['items16'],c['rows'],actual,year,s);hit=fit_SB(rows,actual,allow,base,old,s,year);models[str(year)]={'pitcher':pitch,'hitter':hit};members+=mm;pp=predictions(c,models[str(year)],[r for r in rows if r['target_season']==year],s);choice=dict(season=year,**{role:selection(history[role],year,role,s) for role in ['pitcher','hitter']});choices.append(choice)
   for k,d in pp.items():items[k]=d|dict(selected=d['candidate'] if choice[k[1]]['adopt'] else d['baseline'])
   add_history(year,items,c['rows'],actual,history,s)
  if choices!=replay(c,items,s):raise ValueError('Internal gate replay failure')
  emit(stage,'experiment_predictions.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**d) for k,d in sorted(items.items())]);dump(stage/'rolling_choices.json',choices);dump(stage/'historical_gate_evidence.json',history);dump(stage/'origin_models.json',models);emit(stage,'calibration_fit_members.csv',members);emit(stage,'calibration_parameters.csv',parameter_rows(models));emit(stage,'target_comparison.csv',comparison(c,items,actual,2025))
  emit(stage,'transition_2021.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],prior_role=prior_role(c['rows'][k]),prior_observed_OUTS=c['rows'][k].get('x_actual_lag1_OUTS'),actual_OUTS=actual.get(k+('OUTS',)),**d) for k,d in sorted(items.items()) if k[:2]==(2021,'pitcher')])
  checks=[]
  with ExitStack() as stack:
   ww=[]
   for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();ww.append(w)
   for k,d in sorted(items.items()):
    for method in FULL_METHODS:
     v=forecast(c,k,d,method);checks.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,saves_preserved=True,holds_preserved=True,coherent=True))
     for m,x in v.items():ww[int(k[0]==2026)].writerow(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,metric=m,prediction=x))
  emit(stage,'preservation_audit.csv',checks);shutil.copyfile(Path(run16)/'classification_and_probability_inputs.csv',stage/'classification_and_probability_inputs.csv');counts=scores(stage,c,items,actual);frozen=dict(version='1.8.0',settings=s,models=models['2026'],final_choices=choices[-1],source_hashes=source_hashes(c),evaluation_disclosure=DISCLOSURE);dump(stage/'frozen_models.json',frozen)
  dump(stage/'freeze_manifest.json',{n:sha(stage/n) for n in ['frozen_models.json','origin_models.json','experiment_predictions.csv','rolling_choices.json','historical_forecasts.csv','frozen_2026_forecasts.csv','classification_and_probability_inputs.csv']})
  report=dict(version='1.8.0',status='SEPARATE_REFINEMENTS_FROZEN_RESEARCH_ONLY',v1_6_and_v1_7_preserved=True,saves_preserved_exactly=True,accepted_holds_preserved_exactly=True,pitcher_direction_probabilities_fixed=True,SB_PA_and_onbase_components_fixed=True,experiments_combined=False,evaluation_outcomes_read=False,inputs_unchanged=True,final_historical_choices=choices[-1],final_model_support={role:models['2026'][role]['supported'] for role in ['pitcher','hitter']},**counts,evaluation_disclosure=DISCLOSURE,limitations=['One predeclared candidate per question; no search over multiplier caps, penalties or SB thresholds.','Calibration fits observed-direction magnitudes from earlier v1.6 out-of-fold predictions, shrunk toward multiplier 1. Sparse prior-role groups use pooled calibration; unsupported cases retain accepted v1.5. Direction and participation probabilities remain frozen.','SB uses an unconditional rate including observed zeros, not a positive-only rate multiplied by a newly fitted occurrence model. Accepted opportunity proxy and PA remain fixed.','2020 target outcomes are excluded from fit and selection but reported as stress; 2021 remains eligible. Low-history and established-runner guards require adequate prior folds; insufficient evidence rejects adoption.','Retrospective data are not archived preseason vintages. No injury, prospect, bullpen hierarchy, attempts or stealable-base dataset is introduced.','No separate-candidate success implies a combined production forecast; saves and accepted holds do not change.'])
  dump(stage/'refinement_build_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)

def arguments(evaluation=False):
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in [('run16','standalone_growth_sb_v1_6'),('diagnostics','standalone_magnitude_diagnostics_v1_7'),('run15','standalone_holds_attribution_v1_5'),('run14','standalone_combined_v1_4'),('source','standalone_workload_experiments_v1_3'),('matrix','standalone_lagged_features_v1_0'),('baseline','standalone_role_workload_v1_2'),('labels','training_labels_v1_0')]:p.add_argument('--'+n,default='outputs/'+v)
 p.add_argument('--output',default='outputs/standalone_refinements_'+('evaluation_' if evaluation else '')+'v1_8');p.add_argument('--backup-root',default='backups')
 if evaluation:p.add_argument('--run',default='outputs/standalone_refinements_v1_8');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true')
 else:p.add_argument('--config',default='config/standalone_refinements_v1_8.json')
 return p.parse_args()
if __name__=='__main__':
 a=arguments();print(json.dumps(build(a.run16,a.diagnostics,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.config,a.output,a.backup_root),indent=2))
