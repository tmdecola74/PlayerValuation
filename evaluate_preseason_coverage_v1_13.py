"""Separate disclosed 2026 evaluation; never adopts a policy or changes universe."""
import argparse,json,csv,math,hashlib,shutil
from pathlib import Path
from collections import Counter,defaultdict
from standalone_io_v1_0 import verify,load,sha,dump,table,csvrows,start,finish
from projection_release_v1_11_1 import HOME,CONS,METRICS,finite,emit
from projection_release_audit_v1_12 import labels_index,COHORTS,exposure_partition,checked_file
from consensus_policy_v1_13 import CANDIDATE
from build_preseason_coverage_v1_13 import DEFAULTS

PUBLISHED='PUBLISHED_ORIGINAL_CONSENSUS_REFERENCE'
GROUPS=[('published_original_reference_all',[PUBLISHED]),('published_vs_reconciled_matched',[PUBLISHED,CANDIDATE]),('homegrown_all',[HOME]),('original_consensus_all',[CONS]),('reconciled_candidate_all',[CANDIDATE]),('original_vs_reconciled_common',[CONS,CANDIDATE]),('homegrown_vs_candidate_common',[HOME,CANDIDATE])]
for source in ['Steamer','OOPSY']:
 GROUPS += [(source+'_homegrown_pair',[HOME,source]),(source+'_candidate_pair',[CANDIDATE,source]),(source+'_homegrown_candidate_common',[HOME,CANDIDATE,source])]

PAIR_FIELDS=['season','player_type','mlbam_id','metric','cohort','comparison_group','projection_source','prediction','actual','actual_exposure','error','absolute_error','source_record_id']

def score_forecasts(forecasts,actual,pair_writer=None):
 scores=[];coverage=[];pair_count=0
 for role,metrics in METRICS.items():
  pids=sorted({k[2] for k,r in actual.items() if k[1]==role})
  for metric in metrics:
   eligible={pid:actual[2026,role,pid,metric]['label_value'] for pid in pids if (2026,role,pid,metric) in actual and actual[2026,role,pid,metric]['eligible']}
   cohorts=[('ALL_ELIGIBLE',None,None)]+(COHORTS[role] if metric in ['AVG','OPS','ERA','WHIP'] else [])
   exposure_metric='PA' if role=='hitter' else 'IP'
   def exposure(pid):
    r=actual.get((2026,role,pid,exposure_metric));return r['label_value'] if r and r['eligible'] else None
   for cohort,lo,hi in cohorts:
    subset=sorted(eligible) if cohort=='ALL_ELIGIBLE' else [pid for pid in sorted(eligible) if finite(exposure(pid)) and exposure(pid)>0 and exposure(pid)>=lo and (hi is None or exposure(pid)<hi)]
    for group,sources in GROUPS:
     common=[pid for pid in subset if all(finite(forecasts.get((role,pid,metric,s),(None,None))[0]) for s in sources)];member=hashlib.sha256(json.dumps(common).encode()).hexdigest()
     for source in sources:
      errors=[forecasts[role,pid,metric,source][0]-eligible[pid] for pid in common];n=len(errors);sse=sum(e*e for e in errors)
      scores.append(dict(season=2026,player_type=role,metric=metric,cohort=cohort,comparison_group=group,projection_source=source,n=n,mae=sum(map(abs,errors))/n if n else None,rmse=math.sqrt(sse/n) if n else None,bias=sum(errors)/n if n else None,squared_error_sum=sse,membership_sha256=member))
      coverage.append(dict(player_type=role,metric=metric,cohort=cohort,comparison_group=group,projection_source=source,eligible_actuals=len(eligible),cohort_actuals=len(subset),source_available=sum(finite(forecasts.get((role,pid,metric,source),(None,None))[0]) for pid in subset),matched_n=n,membership_sha256=member))
      if pair_writer:
       for pid,error in zip(common,errors):
        value,record=forecasts[role,pid,metric,source];pair_writer.writerow(dict(season=2026,player_type=role,mlbam_id=pid,metric=metric,cohort=cohort,comparison_group=group,projection_source=source,prediction=value,actual=eligible[pid],actual_exposure=exposure(pid),error=error,absolute_error=abs(error),source_record_id=record));pair_count+=1
 return scores,coverage,pair_count

