"""Audit compatible categorical BBE history before any forecast-error scoring."""
import os
os.environ['OMP_NUM_THREADS']='1'
import csv,json,sqlite3,hashlib,sys
from pathlib import Path
from collections import Counter,defaultdict
from datetime import date,timedelta
import duckdb
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');O=Path('outputs/2027_statcast_strengthened_validation');O.mkdir(exist_ok=True)
sys.path.insert(0,str(R))
from statcast_pipeline_v1_0 import is_completed_regular_game
PREV=Path('outputs/2027_v1_43_statcast_challenger')
CONTRACT={'version':'STATCAST_COMPATIBILITY_EXTENSION_0.1','registered_before_reconstruction_or_model_scoring':True,'source_years':[2021,2022,2023,2024,2025,2026],'features':['gb_rate','ld_rate','fb_rate'],'unchanged_recipe':json.loads((PREV/'experiment_contract.json').read_text()),'allowed_change':'Add earlier compatible source observations and apply independently specified scope masks, increasing earlier training/scoring years. No changes to target components, pooling, ridge penalty, damping, caps, baseline or adoption thresholds.','older_definition':'Use actual bb_type categorical counts on regular-season type=X physical in-play records, divided by ALL in-play BBE. Require every in-play record classified as ground_ball/line_drive/fly_ball/popup and total BBE>=30. No angle threshold or direction proxy.','compatibility_bridge':'Before admitting 2021/2022 require deterministic all-BBE category fractions and BBE denominator to match every formerly admitted 2023-2025 research bundle against archived pitches. Any mismatch is held and prevents declaring an unconditional bridge.','2026_scope':'Check every 2026 batted-ball export row against the season archive, including exact all-BBE denominator, categorical numerators, regular-season/game identity and missing classification. Admit only matching row bundles with existing masks and BBE>=30. Never fix counts by substitution.','rate_tolerance':1e-8,'archive_integrity':'Read frozen windows for2021-2025; use COMPLETE ledger windows for2026. Verify all raw/parquet/schedule hashes and row counts. Unique physical pitch keys, no multiple type=X per PA. Check archive game IDs against cached, previously certified full-season MLB schedules and standings.','schedule_scope':'Final regular-season games only; cancelled/postponed entries not performance outcomes. Scope proof is retrospective as of preserved source snapshots.','2026_performance_usage':'Audit/2027 source history only. No 2026 target, residual, forecast error, tuning or fold is allowed.','publication':'Working v1.43 baseline immutable. Candidate must pass unchanged role guards before player-level adoption review. No automatic production installation.','documentation_url':'https://baseballsavant.mlb.com/csv-docs','documentation_basis':'MLB documents type X as in play and bb_type as the four named classes; no release-position or ABS measurement enters these fractions.'}
(O/'audit_contract.json').write_text(json.dumps(CONTRACT,indent=2))
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(4*1048576),b''):h.update(b)
 return h.hexdigest()
watch={str(PREV/'experiment_contract.json'):sha(PREV/'experiment_contract.json'),str(R/'statcast_pipeline_v1_0.py'):sha(R/'statcast_pipeline_v1_0.py')};manifest=R/'outputs/standalone_lagged_features_v1_0/source_windows.json';watch[str(manifest)]=sha(manifest);frozen=json.loads(manifest.read_text())
ledger=R/'data/statcast_v1_0/download_ledger.sqlite'
with sqlite3.connect(ledger.as_uri()+'?mode=ro',uri=True) as db:
 db.row_factory=sqlite3.Row;latest=[dict(r) for r in db.execute("SELECT * FROM windows WHERE day>='2026-01-01' AND day<'2027-01-01' ORDER BY day")]
