import unittest,tempfile,json
from contextlib import closing
from pathlib import Path
from statcast_model_inputs_v1_0 import attribute_pa,scored_history,select_feature,trace_pitches
from statcast_pipeline_v1_0 import config,download
from test_statcast_pipeline_v1_0 import StatcastTests

class AttributionTests(unittest.TestCase):
 def row(self,n,batter=1,pitcher=10,balls=0,strikes=0,event=None):
  return dict(pitch_number=n,batter=batter,pitcher=pitcher,balls=balls,strikes=strikes,events=event)
 def test_inherited_strikeout_and_other_outcomes(self):
  r=attribute_pa([self.row(1,strikes=1),self.row(2,batter=2,strikes=2,event='strikeout')])
  self.assertEqual(r['batter'],1)
  r=attribute_pa([self.row(1,strikes=1),self.row(2,batter=2,strikes=1,event='strikeout')])
  self.assertEqual(r['batter'],2)
  r=attribute_pa([self.row(1,strikes=1),self.row(2,batter=2,strikes=2,event='walk')])
  self.assertEqual(r['batter'],2)
 def test_all_walk_inheritance_counts_and_pitch_ownership(self):
  for b in range(4):
   for k in range(3):
    r=attribute_pa([self.row(1),self.row(2,pitcher=11,balls=b,strikes=k,event='walk')])
    self.assertEqual(r['pitcher'],10 if (b,k) in {(2,0),(2,1),(3,0),(3,1),(3,2)} else 11)
    r=attribute_pa([self.row(1),self.row(2,pitcher=11,balls=b,strikes=k,event='single')])
    self.assertEqual(r['pitcher'],11)
 def test_multi_change_chain_and_missing_count(self):
  rows=[self.row(1),self.row(2,pitcher=11,balls=2,strikes=1),self.row(3,pitcher=12,balls=3,strikes=1,event='walk')]
  self.assertEqual(attribute_pa(rows)['pitcher'],10)
  rows[1]['balls']=None
  self.assertEqual(attribute_pa(rows)['unresolved'],['pitcher'])
 def test_multiple_terminal_events_rejected(self):
  with self.assertRaises(ValueError):attribute_pa([self.row(1,event='walk'),self.row(2,event='walk')])
 def test_exact_rules_reconciliation_and_official_rate_preference(self):
  key=('pitcher',2024,'p1');f=dict(mlbam_id=10,pa_observed=100,k_pct_observed=.2,bb_pct_observed=.1)
  actual={key:dict(name='A',metrics={'TBF':101,'SO':20,'BB':11})}
  attributed={key:dict(exposure=101,SO=20,BB=11,status='RULE_ATTRIBUTED')}
  h,r=scored_history({key:f},actual,attributed)
  self.assertEqual(r[0]['status'],'EXPLAINED_BY_SUBSTITUTION_RULES')
  self.assertEqual(h[key]['bb_pct_scored'],11/101)
  h,r=scored_history({key:f},{},{})
  self.assertIsNone(h[key]['bb_pct_scored'])
 def test_sample_gate_older_fallback_and_future_actuals_excluded(self):
  h={('hitter',2024,'p1'):dict(swings=200,whiff_pct=.2,measurement_era='PRE_ABS_FRONT_PLATE'),('hitter',2025,'p1'):dict(swings=10,whiff_pct=.9,measurement_era='PRE_ABS_FRONT_PLATE'),('hitter',2026,'p1'):dict(swings=10000,whiff_pct=1,measurement_era='ABS_MIDDLE_PLATE')}
  r=select_feature(h,'hitter','p1',2026,'whiff_pct',('swings',100,400),3)
  self.assertEqual((r['value'],r['feature_season']),(.2,2024))
  self.assertAlmostEqual(r['reliability'],1/3)
  self.assertIsNone(select_feature(h,'hitter','unknown',2026,'whiff_pct',('swings',100,400),3)['value'])
 def test_full_pitch_trace_moves_walk_counts_conserves_totals(self):
  helper=StatcastTests()
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);c=helper.setup_root(root)
   payload=helper.payload().decode().replace('101,201,hit_into_play,single','101,202,hit_into_play,walk')
   # Set the entering pitch count to 3-1 for inherited-walk attribution.
   import csv,io
   rows=list(csv.DictReader(io.StringIO(payload)));rows[1]['balls']='3';rows[1]['strikes']='1';rows[0]['balls']='2'
   stream=io.StringIO();w=csv.DictWriter(stream,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
   def fetch(url,**kw):return helper.fake(url,**kw) if 'schedule?' in url else b'' if '2024-04-02' in url else stream.getvalue().encode()
   download(c,fetch=fetch)
   out=root/'audit';out.mkdir()
   counts,report=trace_pitches(root/'config/statcast.json','2024-04-01','2024-04-02',{201:'p201',202:'p202',101:'h101',102:'h102'},out)
   self.assertEqual(report['changed_completed_pas'],1)
   self.assertEqual(counts[('pitcher',2024,'p201')]['BB'],1)
   self.assertEqual(sum(v['exposure'] for k,v in counts.items() if k[0]=='pitcher'),2)
   self.assertEqual(counts[('pitcher',2024,'p202')]['exposure'],0)

class AssemblyTests(unittest.TestCase):
 def test_complete_assembly_is_readonly_and_target_actuals_cannot_change_features(self):
  import argparse,sqlite3,duckdb,hashlib
  from statcast_model_inputs_v1_0 import build
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);sql=root/'reference.sqlite';features=root/'features.duckdb'
   with closing(sqlite3.connect(sql)) as c, c:
    c.executescript("CREATE TABLE players(player_id TEXT,preferred_name TEXT);INSERT INTO players VALUES ('p1','Player');CREATE TABLE player_id_crosswalk(namespace TEXT,external_id TEXT,player_id TEXT);INSERT INTO player_id_crosswalk VALUES ('mlbam','10','p1');CREATE TABLE record_selection(record_id TEXT,selected INTEGER);")
    for typ in ['hitter','pitcher']:
     c.execute('CREATE TABLE '+typ+'_actuals(record_id TEXT,season INTEGER,player_id TEXT,name TEXT,metrics_json TEXT)')
     c.execute('CREATE TABLE analytical_'+typ+'_projections(record_id TEXT,season INTEGER,source TEXT,player_id TEXT,name TEXT,team TEXT,metrics_json TEXT,excluded_metrics_json TEXT)')
     for year in [2024,2025,2026]:
      rid=typ+str(year)
      c.execute('INSERT INTO '+typ+'_actuals VALUES (?,?,?,?,?)',[rid,year,'p1','Player',json.dumps(dict(PA=100,TBF=100,SO=20,BB=10))])
      c.execute('INSERT INTO record_selection VALUES (?,1)',[rid])
      c.execute('INSERT INTO analytical_'+typ+'_projections VALUES (?,?,?,?,?,?,?,?)',[rid+'p',year,'Source','p1','Player','ARI',json.dumps(dict(PA=200,IP=0,SO=0,BB=0)), '[]'])
   with duckdb.connect(str(features)) as c:
    c.execute('CREATE TABLE player_identity_coverage(season INTEGER,player_type VARCHAR,mlbam_id BIGINT,canonical_player_id VARCHAR)')
    for typ in ['hitter','pitcher']:
     c.execute('CREATE TABLE '+typ+'_statcast_season(season INTEGER,mlbam_id BIGINT,measurement_era VARCHAR,pitch_rows INTEGER,pa_observed INTEGER,k_pct_observed DOUBLE,bb_pct_observed DOUBLE,swings INTEGER,whiff_pct DOUBLE)')
     for year in [2023,2024,2025]:
      c.execute('INSERT INTO '+typ+"_statcast_season VALUES (?,10,'PRE_ABS_FRONT_PLATE',200,100,.2,.1,100,.25)",[year])
      c.execute("INSERT INTO player_identity_coverage VALUES (?,?,10,'p1')",[year,typ])
    c.execute("CREATE TABLE team_context_enriched AS SELECT 2025 AS season,'AZ' AS team,4.0 AS runs_per_game")
   cfg=root/'config.json';cfg.write_text(json.dumps(dict(target_season=2026,training_seasons=[2024,2025],history_lookback_seasons=3,feature_rules={'whiff_pct':['swings',100,400],'k_pct_scored':['scored_exposure',50,300]})))
   audit=root/'feature_audit.json';audit.write_text(json.dumps(dict(target_season=2026,complete_requested_windows=True,event_start='2023-03-01',event_end='2025-11-01',pitch_rows=600,projection_catalog_sha256='other-backend-hash')))
   args=argparse.Namespace(config=cfg,sqlite=sql,features=features,feature_audit=audit,output=root/'out1',backup_root=root/'backups',skip_pitch_trace=True)
   hashes=[hashlib.sha256(p.read_bytes()).hexdigest() for p in [sql,features]]
   report=build(args)
   self.assertEqual(hashes,[hashlib.sha256(p.read_bytes()).hexdigest() for p in [sql,features]])
   self.assertFalse(report['holdout_labels_loaded'])
   self.assertEqual(report['training_label_rows'],4)
   self.assertTrue(Path(report['backup']).is_dir())
   with closing(sqlite3.connect(sql)) as c, c:
    for typ in ['hitter','pitcher']:
     c.execute('UPDATE '+typ+"_actuals SET metrics_json=? WHERE season=2026",[json.dumps(dict(PA=99999,TBF=99999,SO=90000,BB=1))])
   args.output=root/'out2';build(args)
   for filename in ['model_features.csv','projection_baselines.jsonl','model_players.jsonl','training_labels.jsonl','model_team_context.csv']:
    self.assertEqual((root/'out1'/filename).read_bytes(),(root/'out2'/filename).read_bytes())
   with (root/'out1/model_team_context.csv').open(encoding='utf-8',newline='') as handle:
    rows=list(__import__('csv').DictReader(handle))
   self.assertTrue(all(not r['context_season'] or int(r['context_season'])<int(r['projection_season']) for r in rows))

if __name__=='__main__':unittest.main()
