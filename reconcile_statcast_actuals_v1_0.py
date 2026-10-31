"""Compare preserved FanGraphs counts with terminal, rule and MLB-boxscore evidence."""
from __future__ import annotations
import argparse
import csv
import json
import shutil
import sqlite3
from collections import Counter, defaultdict
from contextlib import closing
from pathlib import Path
import duckdb
from actuals_scoring_v1_0 import *
from statcast_pipeline_v1_0 import config, days, verify_dependencies, finished_games


def select_windows(c,start,end):
 expected=list(days(c,start,end))
 if not expected:raise ValueError('No configured days selected')
 path=c['_root']/'download_ledger.sqlite'
 if not path.is_file():raise FileNotFoundError(path)
 with closing(sqlite3.connect(path.resolve().as_uri()+'?mode=ro',uri=True)) as log:
  log.row_factory=sqlite3.Row
  indexed={r['day']:dict(r) for r in log.execute("SELECT * FROM windows WHERE status='COMPLETE'")}
  missing=[d for d in expected if d not in indexed]
  if missing:raise ValueError('Incomplete windows: '+str(missing[:10]))
  selected=[]
  for day in expected:
   r=indexed[day]
   for p,h in [(r['raw_path'],r['raw_hash']),(r['parquet_path'],r['parquet_hash']),(r['schedule_path'],r['schedule_hash'])]:
    if p and (not Path(p).is_file() or sha(p)!=h):raise ValueError('Source hash mismatch: '+str(p))
   verify_dependencies(log,day);selected.append(r)
 return selected


def aggregate(db,role,game=None):
 col='batter' if role=='hitter' else 'pitcher'
 expr={m:'0' for m in SUPPORTED[role]}
 expr.update(H="sum(CASE WHEN events IN ('single','double','triple','home_run') THEN 1 ELSE 0 END)",HR="sum(CASE WHEN events='home_run' THEN 1 ELSE 0 END)",BB="sum(CASE WHEN events IN ('walk','intent_walk') THEN 1 ELSE 0 END)",IBB="sum(CASE WHEN events='intent_walk' THEN 1 ELSE 0 END)",SO="sum(CASE WHEN events IN ('strikeout','strikeout_double_play') THEN 1 ELSE 0 END)",HBP="sum(CASE WHEN events='hit_by_pitch' THEN 1 ELSE 0 END)")
 if role=='pitcher':expr['TBF']='count(*)'
 else:
  expr.update(PA='count(*)',AB="sum(CASE WHEN events NOT IN ('walk','intent_walk','hit_by_pitch','sac_fly','sac_fly_double_play','sac_bunt','sac_bunt_double_play','catcher_interf') THEN 1 ELSE 0 END)")
  for m,events in [('1B',['single']),('2B',['double']),('3B',['triple']),('SF',['sac_fly','sac_fly_double_play']),('SH',['sac_bunt','sac_bunt_double_play'])]:expr[m]='sum(CASE WHEN events IN ('+','.join(lit(e) for e in events)+') THEN 1 ELSE 0 END)'
 where=' WHERE game_pk='+str(int(game)) if game is not None else ''
 cur=db.execute('SELECT '+col+','+','.join(expr[m]+' AS '+ident(m) for m in SUPPORTED[role])+' FROM terminals'+where+' GROUP BY '+col)
 return {int(row[0]):dict(zip(SUPPORTED[role],row[1:])) for row in cur.fetchall()}