windows=[r for r in frozen if 2021<=int(r['day'][:4])<=2025]+latest
assert len({r['day'] for r in windows})==len(windows)
window_summary=[];counts=[];schedule_audit=[];sourcefiles=[]
for year in range(2021,2027):
 ww=[r for r in windows if int(r['day'][:4])==year];assert ww and all(r['status']=='COMPLETE' for r in ww)
 days={r['day'] for r in ww};lo=min(days);hi=max(days);d=date.fromisoformat(lo);expected=set()
 while d<=date.fromisoformat(hi):expected.add(d.isoformat());d+=timedelta(days=1)
 assert days==expected,'Internal missing day'
 for i,r in enumerate(ww):
  for stem in ['raw','parquet','schedule']:
   p=Path(r[stem+'_path']);h=r[stem+'_hash'];assert sha(p)==h,(year,r['day'],stem);watch[str(p)]=h
  sourcefiles.append(dict(year=year,**r))
 print('Verified file hashes for',year,flush=True)
 paths=[r['parquet_path'] for r in ww if int(r['rows'])>0]
 with duckdb.connect() as db:
  db.execute("SET threads=2");db.execute("SET memory_limit='768MB'")
  db.read_parquet(paths,union_by_name=True,hive_partitioning=False).create_view('raw')
  cols={r[0] for r in db.execute('DESCRIBE raw').fetchall()};assert {'game_pk','at_bat_number','pitch_number','game_date','game_type','type','bb_type','batter','pitcher'}<=cols
  assert db.execute("SELECT count(*) FROM raw WHERE game_type IS DISTINCT FROM 'R' OR year(CAST(game_date AS DATE))<>?",[year]).fetchone()[0]==0
  assert db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM raw GROUP BY ALL HAVING count(*)>1)').fetchone()[0]==0
  assert db.execute("SELECT count(*) FROM (SELECT game_pk,at_bat_number FROM raw WHERE type='X' GROUP BY ALL HAVING count(*)>1)").fetchone()[0]==0
  assert db.execute('SELECT count(*) FROM raw WHERE batter IS NULL OR pitcher IS NULL OR game_pk IS NULL OR at_bat_number IS NULL OR pitch_number IS NULL').fetchone()[0]==0
  actualrows=db.execute('SELECT count(*) FROM raw').fetchone()[0];assert actualrows==sum(int(r['rows']) for r in ww)
  dates={str(d):n for d,n in db.execute('SELECT CAST(game_date AS DATE),count(*) FROM raw GROUP BY 1').fetchall()};assert dates=={r['day']:int(r['rows']) for r in ww if int(r['rows'])>0}
  games={int(r[0]) for r in db.execute('SELECT DISTINCT game_pk FROM raw').fetchall()}
  # Cached MLB season schedules have separate certified input bindings, verified here.
  certdir=R/('outputs/pitcher_evaluation_v1_29' if year==2026 else f'outputs/pitcher_label_coverage_{year}_v1_26_1')
  if year==2023:certdir=R/'outputs/pitcher_label_coverage_2023_corrected'
  inp=json.loads((certdir/'input_hashes.json').read_text());watch[str(certdir/'input_hashes.json')]=sha(certdir/'input_hashes.json')
  sched=R/f'cache/pitcher_appearance_mlb/{year}/schedule.json';stand=R/f'cache/pitcher_appearance_mlb/{year}/standings.json'
  for p in [sched,stand]:assert sha(p)==inp[str(p)];watch[str(p)]=sha(p)
  sj=json.loads(sched.read_text());ss=json.loads(stand.read_text());sj=sj.get('payload',sj);ss=ss.get('payload',ss);gs={}
  for dd in sj['dates']:
   for g in dd.get('games',[]):
    if is_completed_regular_game(g):gs[int(g['gamePk'])]=g
  missing=sorted(set(gs)-games);extra=sorted(games-set(gs));assert not missing and not extra,(year,len(missing),len(extra))
  teamgames=Counter()
  for g in gs.values():
   for team in ['home','away']:teamgames[g['teams'][team]['team']['id']]+=1
  official={int(t['team']['id']):int(t['gamesPlayed']) for league in ss['records'] for t in league['teamRecords']}
  assert dict(teamgames)==official,(year,'Standings season game count differs')
  schedule_audit.append(dict(year=year,archive_games=len(games),schedule_final_regular_games=len(gs),missing_games=0,extra_games=0,standings_team_count=len(official),team_game_counts_match=True,schedule_file=str(sched),schedule_sha256=sha(sched)))
  db.execute("CREATE TEMP TABLE inplay AS SELECT game_pk,at_bat_number,pitch_number,batter,pitcher,bb_type FROM raw WHERE type='X'")
  for role,col in [('hitter','batter'),('pitcher','pitcher')]:
   for pid,total,gb,ld,fb,pu,unknown in db.execute(f"SELECT CAST({col} AS BIGINT),count(*),count(*) FILTER(WHERE bb_type='ground_ball'),count(*) FILTER(WHERE bb_type='line_drive'),count(*) FILTER(WHERE bb_type='fly_ball'),count(*) FILTER(WHERE bb_type='popup'),count(*) FILTER(WHERE bb_type IS NULL OR bb_type NOT IN ('ground_ball','line_drive','fly_ball','popup')) FROM inplay GROUP BY 1").fetchall():
    counts.append(dict(year=year,role=role,mlbam_id=str(pid),BBE=total,ground_ball=gb,line_drive=ld,fly_ball=fb,popup=pu,unclassified=unknown,gb_rate=gb/total,ld_rate=ld/total,fb_rate=fb/total,pu_rate=pu/total,eligible_archive_bundle=total>=30 and unknown==0,definition='CATEGORY_COUNT_OVER_ALL_TYPE_X_INPLAY_BBE',source_permission='COMPATIBILITY_CHECK_PENDING'))
  window_summary.append(dict(year=year,windows=len(ww),first_day=lo,last_day=hi,pitch_rows=actualrows,regular_games=len(games),inplay_BBE=db.execute('SELECT count(*) FROM inplay').fetchone()[0],empty_windows=sum(int(r['rows'])==0 for r in ww),all_hashes_verified=True,all_scheduled_regular_games_present=True))
 print('Audited archive year',year,'pitches',actualrows,'games',len(games),flush=True)
