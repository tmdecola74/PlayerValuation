"""Resumable daily regular-season Statcast ingestion; immutable Parquet versions."""
from pathlib import Path
from datetime import date,datetime,timedelta,timezone
from contextlib import closing,contextmanager
import argparse,csv,hashlib,json,os,sqlite3,time,uuid
from urllib.request import Request,urlopen
from urllib.parse import urlencode
import duckdb

VERSION='1.0.2'
KEYS=['game_pk','at_bat_number','pitch_number']
INTS=KEYS+['batter','pitcher','inning','outs_when_up','balls','strikes','on_1b','on_2b','on_3b','zone','launch_speed_angle','home_score','away_score','post_home_score','post_away_score','fielder_2']
FLOATS=['release_speed','release_spin_rate','release_extension','release_pos_x','release_pos_z','pfx_x','pfx_z','plate_x','plate_z','sz_top','sz_bot','launch_speed','launch_angle','estimated_ba_using_speedangle','estimated_woba_using_speedangle','woba_value','woba_denom','delta_run_exp','bat_speed','swing_length']
TEXT=['game_date','game_type','pitch_type','description','events','type','bb_type','stand','p_throws','home_team','away_team','inning_topbot','player_name']
REQUIRED=KEYS+['game_date','game_type','batter','pitcher','description','events','type','home_team','away_team','inning_topbot']

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def lit(v):return "'"+str(v).replace("'","''")+"'"
def ident(v):return '"'+str(v).replace('"','""')+'"'
def now():return datetime.now(timezone.utc).isoformat()
def config(path):
 p=Path(path).resolve();c=json.loads(p.read_text(encoding='utf-8'));c['_project']=p.parent.parent
 r=Path(c['root']);c['_root']=r if r.is_absolute() else c['_project']/r
 return c

def days(c,start=None,end=None):
 for season in sorted(c['seasons'],key=lambda s:s['season']):
  a=date.fromisoformat(season['start']);b=date.fromisoformat(season['end'])
  if a.year!=season['season'] or b.year!=season['season']:raise ValueError('Season windows must remain within calendar year')
  if start:a=max(a,date.fromisoformat(start))
  if end:b=min(b,date.fromisoformat(end))
  b=min(b,date.today()-timedelta(days=1))
  while a<=b:yield a.isoformat();a+=timedelta(days=1)

@contextmanager
def lock(root):
 root.mkdir(parents=True,exist_ok=True);p=root/'pipeline.lock'
 fd=os.open(p,os.O_CREAT|os.O_EXCL|os.O_WRONLY)
 try:
  os.write(fd,json.dumps({'pid':os.getpid(),'created_at':now()}).encode());os.close(fd);fd=None
  yield
 finally:
  if fd is not None:os.close(fd)
  p.unlink(missing_ok=True)

def ledger(c):
 p=c['_root']/'download_ledger.sqlite'
 con=sqlite3.connect(p)
 con.execute('''CREATE TABLE IF NOT EXISTS windows(day TEXT PRIMARY KEY,status TEXT,run_id TEXT,raw_path TEXT,raw_hash TEXT,parquet_path TEXT,parquet_hash TEXT,rows INTEGER,source_rows INTEGER,exact_duplicates INTEGER,schedule_path TEXT,schedule_hash TEXT,available_at TEXT,url TEXT,error TEXT,version TEXT)''')
 con.execute('CREATE TABLE IF NOT EXISTS window_dependencies(day TEXT,game_pk INTEGER,source_day TEXT,source_run_id TEXT,PRIMARY KEY(day,game_pk))')
 con.commit();return con

def request_bytes(url,timeout=120,max_bytes=268435456):
 req=Request(url,headers={'User-Agent':'PlayerValuation/1.0 (historical baseball research)','Accept':'text/csv,application/json'})
 with urlopen(req,timeout=timeout) as response:
  chunks=[];size=0
  while True:
   b=response.read(1024*1024)
   if not b:break
   size+=len(b)
   if size>max_bytes:raise ValueError('Response exceeds configured byte limit')
   chunks.append(b)
  return b''.join(chunks)

def retry(url,c,fetch):
 error=None
 for attempt in range(c.get('attempts',3)):
  try:return fetch(url,timeout=c.get('timeout_seconds',120),max_bytes=c.get('max_response_bytes',268435456))
  except Exception as exc:
   error=exc
   if attempt+1<c.get('attempts',3):time.sleep(min(30,c.get('retry_seconds',3)*2**attempt))
 raise error

