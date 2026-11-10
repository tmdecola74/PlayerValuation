"""Simple SB baselines and read-only pitcher workload-history diagnostics."""
import argparse,csv,json,shutil,math,hashlib
from pathlib import Path
from collections import defaultdict
from contextlib import ExitStack
from standalone_io_v1_0 import load,dump,sha,start,finish
from standalone_SB_history_v1_10 import *
from history_io_v1_10 import context,predictions,replay,source_hashes,emit,forecast,FIELDS
from history_scores_v1_10 import summaries,SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS
from standalone_refinements_v1_8 import cohort_names
from pitcher_history_diagnostics_v1_10 import audit as pitcher_audit

def scores(stage,c,items,actual,maximum=2025,external=None,available=None):
 with ExitStack() as stack:
  ww=[]
  for name,fields in [('category_scores.csv',SCORE_FIELDS),('category_coverage.csv',COVERAGE_FIELDS),('comparison_pairs.csv',PAIR_FIELDS)]:
   f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();ww.append(w)
  return summaries(c,items,actual,*ww,external,available,maximum)

def comparison(c,items,actual,maximum):
 groups=defaultdict(list);out=[]
 for k,d in sorted(items.items()):
  if k[1]!='hitter' or k[0]>maximum:continue
  a=actual.get(k+('SB',));vv={'frozen_v1_5':d['baseline'],'last_season_rate':d['last_season'],'multiyear_candidate':d['candidate'],'selected_SB_experiment':d['selected']}
  if not finite(a) or not all(finite(v) for v in vv.values()):continue
  for cc in cohort_names('hitter',c['rows'][k],c['settings110'])+(['population_only'] if d['population_only'] else []):groups[k[0],cc].append((k,a,vv,d))
 for y in range(2019,maximum+1):groups[y,'all']
 for (y,cc),rr in sorted(groups.items()):
  n=len(rr);member=hashlib.sha256(json.dumps([k for k,a,v,d in rr]).encode()).hexdigest()
  for method in METHODS:
   e=[v[method]-a for k,a,v,d in rr];out.append(dict(season=y,cohort=cc,method=method,n=n,candidate_supported=sum(d['supported'] for k,a,v,d in rr),last_supported=sum(d['last_supported'] for k,a,v,d in rr),population_only_rows=sum(d['population_only'] for k,a,v,d in rr),RMSE=math.sqrt(sum(x*x for x in e)/n) if n else None,MAE=sum(abs(x) for x in e)/n if n else None,bias=sum(e)/n if n else None,membership_sha256=member,stress_season=y==2020,disclosed_evaluation=y==2026))
 return out

def diagnostic_tables(stage,c,actual,s,maximum):
 tables=pitcher_audit(c,actual,s,maximum)
 for n,rr in tables.items():emit(stage,n+'.csv',rr)
 return {n:len(rr) for n,rr in tables.items()}

