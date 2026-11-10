"""Versioned leaderboard intake, reconciliation and lag add-ons; accepted forecasts untouched."""
import argparse,csv,json,shutil,math
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import duckdb
from standalone_io_v1_0 import load,dump,sha,start,finish,write
from standalone_diagnostics_v1_16 import checked,emit
from leaderboard_core_v1_21 import VERSION,DEFAULT,FIELDS,registry,read_sources

def lit(x):return "'"+str(x).replace("'","''")+"'"
def pq(db,path):
 types={n:'VARCHAR' for n in FIELDS};types.update({n:'INTEGER' for n in ['source_row','source_season','minimum_observations']});types.update({n:'DOUBLE' for n in ['raw_value','normalized_value','value','denominator','coverage']});types.update({n:'BOOLEAN' for n in ['sample_eligible','definition_supported','eligible']})
 db.read_csv(str(path),header=True,columns=types).write_parquet(str(path.with_suffix('.parquet')),compression='zstd')

MAP={('batted_ball','gb_rate'):('expanded','gb_pct',1e-8),('batted_ball','air_rate'):('expanded','air_pct',1e-8),('batted_ball','fb_rate'):('expanded','fb_pct',1e-8),('batted_ball','ld_rate'):('expanded','ld_pct',1e-8),('batted_ball','pu_rate'):('expanded','popup_pct',1e-8),('batted_ball','pull_rate'):('expanded','pull_proxy_pct',.02),('batted_ball','pull_air_rate'):('expanded','pulled_air_proxy_per_bbe',.02),('exit_velocity','avg_hit_angle'):('expanded','launch_angle_mean',.0500001),('exit_velocity','anglesweetspotpercent'):('expanded','launch_angle_8_32_pct',.0005001),('exit_velocity','avg_hit_speed'):('classic','ev',.0500001),('exit_velocity','ev95percent'):('classic','hardhit_pct',.0005001),('exit_velocity','brl_percent'):('classic','barrel_pct',.0005001)}

