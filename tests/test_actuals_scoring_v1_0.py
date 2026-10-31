import csv
import json
import shutil
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
import duckdb
from actuals_scoring_v1_0 import *
from import_fangraphs_actuals_v1_0 import build as import_build
from reconcile_statcast_actuals_v1_0 import build as reconcile_build
from download_mlb_scoring_evidence_v1_0 import download
from statcast_pipeline_v1_0 import config,ledger


def pitch(n,batter=10,pitcher=20,balls=0,strikes=0,event=None,pa=1):
 return dict(game_pk=1,at_bat_number=pa,pitch_number=n,batter=batter,pitcher=pitcher,balls=balls,strikes=strikes,events=event,game_date='2015-04-05',game_type='R')


def stats(role,year,mid,**values):
 row={'Season':str(year),'Age':'25','PlayerId':str(mid),'MLBAMID':str(mid),'Name':'Player '+str(mid),'Team':'AAA'}
 row.update({m:'0' for m in (HITTER_COUNTS if role=='hitter' else PITCHER_COUNTS)})
 if role=='pitcher':row['IP']='0.0'
 row.update({k:str(v) for k,v in values.items()});return row


def export(path,rows):
 csv_out(path,rows,list(rows[0]))


def feed(game=1,year=2015,outs='0.1'):
 # Minimal complete batting/pitching team blocks for validated aggregate tests.
 b={v:0 for v in BOX_FIELDS['hitter'].values()};b.update(plateAppearances=1,atBats=1,strikeOuts=1)
 p={v:0 for v in BOX_FIELDS['pitcher'].values()};p.update(battersFaced=1,strikeOuts=1,inningsPitched=outs)
 teams={}
 for side,pid in [('home',10),('away',20)]:
  teams[side]={'teamStats':{'batting':b,'pitching':p},'players':{'ID'+str(pid):{'person':{'id':pid},'stats':{'batting':b,'pitching':p}}}}
 return {'gamePk':game,'gameData':{'game':{'type':'R','season':str(year)},'status':{'abstractGameState':'Final','detailedState':'Final'}},'liveData':{'boxscore':{'teams':teams},'plays':{'allPlays':[]}}}


class RulesTests(unittest.TestCase):
 def test_two_strike_batter_credit_and_pitcher_terminal_strikeout(self):
  rs=[pitch(1),pitch(2,strikes=1),pitch(3,batter=11,pitcher=21,strikes=2,event='strikeout')]
  d=credit_pa(rs);self.assertEqual(d['owners'],{'hitter':10,'pitcher':21});self.assertFalse(d['unresolved_roles'])
 def test_one_strike_replacement_and_non_strikeout_final_batter(self):
  d=credit_pa([pitch(1),pitch(2,batter=11,strikes=1,event='strikeout')]);self.assertEqual(d['owners']['hitter'],11)
  d=credit_pa([pitch(1),pitch(2,batter=11,strikes=2,event='single')]);self.assertEqual(d['owners']['hitter'],11)
 def test_inherited_walk_counts_and_other_outcomes(self):
  for count in [(2,0),(2,1),(3,0),(3,1),(3,2)]:
   d=credit_pa([pitch(1),pitch(2,pitcher=21,balls=count[0],strikes=count[1],event='walk')]);self.assertEqual(d['owners']['pitcher'],20)
  d=credit_pa([pitch(1),pitch(2,pitcher=21,balls=2,strikes=2,event='walk')]);self.assertEqual(d['owners']['pitcher'],21)
  d=credit_pa([pitch(1),pitch(2,pitcher=21,balls=3,strikes=1,event='hit_by_pitch')]);self.assertEqual(d['owners']['pitcher'],21)
 def test_missing_counts_gaps_multichange_and_incomplete_start(self):
  cases=[[pitch(1),pitch(2,pitcher=21,balls=None,event='walk')],[pitch(1),pitch(3,pitcher=21,balls=3,event='walk')],[pitch(1),pitch(2,pitcher=21,balls=2),pitch(3,pitcher=22,balls=3,event='walk')],[pitch(2,balls=3,event='walk')]]
  for rs in cases:self.assertIn('pitcher',credit_pa(rs)['unresolved_roles'])
 def test_nonterminal_and_special_pa_events(self):
  self.assertEqual(event_vector('truncated_pa','hitter'),{})
  self.assertEqual(event_vector('catcher_interf','hitter')['PA'],1);self.assertEqual(event_vector('catcher_interf','hitter')['AB'],0)
  self.assertEqual(event_vector('sac_fly_double_play','hitter')['SF'],1)
  self.assertEqual(event_vector('strikeout_double_play','pitcher')['SO'],1)
  self.assertEqual(event_vector('intent_walk','pitcher')['IBB'],1)


