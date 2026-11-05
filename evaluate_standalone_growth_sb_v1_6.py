"""Evaluate frozen separate experiments; 2026 is disclosed, never refitted or retuned."""
import argparse,json,shutil
from pathlib import Path
from standalone_io_v1_0 import dump,write,start,finish,load
from standalone_combined_v1_4 import read_all_labels
from category_benchmarks_v1_4 import warehouse_forecasts
from standalone_growth_sb_v1_6 import DISCLOSURE
from growth_sb_io_v1_6 import sources,validate
from growth_sb_scores_v1_6 import workload_comparator,direction_scores,DIRECTION_FIELDS
from backtest_standalone_growth_sb_v1_6 import write_scores


def evaluate(run,run15,run14,source,matrix,baseline,labels,output,backups,warehouse=None):
 print('Verifying frozen separate experiments before reading 2026 outcomes...',flush=True);run=Path(run).resolve();c=sources(run15,run14,source,matrix,baseline,labels);f,items,w=validate(run,c);c['watched'].update(w);actual=dict(c['actual_training']);actual.update(read_all_labels(c['labels'],'holdout'));external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});c['watched'].update(w);output,backups,stage=start(output,backups,[run,run15,run14,source,matrix,baseline,labels]+([warehouse] if warehouse else []))
 try:
  counts=write_scores(stage,c,items,actual,external,available);wc=workload_comparator(c,items,actual);write(stage/'prior_change_comparison.csv',wc,['season','method','n','rmse_OUTS','mae_OUTS','bias_OUTS','membership_sha256']);directions=direction_scores(items,actual,load(run/'direction_frequencies.json'));write(stage/'growth_direction_scores.csv',directions,DIRECTION_FIELDS);write(stage/'identity_review.csv',issues,['season','player_type','source','player_id','record_id','reason'])
  report=dict(version='1.6.0',status='SEPARATE_GROWTH_SB_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,inputs_unchanged=True,saves_preserved_exactly=True,holds_preserved_exactly=True,classification_labels_preserved=True,experiments_combined=False,final_historical_choices=f['final_choices'],**counts,benchmark_run=warehouse is not None,source_availability={str(y):sorted(available.get(y,set())) for y in [2024,2025,2026]},identity_review_rows=len(issues),evaluation_disclosure=DISCLOSURE,limitations=['Only identical eligible comparison pools support accuracy comparisons. Missing or excluded labels/forecasts remain missing.','Actual-role and actual-workload cohorts are retrospective diagnostics, never selection features or gates.','Historical choices are replayed and 2026 candidate forecasts reproduced from frozen models before opening 2026 labels. No refitting occurs.','Pitcher comparisons with the earlier rejected v1.3 change candidate are research diagnostics, not automatic adoption.','Opportunity and role probabilities are model estimates without a calibration guarantee. Event-time cutoffs do not certify archived preseason vintages.'])
  dump(stage/'growth_sb_evaluation_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_growth_sb_v1_6');p.add_argument('--run15',default='outputs/standalone_holds_attribution_v1_5');p.add_argument('--run14',default='outputs/standalone_combined_v1_4');p.add_argument('--source',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--output',default='outputs/standalone_growth_sb_evaluation_v1_6');p.add_argument('--backup-root',default='backups');p.add_argument('--warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb');p.add_argument('--skip-benchmarks',action='store_true');a=p.parse_args();print(json.dumps(evaluate(a.run,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
