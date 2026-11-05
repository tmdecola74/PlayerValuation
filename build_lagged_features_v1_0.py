"""Prior-season-only standalone features with separately joined training/holdout outcomes."""
from __future__ import annotations
import argparse,csv,json,math,shutil,tempfile,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from datetime import datetime,timezone
import duckdb
from lagged_io_v1_0 import sha,load,dump,tree,inside,integer
from lagged_statcast_v1_0 import aggregate,MEASURES,era,ERA_NAMES

KEY=['target_season','player_type','mlbam_id']
BASE=KEY+['source_cutoff','max_source_season','history_seasons','age_at_target_estimate','has_any_actual_history','has_any_statcast_history']
def csvout(p,rows,fields):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def csvrows(p):
 with p.open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)
def verify_manifest(root):
 m=load(root/'output_sha256.json')
 for n,h in m.items():
  if sha(inside(root,n))!=h:raise ValueError('Input manifest hash mismatch: '+n)
 return {str(inside(root,n)):h for n,h in m.items()}|{str(root/'output_sha256.json'):sha(root/'output_sha256.json')}
def label_rows(db,path,purpose,years):
 rel=db.read_parquet(str(path));required={'season','player_type','mlbam_id','metric','label_value','eligible','purpose','label_source'}
 if not required<=set(rel.columns):raise ValueError('Unexpected label schema')
 rows=rel.project(','.join('"'+c+'"' for c in sorted(required))).fetchall();out={}
 for row in rows:
  r=dict(zip(sorted(required),row));y=integer(r['season'],'label season');k=(y,r['player_type'],str(integer(r['mlbam_id'],'ID')),r['metric'])
  if y not in years or not r['eligible'] or r['purpose']!=purpose or r['label_source']!='FROZEN_FANGRAPHS_ACTUALS' or k in out or r['label_value'] is None or not math.isfinite(r['label_value']):raise ValueError('Bad/duplicate label or split contamination')
  out[k]=r['label_value']
 return out