class ImportTests(unittest.TestCase):
 def test_innings_null_rates_and_duplicate_headers(self):
  self.assertEqual(innings_outs('146.1'),439);self.assertEqual(innings_outs('0.2'),2)
  with self.assertRaises(ValueError):innings_outs('1.3')
  self.assertIsNone(derive_rates('pitcher',{'ER':0,'OUTS':0,'H':1,'BB':1,'SO':0})['ERA'])
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'r.csv';p.write_text('Season,Season\n2015,2015\n');self.assertEqual(list(checked_rows(p))[0][1]['Season'],'2015')
   p.write_text('Season,Season\n2015,2016\n')
   with self.assertRaises(ValueError):list(checked_rows(p))
 def test_duplicate_identity_and_team_splits_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'h.csv';r=stats('hitter',2015,10);export(p,[r,r])
   with self.assertRaises(ValueError):load_fangraphs(p,'hitter')
 def test_import_preserves_zero_and_complete_backup(self):
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);h=t/'h.csv';p=t/'p.csv';export(h,[stats('hitter',2015,10)]);export(p,[stats('pitcher',2015,20,H=1,R=1,ER=1)])
   r=import_build(h,p,t/'reference',t/'backups')
   with duckdb.connect(str(t/'reference'/'actuals_reference.duckdb'),read_only=True) as db:
    self.assertEqual(db.execute("SELECT value FROM actual_counts WHERE metric='OUTS'").fetchone()[0],0)
    self.assertIsNone(db.execute("SELECT value FROM derived_rates WHERE metric='ERA'").fetchone()[0])
   a={str(x.relative_to(t/'reference')):sha(x) for x in (t/'reference').rglob('*') if x.is_file()};b={str(x.relative_to(r['backup'])):sha(x) for x in Path(r['backup']).rglob('*') if x.is_file()};self.assertEqual(a,b)
   with self.assertRaises(FileExistsError):import_build(h,p,t/'reference',t/'backups')


class EvidenceTests(unittest.TestCase):
 def test_boxscore_sum_validation_and_outs(self):
  payload=feed();counts,blocks,notes=boxscore_counts(payload)
  self.assertIn(('pitcher','OUTS'),blocks);self.assertEqual(counts['pitcher',20,'OUTS'],1)
  # Break player/team agreement without mutating shared test objects.
  payload=json.loads(json.dumps(payload));payload['liveData']['boxscore']['teams']['home']['teamStats']['batting']['hits']=4
  counts,blocks,notes=boxscore_counts(payload);self.assertNotIn(('hitter','H'),blocks)
 def test_invalid_game_type_and_cache_resume_hash(self):
  bad=feed();bad['gameData']['game']['type']='S'
  with self.assertRaises(ValueError):validate_feed(bad,1,2015)
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);plan=t/'plan.csv';csv_out(plan,[dict(season=2015,game_pk=1,priority='PLAYER_CHANGE_OR_INVALID_PA')],['season','game_pk','priority'])
   calls=[]
   def fetcher(url):calls.append(url);return json.dumps(feed()).encode()
   self.assertEqual(download(plan,t/'cache',max_games=1,pause=0,fetcher=fetcher)['completed_this_run'],1)
   self.assertEqual(download(plan,t/'cache',max_games=1,pause=0,fetcher=fetcher)['verified_skipped'],1);self.assertEqual(len(calls),1)
   (t/'cache'/'1'/'feed.json').write_text('{}')
   with self.assertRaises(ValueError):download(plan,t/'cache',pause=0,fetcher=fetcher)
   self.assertFalse((t/'cache'/'download.lock').exists())