def universe_evaluation(universe,records,actual):
 index=defaultdict(list)
 for r in universe:
  if r['mlbam_id']:index[r['player_type'],r['mlbam_id']].append(r)
 home={(r['player_type'],r['mlbam_id']) for r in records if r['projection_source']==HOME};population=sorted({(k[1],k[2]) for k,r in actual.items() if r['eligible'] and k[3] in METRICS[k[1]]});rows=[]
 for role,pid in population:
  matches=index.get((role,pid),[]);u=matches[0] if len(matches)==1 else None
  def value(m):
   x=actual.get((2026,role,pid,m));return x['label_value'] if x and x['eligible'] else None
  rows.append(dict(season=2026,player_type=role,mlbam_id=pid,universe_id=u['universe_id'] if u else None,name=u['name'] if u else 'MLBAM '+pid,preseason_universe_status='UNIQUE_PRESEASON_UNIVERSE_RECORD' if u else 'AMBIGUOUS_UNIVERSE_MLBAM_REVIEW' if matches else 'ABSENT_FROM_FROZEN_PRESEASON_UNIVERSE',preseason_evidence_present=u['preseason_evidence_present'] if u else False,preseason_stratum=u['preseason_stratum'] if u else None,homegrown_forecast_present=(role,pid) in home,reconciled_candidate_basic_valuation_ready=u['reconciled_candidate_basic_valuation_ready'] if u else False,actual_PA=value('PA'),actual_IP=value('IP'),disposition='EVALUATION_ONLY_NO_RETROACTIVE_INCLUSION_OR_FORECAST'))
 return rows