save('archive_window_inventory.csv',sourcefiles);save('archive_season_inventory.csv',window_summary);save('archive_batted_ball_counts.csv',counts);save('schedule_scope_verification.csv',schedule_audit)
# Compare deterministic reconstructed features with every saved export row in all overlap years.
bank={(r['year'],r['role'],r['mlbam_id']):r for r in counts};board=R/'outputs/statcast_leaderboards_v1_21';oldadmit={(int(r['season']),r['role'],r['mlbam_id']) for r in read(PREV/'statcast_source_bundle_audit.csv') if r['status']=='RESEARCH_COMPLETE'}
comparisons=[];admitted=[];excluded=[]
for role,filename in [('hitter','hitter_batted-ball2023-2026_min1.csv'),('pitcher','pitcher_batted-ball2023-2026.csv')]:
 p=board/'source_snapshots'/filename;watch[str(p)]=sha(p)
 for line,r in enumerate(read(p),2):
  y=int(r['year']);pid=r['id'];ar=bank.get((y,role,pid));reasons=[];bbe=int(r['bbe']);values={m:float(r[m]) for m in ['gb_rate','ld_rate','fb_rate','pu_rate']}
  if ar is None:reasons.append('NO_ARCHIVE_INPLAY_FOR_EXPORTED_PLAYER')
  else:
   if bbe!=ar['BBE']:reasons.append('BBE_DENOMINATOR_MISMATCH')
   if ar['unclassified']:reasons.append('UNCLASSIFIED_ARCHIVE_INPLAY')
   for m in ['gb_rate','ld_rate','fb_rate','pu_rate']:
    if abs(values[m]-ar[m])>1e-8:reasons.append('RATE_MISMATCH_'+m)
  if bbe<30:reasons.append('BELOW_30_BBE')
  if any(not 0<=v<=1 for v in values.values()) or abs(sum(values.values())-1)>.0005001:reasons.append('SOURCE_RANGE_OR_SUM_MASK')
  row=dict(year=y,role=role,mlbam_id=pid,name=r['name'],export_BBE=bbe,archive_BBE=ar['BBE'] if ar else None,unclassified=ar['unclassified'] if ar else None,old_research_admitted=(y,role,pid) in oldadmit,exact_category_and_denominator_match=bool(ar and bbe==ar['BBE'] and not ar['unclassified'] and all(abs(values[m]-ar[m])<=1e-8 for m in values)),new_source_eligible=not reasons,reasons=';'.join(reasons),source_file=str(p),source_row=line)
  for m,v in values.items():row['export_'+m]=v;row['archive_'+m]=ar[m] if ar else None
  comparisons.append(row)
bridge=[r for r in comparisons if r['year']<2026 and r['old_research_admitted']];bridge_bad=[r for r in bridge if not r['exact_category_and_denominator_match']]
bridge_pass=bool(bridge) and not bridge_bad
for row in counts:
 if row['year'] in [2021,2022]:
  if row['eligible_archive_bundle'] and bridge_pass:
   row['source_permission']='COMPATIBLE_ARCHIVE_HISTORY';admitted.append(dict(source_season=row['year'],player_type=row['role'],mlbam_id=row['mlbam_id'],BBE=row['BBE'],gb_rate=row['gb_rate'],ld_rate=row['ld_rate'],fb_rate=row['fb_rate'],pu_rate=row['pu_rate'],source='HASH_VERIFIED_CATEGORICAL_ARCHIVE',scope_status='ALL_BBE_CLASSIFIED; OVERLAP_BRIDGE_PASS'))
  else:excluded.append(dict(year=row['year'],role=row['role'],mlbam_id=row['mlbam_id'],reason='BRIDGE_UNPROVEN' if not bridge_pass else 'SMALL_SAMPLE_OR_UNCLASSIFIED_BBE',BBE=row['BBE']))
for r in comparisons:
 if r['year']==2026 and not r['new_source_eligible']:excluded.append(dict(year=2026,role=r['role'],mlbam_id=r['mlbam_id'],reason=r['reasons'],BBE=r['export_BBE']))
save('archive_batted_ball_counts.csv',counts);save('export_archive_scope_comparison.csv',comparisons);save('compatible_2021_2022_features.csv',admitted);save('source_exclusions.csv',excluded)
summary=dict(bridge_passed=bridge_pass,prior_admitted_historical_bundles_compared=len(bridge),prior_admitted_bridge_mismatches=len(bridge_bad),older_compatible_bundles=len(admitted),scope_2026=dict(Counter('ELIGIBLE_MATCH' if r['new_source_eligible'] else 'EXCLUDED' for r in comparisons if r['year']==2026)),scope_2026_exact_matches=sum(r['year']==2026 and r['exact_category_and_denominator_match'] for r in comparisons),archive_years=window_summary)
summary['2026_forecast_errors_read']=False
(O/'source_scope_summary.json').write_text(json.dumps(summary,indent=2));(O/'source_manifest.json').write_text(json.dumps(watch,indent=2));print(json.dumps(summary,indent=2))