class PipelineTests(unittest.TestCase):
 def fixture(self,t,duplicate=False,second_game=False):
  t=Path(t);(t/'config').mkdir();root=t/'statcast';root.mkdir();cfg=t/'config'/'ingestion.json';cfg.write_text(json.dumps({'root':str(root),'seasons':[{'season':2015,'start':'2015-04-05','end':'2015-04-05'}]}));c=config(cfg)
  h=t/'h.csv';p=t/'p.csv'
  export(h,[stats('hitter',2015,10,PA=1,AB=1,SO=1),stats('hitter',2015,11),stats('hitter',2015,12,PA=1,BB=1),stats('hitter',2026,10,PA=100,AB=100,H=100,**{'1B':100})])
  export(p,[stats('pitcher',2015,20,TBF=2,SO=1,BB=1,IP='0.1'),stats('pitcher',2015,21),stats('pitcher',2026,20,TBF=100,SO=100,IP='33.1')])
  import_build(h,p,t/'reference',t/'backups')
  rows=[pitch(1),pitch(2,strikes=1),pitch(3,batter=11,strikes=2,event='strikeout'),pitch(1,batter=12,pa=2),pitch(2,batter=12,pa=2,balls=1),pitch(3,batter=12,pa=2,balls=2),pitch(4,batter=12,pitcher=21,pa=2,balls=3,event='walk')]
  if second_game:rows += [r|{'game_pk':2} for r in list(rows)]
  if duplicate:rows.append(dict(rows[-1]))
  raw=root/'raw.csv';raw.write_text('fixture');parquet=root/'p.parquet'
  with duckdb.connect() as db:
   db.execute('CREATE TABLE pitches(game_pk BIGINT,at_bat_number BIGINT,pitch_number BIGINT,batter BIGINT,pitcher BIGINT,balls INTEGER,strikes INTEGER,events VARCHAR,game_date VARCHAR,game_type VARCHAR)')
   db.executemany('INSERT INTO pitches VALUES (?,?,?,?,?,?,?,?,?,?)',[[r[k] for k in rows[0]] for r in rows]);db.execute('COPY pitches TO '+lit(parquet)+' (FORMAT PARQUET)')
  schedule=root/'schedule.json';schedule.write_text(json.dumps({'dates':[{'games':[{'gamePk':1,'gameType':'R','officialDate':'2015-04-05','status':{'abstractGameState':'Final','detailedState':'Final'},'teams':{'home':{'score':1},'away':{'score':0}}}]}]}))
  if second_game:
   payload=json.loads(schedule.read_text());g=dict(payload['dates'][0]['games'][0]);g['gamePk']=2;payload['dates'][0]['games'].append(g);schedule.write_text(json.dumps(payload))
  with closing(ledger(c)) as log:
   log.execute('INSERT INTO windows(day,status,run_id,raw_path,raw_hash,parquet_path,parquet_hash,rows,schedule_path,schedule_hash) VALUES(?,?,?,?,?,?,?,?,?,?)',['2015-04-05','COMPLETE','a',str(raw),sha(raw),str(parquet),sha(parquet),len(rows),str(schedule),sha(schedule)]);log.commit()
  return cfg,root
 def test_rule_corrections_conserve_counts_unsupported_not_zero_and_holdout_excluded(self):
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);cfg,root=self.fixture(t);before=sha(root/'download_ledger.sqlite')
   r=reconcile_build(t/'reference',cfg,t/'recon',start='2015-04-05',end='2015-04-05',backup_root=t/'backups')
   self.assertEqual(r['rule_credit_moves'],{'hitter':1,'pitcher':1});self.assertTrue(r['inputs_unchanged']);self.assertEqual(before,sha(root/'download_ledger.sqlite'));self.assertFalse(r['model_ready'])
   with (t/'recon'/'player_metric_reconciliation.csv').open() as f:rows=list(csv.DictReader(f))
   self.assertTrue(all(row['season']=='2015' for row in rows))
   row=next(x for x in rows if x['mlbam_id']=='10' and x['player_type']=='hitter' and x['metric']=='SO');self.assertEqual(row['status'],'EXPLAINED_BY_SCORING_RULES')
   self.assertEqual(next(x for x in rows if x['player_type']=='pitcher' and x['metric']=='OUTS')['evidence_count'],'')
   trace=[json.loads(x) for x in (t/'recon'/'pa_scoring_trace.jsonl').read_text().splitlines()];self.assertEqual(len(trace),2)
   with (t/'recon'/'scoring_conservation.csv').open() as f:self.assertTrue(all(x['pass_check']=='True' for x in csv.DictReader(f)))
   self.assertTrue((Path(r['backup'])/'reconciliation_report.json').is_file())
 def test_partial_game_evidence_does_not_certify_full_season_outs(self):
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);cfg,root=self.fixture(t,second_game=True);cache=t/'cache';(cache/'1').mkdir(parents=True)
   raw=cache/'1'/'feed.json';raw.write_text(json.dumps(feed()));dump(cache/'1'/'source.json',{'game_pk':1,'sha256':sha(raw)})
   r=reconcile_build(t/'reference',cfg,t/'recon',start='2015-04-05',end='2015-04-05',backup_root=t/'backups',feed_cache=cache)
   with (t/'recon'/'player_metric_reconciliation.csv').open() as f:rows=list(csv.DictReader(f))
   row=next(x for x in rows if x['player_type']=='pitcher' and x['mlbam_id']=='20' and x['metric']=='OUTS')
   self.assertEqual(row['evidence_count'],'');self.assertEqual(row['partial_boxscore_count'],'1');self.assertEqual(row['mlb_full_game_metric_coverage'],'1/2')
 def test_complete_game_evidence_enables_outs_comparison(self):
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);cfg,root=self.fixture(t);cache=t/'cache';(cache/'1').mkdir(parents=True)
   raw=cache/'1'/'feed.json';raw.write_text(json.dumps(feed()));dump(cache/'1'/'source.json',{'game_pk':1,'sha256':sha(raw)})
   r=reconcile_build(t/'reference',cfg,t/'recon',start='2015-04-05',end='2015-04-05',backup_root=t/'backups',feed_cache=cache)
   with (t/'recon'/'player_metric_reconciliation.csv').open() as f:rows=list(csv.DictReader(f))
   row=next(x for x in rows if x['player_type']=='pitcher' and x['mlbam_id']=='20' and x['metric']=='OUTS')
   self.assertEqual(row['evidence_count'],'1');self.assertEqual(row['status'],'MATCH_AFTER_MLB_GAME_EVIDENCE')
 def test_duplicate_pitches_fail_without_publishing(self):
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);cfg,root=self.fixture(t,True)
   with self.assertRaisesRegex(ValueError,'Duplicate pitch'):reconcile_build(t/'reference',cfg,t/'recon',start='2015-04-05',end='2015-04-05',backup_root=t/'backups')
   self.assertFalse((t/'recon').exists())
 def test_tampered_source_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   t=Path(t);cfg,root=self.fixture(t);(root/'raw.csv').write_text('bad')
   with self.assertRaisesRegex(ValueError,'hash mismatch'):reconcile_build(t/'reference',cfg,t/'recon',start='2015-04-05',end='2015-04-05',backup_root=t/'backups')
   self.assertFalse((t/'recon').exists())
if __name__=='__main__':unittest.main()