def build(run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels,config,output,backups):
 print('Verifying preserved v1.9 and earlier releases; no pitcher fitting...',flush=True);c=context(run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels);config=Path(config).resolve();s=settings_checked(load(config));c['settings110']=s;c['watched'][str(config)]=sha(config);actual=c['actual_training'];items={};models={};choices=[];history=defaultdict(list);members=[]
 output,backups,stage=start(output,backups,[run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels,config])
 try:
  for y in range(2019,2027):
   print(f'{y}: earlier-season population prior, fixed multiyear and last-season SB rates',flush=True);model,mm=population(actual,y,s);models[str(y)]=model;members+=mm;pp=predictions(c,model,y,s);choice=dict(season=y,hitter=selection(history,y,s));choices.append(choice)
   for k,d in pp.items():items[k]=d|dict(selected=d['candidate'] if k[1]=='hitter' and choice['hitter']['adopt'] else d['baseline'])
   add_history(y,items,c['rows'],actual,history,s)
  if choices!=replay(c,items,s):raise ValueError('Historical decision replay failed')
  emit(stage,'experiment_predictions.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**d) for k,d in sorted(items.items())]);dump(stage/'origin_population_priors.json',models);dump(stage/'rolling_choices.json',choices);dump(stage/'historical_gate_evidence.json',history);emit(stage,'SB_population_fit_members.csv',members);emit(stage,'SB_population_priors.csv',list(models.values()));emit(stage,'SB_comparison.csv',comparison(c,items,actual,2025));dcounts=diagnostic_tables(stage,c,actual,s,2025);counts=scores(stage,c,items,actual)
  checks=[]
  with ExitStack() as stack:
   writers=[]
   for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();writers.append(w)
   for k,d in sorted(items.items()):
    for method in METHODS:
     v=forecast(c,k,d,method);checks.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,pitcher_forecasts_preserved=True,saves_holds_preserved=True,hitter_non_SB_components_preserved=True,coherent=True))
     for m,value in v.items():writers[int(k[0]==2026)].writerow(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,metric=m,prediction=value))
  emit(stage,'preservation_audit.csv',checks);frozen=dict(version='1.10.0',settings=s,population_prior=models['2026'],final_choice=choices[-1],source_hashes=source_hashes(c),evaluation_disclosure=DISCLOSURE);dump(stage/'frozen_models.json',frozen);dump(stage/'freeze_manifest.json',{n:sha(stage/n) for n in ['frozen_models.json','origin_population_priors.json','rolling_choices.json','experiment_predictions.csv','historical_forecasts.csv','frozen_2026_forecasts.csv']})
  report=dict(version='1.10.0',status='SB_HISTORY_BASELINES_FROZEN_PITCHER_DIAGNOSIS_ONLY',prior_releases_preserved=True,pitcher_models_fitted=False,pitcher_forecasts_preserved=True,saves_holds_preserved=True,hitter_non_SB_components_preserved=True,complex_SB_model_fitted=False,evaluation_outcomes_read=False,inputs_unchanged=True,final_historical_choice=choices[-1],final_population_prior=models['2026'],**counts,pitcher_diagnostic_tables=dcounts,evaluation_disclosure=DISCLOSURE,limitations=['Fixed lag weights 3/2/1 and 100 proxy prior opportunities; no hyperparameter search. Population prior uses earlier eligible actuals only. True zero SB is retained; missing history is not fabricated zero.','Candidate with no usable prior lag uses the historical population rate; missing projected proxy or unsupported population prior retains accepted SB. Last-season comparator falls back to accepted SB when its rate is undefined.','Selection requires historical improvement against both accepted and last-season comparators, with established-runner, zero-SB and low-history guards. Exposure weighting uses raw observed 2020 lag samples; 2020 targets remain stress-only.','Pitcher history reductions/gaps are descriptive flags, not confirmed injury or missed-season labels. Missing records remain unknown. Observed return/role transitions are retrospective diagnostics and never selection inputs.','Pitcher workload diagnostic normalization retains the frozen 2.7 multiplier for 2020 prior counts. No multiplier tuning or new pitcher forecast occurs. 2021 is retained.','Retrospective sources are not archived preseason vintages. 2026 is disclosed evaluation only; no future labels affect priors or choices.'])
  dump(stage/'history_baselines_build_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)

def arguments(evaluation=False):
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in [('run19','standalone_joint_workload_v1_9'),('run18','standalone_refinements_v1_8'),('run16','standalone_growth_sb_v1_6'),('diagnostics','standalone_magnitude_diagnostics_v1_7'),('run15','standalone_holds_attribution_v1_5'),('run14','standalone_combined_v1_4'),('source','standalone_workload_experiments_v1_3'),('matrix','standalone_lagged_features_v1_0'),('baseline','standalone_role_workload_v1_2'),('labels','training_labels_v1_0')]:p.add_argument('--'+n,default='outputs/'+v)
 p.add_argument('--output',default='outputs/standalone_history_baselines_'+('evaluation_' if evaluation else '')+'v1_10');p.add_argument('--backup-root',default='backups')
 if evaluation:p.add_argument('--run',default='outputs/standalone_history_baselines_v1_10');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true')
 else:p.add_argument('--config',default='config/standalone_history_baselines_v1_10.json')
 return p.parse_args()
if __name__=='__main__':
 a=arguments();print(json.dumps(build(a.run19,a.run18,a.run16,a.diagnostics,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.config,a.output,a.backup_root),indent=2))