def evaluate(run,source_evaluation,labels,output,backups):
 run,ev,labels=map(lambda p:Path(p).resolve(),[run,source_evaluation,labels]);watched=verify(run);watched.update(verify(ev));report=load(run/'preseason_coverage_build_report.json');old=load(ev/'projection_evaluation_report.json')
 if report['version']!='1.13.0' or report['candidate_adopted'] or report['models_fitted'] or report['evaluation_outcomes_read'] or report['universe_uses_2026_outcomes']:raise ValueError('Require frozen, outcome-blind v1.13 build')
 if old['version']!='1.11.2' or not old['previously_reviewed'] or old['forecasts_modified']:raise ValueError('Require disclosed original evaluation')
 for n,h in load(run/'forecast_and_universe_freeze.json').items():
  p=(run/n).resolve()
  if run not in p.parents or sha(p)!=h:raise ValueError('Candidate/universe freeze mismatch')
 original=Path(report['source_release']);w=verify(original);watched.update(w)
 if sha(original/'projection_release_report.json')!=report['source_release_sha256']:raise ValueError('Original release differs')
 bindings=load(ev/'input_hashes.json')
 if bindings.get(str(original/'coherent_projection_records.json'))!=sha(original/'coherent_projection_records.json'):raise ValueError('Evaluation belongs to a different original release')
 actual_path=checked_file(labels,'holdout_labels.parquet',watched);label_report=checked_file(labels,'label_build_report.json',watched)
 if load(label_report)['reference_sha256']!=report['label_reference_sha256'] or bindings.get(str(actual_path))!=sha(actual_path):raise ValueError('Evaluation actuals differ from frozen original evaluation')
 records=load(original/'coherent_projection_records.json');candidates=load(run/'candidate_projection_records.json');universe=load(run/'preseason_universe.json');forecasts={}
 for r in records+candidates:
  if not r['mlbam_id']:continue
  for m in METRICS[r['player_type']]:
   k=r['player_type'],r['mlbam_id'],m,r['projection_source']
   if k in forecasts:raise ValueError('Duplicate released forecast identity')
   forecasts[k]=r.get(m),r['projection_key']
 # Raw published consensus is an evaluation-only reference, including quarantined
 # source rows; no claim of component coherence and never a valuation adapter.
 identity={(r['player_type'],r['player_id']):r['mlbam_id'] for r in universe if r['player_id'] and r['mlbam_id']}
 for r in load(run/'original_consensus_records.json'):
  role=r['player_type'];pid=identity.get((role,r['player_id']))
  if not pid:continue
  values=dict(r['metrics'])
  if values.get('SO') is None and finite(values.get('K')):values['SO']=values['K']
  if values.get('OUTS') is None and finite(values.get('IP')):values['OUTS']=3*values['IP']
  for metric in METRICS[role]:
   key=role,pid,metric,PUBLISHED
   if key in forecasts:raise ValueError('Ambiguous published original consensus identity')
   value=values.get(metric);forecasts[key]=(value if finite(value) and value>=0 else None,'PUBLISHED_ORIGINAL:'+role+':'+r['player_id'])
 with (ev/'player_comparisons.csv').open(encoding='utf-8-sig',newline='') as stream:
  for r in csv.DictReader(stream):
   if r['projection_source'] not in ['Steamer','OOPSY']:continue
   if int(r['season'])!=2026 or r['metric'] not in METRICS[r['player_type']]:raise ValueError('Invalid frozen benchmark domain')
   k=r['player_type'],r['mlbam_id'],r['metric'],r['projection_source'];value=None if r['prediction']=='' else float(r['prediction'])
   if k in forecasts or value is not None and not finite(value):raise ValueError('Invalid/duplicate benchmark')
   forecasts[k]=value,r['source_record_id']
 out,backups,stage=start(output,backups,[run,ev,labels,original])
 try:
  print('Frozen candidate and universe verified. Evaluating reviewed 2026 labels separately...',flush=True)
  actual=labels_index(table(actual_path),2026,2026)
  with (stage/'matched_pairs.csv').open('w',encoding='utf-8',newline='') as f:
   writer=csv.DictWriter(f,fieldnames=PAIR_FIELDS);writer.writeheader();scores,coverage,pair_count=score_forecasts(forecasts,actual,writer)
  rate_scores=[r for r in scores if r['metric'] in ['AVG','OPS','ERA','WHIP'] and r['cohort']!='ALL_ELIGIBLE']
  emit(stage,'matched_scores.csv',[r for r in scores if r['cohort']=='ALL_ELIGIBLE']);emit(stage,'exposure_cohort_scores.csv',rate_scores);emit(stage,'comparison_coverage.csv',coverage);emit(stage,'exposure_error_partition.csv',exposure_partition(rate_scores))
  coverage_rows=universe_evaluation(universe,records,actual);missing=[r for r in coverage_rows if not r['homegrown_forecast_present']]
  if len(missing)!=old['actual_participants_without_homegrown']:raise ValueError('Original missing-homegrown population changed')
  emit(stage,'universe_coverage_evaluation.csv',coverage_rows);emit(stage,'original_missing_homegrown_coverage.csv',missing)
  result=dict(version='1.13.0',status='DISCLOSED_EVALUATION_CANDIDATE_NOT_ADOPTED',previously_reviewed=True,candidate_adopted=False,models_fitted=False,selection_changed=False,homegrown_forecasts_modified=False,universe_modified=False,inputs_unchanged=True,matched_pair_rows=pair_count,original_missing_homegrown=len(missing),missing_homegrown_with_preseason_evidence=sum(r['preseason_evidence_present'] for r in missing),missing_homegrown_with_candidate_basic_coverage=sum(r['reconciled_candidate_basic_valuation_ready'] for r in missing),actual_universe_statuses=dict(Counter(r['preseason_universe_status'] for r in coverage_rows)),limitations=['This comparison reports a fixed arithmetic policy, never a 2026-based policy selection. Candidate adoption remains false.','Published-original/candidate matched scores include recovered quarantined rows and isolate arithmetic changes; that raw original reference is not a coherent valuation source. Original usable-consensus/candidate common-pool scores isolate changes among shared usable players. Candidate-only/all-eligible scores also reflect recovered coverage and are not interchangeable.','Homegrown/source pairs and triple common pools have different membership; compare within a named group and metric/cohort only.','Actual participation/exposure is used only after universe and forecasts are frozen. No actual-only player is added to the preseason universe.','All original references and accepted homegrown forecasts remain unchanged. No new skill or workload model is fitted or selected.'])
  dump(stage/'preseason_coverage_evaluation_report.json',result);backup=finish(out,backups,stage,watched);return dict(result,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default=DEFAULTS['output']);p.add_argument('--source-evaluation',default='outputs/projection_evaluation_2026_v1_11_2');p.add_argument('--labels',default=DEFAULTS['labels']);p.add_argument('--output',default='outputs/preseason_coverage_evaluation_v1_13');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(evaluate(a.run,a.source_evaluation,a.labels,a.output,a.backup_root),indent=2))
if __name__=='__main__':main()
