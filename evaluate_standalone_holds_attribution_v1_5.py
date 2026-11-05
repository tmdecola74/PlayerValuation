"""Disclosed evaluation of frozen holds opportunity and count-error attribution."""
import argparse,csv,json,math,hashlib,shutil
from pathlib import Path
from standalone_io_v1_0 import dump,start,finish,write
from standalone_combined_v1_4 import read_all_labels,vectors,finite
from category_benchmarks_v1_4 import warehouse_forecasts
from standalone_holds_v1_5 import METHODS,DISCLOSURE
from standalone_attribution_v1_5 import holds_scores,HOLD_FIELDS
from holds_io_v1_5 import source_context,validate_run
from backtest_standalone_holds_attribution_v1_5 import write_attribution

BENCH_FIELDS=['season','metric','comparison_group','method','n','mae','rmse','bias','membership_sha256']
PAIR_FIELDS=['season','mlbam_id','metric','comparison_group','method','prediction','actual','source_record_id']

def benchmark(items,c,actual,external,available):
 scores=[];pairs=[];coverage=[]
 for year in [2024,2025,2026]:
  sources=sorted(available.get(year,set()));groups=[(s+'_paired',[s]) for s in sources]+([('all_available_sources',sources)] if sources else []);pool={k:d for k,d in items.items() if k[0]==year}
  for metric in ['HLD','SV_plus_HLD']:
   eligible={k:actual[k+(metric,)] for k in pool if k+(metric,) in actual}
   for group,ss in groups:
    methods=METHODS+ss
    def value(k,m):
     if m not in METHODS:return external.get(k+(metric,m),(None,None))[0]
     h=pool[k].get(m)
     if metric=='HLD':return h
     sv=c['base'][k].get('SV');return sv+h if finite(sv) and finite(h) else None
    common=sorted(k for k in eligible if all(finite(value(k,m)) for m in methods));membership=hashlib.sha256(json.dumps(common).encode()).hexdigest()
    for m in methods:
     errors=[value(k,m)-eligible[k] for k in common];n=len(errors);scores.append(dict(season=year,metric=metric,comparison_group=group,method=m,n=n,mae=sum(abs(e) for e in errors)/n if n else None,rmse=math.sqrt(sum(e*e for e in errors)/n) if n else None,bias=sum(errors)/n if n else None,membership_sha256=membership));coverage.append(dict(season=year,metric=metric,comparison_group=group,method=m,eligible_actuals=len(eligible),available_forecasts=sum(finite(value(k,m)) for k in eligible),common_pool=n))
     for k in common:pairs.append(dict(season=year,mlbam_id=k[2],metric=metric,comparison_group=group,method=m,prediction=value(k,m),actual=eligible[k],source_record_id='FROZEN_STANDALONE' if m in METHODS else external[k+(metric,m)][1]))
 return scores,pairs,coverage

def evaluate(run,run14,source,matrix,baseline,labels,output,backups,warehouse=None):
 print('Verifying frozen v1.5 before reading 2026 labels...',flush=True);c=source_context(run14,source,matrix,baseline,labels);actual=read_all_labels(c['labels'],'training');frozen,items,w=validate_run(run,c,actual);c['watched'].update(w)
 # Training targets are used only to verify the sealed earlier-fold choices. No refitting occurs.
 actual.update(read_all_labels(c['labels'],'holdout'));external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});c['watched'].update(w);scores,pairs,coverage=benchmark(items,c,actual,external,available);hs,hc=holds_scores(items,c['rows'],actual,METHODS);output,backups,stage=start(output,backups,[run,run14,source,matrix,baseline,labels]+([warehouse] if warehouse else []))
 try:
  ac=write_attribution(stage,c,actual,2026);write(stage/'holds_scores.csv',hs,HOLD_FIELDS);write(stage/'holds_coverage.csv',hc,['season','mlbam_id','actual_HLD','paired','candidate_supported']);write(stage/'holds_benchmark_scores.csv',scores,BENCH_FIELDS);write(stage/'holds_benchmark_pairs.csv',pairs,PAIR_FIELDS);write(stage/'holds_benchmark_coverage.csv',coverage,['season','metric','comparison_group','method','eligible_actuals','available_forecasts','common_pool']);write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  report=dict(version='1.5.0',status='FROZEN_HOLDS_AND_ATTRIBUTION_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,inputs_unchanged=True,v1_4_preserved=True,saves_preserved_exactly=True,classification_labels_preserved=True,non_holds_forecasts_preserved=True,final_historical_choice=frozen['final_choice'],holds_score_rows=len(hs),benchmark_score_rows=len(scores),attribution_coverage=ac,benchmark_run=warehouse is not None,identity_review_rows=len(issues),source_availability={str(y):sorted(available.get(y,set())) for y in [2024,2025,2026]},evaluation_disclosure=DISCLOSURE,limitations=['Workload and rate contributions are an exact symmetric arithmetic allocation, not causal estimates. MSE includes their interaction and cannot be allocated using squared terms alone.','Attribution compares frozen v1.2 and combined v1.4 on identical eligible numerator/denominator pools. v1.5 does not change HR, SB, W or SO forecasts.','Actual-role, actual-workload and actual-positive-holds cohorts are retrospective diagnostics, never selection features or gates.','Unavailable/excluded target components are not backfilled; zero actual or forecast exposure leaves rate attribution unresolved.','Ratio outliers are the top 25 per year/metric on the internal v1.4 eligible pool, not identical to external benchmark pools.','Holds selection uses historical gates against both prior releases, protecting prior-reliever and prior-holds cohorts. No 2026 retuning occurs.'])
  dump(stage/'holds_attribution_evaluation_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_holds_attribution_v1_5');p.add_argument('--run14',default='outputs/standalone_combined_v1_4');p.add_argument('--source',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--output',default='outputs/standalone_holds_attribution_evaluation_v1_5');p.add_argument('--backup-root',default='backups');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true');a=p.parse_args();print(json.dumps(evaluate(a.run,a.run14,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
