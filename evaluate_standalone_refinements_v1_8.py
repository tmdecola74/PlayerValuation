"""Evaluate immutable v1.8 choices on previously reviewed 2026, without refitting."""
import json,shutil
from pathlib import Path
from standalone_io_v1_0 import dump,start,finish
from standalone_combined_v1_4 import read_all_labels
from category_benchmarks_v1_4 import warehouse_forecasts
from refinement_io_v1_8 import context,validate,emit
from standalone_refinements_v1_8 import DISCLOSURE
from backtest_standalone_refinements_v1_8 import arguments,scores,comparison

def evaluate(run,run16,diagnostics,run15,run14,source,matrix,baseline,labels,output,backups,warehouse=None):
 print('Verifying immutable v1.8 models, historical choices and forecasts...',flush=True);c=context(run16,diagnostics,run15,run14,source,matrix,baseline,labels);f,items,w=validate(run,c);c['watched'].update(w)
 print('Frozen verification complete; reading disclosed 2026 evaluation labels...',flush=True);actual=dict(c['actual_training']);actual.update(read_all_labels(c['labels'],'holdout'));external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});c['watched'].update(w);output,backups,stage=start(output,backups,[run,run16,diagnostics,run15,run14,source,matrix,baseline,labels]+([warehouse] if warehouse else []))
 try:
  counts=scores(stage,c,items,actual,2026,external,available);emit(stage,'target_comparison.csv',comparison(c,items,actual,2026));emit(stage,'benchmark_identity_review.csv',issues)
  report=dict(version='1.8.0',status='SEPARATE_REFINEMENTS_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,inputs_unchanged=True,experiments_combined=False,saves_preserved_exactly=True,accepted_holds_preserved_exactly=True,final_historical_choices=f['final_choices'],benchmark_run=warehouse is not None,source_availability={str(y):sorted(available.get(y,set())) for y in [2024,2025,2026]},identity_review_rows=len(issues),**counts,evaluation_disclosure=DISCLOSURE)
  dump(stage/'refinement_evaluation_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 a=arguments(True);print(json.dumps(evaluate(a.run,a.run16,a.diagnostics,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
