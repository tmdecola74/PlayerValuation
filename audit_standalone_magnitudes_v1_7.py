"""Diagnose frozen v1.6 forecasts without fitting or changing selections."""
import argparse,json,shutil
from pathlib import Path
from collections import Counter
from standalone_io_v1_0 import load,dump,write,start,finish
from growth_sb_io_v1_6 import sources,validate
from standalone_combined_v1_4 import read_all_labels
from standalone_magnitude_diagnostics_v1_7 import *
from magnitude_stability_v1_7 import stability

def emit(stage,name,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r));write(stage/name,rows,fields or ['status'])

def build(run,run15,run14,source,matrix,baseline,labels,output,backups,include_2026=False):
 print('Verifying frozen releases, forecasts and historical choices; no fitting...',flush=True)
 c=sources(run15,run14,source,matrix,baseline,labels);f,items,watched=validate(run,c);watched=dict(c['watched'])|watched;actual=dict(c['actual_training']);maximum=2026 if include_2026 else 2025
 if include_2026:
  print('Reading previously reviewed 2026 labels for disclosed diagnostics only...',flush=True);actual.update(read_all_labels(c['labels'],'holdout'))
 output,backups,stage=start(output,backups,[run,run15,run14,source,matrix,baseline,labels])
 try:
  pitchers=[];hitters=[]
  for k,d in sorted(items.items()):
   if k[0]>maximum:continue
   if k[1]=='pitcher':pitchers.append(pitcher_row(k,d,c['rows'][k],actual,f['settings']))
   else:hitters.extend(sb_rows(k,d,c['rows'][k],c['base15'][k],actual,f['settings']))
  mag,comp,cal=pitcher_summary(pitchers);sb,three=sb_summary(hitters);choices=load(Path(run)/'rolling_choices.json');annual,roll=stability(pitchers,hitters,choices,maximum)
  tables={'pitcher_player_diagnostics.csv':pitchers,'pitcher_magnitude_summary.csv':mag,'pitcher_error_components.csv':comp,'growth_probability_bins.csv':cal,'pitcher_largest_misses.csv':largest_pitcher_misses(pitchers),'transition_2021.csv':[d for d in pitchers if d['season']==2021],'sb_player_diagnostics.csv':hitters,'sb_error_components.csv':sb,'sb_three_factor_components.csv':three,'sb_largest_misses.csv':largest_sb_misses(hitters),'season_stability.csv':annual,'historical_stability_rollup.csv':roll}
  coverage=[]
  for y in range(2019,maximum+1):
   for role,rr,status in [('pitcher',[d for d in pitchers if d['season']==y],'magnitude_status'),('hitter',[d for d in hitters if d['season']==y and d['method']=='v1_6_candidate'],'status')]:
    for st,n in sorted(Counter(d[status] for d in rr).items()):coverage.append(dict(season=y,split=phase(y),player_type=role,status=st,rows=n))
  tables['diagnostic_coverage.csv']=coverage
  for name,rr in tables.items():emit(stage,name,rr)
  dump(stage/'source_rolling_choices_v1_6.json',choices)
  limitations=['Algebraic error decompositions are diagnostic identities, not causal explanations. MSE includes signed interaction terms; component squared errors cannot be added alone.','SB opportunity is non-HR hits plus walks plus HBP, not actual stealable-base opportunities. Implied propensity includes caps and fallback; raw model probability/rate and cap effects are separately reported.','Conditional pitcher magnitudes require eligible actual G>0 and OUTS. Nonparticipation or missing outcomes are not fabricated zero workloads.','2021 retains the frozen 2020 workload normalization; raw prior OUTS, normalized anchor and realized OUTS are reported without refitting.','Development-policy rollup retains the existing 2020 stress exclusion; the separate all-historical rollup includes 2020. Both retain 2021 and every other unfavorable eligible season.','Sources were retrieved retrospectively, not archived preseason vintages. Previously reviewed 2026 is disclosed evaluation only. No model choices change.','Outliers use MLBAM identities; names are not inferred. Missing decomposition components remain missing even where scalar count errors are available.']
  report=dict(version='1.7.0',status='FROZEN_FORECAST_DIAGNOSTICS_ONLY',source_v1_6_preserved=True,models_fitted=False,selection_changed=False,forecasts_modified=False,saves_and_holds_unchanged=True,include_2026=include_2026,evaluation_disclosure='2026 previously reviewed; evaluation only',historical_seasons=list(range(2019,2026)),pitcher_rows=len(pitchers),hitter_player_method_rows=len(hitters),tables={n:len(r) for n,r in tables.items()},inputs_unchanged=True,limitations=limitations)
  dump(stage/'magnitude_diagnostic_report.json',report);(stage/'diagnostic_notes.md').write_text('\n\n'.join(limitations),encoding='utf-8');backup=finish(output,backups,stage,watched);return report|dict(backup=backup)
 finally:
  if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in [('run','standalone_growth_sb_v1_6'),('run15','standalone_holds_attribution_v1_5'),('run14','standalone_combined_v1_4'),('source','standalone_workload_experiments_v1_3'),('matrix','standalone_lagged_features_v1_0'),('baseline','standalone_role_workload_v1_2'),('labels','training_labels_v1_0')]:p.add_argument('--'+n,default='outputs/'+v)
 p.add_argument('--output',default='outputs/standalone_magnitude_diagnostics_v1_7');p.add_argument('--backup-root',default='backups');p.add_argument('--include-2026',action='store_true');a=p.parse_args();print(json.dumps(build(a.run,a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root,a.include_2026),indent=2))
