"""Previously reviewed 2026 evaluation; no new fits or choice changes."""
import json,shutil
from standalone_io_v1_0 import load,dump,start,finish
from standalone_combined_v1_4 import read_all_labels
from category_benchmarks_v1_4 import warehouse_forecasts
from history_io_v1_10 import context,validate,emit
from standalone_SB_history_v1_10 import DISCLOSURE
from backtest_standalone_history_baselines_v1_10 import arguments,scores,comparison,diagnostic_tables

def evaluate(run,run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels,output,backups,warehouse=None):
 print('Verifying frozen priors, all forecasts and historical choices before evaluation...',flush=True);c=context(run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels);f,items,w=validate(run,c);c['watched'].update(w);c['settings110']=f['settings']
 print('Verification complete; reading disclosed 2026 actuals...',flush=True);actual=dict(c['actual_training']);actual.update(read_all_labels(c['labels'],'holdout'));external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});c['watched'].update(w);output,backups,stage=start(output,backups,[run,run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels]+([warehouse] if warehouse else []))
 try:
  counts=scores(stage,c,items,actual,2026,external,available);emit(stage,'SB_comparison.csv',comparison(c,items,actual,2026));dcounts=diagnostic_tables(stage,c,actual,f['settings'],2026);emit(stage,'benchmark_identity_review.csv',issues)
  report=dict(version='1.10.0',status='SB_HISTORY_BASELINES_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,pitcher_forecasts_preserved=True,saves_holds_preserved=True,hitter_non_SB_components_preserved=True,inputs_unchanged=True,final_historical_choice=f['final_choice'],benchmark_run=warehouse is not None,source_availability={str(y):sorted(available.get(y,set())) for y in [2024,2025,2026]},**counts,pitcher_diagnostic_tables=dcounts,evaluation_disclosure=DISCLOSURE)
  dump(stage/'history_baselines_evaluation_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 a=arguments(True);print(json.dumps(evaluate(a.run,a.run19,a.run18,a.run16,a.diagnostics,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
