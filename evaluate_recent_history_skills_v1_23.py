"""Disclosed 2026 reporting for frozen v1.23 forecasts. No fitting or selection."""
import argparse,csv,json,math,shutil
from pathlib import Path
from collections import defaultdict,Counter
from standalone_io_v1_0 import load,dump,sha,start,finish
from recent_skill_core_v1_23 import *
from recent_skill_inputs_v1_23 import labels,BENCHMARKS,IMPLEMENTATION_VERSION
from recent_history_skills_v1_23 import score_vectors,rate_scores

def csvrows(p):
 with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def paired_benchmarks(vectors,external,actual,context):
 bank={(k,m,method):(v,None) for (k,method),vv in vectors.items() if method in ['accepted_frozen','historical_selected'] for m,v in vv.items()};names={};sources=set()
 for r in external:
  if int(r['season'])!=2026:continue
  k=2026,r['player_type'],str(r['mlbam_id']);token=k,r['metric'],r['source']
  if token in bank:raise ValueError('Duplicate frozen benchmark prediction')
  value=number(r['prediction'])
  if not finite(value) or value<0:raise ValueError('Invalid benchmark prediction')
  bank[token]=(value,r['source_record_id']);names[k]=r.get('name');sources.add(r['source'])
 groups=[('accepted_vs_selected',['accepted_frozen','historical_selected'])]+[('paired_'+s,['accepted_frozen','historical_selected',s]) for s in BENCHMARKS if s in sources]
 if sources:groups.append(('all_available_benchmarks',['accepted_frozen','historical_selected']+sorted(sources)))
 buckets=defaultdict(list);coverage=[];pairs=[]
 for role in METRICS:
  for m in METRICS[role]:
   eligible=[k[:3] for k,v in actual.items() if k[1]==role and k[3]==m and (m not in ['AVG','OBP','SLG','OPS','ERA','WHIP'] or actual.get(k[:3]+(('AB' if role=='hitter' else 'OUTS'),),0)>0)]
   for group,methods in groups:
    common=[k for k in eligible if all(finite(bank.get((k,m,method),(None,None))[0]) for method in methods)]
    for method in methods:coverage.append(dict(player_type=role,metric=m,comparison_group=group,method=method,eligible_actual_players=len(eligible),available_forecasts=sum(finite(bank.get((k,m,method),(None,None))[0]) for k in eligible),matched_players=len(common),membership_sha256=member(common)))
    for k in common:
     exposure=actual.get(k+(('PA' if role=='hitter' else 'OUTS'),));cohort='UNKNOWN' if exposure is None else 'ZERO' if exposure==0 else ('LT100_PA' if exposure<100 else '100_299_PA' if exposure<300 else 'GE300_PA') if role=='hitter' else ('LT20_IP' if exposure<60 else '20_99_IP' if exposure<300 else 'GE100_IP')
     for method in methods:
      v,record=bank[k,m,method];e=v-actual[k+(m,)]
      for dim,cc in [('ALL','ALL'),('ACTUAL_EXPOSURE',cohort),('HISTORY',context.get(k,{}).get('history_cohort','UNKNOWN'))]:buckets[role,m,group,method,dim,cc].append((k[2],e))
      pairs.append(dict(season=2026,player_type=role,mlbam_id=k[2],name=names.get(k),metric=m,comparison_group=group,method=method,prediction=v,actual=actual[k+(m,)],error=e,source_record_id=record,exposure_cohort=cohort))
 scores=[]
 for (role,m,group,method,dim,cohort),rr in sorted(buckets.items()):
  n=len(rr);ee=[e for pid,e in rr];scores.append(dict(season=2026,player_type=role,metric=m,comparison_group=group,method=method,cohort_dimension=dim,cohort=cohort,n=n,mae=sum(map(abs,ee))/n,rmse=math.sqrt(sum(e*e for e in ee)/n),bias=sum(ee)/n,membership_sha256=member([pid for pid,e in rr])))
 return scores,pairs,coverage