def build(actuals,ingestion_config,output,start='2015-03-01',end='2025-11-01',backup_root='backups',feed_cache=None):
 actuals=Path(actuals).resolve();c=config(ingestion_config);ledger_path=c['_root']/'download_ledger.sqlite'
 # A frozen ingestion archive is required while this read-only report runs.
 if (c['_root']/'pipeline.lock').exists():raise ValueError('Ingestion is running; retry when it finishes')
 fingerprints={str(p):sha(p) for p in [actuals/'actual_counts.parquet',actuals/'player_seasons.parquet',Path(ingestion_config).resolve(),ledger_path]}
 print('Verifying registered source versions and file hashes...',flush=True)
 selected=select_windows(c,start,end);years=sorted({int(r['day'][:4]) for r in selected})
 # Reconciliation is evaluation only. No future-season counts are read.
 with duckdb.connect() as ref:
  ylist=','.join(map(str,years))
  refs={(int(y),r,int(mid),m):int(v) for y,r,mid,m,v in ref.execute('SELECT season,player_type,mlbam_id,metric,value FROM read_parquet(?) WHERE season IN ('+ylist+')',[str(actuals/'actual_counts.parquet')]).fetchall()}
  names={(int(y),r,int(mid)):n for y,r,mid,n in ref.execute('SELECT season,player_type,mlbam_id,name FROM read_parquet(?) WHERE season IN ('+ylist+')',[str(actuals/'player_seasons.parquet')]).fetchall()}
 if not refs:raise ValueError('No reference actuals for requested years')
 if any(not any(k[0]==y and k[1]==role for k in refs) for y in years for role in SUPPORTED):raise ValueError('Reference missing a requested year/role')
 out,stage=stage_output(output,[actuals,c['_root'],Path(ingestion_config)],backup_root)
 baseline=Counter();scored=Counter();final=Counter();physical=set();review=set();changes=[];unknown=[];invalid=[];source_games={};observed_games={};rule_totals=Counter();feed_audit=[];mlb_pa_evidence=[];feed_blocks=Counter();change_games=set();player_games=defaultdict(set);conservation=[]
 try:
  dump(stage/'source_windows.json',selected)
  work=stage/'_working.duckdb'
  with duckdb.connect(str(work)) as db:
   db.execute("SET memory_limit='2GB'")
   for year in years:
    windows=[r for r in selected if int(r['day'][:4])==year]
    print(f'{year}: scanning pitches and tracing scoring credit...',flush=True)
    paths=[r['parquet_path'] for r in windows if r['parquet_path'] and r['rows']]
    expected_games=set()
    for w in windows:
     payload=json.loads(Path(w['schedule_path']).read_text(encoding='utf-8'))
     expected_games.update(int(g['gamePk']) for g in finished_games(payload) if g.get('officialDate',w['day'])==w['day'])
    source_games[year]=expected_games
    if not paths:
     observed_games[year]=set();continue
    db.execute('CREATE OR REPLACE TABLE pitches AS SELECT game_pk,at_bat_number,pitch_number,batter,pitcher,balls,strikes,events,game_date,game_type FROM read_parquet(['+','.join(lit(p) for p in paths)+'],union_by_name=true,hive_partitioning=false)')
    n=db.execute('SELECT count(*) FROM pitches').fetchone()[0]
    if n!=sum(r['rows'] for r in windows):raise ValueError('Active Parquet/ledger count mismatch')
    if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM pitches GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Duplicate pitch keys; run readiness audit')
    if db.execute("SELECT count(*) FROM pitches WHERE year(try_cast(game_date AS DATE)) IS DISTINCT FROM ? OR game_type IS DISTINCT FROM 'R' OR batter IS NULL OR pitcher IS NULL OR game_pk IS NULL OR at_bat_number IS NULL OR pitch_number IS NULL OR batter<=0 OR pitcher<=0 OR game_pk<=0 OR at_bat_number<=0 OR pitch_number<=0",[year]).fetchone()[0]:raise ValueError('Invalid Statcast IDs, dates or game type')
    games={int(r[0]) for r in db.execute('SELECT DISTINCT game_pk FROM pitches').fetchall()};observed_games[year]=games
    if games!=expected_games:raise ValueError(f'{year}: saved schedule / Parquet game mismatch')
    if any(g in other for y,other in observed_games.items() if y!=year for g in games):raise ValueError('Game appears in multiple seasons')
    for role,col in [('hitter','batter'),('pitcher','pitcher')]:
     for game,pid in db.execute('SELECT DISTINCT game_pk,'+col+' FROM pitches').fetchall():physical.add((year,role,int(pid)));player_games[year,role,int(pid)].add(int(game))
    event_list=','.join(lit(e) for e in sorted(PA_EVENTS))
    db.execute('CREATE OR REPLACE TABLE pa_quality AS SELECT game_pk,at_bat_number,count(*) FILTER(WHERE events IN ('+event_list+')) AS terminal_count,max(pitch_number) AS last_pitch FROM pitches GROUP BY ALL')
    db.execute('CREATE OR REPLACE TABLE terminals AS SELECT p.* FROM pitches p JOIN pa_quality q USING(game_pk,at_bat_number) WHERE p.events IN ('+event_list+') AND q.terminal_count=1 AND p.pitch_number=q.last_pitch')
    bad=db.execute('SELECT q.game_pk,q.at_bat_number,q.terminal_count FROM pa_quality q WHERE q.terminal_count>1 OR (q.terminal_count=1 AND NOT EXISTS(SELECT 1 FROM terminals t WHERE t.game_pk=q.game_pk AND t.at_bat_number=q.at_bat_number))').fetchall()
    for game,pa,count in bad:invalid.append(dict(season=year,game_pk=game,at_bat_number=pa,reason='Multiple terminals or rows after terminal',terminal_count=count));change_games.add(game)
    known=','.join(lit(e) for e in sorted(PA_EVENTS|NON_PA_EVENTS))
    for e,num in db.execute("SELECT events,count(*) FROM pitches WHERE nullif(trim(events),'') IS NOT NULL AND events NOT IN ("+known+') GROUP BY events').fetchall():unknown.append(dict(season=year,event=e,rows=num))
    game_deltas=Counter()
    for role in SUPPORTED:
     agg=aggregate(db,role)
     for pid in {p for y,r,p in physical if y==year and r==role}:
      for m in SUPPORTED[role]:baseline[year,role,pid,m]=int(agg.get(pid,{}).get(m,0))
    # All changed PAs plus apparently truncated starts for inherited credit.
    db.execute("CREATE OR REPLACE TABLE trace_groups AS SELECT game_pk,at_bat_number FROM pitches GROUP BY ALL HAVING count(DISTINCT batter)>1 OR count(DISTINCT pitcher)>1 OR (first(balls ORDER BY pitch_number) IS DISTINCT FROM 0) OR (first(strikes ORDER BY pitch_number) IS DISTINCT FROM 0) OR min(pitch_number)<>1")
    cur=db.execute('SELECT p.* FROM pitches p JOIN trace_groups USING(game_pk,at_bat_number) ORDER BY p.game_pk,p.at_bat_number,p.pitch_number');fields=[d[0] for d in cur.description];groups=defaultdict(list)
    for row in cur.fetchall():
     data=dict(zip(fields,row));groups[data['game_pk'],data['at_bat_number']].append(data)
    for (game,pa),rows in groups.items():
     is_change=len({r['batter'] for r in rows})>1 or len({r['pitcher'] for r in rows})>1
     if is_change:change_games.add(game)
     terminals=[r for r in rows if r.get('events') in PA_EVENTS]
     if not terminals:
      changes.append(dict(season=year,game_pk=game,at_bat_number=pa,player_change=is_change,status='NONTERMINAL_NO_COUNTS_MOVED',sequence=rows));continue
     decision=credit_pa(rows)
     if decision['status']=='INVALID_TERMINAL_SEQUENCE':
      changes.append(dict(season=year,game_pk=game,at_bat_number=pa,player_change=is_change,**decision,sequence=rows));continue
     last=terminals[0];moves=[]
     for role,col in [('hitter','batter'),('pitcher','pitcher')]:
      participants={int(r[col]) for r in rows}
      if role in decision['unresolved_roles']:
       for pid in participants:review.add((year,role,pid))
       continue
      old=int(last[col]);new=int(decision['owners'][role])
      if old!=new:
       for m,v in event_vector(last['events'],role).items():
        game_deltas[game,role,old,m]-=v;game_deltas[game,role,new,m]+=v
       moves.append(dict(player_type=role,from_mlbam_id=old,to_mlbam_id=new,metrics=event_vector(last['events'],role)))
       rule_totals[role]+=1
     changes.append(dict(season=year,game_pk=game,at_bat_number=pa,event=last['events'],player_change=is_change,terminal_batter=last['batter'],terminal_pitcher=last['pitcher'],**decision,moves=moves,sequence=rows))
    for key,v in baseline.items():
     if key[0]==year:scored[key]=v
    for (game,role,pid,m),v in game_deltas.items():scored[year,role,pid,m]+=v
    for role in SUPPORTED:
     for m in SUPPORTED[role]:
      a=sum(v for (y,r,p,metric),v in baseline.items() if y==year and r==role and metric==m);b=sum(v for (y,r,p,metric),v in scored.items() if y==year and r==role and metric==m)
      if a!=b:raise ValueError('Rule attribution did not conserve '+m)
      conservation.append(dict(season=year,player_type=role,metric=m,terminal_total=a,rule_total=b,pass_check=a==b))
    if any(v<0 for k,v in scored.items() if k[0]==year):raise ValueError('Negative scored count')
    for key,v in scored.items():
     if key[0]==year:final[key]=v
    if feed_cache:
     for game in sorted(games):
      payload=read_cached_feed(feed_cache,game,year)
      if payload is None:continue
      box,blocks,notes=boxscore_counts(payload)
      for trace in changes:
       if trace['game_pk']==game:confirm_trace_from_feed(trace,payload)
      traced={r['at_bat_number'] for r in changes if r['game_pk']==game}
      traced.update(r[0] for r in db.execute("SELECT DISTINCT at_bat_number FROM pitches WHERE game_pk=? AND nullif(trim(events),'') IS NOT NULL AND events NOT IN ("+known+")",[game]).fetchall())
      for play in payload.get('liveData',{}).get('plays',{}).get('allPlays',[]):
       index=play.get('atBatIndex')
       candidate=index+1 if isinstance(index,int) else None
       no_pitch=not play.get('pitchIndex',[]) and play.get('about',{}).get('isComplete',False)
       if candidate in traced or no_pitch:
        mlb_pa_evidence.append(dict(season=year,game_pk=game,candidate_statcast_at_bat_number=candidate,index_link='CANDIDATE_ONLY_NOT_USED_TO_MOVE_CREDIT',no_pitch_completion=no_pitch,mlb_play=play))
      feed_audit.append(dict(season=year,game_pk=game,admitted_blocks=len(blocks),not_admitted=notes,feed_sha256=sha(Path(feed_cache)/str(game)/'feed.json')))
      for role in SUPPORTED:
       local=aggregate(db,role,game)
       participants={int(p[0]) for p in db.execute('SELECT DISTINCT '+('batter' if role=='hitter' else 'pitcher')+' FROM pitches WHERE game_pk=?',[game]).fetchall()}
       for r,m in blocks:
        if r!=role:continue
        feed_blocks[year,role,m]+=1
        for pid in participants:
         previous=local.get(pid,{}).get(m,0)+game_deltas[game,role,pid,m] if m in SUPPORTED[role] else 0
         final[year,role,pid,m]-=previous
        for (r,pid,metric),v in box.items():
         if r==role and metric==m:final[year,role,pid,m]+=v
      # Feed-player presence does not manufacture physical pitch observations.
    print(f'{year}: {n:,} pitches; {len(games):,} games; {sum(r["season"]==year and r.get("player_change",False) for r in changes)} changed PAs',flush=True)
   db.execute('CHECKPOINT')
  work.unlink()
  for p in stage.glob('_working.duckdb*'):
   if p.is_file():p.unlink()
  review={(t['season'],role,int(p['batter' if role=='hitter' else 'pitcher'])) for t in changes for role in t.get('unresolved_roles',[]) for p in t['sequence']}
  compared=[];status_counts=Counter();review_players=set()
  domain=season_comparison_domain(refs,baseline)
  evidence_only=[dict(season=y,player_type=role,mlbam_id=pid,metric=m,partial_mlb_count=final[y,role,pid,m],statcast_player_observed=(y,role,pid) in physical,status='PARTIAL_MLB_METRIC_OUTSIDE_SEASON_COMPARISON_DOMAIN') for y,role,pid,m in sorted(set(final)-domain)]
  csv_out(stage/'mlb_evidence_only.csv',evidence_only,['season','player_type','mlbam_id','metric','partial_mlb_count','statcast_player_observed','status'])
  for key in sorted(domain):
   y,role,pid,m=key
   if m not in ALL_METRICS[role]:continue
   reference=refs.get(key);present=(y,role,pid) in physical
   raw=baseline.get(key,0) if present and m in SUPPORTED[role] else None
   rule=scored.get(key,0) if present and m in SUPPORTED[role] else None
   full_feed=bool(source_games.get(y)) and feed_blocks[y,role,m]==len(source_games[y])
   usable=m in SUPPORTED[role] or full_feed
   value=final.get(key,0) if usable and (present or key in final or full_feed) else None
   # Partially fetched games do not establish a full-season count for unseen IDs.
   if not present and not full_feed:value=None
   if reference is None:status='NO_FANGRAPHS_REFERENCE'
   elif not usable:status='NOT_RECONSTRUCTED_FULL_GAME_EVIDENCE_REQUIRED'
   elif value is None:status='NO_STATCAST_PLAYER_OBSERVATION'
   elif value!=reference:status='UNRESOLVED_DIFFERENCE'
   elif full_feed or (value!=rule):status='MATCH_AFTER_MLB_GAME_EVIDENCE'
   elif rule!=raw:status='EXPLAINED_BY_SCORING_RULES'
   elif (y,role,pid) in review:status='MATCH_WITH_SEQUENCE_REVIEW'
   else:status='EXACT_TERMINAL_MATCH'
   if status in {'UNRESOLVED_DIFFERENCE','NO_STATCAST_PLAYER_OBSERVATION','NO_FANGRAPHS_REFERENCE','MATCH_WITH_SEQUENCE_REVIEW'}:review_players.add((y,role,pid))
   status_counts[y,role,status]+=1
   compared.append(dict(season=y,player_type=role,mlbam_id=pid,name=names.get((y,role,pid),''),metric=m,fangraphs_actual=reference,terminal_count=raw,rule_count=rule,evidence_count=value,partial_boxscore_count=final.get(key) if not usable and key in final else None,terminal_difference=raw-reference if raw is not None and reference is not None else None,rule_difference=rule-reference if rule is not None and reference is not None else None,final_difference=value-reference if value is not None and reference is not None else None,status=status,sequence_review=(y,role,pid) in review,mlb_full_game_metric_coverage=f'{feed_blocks[y,role,m]}/{len(source_games.get(y,()))}'))
  csv_out(stage/'player_metric_reconciliation.csv',compared,['season','player_type','mlbam_id','name','metric','fangraphs_actual','terminal_count','rule_count','evidence_count','partial_boxscore_count','terminal_difference','rule_difference','final_difference','status','sequence_review','mlb_full_game_metric_coverage'])
  discrepancies=[r for r in compared if r['status'] in {'UNRESOLVED_DIFFERENCE','NO_STATCAST_PLAYER_OBSERVATION','NO_FANGRAPHS_REFERENCE','MATCH_WITH_SEQUENCE_REVIEW'}]
  csv_out(stage/'discrepancies.csv',discrepancies,list(compared[0]) if compared else ['season'])
  reference_players={k[:3] for k in refs}
  identity_rows=[dict(season=y,player_type=r,mlbam_id=p,name=names.get((y,r,p),''),fangraphs_present=(y,r,p) in reference_players,statcast_present=(y,r,p) in physical,status='BOTH_SOURCES' if (y,r,p) in reference_players and (y,r,p) in physical else 'MISSING_FANGRAPHS_REFERENCE' if (y,r,p) in physical else 'NO_STATCAST_PITCH_OBSERVATION') for y,r,p in sorted(reference_players|physical)]
  csv_out(stage/'reference_player_coverage.csv',identity_rows,['season','player_type','mlbam_id','name','fangraphs_present','statcast_present','status'])
  csv_out(stage/'scoring_conservation.csv',conservation,['season','player_type','metric','terminal_total','rule_total','pass_check'])
  csv_out(stage/'unknown_events.csv',unknown,['season','event','rows'])
  csv_out(stage/'invalid_pa_sequences.csv',invalid,['season','game_pk','at_bat_number','reason','terminal_count'])
  with (stage/'pa_scoring_trace.jsonl').open('w',encoding='utf-8') as f:
   for row in changes:f.write(json.dumps(row,allow_nan=False)+'\n')
  links=[]
  for row in changes:
   for role,col in [('hitter','batter'),('pitcher','pitcher')]:
    for pid in {int(p[col]) for p in row['sequence']}:
     if (row['season'],role,pid) in review_players:links.append(dict(season=row['season'],player_type=role,mlbam_id=pid,game_pk=row['game_pk'],at_bat_number=row['at_bat_number'],trace_status=row['status']))
  csv_out(stage/'discrepancy_pa_links.csv',links,['season','player_type','mlbam_id','game_pk','at_bat_number','trace_status'])
  review_games=set(change_games)
  for key in review_players:review_games.update(player_games.get(key,set()))
  plan=[dict(season=y,game_pk=g,priority='PLAYER_CHANGE_OR_INVALID_PA' if g in change_games else 'PLAYER_SEASON_DIFFERENCE' if g in review_games else 'FULL_COVERAGE_ONLY',url=f'https://statsapi.mlb.com/api/v1.1/game/{g}/feed/live') for y,games in source_games.items() for g in sorted(games)]
  csv_out(stage/'game_fetch_plan.csv',plan,['season','game_pk','priority','url'])
  dump(stage/'mlb_feed_usage.json',feed_audit)
  with (stage/'mlb_pa_evidence.jsonl').open('w',encoding='utf-8') as f:
   for row in mlb_pa_evidence:f.write(json.dumps(row,allow_nan=False)+'\n')
  summary=[dict(season=y,player_type=r,status=s,metric_rows=n) for (y,r,s),n in sorted(status_counts.items())]
  csv_out(stage/'reconciliation_summary.csv',summary,['season','player_type','status','metric_rows'])
  unchanged=all(sha(p)==h for p,h in fingerprints.items())
  if not unchanged:raise ValueError('An input changed during reconciliation')
  report=dict(version=VERSION,built_at=now(),status='RECONCILIATION_REVIEW_REQUIRED' if discrepancies or unknown or invalid or review else 'SUPPORTED_COUNTS_RECONCILED',model_ready=False,reference='Retrospective user-supplied FanGraphs actuals',effective_first_day=selected[0]['day'],effective_last_day=selected[-1]['day'],seasons=years,windows=len(selected),pitch_rows=sum(r['rows'] for r in selected),player_change_pas=sum(r.get('player_change',False) for r in changes),rule_credit_moves=dict(rule_totals),trace_rows=len(changes),unresolved_sequence_player_seasons=len(review),unknown_event_types=len(unknown),invalid_pa_sequences=len(invalid),discrepancy_metric_rows=len(discrepancies),not_reconstructed_metric_rows=sum(r['status']=='NOT_RECONSTRUCTED_FULL_GAME_EVIDENCE_REQUIRED' for r in compared),cached_mlb_games_used=len(feed_audit),evidence_confirmed_pa_sequences=sum('mlb_scoring_confirmation' in t for t in changes),mlb_evidence_only_metric_rows=len(evidence_only),planned_evidence_games=len(plan),priority_change_games=sum(r['priority']=='PLAYER_CHANGE_OR_INVALID_PA' for r in plan),inputs_unchanged=True,input_sha256=fingerprints,summary=summary,limitations=['Hitter PA/AB and listed terminal outcomes are reconstructed; known runner-only events and truncated PAs do not count as PAs. Unknown events remain review cases.','OBR 9.15(b) and 9.16(h) are applied only where observed substitution counts support unambiguous credit. Multiple relevant substitutions and incomplete starts require evidence.','Physical pitch ownership and original FanGraphs counts are never rewritten. No aggregate-difference-driven reassignment.','Pitching OUTS/IP, ER/R and other nonterminal statistics require complete validated MLB game evidence for each season/metric; they are never inferred from inning-end assumptions.','A zero is used only for supported metrics of observed participants or complete admitted game evidence; absent players remain unknown.','Partial MLB cache coverage does not certify non-reconstructed season totals.','Season coverage uses registered saved regular-season schedules; no independent current schedule census. FanGraphs snapshots may differ from later scoring revisions.','FanGraphs season Age is retained; it is not an independently verified birth date.','Actuals for years outside the selected reconciliation range are not loaded. This tool does not train or approve a model.'])
  dump(stage/'reconciliation_report.json',report)
  backup=finish_output(stage,out,backup_root)
  return report|{'output':str(out),'backup':backup}
 except BaseException:
  shutil.rmtree(stage,ignore_errors=True);raise


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--actuals',default='data/actuals_reference_v1_0');p.add_argument('--config',default='config/statcast_ingestion_v1_0.json');p.add_argument('--start',default='2015-03-01');p.add_argument('--end',default='2025-11-01');p.add_argument('--output',default='outputs/actuals_statcast_reconciliation_v1_0');p.add_argument('--backup-root',default='backups');p.add_argument('--mlb-feed-cache')
 a=p.parse_args();print(json.dumps(build(a.actuals,a.config,a.output,a.start,a.end,a.backup_root,a.mlb_feed_cache),indent=2))
if __name__=='__main__':main()
