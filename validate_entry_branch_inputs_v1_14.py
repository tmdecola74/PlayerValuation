"""Validate dated branch intake and freeze a fold plan; no label join or model fit."""
import argparse,json,shutil
from standalone_io_v1_0 import start,finish,dump
from projection_release_v1_11_1 import emit
from entry_branch_v1_14 import intake,CONFIG

def build(population,history,context,cutoffs,output,backups):
 rows,folds,report,watched=intake(population,history,context,cutoffs);out,bak,stage=start(output,backups,[p for p in [population,history,context,cutoffs] if p])
 try:
  for n,rr in rows.items():emit(stage,'validated_'+n+'.csv',rr)
  emit(stage,'historical_fold_plan.csv',folds);dump(stage/'entry_branch_contract.json',CONFIG);dump(stage/'entry_branch_intake_report.json',report);backup=finish(out,bak,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n in ['population','history','context','cutoffs']:p.add_argument('--'+n)
 p.add_argument('--output',default='outputs/entry_branch_intake_v1_14');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.population,a.history,a.context,a.cutoffs,a.output,a.backup_root),indent=2))
if __name__=='__main__':main()
