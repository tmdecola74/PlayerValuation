"""Evaluate frozen v1.11 exports; 2026 is previously reviewed evaluation data."""
import argparse,hashlib,json,math,shutil
from collections import Counter
from pathlib import Path
from projection_release_v1_11 import *
from category_benchmarks_v1_4 import warehouse_forecasts

def evaluation_rows(records,labels,external):
 forecasts={};meta={}
 for r in records:
  role=r['player_type'];mlbam=r['mlbam_id'];source=r['projection_source']
  if not mlbam:continue
  key=(role,mlbam,source)
  if key in meta:raise ValueError('Ambiguous evaluation MLBAM ownership')
  meta[key]=r
  for m in METRICS[role]:forecasts[2026,role,mlbam,m,source]=(r.get(m),r['projection_key'])
 for k,v in external.items():
  if k[0]==2026:forecasts[k]=v
 actual={};eligible={};seen=set()
 for r in labels:
  k=(int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric'])
  if k[0]!=2026 or k[1] not in METRICS or not mid(k[2]) or k in seen:raise ValueError('Invalid/duplicate evaluation label')
  seen.add(k)
  if r['eligible']:
   if not finite(r['label_value']) or r['label_value']<0:raise ValueError('Invalid eligible evaluation value')
   actual[k]=r['label_value']
  eligible[k]=r
 individual=[]
 for k,(value,record) in sorted(forecasts.items()):
  y,role,mlbam,m,source=k;a=actual.get(k[:4]);status='AVAILABLE' if finite(value) and a is not None else 'UNSUPPORTED_PROJECTION_COMPONENT' if not finite(value) else 'MISSING_OR_INELIGIBLE_ACTUAL'
  identity=meta.get((role,mlbam,source),meta.get((role,mlbam,HOME),meta.get((role,mlbam,CONS),{})));error=value-a if status=='AVAILABLE' else None
  individual.append(dict(season=y,player_type=role,mlbam_id=mlbam,player_id=identity.get('player_id'),name=identity.get('name'),projection_source=source,metric=m,prediction=value,actual=a,error=error,absolute_error=abs(error) if error is not None else None,status=status,source_record_id=record,actual_eligible=bool(k[:4] in actual),label_eligibility_details=json.dumps(eligible.get(k[:4],{}),sort_keys=True)))
 summaries=[];pairs=[];coverage=[]
 groups=[('homegrown_all_eligible',[HOME]),('consensus_all_eligible',[CONS]),('homegrown_consensus_matched',[HOME,CONS]),('Steamer_matched',[HOME,'Steamer']),('OOPSY_matched',[HOME,'OOPSY']),('all_sources_matched',[HOME,CONS,'Steamer','OOPSY'])]
 for role in METRICS:
  for m in METRICS[role]:
   eligible_keys=sorted(k for k in actual if k[1]==role and k[3]==m)
   for group,sources in groups:
    common=[k for k in eligible_keys if all(finite(forecasts.get(k+(s,),(None,None))[0]) for s in sources)]
    member=hashlib.sha256(json.dumps(common).encode('utf-8')).hexdigest()
    for source in sources:
     errors=[forecasts[k+(source,)][0]-actual[k] for k in common];n=len(errors)
     summaries.append(dict(season=2026,player_type=role,metric=m,comparison_group=group,projection_source=source,n=n,mae=sum(map(abs,errors))/n if n else None,rmse=math.sqrt(sum(e*e for e in errors)/n) if n else None,bias=sum(errors)/n if n else None,membership_sha256=member))
     coverage.append(dict(player_type=role,metric=m,comparison_group=group,projection_source=source,eligible_actuals=len(eligible_keys),forecasts_with_eligible_actuals=sum(finite(forecasts.get(k+(source,),(None,None))[0]) for k in eligible_keys),matched_players=n,membership_sha256=member))
     for k in common:
      value,record=forecasts[k+(source,)];pairs.append(dict(season=2026,player_type=role,mlbam_id=k[2],metric=m,comparison_group=group,projection_source=source,prediction=value,actual=actual[k],error=value-actual[k],absolute_error=abs(value-actual[k]),source_record_id=record))
 missing_actual_population=[]
 for role,mlbam in sorted({(k[1],k[2]) for k in actual}):
  if (role,mlbam,HOME) not in meta:missing_actual_population.append(dict(season=2026,player_type=role,mlbam_id=mlbam,reason='ACTUAL_PARTICIPANT_ABSENT_FROM_FROZEN_HOMEGROWN_UNIVERSE',usage='EVALUATION_COVERAGE_ONLY_NOT_ADDED_TO_EXPORT'))
 return individual,summaries,pairs,coverage,missing_actual_population

def evaluate(run,labels,warehouse,output,backups):
 run,labels,warehouse=map(lambda p:Path(p).resolve(),(run,labels,warehouse));w=verify(run)
 for n,h in load(run/'forecast_freeze.json').items():
  if sha(run/n)!=h:raise ValueError('Released forecast freeze changed')
 report=load(run/'projection_release_report.json')
 if report['version']!=VERSION or report['evaluation_outcomes_read'] or report['models_fitted']:raise ValueError('Invalid release provenance')
 if sha(warehouse)!=report['warehouse_sha256']:raise ValueError('Evaluation warehouse differs from release warehouse')
 labreport=labels/'label_build_report.json';hold=labels/'holdout_labels.parquet';manifest=load(labels/'output_sha256.json')
 # Only the evaluation label table is opened; training selection is frozen already.
 for p in [labreport,hold]:
  if sha(p)!=manifest.get(p.name):raise ValueError('Evaluation label hash mismatch')
  w[str(p)]=sha(p)
 w[str(labels/'output_sha256.json')]=sha(labels/'output_sha256.json')
 if load(labreport)['reference_sha256']!=report['label_reference_sha256']:raise ValueError('Evaluation uses a different frozen FanGraphs reference')
 print('Projection exports verified and frozen. Reading separate 2026 eligible actuals...',flush=True)
 external,available,issues,ww=warehouse_forecasts(warehouse);w.update(ww);rr=load(run/'coherent_projection_records.json');ll=table(hold)
 catalog,names,catalog_w=canonical_catalog(warehouse);w.update(catalog_w);reverse={m:pid for pid,m in catalog.items()}
 out,bak,stage=start(output,backups,[run,labels,warehouse])
 try:
  individual,scores,pairs,coverage,absent=evaluation_rows(rr,ll,external)
  for r in individual:
   if not r['player_id']:r['player_id']=reverse.get(r['mlbam_id'])
   if not r['name']:r['name']=names.get(r['player_id']) or 'MLBAM '+r['mlbam_id']
  issues=[r for r in issues if int(r['season'])==2026]
  for n,rows in [('player_comparisons.csv',individual),('matched_benchmark_scores.csv',scores),('matched_benchmark_pairs.csv',pairs),('comparison_coverage.csv',coverage),('actual_participants_without_homegrown.csv',absent),('benchmark_identity_exceptions.csv',issues)]:emit(stage,n,rows)
  largest=[]
  for role in METRICS:
   for m in METRICS[role]:largest.extend(sorted([r for r in individual if r['player_type']==role and r['metric']==m and r['projection_source']==HOME and r['absolute_error'] is not None],key=lambda r:(-r['absolute_error'],r['mlbam_id']))[:25])
  emit(stage,'largest_homegrown_errors.csv',largest)
  result=dict(version=VERSION,status='DISCLOSED_2026_EVALUATION_NOT_NEW_SELECTION',evaluation_season=2026,previously_reviewed=True,models_fitted=False,selection_changed=False,forecasts_modified=False,inputs_unchanged=True,player_comparison_rows=len(individual),matched_pair_rows=len(pairs),benchmark_sources=sorted(available.get(2026,[])),actual_participants_without_homegrown=len(absent),comparison_statuses=dict(Counter(r['status'] for r in individual)),limitations=['Each paired score uses identical eligible players per metric and source group; groups can differ in membership.','Missing/ineligible actual components remain excluded; no source substitution or inferred zero participation.','Survivorship/participation coverage is reported separately; absent actual labels are not treated as zero.','Source projections retain their published/available metrics and exclusions; matched scores are not evidence of archived-as-of performance.','2026 has already been reviewed and cannot be treated as an untouched holdout.'])
  dump(stage/'projection_evaluation_report.json',result);backup=finish(out,bak,stage,w);return dict(result,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default=DEFAULTS['output']);p.add_argument('--labels',default=DEFAULTS['labels']);p.add_argument('--warehouse',default=DEFAULTS['warehouse']);p.add_argument('--output',default='outputs/projection_evaluation_2026_v1_11');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(evaluate(a.run,a.labels,a.warehouse,a.output,a.backup_root),indent=2))
if __name__=='__main__':main()