def urls(day):
 savant='https://baseballsavant.mlb.com/statcast_search/csv?'+urlencode({'all':'true','type':'details','player_type':'pitcher','hfGT':'R|','game_date_gt':day,'game_date_lt':day,'group_by':'name','sort_col':'pitches','sort_order':'desc','min_pitches':0,'min_results':0,'min_abs':0})
 schedule='https://statsapi.mlb.com/api/v1/schedule?'+urlencode({'sportId':1,'date':day,'gameTypes':'R'})
 return savant,schedule

def is_completed_regular_game(game):
 status=game.get('status',{})
 detail=str(status.get('detailedState','')).strip().lower()
 if game.get('gameType')!='R' or status.get('abstractGameState')!='Final':return False
 # MLB can report postponed/cancelled entries as abstract Final. They are not played games.
 if any(word in detail for word in ('postpon','cancel','suspend','delay','forfeit')):return False
 code=str(status.get('codedGameState','')).upper()
 if detail:
  if not (detail.startswith('final') or detail.startswith('completed early') or detail=='game over'):return False
 elif code and code not in ('F','O'):return False
 # A completed played game must have scores; this also guards sparse terminal schedule entries.
 teams=game.get('teams',{})
 return all(teams.get(side,{}).get('score') is not None for side in ('home','away'))

def finished_games(schedule):
 result={}
 for d in schedule.get('dates',[]):
  for game in d.get('games',[]):
   if is_completed_regular_game(game):result[int(game['gamePk'])]=game
 return list(result.values())

def verify_dependency(log,source_day,game_pk,source_run_id=None):
 row=log.execute("SELECT run_id,raw_path,raw_hash,parquet_path,parquet_hash,schedule_path,schedule_hash FROM windows WHERE day=? AND status='COMPLETE'",[source_day]).fetchone()
 if not row or (source_run_id is not None and row[0]!=source_run_id):
  raise ValueError('Cross-date source missing or refreshed; download source then refresh dependent day: '+source_day)
 for path,h in [(row[1],row[2]),(row[3],row[4]),(row[5],row[6])]:
  if path and (not Path(path).is_file() or sha(path)!=h):raise ValueError('Cross-date source hash mismatch: '+source_day)
 if not row[3]:raise ValueError('Cross-date source has no pitches: '+source_day)
 with duckdb.connect() as db:
  count=db.execute('SELECT count(*) FROM read_parquet(?) WHERE game_pk=? AND game_date=?',[row[3],game_pk,source_day]).fetchone()[0]
 if not count:raise ValueError('Cross-date game absent from verified source: '+str(game_pk))
 return {'game_pk':game_pk,'source_day':source_day,'source_run_id':row[0],'pitch_rows':count}

def verify_dependencies(log,day):
 for game_pk,source_day,run in log.execute('SELECT game_pk,source_day,source_run_id FROM window_dependencies WHERE day=?',[day]).fetchall():
  verify_dependency(log,source_day,game_pk,run)

def excluded_terminal_games(schedule):
 return [{'game_pk':g.get('gamePk'),'detailed_state':g.get('status',{}).get('detailedState'),'coded_state':g.get('status',{}).get('codedGameState')} for d in schedule.get('dates',[]) for g in d.get('games',[]) if g.get('gameType')=='R' and g.get('status',{}).get('abstractGameState')=='Final' and not is_completed_regular_game(g)]