def build(labels,reference,source_windows,config,output,backups):
 labels,reference,source_windows,config,output,backups=map(lambda p:Path(p).resolve(),(labels,reference,source_windows,config,output,backups))
 if output.exists():raise FileExistsError('Choose a new output folder')
 for a,b in [(output,labels),(output,reference),(output,backups),(backups,labels),(backups,reference)]:
  if a==b or a in b.parents or b in a.parents:raise ValueError('Overlapping input/output/backup')
 if output==source_windows or output in source_windows.parents:raise ValueError('Output overlaps source manifest')
 c=load(config);report=load(labels/'label_build_report.json');policy=load(labels/'register_snapshot/modeling_label_policy.json');lc=load(labels/'training_labels_config.json')
 if c['source_seasons']!=list(range(min(c['source_seasons']),c['holdout_target_season'])) or c['training_target_seasons']!=list(range(min(c['source_seasons'])+1,c['holdout_target_season'])):raise ValueError('Chronology configuration mismatch')
 if c['lags']!=[1,2,3] or c['raw_outcome_features'] or c['bat_tracking_features']:raise ValueError('Unsupported feature contract')
 if c['holdout_target_season']!=report['holdout_season'] or max(report['training_seasons'])!=c['holdout_target_season']-1 or report['primary_source']!='FROZEN_FANGRAPHS_ACTUALS':raise ValueError('Label report chronology/source mismatch')
 watched=verify_manifest(labels);watched[str(config)]=sha(config)
 for n,h in report['reference_sha256'].items():
  p=reference/n
  if sha(p)!=h or h!=policy['expected_reference_hashes'][n]:raise ValueError('Frozen actuals reference mismatch')
  watched[str(p)]=h
 actual={};ages={};actual_players=set()
 with duckdb.connect() as db:
  train=label_rows(db,labels/'training_labels.parquet','training',set(report['training_seasons']))
  if len(train)!=report['rows']['training_eligible']:raise ValueError('Training label count mismatch')
  for (y,role,pid,m),v in train.items():actual[y,role,pid,m]=v
  rel=db.read_parquet(str(reference/'player_seasons.parquet'))
  for y,role,pid,age in rel.project('season,player_type,mlbam_id,age').fetchall():
   y=integer(y,'source year');pid=str(integer(pid,'ID'))
   if y not in c['source_seasons']:continue
   if role not in ('hitter','pitcher') or pid=='0' or (y,role,pid) in actual_players:raise ValueError('Invalid or duplicate historical identity')
   actual_players.add((y,role,pid));ages[y,role,pid]=age
 print('Checking frozen daily windows and physical measurements...',flush=True)
 stats,audit,schemas,selected,source_hashes=aggregate(source_windows,c);watched.update(source_hashes)
 # No target outcome is used to select candidates. Prior participants define the pool.
 fields=BASE[:];numeric=set(BASE)-{'target_season','player_type','mlbam_id','source_cutoff'}
 metrics=sorted(set().union(*map(set,lc['metrics'].values())))
 for lag in c['lags']:
  meta=[f'source_season_lag{lag}',f'tracking_era_lag{lag}',f'short_season_lag{lag}'];fields+=meta;numeric.update(meta)
  cols=[f'x_actual_lag{lag}_{m}' for m in metrics]
  cols += [f'x_statcast_lag{lag}_{m}_{s}' for m in MEASURES for s in ['value','observations','coverage','eligible']]
  fields+=cols;numeric.update(cols)
 # Explicit feature allowlist; target columns are created only after feature files freeze.
 if any(n.startswith('y_') for n in fields):raise ValueError('Target entered feature schema')
 output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent));backup=None
 try:
  pools={};lineage=[];pool_counts=[]
  for split,targets in [('training',c['training_target_seasons']),('holdout',[c['holdout_target_season']])]:
   rows=[]
   for target in targets:
    years={target-l for l in c['lags'] if target-l in c['source_seasons']}
    candidates={(role,pid) for y,role,pid in actual_players|set(stats) if y in years}
    pools[target]=candidates;pool_counts.append(dict(target_season=target,split=split,candidates=len(candidates)))
    for role,pid in sorted(candidates):
     r=dict.fromkeys(fields);r.update(target_season=target,player_type=role,mlbam_id=pid,source_cutoff=f'{target-1}-12-31')
     history=[y for y in years if (y,role,pid) in actual_players or (y,role,pid) in stats]
     r.update(max_source_season=max(history),history_seasons=len(history),has_any_actual_history=int(any((y,role,pid) in actual_players for y in years)),has_any_statcast_history=int(any((y,role,pid) in stats for y in years)))
     age_years=[y for y in years if ages.get((y,role,pid)) is not None]
     if age_years:
      last=max(age_years);r['age_at_target_estimate']=float(ages[last,role,pid])+target-last
     for lag in c['lags']:
      y=target-lag
      if y not in c['source_seasons']:continue
      r[f'source_season_lag{lag}']=y;r[f'tracking_era_lag{lag}']=era(y);r[f'short_season_lag{lag}']=int(y==2020)
      for m in lc['metrics'][role]:r[f'x_actual_lag{lag}_{m}']=actual.get((y,role,pid,m))
      for m,f in stats.get((y,role,pid),{}).items():
       for suffix,v in [('value',f['value']),('observations',f['observations']),('coverage',f['coverage']),('eligible',int(f['eligible']))]:r[f'x_statcast_lag{lag}_{m}_{suffix}']=v
      if (y,role,pid) in actual_players or (y,role,pid) in stats:
       lineage.append(dict(target_season=target,player_type=role,mlbam_id=pid,lag=lag,source_season=y,source_event_cutoff=f'{y}-{c["window_end_mmdd"]}',actual_source_present=(y,role,pid) in actual_players,statcast_source_present=(y,role,pid) in stats))
     if r['max_source_season']>=target:raise ValueError('Future feature history')
     rows.append(r)
   csvout(stage/(split+'_features.csv'),rows,fields)
  feature_hashes={s:sha(stage/(s+'_features.csv')) for s in ['training','holdout']}
  # Only now open 2026 outcomes; no candidate selection or features can depend on them.
  with duckdb.connect() as db:hold=label_rows(db,labels/'holdout_labels.parquet','holdout_evaluation',{c['holdout_target_season']})
  if len(hold)!=report['rows']['holdout_eligible']:raise ValueError('Holdout label count mismatch')
  outcomes={'training':train,'holdout':hold};cold=[];matrix_counts=Counter();join_counts=Counter()
  for split,lookup in outcomes.items():
   yfields=[f'y_{m}' for m in metrics]+[f'y_eligible_{m}' for m in metrics]
   with (stage/(split+'_matrix.csv')).open('w',newline='',encoding='utf-8') as f:
    w=csv.DictWriter(f,fieldnames=fields+yfields);w.writeheader()
    for r in csvrows(stage/(split+'_features.csv')):
     target=int(r['target_season']);role=r['player_type'];pid=r['mlbam_id']
     for m in metrics:
      v=lookup.get((target,role,pid,m));r['y_'+m]=v;r['y_eligible_'+m]=int(v is not None)
     join_counts[target,role,'HAS_ELIGIBLE_LABEL' if any(r['y_eligible_'+m] for m in metrics) else 'NO_ELIGIBLE_TARGET_LABEL']+=1
     r.update({k:None for k,v in r.items() if v==''})
     w.writerow(r);matrix_counts[split]+=1
   keys=Counter((y,role,pid) for y,role,pid,m in lookup if y in pools and (role,pid) not in pools[y])
   cold.extend(dict(target_season=y,player_type=role,mlbam_id=pid,eligible_target_metrics=n,split=split,reason='NO_PRIOR_HISTORY_IN_CONFIGURED_LAGS_NO_INVENTED_ZERO') for (y,role,pid),n in sorted(keys.items()))
  if any(sha(stage/(s+'_features.csv'))!=h for s,h in feature_hashes.items()):raise ValueError('Features changed during target attachment')
  csvout(stage/'target_join_coverage.csv',[dict(target_season=y,player_type=role,status=status,rows=n) for (y,role,status),n in sorted(join_counts.items())],['target_season','player_type','status','rows'])
  csvout(stage/'lag_lineage.csv',lineage,list(lineage[0]));csvout(stage/'candidate_pool_audit.csv',pool_counts,list(pool_counts[0]));csvout(stage/'cold_start_targets.csv',cold,['target_season','player_type','mlbam_id','eligible_target_metrics','split','reason'])
  csvout(stage/'measurement_player_season_audit.csv',audit,list(audit[0]));csvout(stage/'measurement_schema_audit.csv',schemas,list(schemas[0]))
  pooled=defaultdict(lambda:dict(players=0,available_players=0,observations=0,opportunities=0))
  for a in audit:
   v=pooled[a['source_season'],a['player_type'],a['measurement'],a['tracking_era_code']];v['players']+=1;v['available_players']+=int(a['eligible']);v['observations']+=a['observations'];v['opportunities']+=a['opportunities']
  availability=[dict(source_season=y,player_type=role,measurement=m,tracking_era_code=e,**v,measurement_coverage=v['observations']/v['opportunities'] if v['opportunities'] else None) for (y,role,m,e),v in sorted(pooled.items())]
  csvout(stage/'measurement_availability_by_era.csv',availability,list(availability[0]))
  types={k:('DOUBLE' if k in numeric else 'VARCHAR') for k in fields};types['target_season']='INTEGER'
  with duckdb.connect() as db:
   for split in ['training','holdout']:
    for kind in ['features','matrix']:
     t=types if kind=='features' else types|{f'y_{m}':'DOUBLE' for m in metrics}|{f'y_eligible_{m}':'INTEGER' for m in metrics}
     db.read_csv(str(stage/(split+'_'+kind+'.csv')),header=True,columns=t).write_parquet(str(stage/(split+'_'+kind+'.parquet')),compression='zstd')
  folds=[dict(evaluation_target_season=y,training_target_seasons=[p for p in c['training_target_seasons'] if p<y],feature_event_cutoff=f'{y-1}-12-31') for y in c['training_target_seasons'] if y>=c['first_rolling_evaluation_year']]
  dump(stage/'rolling_origin_folds.json',folds);dump(stage/'feature_schema.json',dict(feature_columns=fields,numeric_features=sorted(numeric),predictor_allowlist=[n for n in fields if n.startswith(('x_','tracking_era_lag','short_season_lag')) or n in ['history_seasons','age_at_target_estimate','has_any_actual_history','has_any_statcast_history']],categorical_predictors=[n for n in fields if n.startswith('tracking_era_lag')],label_columns=[f'y_{m}' for m in metrics],label_metric_mapping={f'y_{m}':m for m in metrics},tracking_eras=ERA_NAMES))
  shutil.copyfile(source_windows,stage/'source_windows.json');shutil.copyfile(config,stage/'effective_config.json');shutil.copyfile(labels/'label_build_report.json',stage/'label_source_report.json');dump(stage/'input_hashes.json',watched)
  if any(sha(p)!=h for p,h in watched.items()):raise ValueError('Source changed during feature build')
  backup=backups/(output.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
  result=dict(version='1.0.0',status='LAGGED_MATRIX_BUILT_REVIEW_REQUIRED',source_seasons=c['source_seasons'],training_target_seasons=c['training_target_seasons'],holdout_target_season=c['holdout_target_season'],matrix_rows=dict(matrix_counts),pitch_rows=sum(r['rows'] for r in selected),selected_windows=len(selected),latest_source_retrieved_at=max((r.get('available_at','') for r in selected),default=''),cold_start_player_seasons=len(cold),eligible_label_source='FROZEN_FANGRAPHS_ACTUALS',feature_population='UNION_OF_PRIOR_ACTUALS_AND_PHYSICAL_STATCAST_PARTICIPANTS_WITHIN_LAGS',feature_hashes_before_labels=feature_hashes,external_projections_used=False,inputs_unchanged=True,models_fitted=False,model_ready=False,backup=str(backup),limitations=['Event-time chronology only; sources retrieved retrospectively, not archived preseason vintages.','No scaling, mean imputation, shrinkage fitting or hyperparameter selection performed.','Measurement availability and era indicators do not certify physical comparability.','No prospect/minor-league inputs or complete preseason roster universe; cold starts are audited separately.','Only physical pitch/contact metrics are derived here; official outcome features come from eligible FanGraphs labels.','2015 target labels have no earlier source history and are not in training matrices.','Use only x_/history/age feature allowlist; y_ columns are outcomes, never predictors.','2020 is flagged without automatic exposure rescaling.'])
  dump(stage/'lagged_build_report.json',result);dump(stage/'output_sha256.json',tree(stage));backups.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
  if tree(stage)!=tree(backup):raise ValueError('Backup hash mismatch')
  if any(sha(p)!=h for p,h in watched.items()):raise ValueError('Source changed before publication')
  stage.rename(output);return result
 finally:
  if stage.exists():
   shutil.rmtree(stage)
   if backup is not None and backup.exists():shutil.rmtree(backup)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--reference',default='data/actuals_reference_v1_0_min0ip');p.add_argument('--source-windows',default='outputs/actuals_statcast_reconciliation_v1_0_error_evidence/source_windows.json');p.add_argument('--config',default='config/lagged_features_v1_0.json');p.add_argument('--output',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.labels,a.reference,a.source_windows,a.config,a.output,a.backup_root),indent=2))
