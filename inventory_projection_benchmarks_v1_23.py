"""Optional benchmark preflight before model fitting. Does not read actual labels."""
import argparse,json,shutil
from recent_skill_inputs_v1_23 import benchmark_snapshot
from recent_skill_core_v1_23 import emit,VERSION
from standalone_io_v1_0 import start,finish,dump

def inventory(a):
 watched={};rows,available,issues,raw=benchmark_snapshot(a.warehouse,a.benchmark_dir,watched)
 out,backups,stage=start(a.output,a.backup_root,[a.warehouse,a.benchmark_dir])
 try:
  for name,rr in [('benchmark_inventory',available),('benchmark_raw_file_inventory',raw),('benchmark_identity_exceptions',issues)]:emit(stage/(name+'.csv'),rr)
  report=dict(version=VERSION,status='BENCHMARK_INVENTORY_ONLY',forecast_metric_rows=len(rows),identity_exceptions=len(issues),models_fitted=False,actual_labels_read=False,external_forecasts_used_as_predictors=False,note='Only registered warehouse selections can supply matched comparisons; discovered raw files are not silently imported.')
  dump(stage/'benchmark_inventory_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(warehouse='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb',benchmark_dir='../last3yrsproj',output='outputs/projection_benchmark_inventory_v1_23',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(inventory(p.parse_args()),indent=2))