def ingest_csv(raw,day,expected,out):
 # All unknown columns retained as strings; canonical numeric fields typed explicitly.
 with raw.open(encoding='utf-8-sig',newline='') as f:
  headers=next(csv.reader(f),[])
 if not headers:
  if expected:raise ValueError('Empty response despite completed games')
  return {'rows':0,'source_rows':0,'exact_duplicates':0,'missing_columns':[]}
 if len(headers)!=len(set(headers)):raise ValueError('Duplicate CSV headings')
 if not set(REQUIRED)<=set(headers):raise ValueError('Missing required headings / non-CSV response: '+str(sorted(set(REQUIRED)-set(headers))))
 with duckdb.connect() as db:
  db.execute('CREATE TABLE raw AS SELECT * FROM read_csv('+lit(raw.as_posix())+',header=true,all_varchar=true,strict_mode=true)')
  n=db.execute('SELECT count(*) FROM raw').fetchone()[0]
  if n>=30000:raise ValueError('Daily result may be truncated (>=30,000 rows)')
  for k in KEYS+['batter','pitcher']:
   if db.execute('SELECT count(*) FROM raw WHERE try_cast('+ident(k)+' AS BIGINT) IS NULL OR try_cast('+ident(k)+' AS BIGINT)<=0 OR try_cast('+ident(k)+' AS DOUBLE)!=try_cast('+ident(k)+' AS BIGINT)').fetchone()[0]:raise ValueError('Invalid required ID/key: '+k)
  if db.execute("SELECT count(*) FROM raw WHERE game_type!='R' OR game_type IS NULL OR try_cast(game_date AS DATE) IS DISTINCT FROM CAST(? AS DATE)",[day]).fetchone()[0]:raise ValueError('Wrong date/game type in response')
  present={r[0] for r in db.execute('SELECT DISTINCT cast(game_pk AS BIGINT) FROM raw').fetchall()}
  if present!=set(expected):raise ValueError(f'Game coverage differs from completed MLB schedule: missing={set(expected)-present},extra={present-set(expected)}')
  db.execute('CREATE TABLE unique_raw AS SELECT DISTINCT * FROM raw')
  duplicates=db.execute('SELECT count(*) FROM (SELECT cast(game_pk AS BIGINT),cast(at_bat_number AS BIGINT),cast(pitch_number AS BIGINT) FROM unique_raw GROUP BY ALL HAVING count(*)>1)').fetchone()[0]
  if duplicates:raise ValueError('Conflicting duplicate pitch keys')
  known=set(INTS+FLOATS+TEXT)
  fields=[ident(k) for k in headers if k not in known and k not in ('season','measurement_era')]
  for k in INTS+FLOATS:
   t='BIGINT' if k in INTS else 'DOUBLE'
   if k in headers:
    invalid=db.execute('SELECT count(*) FROM unique_raw WHERE '+ident(k)+' IS NOT NULL AND trim('+ident(k)+") NOT IN ('','null','NA','NaN') AND (try_cast("+ident(k)+' AS '+t+') IS NULL'+(' OR NOT isfinite(try_cast('+ident(k)+' AS DOUBLE))' if k in FLOATS else '')+')').fetchone()[0]
    if invalid:raise ValueError(f'Invalid numeric values in {k}: {invalid}')
    fields.append('try_cast('+ident(k)+' AS '+t+') AS '+ident(k))
   else:fields.append('CAST(NULL AS '+t+') AS '+ident(k))
  for k in TEXT:fields.append((ident(k) if k in headers else 'CAST(NULL AS VARCHAR)')+' AS '+ident(k))
  fields+=['CAST('+day[:4]+' AS INTEGER) AS season',lit('ABS_MIDDLE_PLATE' if int(day[:4])>=2026 else 'PRE_ABS_FRONT_PLATE')+' AS measurement_era']
  db.execute('COPY (SELECT '+','.join(fields)+' FROM unique_raw ORDER BY game_pk,at_bat_number,pitch_number) TO '+lit(out.as_posix())+' (FORMAT PARQUET,COMPRESSION ZSTD)')
  count=db.execute('SELECT count(*) FROM unique_raw').fetchone()[0]
 return {'rows':count,'source_rows':n,'exact_duplicates':n-count,'missing_columns':sorted(known-set(headers))}