def reconcile(rows,expanded,matrix,watched):
 path=checked(expanded,'expanded_features_season.parquet',watched);report=load(checked(expanded,'expanded_feature_report.json',watched))
 if report['version']!='1.20.0' or report['models_fitted'] or report['accepted_matrix_modified']:raise ValueError('Require immutable v1.20 feature build')
 bindings=load(checked(expanded,'input_hashes.json',watched));source=checked(matrix,'source_windows.json',watched)
 if bindings.get(str(source))!=sha(source):raise ValueError('Expanded archive differs from frozen matrix source')
 selected=sorted({v[1] for v in MAP.values() if v[0]=='expanded'});index={}
 with duckdb.connect() as db:
  cur=db.execute('SELECT source_season,player_type,mlbam_id,metric,raw_value,denominator,opportunities,coverage FROM read_parquet('+lit(path)+') WHERE source_season BETWEEN 2023 AND 2025 AND metric IN ('+','.join(map(lit,selected))+')');names=[x[0] for x in cur.description]
  for rr in cur.fetchall():
   r=dict(zip(names,rr));k='expanded',int(r['source_season']),r['player_type'],str(r['mlbam_id']),r['metric']
   if k in index:raise ValueError('Duplicate archive reconciliation metric')
   index[k]=dict(value=r['raw_value'],observations=r['denominator'],bbe=r['opportunities'],coverage=r['coverage'])
 # Original physical summaries are optional, but only a registered file can supply them.
 manifest=load(matrix/'output_sha256.json');classic_status='REGISTERED_CLASSIC_AUDIT_UNAVAILABLE'
 if 'measurement_player_season_audit.csv' in manifest:
  cp=checked(matrix,'measurement_player_season_audit.csv',watched);classic_status='REGISTERED_CLASSIC_AUDIT_USED'
  with cp.open(encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    if int(r['source_season']) not in [2023,2024,2025] or r['measurement'] not in ['ev','hardhit_pct','barrel_pct']:continue
    k='classic',int(r['source_season']),r['player_type'],str(r['mlbam_id']),r['measurement']
    if k in index:raise ValueError('Duplicate classic audit key')
    cv=lambda n:float(r[n]) if r[n]!='' else None
    index[k]=dict(value=cv('raw_value'),observations=cv('observations'),bbe=cv('opportunities'),coverage=cv('coverage'))
 out=[]
 for r in rows:
  spec=MAP.get((r['family'],r['metric']))
  if not spec:continue
  kind,metric,tol=spec;a=index.get((kind,r['source_season'],r['player_type'],r['mlbam_id'],metric));delta=r['normalized_value']-a['value'] if a and a['value'] is not None and r['normalized_value'] is not None else None;countmatch=bool(a and a['bbe']==r['denominator']);proxy='proxy' in metric
  status='NO_ARCHIVE_PLAYER_METRIC' if not a else 'ARCHIVE_OR_EXPORT_VALUE_MISSING' if delta is None else 'PROXY_MATCH_NOT_CERTIFICATION' if proxy and countmatch and abs(delta)<=tol else 'PROXY_OR_SCOPE_REVIEW_REQUIRED' if proxy else 'DENOMINATOR_OR_SCOPE_DIFFERENCE' if not countmatch else 'MATCH_WITHIN_ROUNDING_TOLERANCE' if abs(delta)<=tol else 'VALUE_DIFFERENCE_SCOPE_UNVERIFIED'
  out.append(dict(source_season=r['source_season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],family=r['family'],metric=r['metric'],archive_metric=metric,export_original=r['raw_text'],export_normalized=r['normalized_value'],export_denominator=r['denominator'],archive_value=a['value'] if a else None,archive_observations=a['observations'] if a else None,archive_bbe=a['bbe'] if a else None,archive_coverage=a['coverage'] if a else None,value_difference=delta,review_tolerance=tol,denominator_matches=countmatch,status=status,counts_replaced=False,source_id=r['source_id']))
 return out,classic_status

def lags(db,stage,matrix,watched,features):
 db.execute('CREATE TEMP TABLE names(family VARCHAR,feature VARCHAR,metric VARCHAR)');db.executemany('INSERT INTO names VALUES (?,?,?)',features)
 db.execute('CREATE VIEW history AS SELECT * FROM read_parquet('+lit(stage/'historical/leaderboard_features.parquet')+')')
 population=[];availability=[]
 for split in ['training','holdout']:
  path=checked(matrix,split+'_features.parquet',watched)
  db.execute('CREATE OR REPLACE VIEW pop AS SELECT target_season,player_type,CAST(mlbam_id AS VARCHAR) AS mlbam_id,history_seasons,age_at_target_estimate,max_source_season,source_cutoff FROM read_parquet('+lit(path)+')')
  bad=db.execute("SELECT count(*) FROM pop WHERE target_season IS NULL OR player_type NOT IN ('hitter','pitcher') OR player_type IS NULL OR try_cast(mlbam_id AS BIGINT)<=0 OR try_cast(mlbam_id AS BIGINT) IS NULL OR max_source_season IS NULL OR max_source_season>=target_season OR try_cast(source_cutoff AS DATE) IS NULL OR try_cast(source_cutoff AS DATE)>=CAST(CAST(target_season AS VARCHAR)||'-01-01' AS DATE)"+(' OR target_season<>2026' if split=='holdout' else ' OR target_season NOT BETWEEN 2016 AND 2025')).fetchone()[0]
  if bad or db.execute('SELECT count(*) FROM (SELECT target_season,player_type,mlbam_id FROM pop GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Invalid/duplicate prior-history population')
  q='''SELECT p.target_season,p.player_type,p.mlbam_id,p.history_seasons,p.age_at_target_estimate,l.lag,p.target_season-l.lag AS source_season,n.family,n.feature,h.value,h.denominator,h.sample_eligible,coalesce(h.eligible,false) AS eligible,coalesce(h.reason,'NO_MATCHING_PRIOR_SOURCE') AS reason,h.sample_basis,h.period_scope,h.source_id FROM pop p CROSS JOIN (VALUES (1),(2),(3)) l(lag) CROSS JOIN names n LEFT JOIN history h ON h.source_season=p.target_season-l.lag AND h.player_type=p.player_type AND h.mlbam_id=p.mlbam_id AND h.feature=n.feature WHERE n.family<>'baserunning' OR p.player_type='hitter' '''
  dest=stage/(split+'_leaderboard_features.parquet');db.execute('COPY ('+q+') TO '+lit(dest)+' (FORMAT PARQUET,COMPRESSION ZSTD)')
  db.execute('CREATE OR REPLACE VIEW add_on AS SELECT * FROM read_parquet('+lit(dest)+')')
  for y,role,lag,family,feature,n,available in db.execute('SELECT target_season,player_type,lag,family,feature,count(*),count(value) FROM add_on GROUP BY ALL ORDER BY ALL').fetchall():availability.append(dict(split=split,target_season=y,player_type=role,lag=lag,family=family,feature=feature,population_rows=n,available_rows=available))
  existing=db.execute('SELECT target_season,player_type,mlbam_id FROM pop').fetchall();population.extend(dict(split=split,target_season=y,player_type=role,mlbam_id=pid,source='EXISTING_FROZEN_PRIOR_HISTORY_POPULATION') for y,role,pid in existing)
  if db.execute('SELECT count(*) FROM add_on WHERE source_season>=target_season OR source_season>2025').fetchone()[0]:raise ValueError('Future source entered lag add-on')
 emit(stage/'lag_availability.csv',availability);emit(stage/'frozen_population_audit.csv',population)
 # Supplemental rows outside the old prior-history population stay explicit, not inserted based on target actual participation.
 return availability

def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 config_path=Path(a.config).resolve();cfg=load(config_path)
 if cfg['settings']!=DEFAULT:raise ValueError('Versioned normalization/sample controls changed')
 sources=cfg['sources'];ids=[s['source_id'] for s in sources]
 if len({Path(s['file']).name for s in sources})!=len(sources):raise ValueError('Source snapshot basenames must be unique')
 if not sources or len(ids)!=len(set(ids)):raise ValueError('Missing/duplicate source registry IDs')
 root=Path(a.input_dir).resolve();matrix=Path(a.matrix).resolve();expanded=Path(a.expanded).resolve();watched={str(config_path):sha(config_path)}
 print('Registering supplied CSVs; separating 2026 records from historical features...',flush=True)
 historical,quarantine,issues,inventory,paths,extra=read_sources(sources,root,DEFAULT,sha);watched.update({str(p):sha(p) for p in paths})
 print('Reconciling historical leaderboard measurements with frozen archive summaries...',flush=True)
 reconciled,classic_status=reconcile(historical,expanded,matrix,watched)
 corrected=[];removed=[]
 if 'bat_tracking_field_inventory.csv' in load(expanded/'output_sha256.json'):
  bp=checked(expanded,'bat_tracking_field_inventory.csv',watched)
  with bp.open(encoding='utf-8-sig',newline='') as bf:
   for row in csv.DictReader(bf):
    (removed if row.get('column') in ['bat_score','bat_score_diff','bat_win_exp'] else corrected).append(row)
 out,backups,stage=start(a.output,a.backup_root,[root,matrix,expanded,config_path]);(stage/'historical').mkdir();(stage/'quarantine_2026').mkdir();(stage/'source_snapshots').mkdir()
 try:
  for source,path in zip(sources,paths):
   dest=stage/'source_snapshots'/path.name;shutil.copyfile(path,dest)
   if sha(dest)!=source['expected_sha256']:raise ValueError('Source snapshot differs from registered input')
  for sub,rows in [('historical',historical),('quarantine_2026',quarantine)]:
   write(stage/sub/'leaderboard_features.csv',rows,FIELDS)
   with duckdb.connect() as db:pq(db,stage/sub/'leaderboard_features.csv')
  feature_names=sorted({(s['family'],'savant_'+s['family']+'_'+m,m) for s in sources for m in registry(s['family'])})
  with duckdb.connect() as db:availability=lags(db,stage,matrix,watched,feature_names)
  # Identity coverage uses prior population keys only. Names are retained solely as display/provenance.
  pop={(int(r['target_season']),r['player_type'],str(r['mlbam_id'])) for r in __import__('standalone_io_v1_0').csvrows(stage/'frozen_population_audit.csv')};outside=[]
  for key in sorted({(r['source_season'],r['player_type'],r['mlbam_id'],r['family']) for r in historical}):
   y,role,pid,family=key
   if (y+1,role,pid) not in pop:outside.append(dict(source_season=y,player_type=role,mlbam_id=pid,family=family,status='NOT_IN_FROZEN_NEXT_SEASON_POPULATION_NO_AUTOMATIC_EXPANSION'))
  counts=Counter((r['source_season'],r['player_type'],r['family'],r['metric'],r['reason']) for r in historical)
  for name,rows in [('corrected_bat_tracking_inventory',corrected),('excluded_game_context_inventory_rows',removed),('reconciliation_details',reconciled),('normalization_review',issues),('unmapped_source_columns',extra),('outside_frozen_population',outside),('historical_eligibility_summary',[dict(source_season=y,player_type=role,family=f,metric=m,reason=reason,rows=n) for (y,role,f,m,reason),n in sorted(counts.items())])]:emit(stage/(name+'.csv'),rows)
  rc=Counter((r['source_season'],r['player_type'],r['family'],r['metric'],r['status']) for r in reconciled);emit(stage/'reconciliation_summary.csv',[dict(source_season=y,player_type=role,family=f,metric=m,status=status,rows=n) for (y,role,f,m,status),n in sorted(rc.items())])
  coverage=Counter((r['source_season'],r['player_type'],r['family']) for r in historical+quarantine if r['metric']==registry(r['family'])[0]);emit(stage/'source_coverage.csv',[dict(source_season=y,player_type=role,family=f,player_seasons=n,split='quarantine_2026' if y==2026 else 'historical') for (y,role,f),n in sorted(coverage.items())])
  dump(stage/'source_inventory.json',dict(registered_at=datetime.now(timezone.utc).isoformat(),sources=inventory,filter_policy='Unknown filter settings remain unknown; observed minima do not certify complete scope',source_snapshot_policy='Byte-identical unedited CSVs; combined files contain both historical and quarantined records'))
  dump(stage/'feature_contract.json',dict(version=VERSION,settings=DEFAULT,feature_names=[f for family,f,m in feature_names],join='MLBAM ID + role + source season; no name matching; no target-outcome expansion',yearless_EV='Season explicitly declared in source registry, not guessed during import',rounding='Preserve exported value and count; audit relationships, never replace either reference',bat_tracking='Separate per-contact and per-competitive-swing denominators; partial 2023 scope retained',baserunning='Signed context preserved; all model values masked pending opportunity/definition review; not SB counts',evaluation_2026_policy='Quarantine table is not a historical feature source; no 2027 forecasting or model selection',unavailable_policy='Missing values, missing players and unsupported denominators remain null; no archive/leaderboard substitution',model_policy='Sample eligibility is not era comparability or model approval; no fitting, shrinkage or adopted-source changes'))
  report=dict(version=VERSION,status='SUPPLEMENTAL_FEATURES_IMPORTED_RECONCILIATION_REVIEW_REQUIRED',source_files=len(paths),historical_metric_rows=len(historical),quarantined_2026_metric_rows=len(quarantine),historical_source_seasons=sorted({r['source_season'] for r in historical}),normalization_review_rows=len(issues),historical_normalization_review_rows=sum(r['split']=='historical' for r in issues),reconciliation_rows=len(reconciled),classic_archive_status=classic_status,lag_availability_rows=len(availability),models_fitted=False,accepted_projection_source_modified=False,original_references_modified=False,source_counts_replaced=False,training_labels_read=False,training_uses_2026_data=False,source_2026_rows_read_and_quarantined=True,model_ready=False,inputs_unchanged=True,limitations=['Postseason leaderboard exports retrieved retrospectively; no independent preseason-vintage certification.', 'Official fractions and archive proxies preserve separate definitions and counts; matching is not certification.', 'Combined source snapshots include 2026; only historical normalized tables may feed lag builders.', 'Baserunning values and unsupported metric denominators are preserved for review, not automatically enabled.', 'EV sample eligibility uses exported BBE proxy; actual measurement/subset denominators may differ.', 'Only 2023-2025 supplements feed current add-ons; short/partial bat-tracking history is not long-fold evidence.', 'No new population, forecasts or model choices created.'])
  dump(stage/'leaderboard_build_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(input_dir='data/statcast_leaderboards_v1_21/source_files',config='config/statcast_leaderboards_v1_21.json',matrix='outputs/standalone_lagged_features_v1_0',expanded='outputs/expanded_statcast_v1_20',output='outputs/statcast_leaderboards_v1_21',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
