from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import duckdb
from statcast_pipeline_v1_0 import config,ledger,sha
from audit_statcast_readiness_v1_0 import audit

class AuditTests(unittest.TestCase):
 def fixture(self, base, duplicate=False):
  project=Path(base);(project/'config').mkdir();root=project/'data';root.mkdir()
  cfg=project/'config'/'c.json';cfg.write_text(json.dumps({'root':'data','seasons':[{'season':2015,'start':'2015-04-05','end':'2015-04-05'}]}));c=config(cfg)
  raw=root/'raw.csv';raw.write_text('fixture')
  schedule=root/'schedule.json';schedule.write_text(json.dumps({'dates':[{'games':[{'gamePk':1,'gameType':'R','officialDate':'2015-04-05','status':{'abstractGameState':'Final','detailedState':'Final'},'teams':{'home':{'score':1},'away':{'score':0}}}]}]}))
  parquet=root/'p.parquet'
  with duckdb.connect() as db:
   db.execute("CREATE TABLE p AS SELECT 1 game_pk,1 at_bat_number,1 pitch_number,10 batter,20 pitcher,'2015-04-05' game_date,'R' game_type,'hit_into_play' description,'home_run' events,'X' AS \"type\",100.0 launch_speed,NULL::DOUBLE launch_angle,95.0 release_speed")
   if duplicate:db.execute('INSERT INTO p SELECT * FROM p')
   db.execute('COPY p TO ? (FORMAT PARQUET)',[str(parquet)])
  with closing(ledger(c)) as log:
   log.execute('INSERT INTO windows(day,status,run_id,raw_path,raw_hash,parquet_path,parquet_hash,rows,schedule_path,schedule_hash) VALUES(?,?,?,?,?,?,?,?,?,?)',['2015-04-05','COMPLETE','a',str(raw),sha(raw),str(parquet),sha(parquet),2 if duplicate else 1,str(schedule),sha(schedule)])
   log.commit()
  return c
 def test_coverage_reference_and_read_only(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(t);before=sha(c['_root']/'download_ledger.sqlite')
   ref=Path(t)/'official.csv';ref.write_text('season,player_type,mlbam_id,metric,value\n2015,hitter,10,HR,1\n')
   r=audit(c,Path(t)/'out',official=ref)
   self.assertTrue(r['integrity_pass']);self.assertFalse(r['model_ready']);self.assertEqual(before,sha(c['_root']/'download_ledger.sqlite'))
   self.assertIn('UNAVAILABLE',(Path(t)/'out'/'measurement_coverage.csv').read_text())
   self.assertIn('MATCH',(Path(t)/'out'/'official_comparison.csv').read_text())
 def test_duplicate_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=audit(self.fixture(t,True),Path(t)/'out');self.assertFalse(r['integrity_pass'])
 def test_hash_failure_reported(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(t);(c['_root']/'raw.csv').write_text('tampered')
   self.assertFalse(audit(c,Path(t)/'out')['integrity_pass'])
 def test_missing_window_and_output_guard(self):
  with tempfile.TemporaryDirectory() as t:
   c=self.fixture(t);c['seasons'][0]['end']='2015-04-06'
   self.assertFalse(audit(c,Path(t)/'out')['integrity_pass'])
   with self.assertRaises(ValueError):audit(c,c['_root']/'output')
if __name__=='__main__':unittest.main()
