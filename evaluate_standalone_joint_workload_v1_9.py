"""Disclosed 2026 evaluation after immutable forecast/choice verification."""
import json,shutil
from pathlib import Path
from standalone_io_v1_0 import load,dump,start,finish
from standalone_combined_v1_4 import read_all_labels
from category_benchmarks_v1_4 import warehouse_forecasts
from joint_io_v1_9 import context,validate,emit
from standalone_joint_workload_v1_9 import DISCLOSURE
from backtest_standalone_joint_workload_v1_9 import arguments,scores,comparison,sb_audit

def evaluate(run,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels,output,backups,warehouse=None):
 print('Verifying frozen joint model, all origin forecasts and historical choices...',flush=True);c=context(run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels);f,items,w=validate(run,c);c['watched'].update(w)
 print('Verification complete; reading previously reviewed 2026 evaluation outcomes...',flush=True);actual=dict(c['actual_training']);actual.update(read_all_labels(c['labels'],'holdout'));external,available,issues,w=warehouse_forecasts(warehouse) if warehouse else ({},{},[],{});c['watched'].update(w);output,backups,stage=start(output,backups,[run,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels]+([warehouse] if warehouse else []))
 try:
  counts=scores(stage,c,items,actual,2026,external,available);emit(stage,'workload_comparison.csv',comparison(c,items,actual,2026));allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist'];auditcounts=sb_audit(stage,c,actual,allow,f['settings'],load(Path(run)/'sb_frozen_feature_bins.json'),2026);emit(stage,'benchmark_identity_review.csv',issues)
  report=dict(version='1.9.0',status='JOINT_WORKLOAD_DISCLOSED_EVALUATION_COMPLETE',models_refitted=False,selection_retuned=False,inputs_unchanged=True,accepted_saves_holds_SB_preserved=True,SB_replacement_fitted=False,SB_features_selected=False,final_historical_choice=f['final_choice'],benchmark_run=warehouse is not None,source_availability={str(y):sorted(available.get(y,set())) for y in [2024,2025,2026]},**counts,SB_audit_tables=auditcounts,evaluation_disclosure=DISCLOSURE)
  dump(stage/'joint_workload_evaluation_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 a=arguments(True);print(json.dumps(evaluate(a.run,a.run18,a.run16,a.diagnostics,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,None if a.skip_benchmarks else a.warehouse),indent=2))
