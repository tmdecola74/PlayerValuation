"""Read-only audit of active Statcast partitions. No network or source writes."""
import argparse
import csv
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import date, timedelta
from pathlib import Path
import duckdb
from statcast_pipeline_v1_0 import config, days, sha, finished_games, ident, lit, verify_dependencies

FIELDS = {
 'pitch': ['release_speed','release_spin_rate','release_extension','release_pos_x','release_pos_z','pfx_x','pfx_z','plate_x','plate_z','sz_top','sz_bot'],
 'contact': ['launch_speed','launch_angle','estimated_ba_using_speedangle','estimated_woba_using_speedangle'],
 'swing': ['bat_speed','swing_length'],
}
SWINGS = ('swinging_strike','swinging_strike_blocked','foul','foul_tip','hit_into_play','foul_bunt','missed_bunt','bunt_foul_tip')

def write_csv(path, rows, headings):
 with path.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=headings);w.writeheader();w.writerows(rows)

def audit(c, output, start=None, end=None, official=None):
 output=Path(output).resolve()
 root=c['_root'].resolve()
 if output==root or root in output.parents:
  raise ValueError('Output must be outside the Statcast source root')
 output.mkdir(parents=True,exist_ok=False)
 ledger_path=root/'download_ledger.sqlite'
 before=sha(ledger_path)
 issues=[]; windows=[]; coverage=[]; seasons=[]; observed=[]
 def issue(day,check,detail):issues.append(dict(day=day,check=check,detail=str(detail)))
 expected=list(days(c,start,end))
 if not expected:raise ValueError('No configured days selected')
 # sqlite mode=ro avoids the initializer in the original active() function.
 with closing(sqlite3.connect(ledger_path.as_uri()+'?mode=ro',uri=True)) as log, duckdb.connect() as db:
  log.row_factory=sqlite3.Row
  indexed={r['day']:dict(r) for r in log.execute('SELECT * FROM windows')}
  db.execute('CREATE TABLE keys(season INTEGER,day VARCHAR,game_pk BIGINT,at_bat_number BIGINT,pitch_number BIGINT,batter BIGINT,pitcher BIGINT,events VARCHAR)')
  for year in sorted({int(d[:4]) for d in expected}):
   print(f'{year}: checking active files, schedule and measurements',flush=True)
   counts=Counter(); valid=Counter(); denominators=Counter(); rows_total=0
   for day in [d for d in expected if int(d[:4])==year]:
    r=indexed.get(day)
    if not r or r['status']!='COMPLETE':issue(day,'window','Missing or incomplete');continue
    try:
     for p,h in [(r['raw_path'],r['raw_hash']),(r['parquet_path'],r['parquet_hash']),(r['schedule_path'],r['schedule_hash'])]:
      if p and (not Path(p).is_file() or sha(p)!=h):raise ValueError('Hash mismatch: '+str(p))
     verify_dependencies(log,day)
     schedule=json.loads(Path(r['schedule_path']).read_text(encoding='utf-8'))
     games=finished_games(schedule)
     expected_games={int(g['gamePk']) for g in games if g.get('officialDate',day)==day}
     path=r['parquet_path']
     if path:
      db.execute('CREATE OR REPLACE VIEW pitches AS SELECT * FROM read_parquet('+lit(path)+')')
      n=db.execute('SELECT count(*) FROM pitches').fetchone()[0]
      cols={v[0] for v in db.execute('DESCRIBE pitches').fetchall()}
      present={v[0] for v in db.execute('SELECT DISTINCT game_pk FROM pitches').fetchall()}
      bad=db.execute("SELECT count(*) FROM pitches WHERE try_cast(game_date AS DATE) IS DISTINCT FROM CAST(? AS DATE) OR game_type IS DISTINCT FROM 'R' OR game_pk IS NULL OR at_bat_number IS NULL OR pitch_number IS NULL OR batter IS NULL OR pitcher IS NULL OR game_pk<=0 OR at_bat_number<=0 OR pitch_number<=0 OR batter<=0 OR pitcher<=0",[day]).fetchone()[0]
      if bad:issue(day,'date_type_keys_ids',bad)
      db.execute('INSERT INTO keys SELECT ?,?,game_pk,at_bat_number,pitch_number,batter,pitcher,events FROM pitches',[year,day])
      for group,fields in FIELDS.items():
       condition='TRUE' if group=='pitch' else ident("type")+"='X'" if group=='contact' else 'description IN ('+','.join(lit(x) for x in SWINGS)+')'
       denom=db.execute('SELECT count(*) FROM pitches WHERE '+condition).fetchone()[0]
       denominators[group]+=denom
       for field in fields:
        if field in cols:
         expr='try_cast('+ident(field)+' AS DOUBLE)'
         value=db.execute('SELECT count(*) FROM pitches WHERE '+condition+' AND '+expr+' IS NOT NULL AND isfinite('+expr+')').fetchone()[0]
         valid[field]+=value
     else:n=0;present=set()
     if n!=r['rows']:issue(day,'row_count',f'{n} != {r["rows"]}')
     if present!=expected_games:issue(day,'game_coverage',f'missing={sorted(expected_games-present)}, extra={sorted(present-expected_games)}')
     rows_total+=n
     counts['empty']+=int(n==0);counts['complete']+=1
     windows.append(dict(day=day,rows=n,expected_local_games=len(expected_games),observed_games=len(present)))
    except Exception as exc:issue(day,'integrity',exc)
   for group,fields in FIELDS.items():
    for field in fields:
     denom=denominators[group];num=valid[field]
     coverage.append(dict(season=year,field=field,denominator_kind=group,eligible_rows=denom,finite_values=num,coverage_fraction=num/denom if denom else None,status='NO_ELIGIBLE_ROWS' if not denom else 'UNAVAILABLE' if not num else 'PARTIAL' if num<denom else 'COMPLETE'))
   dup=db.execute('SELECT count(*),coalesce(sum(n-1),0) FROM (SELECT count(*) n FROM keys WHERE season=? GROUP BY game_pk,at_bat_number,pitch_number HAVING count(*)>1)',[year]).fetchone()
   if dup[0]:issue(str(year),'duplicate_pitch_keys',dict(groups=dup[0],excess_rows=dup[1]))
   changes=db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number FROM keys WHERE season=? GROUP BY ALL HAVING count(DISTINCT batter)>1 OR count(DISTINCT pitcher)>1)',[year]).fetchone()[0]
   seasons.append(dict(season=year,expected_windows=sum(d.startswith(str(year)) for d in expected),verified_windows=counts['complete'],pitch_rows=rows_total,empty_windows=counts['empty'],duplicate_key_groups=dup[0],player_change_pas=changes))
  # Terminal-event attribution is deliberately diagnostic: official scoring can assign
  # inherited counts to an earlier batter/pitcher. Do not silently redistribute them.
  for role,col in [('hitter','batter'),('pitcher','pitcher')]:
   result=db.execute('SELECT season,'+col+",events,count(*) FROM keys WHERE nullif(trim(events),'') IS NOT NULL GROUP BY ALL").fetchall()
   totals=Counter()
   for year,pid,event,n in result:
    if event in ('truncated_pa','pickoff_1b','pickoff_2b','pickoff_3b','caught_stealing_2b','caught_stealing_3b','caught_stealing_home','pickoff_caught_stealing_2b','pickoff_caught_stealing_3b','pickoff_caught_stealing_home','stolen_base_2b','stolen_base_3b','stolen_base_home','other_advance','wild_pitch','passed_ball'):continue
    if event in ('single','double','triple','home_run'):totals[year,role,pid,'H']+=n
    if event=='home_run':totals[year,role,pid,'HR']+=n
    if event in ('walk','intent_walk'):totals[year,role,pid,'BB']+=n
    if event in ('strikeout','strikeout_double_play'):totals[year,role,pid,'SO']+=n
   observed += [dict(season=y,player_type=r,mlbam_id=p,metric=m,value=n) for (y,r,p,m),n in sorted(totals.items())]
 comparisons=[]
 if official:
  lookup={(r['season'],r['player_type'],r['mlbam_id'],r['metric']):r['value'] for r in observed}
  seen=set()
  observed_ids={k[:3] for k in lookup}
  with Path(official).open(encoding='utf-8-sig',newline='') as f:
   for row in csv.DictReader(f):
    key=(int(row['season']),row['player_type'],int(row['mlbam_id']),row['metric'])
    if key[0] not in {r['season'] for r in seasons}:raise ValueError('Reference season outside audit range')
    if key in seen:raise ValueError('Duplicate official key: '+str(key))
    seen.add(key)
    if key[1] not in ('hitter','pitcher') or key[3] not in ('H','HR','BB','SO'):raise ValueError('Unsupported reference role/metric')
    actual=float(row['value'])
    if actual<0 or not actual.is_integer():raise ValueError('Official counts must be nonnegative integers')
    # Absent IDs are unknown, not projected/observed zeros.
    pid_present=key[:3] in observed_ids
    value=lookup.get(key,0) if pid_present else None
    comparisons.append(dict(season=key[0],player_type=key[1],mlbam_id=key[2],metric=key[3],official=actual,terminal_observed=value,difference=value-actual if value is not None else None,status='PLAYER_NOT_OBSERVED' if value is None else 'MATCH' if value==actual else 'REVIEW'))
 write_csv(output/'season_summary.csv',seasons,['season','expected_windows','verified_windows','pitch_rows','empty_windows','duplicate_key_groups','player_change_pas'])
 write_csv(output/'measurement_coverage.csv',coverage,['season','field','denominator_kind','eligible_rows','finite_values','coverage_fraction','status'])
 write_csv(output/'window_checks.csv',windows,['day','rows','expected_local_games','observed_games'])
 write_csv(output/'issues.csv',issues,['day','check','detail'])
 write_csv(output/'terminal_event_counts.csv',observed,['season','player_type','mlbam_id','metric','value'])
 write_csv(output/'official_comparison.csv',comparisons,['season','player_type','mlbam_id','metric','official','terminal_observed','difference','status'])
 unchanged=before==sha(ledger_path)
 report=dict(version='1.0.1',integrity_pass=not issues and unchanged,model_ready=False,official_reconciliation='DIAGNOSTIC_PARTIAL' if official else 'NOT_RUN_REFERENCE_REQUIRED',requested_start=start,requested_end=end,effective_first_day=expected[0],effective_last_day=expected[-1],ledger_unchanged=unchanged,seasons=seasons,issues=len(issues),limitations=['No network calls; schedule coverage uses saved snapshots, not independently refreshed official schedules.','Only active ledger versions scanned; obsolete refresh versions excluded.','Finite-value coverage is not physical plausibility or historical comparability validation.','Contact denominator uses type=X; swing denominator uses listed swing descriptions, not all pitches.','Terminal H/HR/BB/SO diagnostic attribution is not official PA/AB/IP reconciliation; player changes require scoring-aware reconciliation.','No automatic modeling approval. Missing measurements must remain missing; historical era controls and fallback policy still required.','Configured end dates are clipped to yesterday by the ingestion days() function.'])
 (output/'readiness_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='config/statcast_ingestion_v1_0.json');p.add_argument('--start');p.add_argument('--end');p.add_argument('--official-counts');p.add_argument('--output',default='outputs/statcast_readiness_v1_0')
 a=p.parse_args();r=audit(config(a.config),a.output,a.start,a.end,a.official_counts);print(json.dumps(r,indent=2));return 0 if r['integrity_pass'] else 1
if __name__=='__main__':raise SystemExit(main())
