"""Read-only evaluation of already-frozen forecasts; no training or selection."""
import argparse,shutil
from pathlib import Path
from standalone_io_v1_0 import *
from backtest_standalone_baselines_v1_0 import scores

def evaluate(run,matrix,output,backups):
 run,matrix=Path(run).resolve(),Path(matrix).resolve();watched=verify(run);watched.update(verify(matrix));freeze=load(run/'freeze_manifest.json')
 if sha(run/'frozen_models.json')!=freeze['models_sha256'] or sha(run/'frozen_2026_forecasts.csv')!=freeze['forecasts_sha256']:raise ValueError('Frozen forecast/model hash mismatch')
 frozen=load(run/'frozen_models.json')
 if frozen['holdout_features_sha256']!=sha(matrix/'holdout_features.parquet'):raise ValueError('Different holdout features')
 rows=table(matrix/'holdout_matrix.parquet')
 if any(int(r['target_season'])!=2026 for r in rows):raise ValueError('Holdout season mismatch')
 predictions=csvrows(run/'frozen_2026_forecasts.csv')
 for r in predictions:
  r['season']=int(r['season']);r['prediction']=float(r['prediction']) if r['prediction']!='' else None
  if r['season']!=2026:raise ValueError('Non-holdout forecast')
 summary,pairs=scores(predictions,rows);output,backups,stage=start(output,backups,[run,matrix])
 try:
  write(stage/'holdout_scores.csv',summary,['season','player_type','metric','method','n','mae','rmse','bias','membership_sha256','playing_time_stress_season']);write(stage/'holdout_paired_predictions.csv',pairs,['season','player_type','mlbam_id','metric','actual','baseline','standalone'])
  report=dict(version='1.0.0',status='FROZEN_HOLDOUT_EVALUATED',season=2026,paired_metric_rows=len(pairs),models_refitted=False,selection_retuned=False,models_sha256=freeze['models_sha256'],forecasts_sha256=freeze['forecasts_sha256'],inputs_unchanged=True,limitations=['Conditional on available eligible actual labels; missing outcomes are not zero.','Comparison pools are identical for historical-baseline and selected-standalone methods per metric.','This report must not be used to retune the frozen research release.'])
  dump(stage/'holdout_evaluation_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='outputs/standalone_baselines_v1_0');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--output',default='outputs/standalone_holdout_evaluation_v1_0');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(evaluate(a.run,a.matrix,a.output,a.backup_root),indent=2))