def evaluate(a):
 run=Path(a.run).resolve();labs=Path(a.labels).resolve();w={};report=load(checked(run,'recent_history_build_report.json',w));freeze=load(checked(run,'forecast_freeze.json',w));bindings=load(checked(run,'input_hashes.json',w))
 if report['version']!=VERSION or report['evaluation_outcomes_read'] or report['accepted_forecasts_modified']:raise ValueError('Invalid research forecast release')
 # Validate the entire frozen run, including choice/model/snapshot files, without touching original outcome sources.
 for n,h in portable(freeze).items():
  p=checked(run,n,w)
  if sha(p)!=h:raise ValueError('Forecast/choice freeze mismatch')
 lr=checked(labs,'label_build_report.json',w)
 if bindings.get(str(lr))!=sha(lr):raise ValueError('Evaluation label reference differs from frozen development reference')
 lp=checked(labs,'holdout_labels.parquet',w)
 print('Frozen choices and forecasts verified. Reading disclosed 2026 eligible actuals for reporting only...',flush=True)
 label_scope=[];actual=labels(lp,2026,scope_audit=label_scope);vectors=defaultdict(dict);seen=set()
 for r in csvrows(run/'frozen_2026_forecasts.csv'):
  k=int(r['season']),r['player_type'],str(r['mlbam_id']);token=k,r['method'],r['metric']
  if k[0]!=2026 or token in seen or r['method'] not in ARMS+['accepted_frozen','historical_selected']:raise ValueError('Duplicate/invalid frozen 2026 forecast')
  seen.add(token);vectors[k,r['method']][r['metric']]=number(r['prediction'])
 for (k,method),v in vectors.items():coherent(k[1],v)
 choices=load(run/'frozen_choices_2026.json')
 for k in {k for k,method in vectors}:
  accepted=vectors[k,'accepted_frozen'];selected=vectors[k,choices[k[1]]['selected']]
  if vectors[k,'historical_selected']!=selected:raise ValueError('Frozen selected forecast does not match historical choice')
  for method in ARMS:
   if any(vectors[k,method][m]!=accepted[m] for m in METRICS[k[1]] if m not in CHANGED[k[1]]):raise ValueError('Frozen anchor differs')
 context={};feature_context={}
 for r in csvrows(run/'frozen_evaluation_context.csv'):
  k=int(r['season']),r['player_type'],str(r['mlbam_id'])
  if k[0]!=2026 or k in context:raise ValueError('Invalid evaluation context')
  context[k]=r;feature_context[k]=dict(recent_history_seasons=1 if r['history_cohort']=='LOW_HISTORY' else 2)
 support={}
 for r in csvrows(run/'composition_support.csv'):
  if int(r['season'])==2026:support[(2026,r['player_type'],str(r['mlbam_id']),r['method'])]=r['fitted_group']=='True'
 for k in context:
  arm=choices[k[1]]['selected'];support[k+('historical_selected',)]=True if arm=='accepted_frozen' else support[k+(arm,)]
 scores,individual=score_vectors(vectors,actual,feature_context,include_player=True);fitted,_=score_vectors(vectors,actual,feature_context,support)
 for r in individual:
  k=r['season'],r['player_type'],r['mlbam_id'];r['fitted_group']=True if r['method']=='accepted_frozen' else support.get(k+(r['method'],),False)
 raw_rates=csvrows(run/'frozen_2026_skill_rates.csv')
 for r in raw_rates:r['season']=int(r['season']);r['prediction']=number(r['prediction']);r['accepted_rate']=number(r['accepted_rate'])
 rs=rate_scores(raw_rates,actual,feature_context);external=csvrows(run/'frozen_benchmark_predictions.csv');bs,pairs,coverage=paired_benchmarks(vectors,external,actual,context)
 existing={k for k,method in vectors if method=='accepted_frozen'};absent=[dict(season=k[0],player_type=k[1],mlbam_id=k[2],reason='ACTUAL_LABEL_PARTICIPANT_OUTSIDE_FROZEN_HOMEGROWN_POPULATION',usage='DIAGNOSTIC_ONLY_NOT_ADDED_TO_FORECASTS') for k in sorted({k[:3] for k in actual}-existing)]
 output,backups,stage=start(a.output,a.backup_root,[run,labs])
 try:
  emit(stage/'evaluation_label_scope_audit.csv',label_scope)
  for name,rows in [('evaluation_player_comparisons',individual),('evaluation_scores',scores),('evaluation_fitted_scores',fitted),('evaluation_skill_rate_scores',rs),('matched_benchmark_scores',bs),('matched_benchmark_player_comparisons',pairs),('benchmark_comparison_coverage',coverage),('actual_participants_outside_forecast_universe',absent)]:emit(stage/(name+'.csv'),rows)
  rr=dict(version=VERSION,status='PREVIOUSLY_REVIEWED_2026_EVALUATION_ONLY',models_fitted=False,choices_changed=False,forecasts_modified=False,selection_uses_2026=False,forecast_freeze_sha256=sha(run/'forecast_freeze.json'),player_comparison_rows=len(individual),benchmark_pair_rows=len(pairs),actual_participants_outside_frozen_universe=len(absent),limitations=['2026 was previously reviewed, not an untouched holdout.','Each source group and exposure cohort uses identical eligible comparison members; groups can have different coverage.','Missing/ineligible labels and forecast components never become zeros.','Full scoring includes explicit accepted-group fallbacks; fitted-only reports isolate supported research predictions.','Benchmark files are frozen retrospective exports, not independently certified preseason vintages.','No acceptance, weighting change or model fitting occurs during evaluation.'])
  rr['build_implementation_version']=IMPLEMENTATION_VERSION
  rr['ignored_non_scoring_label_rows']=sum(r['rows'] for r in label_scope if r['status']=='IGNORED_NONSCORING_METRIC')
  dump(stage/'recent_history_evaluation_report.json',rr);backup=finish(output,backups,stage,w);return dict(rr,output=str(output),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(run='outputs/recent_history_skills_v1_23',labels='outputs/training_labels_v1_0',output='outputs/recent_history_skills_v1_23_evaluation',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(evaluate(parser().parse_args()),indent=2))
