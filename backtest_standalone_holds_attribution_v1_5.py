"""Historical holds opportunity test and frozen workload-versus-skill attribution."""
import argparse,csv,json,shutil
from pathlib import Path
from collections import defaultdict
from contextlib import ExitStack
from standalone_io_v1_0 import load,sha,dump,start,finish,write
from standalone_combined_v1_4 import read_all_labels,vectors,FIELDS,near
from standalone_holds_v1_5 import *
from standalone_attribution_v1_5 import *
from holds_io_v1_5 import *


def write_attribution(stage,c,actual,maximum):
 with ExitStack() as stack:
  ww=[]
  for name,fields in [('count_error_attribution.csv',ATTR_FIELDS),('attribution_summary.csv',SUMMARY_FIELDS),('ratio_outliers.csv',RATIO_FIELDS),('count_outliers.csv',COUNT_OUTLIER_FIELDS)]:
   f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();ww.append(w)
  coverage=attribution(c,actual,*ww[:3],maximum=maximum,count_outlier_writer=ww[3])
 write(stage/'attribution_coverage.csv',coverage,['player_type','metric','status','method_rows']);return coverage

def build(run,source,matrix,baseline,labels,config,output,backups):
 print('Verifying frozen v1.4 and historical labels...',flush=True);c=source_context(run,source,matrix,baseline,labels);config=Path(config).resolve();s=load(config);c['watched'][str(config)]=sha(config)
 if s['first_origin']!=2019 or s['evaluation_year']!=2026 or s['occurrence_penalty']<=0 or s['minimum_selection_folds']<2 or not 0<s['minimum_candidate_fraction']<=1:raise ValueError('Unsupported settings/chronology')
 actual=read_all_labels(c['labels'],'training');rows=prepared(c);allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist'];base=load(c['baseline']/'frozen_models.json')['workload_model']['config'];history=defaultdict(list);items={};choices=[];audit=[]
 output,backups,stage=start(output,backups,[run,source,matrix,baseline,labels,config])
 try:
  for year in range(2019,2027):
   print(f'{year}: holds opportunity fits only earlier targets; saves unchanged',flush=True);bundle,aa=fit_holds(rows,actual,allow,base,s,year);audit+=aa;current=[r for r in rows if r['target_season']==year];raw=predict_holds(bundle,current,s);choice=dict(season=year,**choose(history,year,s));choices.append(choice)
   for k,d in raw.items():
    vv=vectors(c,k);b12=vv['frozen_v1_2'].get('HLD');b14=vv['combined_v1_4'].get('HLD');candidate=d['raw_candidate_HLD'] if d['supported'] else b14;items[k]=dict(**d,frozen_v1_2=b12,combined_v1_4=b14,holds_opportunity_candidate=candidate,selected_v1_5=candidate if choice['adopt'] else b14)
   fold_history(year,items,c['rows'],actual,history,s)
   if year==2026:final_model=bundle
  if choices!=replay(c,items,actual,s):raise ValueError('Internal gate replay mismatch')
  write(stage/'holds_predictions.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**d) for k,d in items.items()],HOLD_PRED_FIELDS);dump(stage/'historical_holds_choices.json',choices);dump(stage/'historical_gate_evidence.json',history);dump(stage/'fit_audit.json',audit)
  with ExitStack() as stack:
   ww=[]
   for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();ww.append(w)
   for k in sorted(c['predictions']):
    v=vectors(c,k)['combined_v1_4'];v=overlay(v,items[k]['selected_v1_5']) if k[1]=='pitcher' else v
    for m,x in v.items():ww[int(k[0]==2026)].writerow(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method='selected_v1_5',metric=m,prediction=x))
  shutil.copyfile(c['run14']/'classification_and_probability_inputs.csv',stage/'classification_and_probability_inputs.csv');coverage=write_attribution(stage,c,actual,2025);hs,hc=holds_scores({k:d for k,d in items.items() if k[0]<2026},c['rows'],actual,METHODS);write(stage/'historical_holds_scores.csv',hs,HOLD_FIELDS);write(stage/'historical_holds_coverage.csv',hc,['season','mlbam_id','actual_HLD','paired','candidate_supported'])
  frozen=dict(version='1.5.0',settings=s,model=final_model,final_choice=choices[-1],v1_4_freeze_sha256=sha(c['run14']/'freeze_manifest.json'),v1_3_models_sha256=sha(c['source']/'frozen_models.json'),training_labels_sha256=sha(c['labels']/'training_labels.parquet'),label_reference_sha256=load(c['labels']/'label_build_report.json')['reference_sha256'],evaluation_disclosure=DISCLOSURE)
  dump(stage/'frozen_models.json',frozen);dump(stage/'freeze_manifest.json',{n:sha(stage/n) for n in ['frozen_models.json','holds_predictions.csv','historical_holds_choices.json','historical_forecasts.csv','frozen_2026_forecasts.csv','fit_audit.json','classification_and_probability_inputs.csv']})
  report=dict(version='1.5.0',status='HOLDS_CANDIDATE_AND_ATTRIBUTION_FROZEN_RESEARCH_ONLY',earlier_releases_preserved=True,new_holds_models_fitted=True,prior_release_models_refitted=False,saves_preserved_exactly=True,classification_labels_preserved=True,non_holds_forecasts_preserved=True,evaluation_outcomes_read=False,inputs_unchanged=True,final_holds_choice=choices[-1],final_candidate_supported=final_model['supported'],attribution_coverage=coverage,historical_holds_score_rows=len(hs),changed_HLD_player_seasons=sum(not near(d['selected_v1_5'],d['combined_v1_4']) for d in items.values()),evaluation_disclosure=DISCLOSURE,limitations=['Attribution uses observed exposure and rates only as retrospective diagnostics, never preseason features. Symmetric allocation is algebraic, not causal.','Positive actual and forecast denominators are required. Missing/excluded values remain missing and zero-denominator rates are not fabricated.','Holds candidate models relief appearances, probability of any hold given relief, and positive holds per relief appearance, retaining frozen participation assumptions.','No full team bullpen hierarchy, injuries, transactions, leverage or preseason roster-universe information is added. Conditional-participation limitations remain.','Candidate must beat both baselines overall and protect prior-reliever and prior-HLD>=5 cohorts using earlier folds only. Rejection retains v1.4 holds.','Saves, skill rates, workload forecasts, hitter forecasts and hard role classification remain unchanged.','2026 is previously reviewed disclosed evaluation data, not independent untouched holdout evidence.'])
  dump(stage/'holds_attribution_build_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_combined_v1_4');p.add_argument('--source',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--config',default='config/standalone_holds_attribution_v1_5.json');p.add_argument('--output',default='outputs/standalone_holds_attribution_v1_5');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.run,a.source,a.matrix,a.baseline,a.labels,a.config,a.output,a.backup_root),indent=2))
