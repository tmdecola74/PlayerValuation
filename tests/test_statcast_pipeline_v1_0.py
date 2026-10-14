import unittest,tempfile,csv,json,io
from pathlib import Path
from unittest.mock import patch
from statcast_pipeline_v1_0 import config,download,active,ingest_csv,lock
from build_statcast_features_v1_0 import build
from validate_statcast_ingestion_v1_0 import validate
from download_team_context_v1_0 import normalize,download as download_teams
import duckdb
class StatcastTests(unittest.TestCase):
 def setup_root(self,root):
  (root/'config').mkdir();p=root/'config/statcast.json'
  p.write_text(json.dumps({'root':'data/statcast','seasons':[{'season':2024,'start':'2024-04-01','end':'2024-04-02'}],'pause_seconds':0,'attempts':1}))
  return config(p)
 def payload(self,duplicate=False,conflict=False):
  headers=['game_pk','at_bat_number','pitch_number','game_date','game_type','batter','pitcher','description','events','type','home_team','away_team','inning_topbot','inning','zone','strikes','launch_speed','launch_speed_angle','estimated_woba_using_speedangle','release_speed','release_spin_rate','pfx_x','pfx_z','home_score','away_score','on_1b','on_2b','outs_when_up','pitch_type','stand']
  rows=[[1,1,1,'2024-04-01','R',101,201,'swinging_strike','','S','NYY','BOS','Top',1,11,0,'','','',95,2200,-.5,1,0,0,102,'',0,'FF','R'],[1,1,2,'2024-04-01','R',101,201,'hit_into_play','single','X','NYY','BOS','Top',1,5,1,100,6,.8,96,2250,-.4,1,0,0,102,'',0,'FF','R'],[1,2,1,'2024-04-01','R',102,201,'called_strike','strikeout','S','NYY','BOS','Top',9,5,2,'','','',94,2200,-.5,1,2,1,'','',1,'FF','L']]
  if duplicate:rows.append(rows[0].copy())
  if conflict:row=rows[0].copy();row[headers.index('release_speed')]=97;rows.append(row)
  out=io.StringIO();w=csv.writer(out);w.writerow(headers);w.writerows(rows);return out.getvalue().encode()
 def schedule(self,empty=False):
  return {'dates':[] if empty else [{'games':[{'gamePk':1,'gameType':'R','status':{'abstractGameState':'Final'},'teams':{'home':{'team':{'id':147},'score':2},'away':{'team':{'id':111},'score':1}}}]}]}
 def fake(self,url,**kwargs):
  if 'schedule?' in url:return json.dumps(self.schedule('2024-04-02' in url)).encode()
  return b'' if '2024-04-02' in url else self.payload(duplicate=True)
 def test_resumed_game_uses_verified_original_day_without_duplicate_pitches(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.setup_root(Path(t))
   def fetch(url,**kwargs):
    if 'schedule?' in url:
     schedule=self.schedule()
     if '2024-04-02' in url:
      schedule['dates'][0]['games'][0].update(officialDate='2024-04-01',resumedFromDate='2024-04-01')
     return json.dumps(schedule).encode()
    return b'' if '2024-04-02' in url else self.payload()
   r=download(c,fetch=fetch)
   self.assertEqual(r['failed_this_run'],[])
   self.assertEqual(r['results'][1]['cross_date_games'][0]['pitch_rows'],3)
   self.assertEqual(validate(c)['pitch_rows'],3)
   self.assertEqual(len(active(c,'2024-04-02','2024-04-02')),1)
   report=build(c,Path(t)/'features');self.assertEqual(report['pitch_rows'],3)
   source=Path(active(c)[0]['raw_path']);source.write_bytes(b'tampered')
   with self.assertRaisesRegex(ValueError,'hash mismatch'):
    active(c,'2024-04-02','2024-04-02')
 def test_resumed_game_requires_original_day_and_explicit_metadata(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.setup_root(Path(t))
   def fetch(url,**kwargs):
    schedule=self.schedule();schedule['dates'][0]['games'][0].update(officialDate='2024-04-01',resumedFromDate='2024-04-01')
    return json.dumps(schedule).encode() if 'schedule?' in url else b''
   r=download(c,'2024-04-02','2024-04-02',fetch=fetch)
   self.assertEqual(len(r['failed_this_run']),1)
   self.assertIn('Cross-date source missing',r['failed_this_run'][0]['error'])

 def test_resume_empty_day_hashes_and_full_features(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=self.setup_root(root);r=download(c,fetch=self.fake)
   self.assertEqual(r['completed_this_run'],2);self.assertEqual(r['results'][0]['exact_duplicates'],1)
   r=download(c,fetch=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network')));self.assertEqual(r['completed_this_run'],0)
   self.assertEqual(validate(c)['pitch_rows'],3)
   out=root/'features';report=build(c,out);self.assertEqual(report['pitch_rows'],3)
   with duckdb.connect(str(out/'statcast_features.duckdb'),read_only=True) as db:
    self.assertAlmostEqual(db.execute('select whiff_pct from pitcher_statcast_season').fetchone()[0],.5)
    self.assertEqual(db.execute("select wins from team_context_season where team='NYY'").fetchone()[0],1)
    self.assertIsNone(db.execute('select stolen_bases from team_context_season limit 1').fetchone()[0])
    self.assertEqual(db.execute('select count(*) from statcast_pitch').fetchone()[0],3)
   first=active(c)[0];Path(first['raw_path']).write_bytes(b'tampered')
   with self.assertRaises(ValueError):active(c)
 def test_invalid_csv_conflict_missing_games_wrong_date(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);raw=root/'raw.csv';out=root/'p.parquet';raw.write_bytes(self.payload(conflict=True))
   with self.assertRaises(ValueError):ingest_csv(raw,'2024-04-01',[1],out)
   raw.write_bytes(self.payload())
   with self.assertRaises(ValueError):ingest_csv(raw,'2024-04-02',[1],out)
   with self.assertRaises(ValueError):ingest_csv(raw,'2024-04-01',[1,2],out)
   raw.write_text('<html>Error</html>')
   with self.assertRaises(ValueError):ingest_csv(raw,'2024-04-01',[1],out)
 def test_failed_refresh_preserves_active_missing_window_blocks_features(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=self.setup_root(root);download(c,start='2024-04-01',end='2024-04-01',fetch=self.fake)
   original=active(c,'2024-04-01','2024-04-01')[0]['raw_hash']
   download(c,start='2024-04-01',end='2024-04-01',refresh=True,fetch=lambda *a,**k:b'bad')
   self.assertEqual(active(c,'2024-04-01','2024-04-01')[0]['raw_hash'],original)
   with self.assertRaises(ValueError):build(c,root/'features')
 def test_lock_and_interrupt_release(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)
   with self.assertRaises(KeyboardInterrupt):
    with lock(p):
     with self.assertRaises(FileExistsError):
      with lock(p):pass
     raise KeyboardInterrupt
   self.assertFalse((p/'pipeline.lock').exists())
 def test_team_missing_fields_and_resume(self):
  payload={'stats':[{'splits':[{'team':{'id':147,'name':'Yankees'},'stat':{'gamesPlayed':162,'stolenBases':0,'caughtStealing':0,'plateAppearances':6000}}]}]}
  rows=normalize(payload,2024,'hitting');self.assertIsNone(rows[0]['sb_success_pct']);self.assertEqual(rows[0]['sb_attempts_per_pa'],0)
  self.assertIsNone(normalize(payload,2024,'pitching')[0]['holds'])
  with tempfile.TemporaryDirectory() as t:
   c=self.setup_root(Path(t));r=download_teams(c,[2024],fetch=lambda *a,**k:json.dumps(payload).encode());self.assertEqual(len(r),2)
   r=download_teams(c,[2024],fetch=lambda *a,**k:(_ for _ in ()).throw(AssertionError('network')));self.assertEqual(len(r),2)
 def test_2026_target_cutoff_excludes_2026_downloads(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=self.setup_root(root)
   c['seasons'].append({'season':2026,'start':'2026-04-01','end':'2026-04-02'})
   download(c,start='2024-04-01',end='2024-04-02',fetch=self.fake)
   # 2026 has no completed windows; target-2026 build must neither require nor read them.
   report=build(c,root/'features',target_season=2026)
   self.assertEqual(report['feature_cutoff'],'2025-12-31')
   self.assertEqual(report['selected_windows'],2)
   with self.assertRaises(ValueError):build(c,root/'bad',end='2026-01-01',target_season=2026)
 def test_team_supplement_only_for_complete_season_window(self):
  payload={'stats':[{'splits':[{'team':{'id':147,'name':'Yankees'},'stat':{'gamesPlayed':162,'stolenBases':10,'caughtStealing':2,'plateAppearances':6000,'saves':35,'holds':50}}]}]}
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=self.setup_root(root)
   download(c,fetch=self.fake);download_teams(c,[2024],fetch=lambda *a,**k:json.dumps(payload).encode())
   report=build(c,root/'full');self.assertEqual(len(report['included_team_supplement_paths']),2)
   with duckdb.connect(str(root/'full/statcast_features.duckdb'),read_only=True) as db:
    self.assertEqual(db.execute("select official_sb from team_context_enriched where team='NYY'").fetchone()[0],10)
   report=build(c,root/'partial',end='2024-04-01');self.assertEqual(report['included_team_supplement_paths'],[])
 def test_postponed_abstract_final_excluded_and_early_final_retained(self):
  from statcast_pipeline_v1_0 import finished_games,excluded_terminal_games
  original=self.schedule()['dates'][0]['games'][0]
  import copy
  games=[]
  for key,detail,code in [(1,'Final','F'),(2,'Postponed','D'),(3,'Cancelled','C'),(4,'Suspended','U'),(5,'Completed Early: Rain','F')]:
   g=copy.deepcopy(original);g['gamePk']=key;g['status'].update(detailedState=detail,codedGameState=code);games.append(g)
  sched={'dates':[{'games':games}]}
  self.assertEqual([g['gamePk'] for g in finished_games(sched)],[1,5])
  self.assertEqual(len(excluded_terminal_games(sched)),3)
 def test_download_with_postponed_schedule_entry_and_feature_counts(self):
  import copy
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=self.setup_root(root)
   schedule=self.schedule();postponed=copy.deepcopy(schedule['dates'][0]['games'][0])
   postponed['gamePk']=718700;postponed['status'].update(detailedState='Postponed',codedGameState='D')
   schedule['dates'][0]['games'].append(postponed)
   def fetch(url,**kwargs):return json.dumps(schedule).encode() if 'schedule?' in url else self.payload()
   result=download(c,start='2024-04-01',end='2024-04-01',fetch=fetch)
   self.assertEqual(result['completed_this_run'],1);self.assertEqual(result['results'][0]['schedule_games'],1)
   self.assertEqual(result['results'][0]['excluded_terminal_schedule_entries'][0]['game_pk'],718700)
   build(c,root/'features',start='2024-04-01',end='2024-04-01')
   with duckdb.connect(str(root/'features/statcast_features.duckdb'),read_only=True) as db:self.assertEqual(db.execute('select count(*) from mlb_game').fetchone()[0],1)
if __name__=='__main__':unittest.main()