def download(c,start=None,end=None,max_windows=0,refresh=False,fetch=request_bytes):
 root=c['_root'];results=[];failed=[];attempted=0
 with lock(root),closing(ledger(c)) as log:
  for day in days(c,start,end):
   old=log.execute('SELECT status,raw_path,raw_hash,parquet_path,parquet_hash,schedule_path,schedule_hash FROM windows WHERE day=?',[day]).fetchone()
   if old and old[0]=='COMPLETE' and not refresh:
    for path,h in [(old[1],old[2]),(old[3],old[4]),(old[5],old[6])]:
     if path and (not Path(path).is_file() or sha(path)!=h):raise ValueError('Completed window hash mismatch; use --refresh: '+day)
    verify_dependencies(log,day)
    print(day+': verified; skipped',flush=True);continue
   if max_windows and attempted>=max_windows:break
   attempted+=1;run=uuid.uuid4().hex;folder=root/'raw'/day[:4]/day/run;folder.mkdir(parents=True)
   raw=folder/'statcast.csv';sched=folder/'schedule.json';out=root/'parquet'/f'season={day[:4]}'/f'month={day[5:7]}'/f'day={day[8:]}'/run/'pitches.parquet'
   out.parent.mkdir(parents=True)
   url,schedule_url=urls(day);started=time.perf_counter();print(day+': fetching schedule and pitches',flush=True)
   try:
    schedule_bytes=retry(schedule_url,c,fetch);sched.write_bytes(schedule_bytes)
    schedule=json.loads(schedule_bytes)
    if 'dates' not in schedule:raise ValueError('Invalid schedule response')
    games=finished_games(schedule);expected=[];dependencies=[]
    for g in games:
     official=g.get('officialDate',day)
     if official!=day:
      # Only explicit suspended-game resumption metadata permits a cross-date exception.
      if g.get('resumedFromDate')!=official or official>=day:
       raise ValueError('Unexplained schedule/date mismatch: '+str(g['gamePk']))
      dependencies.append(verify_dependency(log,official,int(g['gamePk'])))
     else:expected.append(int(g['gamePk']))
    raw.write_bytes(retry(url,c,fetch))
    stats=ingest_csv(raw,day,expected,out)
    parquet=str(out.resolve()) if out.exists() else None
    log.execute('INSERT OR REPLACE INTO windows VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',[day,'COMPLETE',run,str(raw.resolve()),sha(raw),parquet,sha(out) if parquet else None,stats['rows'],stats['source_rows'],stats['exact_duplicates'],str(sched.resolve()),sha(sched),now(),url,None,VERSION]);
    log.execute('DELETE FROM window_dependencies WHERE day=?',[day])
    log.executemany('INSERT INTO window_dependencies VALUES (?,?,?,?)',[(day,d['game_pk'],d['source_day'],d['source_run_id']) for d in dependencies]);log.commit()
    audit={'day':day,'run_id':run,'url':url,'schedule_url':schedule_url,'schedule_games':len(games),'cross_date_games':dependencies,'excluded_terminal_schedule_entries':excluded_terminal_games(schedule),'retrieved_at':now(),'elapsed_seconds':round(time.perf_counter()-started,3),**stats}
    (folder/'audit.json').write_text(json.dumps(audit,indent=2));results.append(audit)
    print(f'{day}: COMPLETE {stats["rows"]:,} rows ({audit["elapsed_seconds"]}s)',flush=True)
   except Exception as exc:
    # A failed refresh must not replace a previously completed active version.
    if not old or old[0]!='COMPLETE':
     log.execute('INSERT OR REPLACE INTO windows(day,status,run_id,error,version) VALUES (?,?,?,?,?)',[day,'FAILED',run,str(exc),VERSION]);log.commit()
    (folder/'failure.json').write_text(json.dumps({'day':day,'error':str(exc),'at':now()},indent=2));failed.append({'day':day,'error':str(exc)});print(day+': FAILED '+str(exc),flush=True)
   time.sleep(c.get('pause_seconds',2))
  report={'version':VERSION,'completed_this_run':len(results),'failed_this_run':failed,'results':results,'partial_run':bool(max_windows)}
  (root/'latest_download_report.json').write_text(json.dumps(report,indent=2))
 return report

def active(c,start=None,end=None):
 expected=list(days(c,start,end))
 if not expected:raise ValueError('No configured days selected')
 with closing(ledger(c)) as log:
  log.row_factory=sqlite3.Row
  indexed={r['day']:dict(r) for r in log.execute("SELECT * FROM windows WHERE status='COMPLETE'")}
  for day in expected:
   verify_dependencies(log,day)
 missing=[d for d in expected if d not in indexed]
 if missing:raise ValueError(f'{len(missing)} incomplete daily windows; first: {missing[:5]}')
 selected=[indexed[d] for d in expected]
 for r in selected:
  for p,h in [(r['raw_path'],r['raw_hash']),(r['parquet_path'],r['parquet_hash']),(r['schedule_path'],r['schedule_hash'])]:
   if p and sha(p)!=h:raise ValueError('Hash mismatch: '+str(p))
 return selected

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='config/statcast_ingestion_v1_0.json');p.add_argument('--start');p.add_argument('--end')
 p.add_argument('--plan',action='store_true');p.add_argument('--max-windows',type=int,default=0);p.add_argument('--refresh',action='store_true')
 a=p.parse_args();c=config(a.config)
 if a.plan:
  ds=list(days(c,a.start,a.end));print(json.dumps({'daily_windows':len(ds),'first':ds[:3],'last':ds[-3:]},indent=2));return
 r=download(c,a.start,a.end,a.max_windows,a.refresh)
 print(json.dumps({'completed_this_run':r['completed_this_run'],'failed_this_run':r['failed_this_run']},indent=2))
 if r['failed_this_run']:raise SystemExit(1)
if __name__=='__main__':main()
