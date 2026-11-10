import unittest,tempfile,argparse,copy,json,csv
from pathlib import Path
from unittest.mock import patch
import duckdb
import leaderboard_core_v1_21 as core
import import_statcast_leaderboards_v1_21 as b
from standalone_io_v1_0 import load,dump,sha,tree,write,table,csvrows

def pq(p,rows):
 js=p.with_suffix('.tmp.json');js.write_text(json.dumps(rows,default=str))
 with duckdb.connect() as db:db.read_json(str(js)).write_parquet(str(p))
 js.unlink()
def manifest(p):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',tree(p))
def raw(family,y=2024,pid='10'):
 if family=='batted_ball':
  r=dict(id=pid,name='Example Player',year=str(y),bbe='100');r.update({m:'0' for m in core.BB_RATES});r.update(gb_rate='.5',air_rate='.5',fb_rate='.2',ld_rate='.2',pu_rate='.1',pull_rate='.4',straight_rate='.3',oppo_rate='.3',pull_gb_rate='.2',straight_gb_rate='.15',oppo_gb_rate='.15',pull_air_rate='.2',straight_air_rate='.15',oppo_air_rate='.15');return r
 if family=='bat_tracking':
  return dict(id=pid,name='Example Player',year=str(y),swings_competitive='200',percent_swings_competitive='.9',contact='100',avg_bat_speed='70',hard_swing_rate='.2',squared_up_per_bat_contact='.4',squared_up_per_swing='.2',blast_per_bat_contact='.2',blast_per_swing='.1',swing_length='7',swords='2',batter_run_value='-1.5',whiffs='100',whiff_per_swing='.5',batted_ball_events='50',batted_ball_event_per_swing='.25')
 if family=='exit_velocity':return dict(zip(core.COLUMNS[family],['Example Player',pid,'100']+[str(x) for x in [10,115,90,100,95,85,450,180,400]]+[str(x) for x in [40,50,10,5]]+['50','10']))
 r=dict(player_id=pid,entity_name='Example Player',team_name='AAA',start_year=str(y),end_year=str(y));r.update({m:'30' for m in core.RUN_COUNTS});r.update({m:'-1.5' for m in core.RUN_VALUES});return r

def source(family,role='hitter',y=2024):return dict(source_id=role+'_'+family,file=role+'_'+family+'.csv',family=family,player_type=role,season=y,expected_seasons=[2023,2024,2025,2026],expected_sha256='fixture')
def normalize(family,r=None,role='hitter'):
 rows,issues=core.normalize(r or raw(family),source(family,role),2,core.DEFAULT);return {x['metric']:x for x in rows},issues

def fixture(p):
 inp=p/'input';m=p/'matrix';e=p/'expanded'
 for d in [inp,m,e]:d.mkdir()
 sources=[]
 for family in core.COLUMNS:
  for role in ['hitter','pitcher'] if family!='baserunning' else ['hitter']:
   s=source(family,role);rr=[raw(family,y,'10' if role=='hitter' else '20') for y in [2023,2024,2025,2026]] if family!='exit_velocity' else [raw(family,2024,'10' if role=='hitter' else '20')]
   b.emit(inp/s['file'],rr);s['expected_sha256']=sha(inp/s['file']);sources.append(s)
 cfg=p/'config.json';dump(cfg,dict(settings=core.DEFAULT,sources=sources))
 dump(m/'source_windows.json',[]);pop=[]
 for y in [2021,2024,2025,2026]:
  for role,pid in [('hitter','10'),('hitter','99'),('pitcher','20')]:pop.append(dict(target_season=y,player_type=role,mlbam_id=pid,history_seasons=2,age_at_target_estimate=28,max_source_season=y-1,source_cutoff=f'{y-1}-12-31'))
 for split in ['training','holdout']:pq(m/(split+'_features.parquet'),[r for r in pop if (r['target_season']==2026)==(split=='holdout')])
 classic=[];ar=[]
 for y in [2023,2024,2025]:
  for role,pid in [('hitter','10'),('pitcher','20')]:
   for metric,value in [('gb_pct',.5),('air_pct',.5),('fb_pct',.2),('ld_pct',.2),('popup_pct',.1),('pull_proxy_pct',.4),('pulled_air_proxy_per_bbe',.2),('launch_angle_mean',10.),('launch_angle_8_32_pct',.4)]:ar.append(dict(source_season=y,player_type=role,mlbam_id=pid,metric=metric,raw_value=value,denominator=100.,opportunities=100.,coverage=1.))
   for metric,value in [('ev',90.),('hardhit_pct',.5),('barrel_pct',.1)]:classic.append(dict(source_season=y,player_type=role,mlbam_id=pid,measurement=metric,raw_value=value,observations=100.,opportunities=100.,coverage=1.))
 b.emit(m/'measurement_player_season_audit.csv',classic);manifest(m);pq(e/'expanded_features_season.parquet',ar);dump(e/'expanded_feature_report.json',dict(version='1.20.0',models_fitted=False,accepted_matrix_modified=False));dump(e/'input_hashes.json',{str((m/'source_windows.json').resolve()):sha(m/'source_windows.json')});manifest(e)
 return argparse.Namespace(input_dir=inp,config=cfg,matrix=m,expanded=e,output=p/'out',backup_root=p/'backups')

class Units(unittest.TestCase):
 def test_fraction_vs_percentage_and_ev50_roles(self):
  bb,_=normalize('batted_ball');ev,_=normalize('exit_velocity');pitch,_=normalize('exit_velocity',role='pitcher');self.assertEqual(bb['pull_air_rate']['value'],.2);self.assertEqual(ev['anglesweetspotpercent']['value'],.4);self.assertEqual(ev['ev50']['definition'],'EV50_HARDEST_HALF');self.assertEqual(pitch['ev50']['definition'],'EV50_SOFTEST_HALF_ALLOWED')
 def test_missing_zero_and_small_sample(self):
  r=raw('exit_velocity');r['barrels']='0';r['brl_percent']='0';v,_=normalize('exit_velocity',r);self.assertEqual(v['brl_percent']['value'],0.)
  r['avg_hit_speed']='';v,_=normalize('exit_velocity',r);self.assertIsNone(v['avg_hit_speed']['value'])
  r['attempts']='1';r['ev95plus']='0';v,_=normalize('exit_velocity',r);self.assertIsNone(v['ev50']['value'])
 def test_signed_baserunning_preserved_not_sb_counts(self):
  r,_=normalize('baserunning');self.assertEqual(r['runner_runs_tot']['normalized_value'],-1.5);self.assertIsNone(r['runner_runs_tot']['value']);self.assertEqual(r['runner_runs_tot']['sample_basis'],'RECORDED_MOVEMENTS_NOT_ALL_OPPORTUNITIES')
 def test_unexported_denominators_not_invented(self):
  r,_=normalize('exit_velocity');self.assertIsNone(r['brl_pa']['value']);self.assertIsNone(r['brl_pa']['denominator']);r,_=normalize('bat_tracking');self.assertIsNone(r['percent_swings_competitive']['value'])
 def test_distinct_bat_denominators_partial_2023(self):
  r,_=normalize('bat_tracking',raw('bat_tracking',2023));self.assertEqual(r['squared_up_per_bat_contact']['denominator'],100);self.assertEqual(r['squared_up_per_swing']['denominator'],200);self.assertIn('PARTIAL',r['avg_bat_speed']['period_scope'])
 def test_missing_year_multi_year_or_invalid_ids_rejected(self):
  r=raw('baserunning');r['end_year']='2025'
  with self.assertRaises(ValueError):normalize('baserunning',r)
  r=raw('bat_tracking');r['id']='0'
  with self.assertRaises(ValueError):normalize('bat_tracking',r)
 def test_count_rate_disagreement_held_for_review_not_corrected(self):
  r=raw('exit_velocity');r['ev95percent']='51';v,issues=normalize('exit_velocity',r);self.assertTrue(issues);self.assertEqual(v['ev95percent']['normalized_value'],.51);self.assertIsNone(v['ev95percent']['value']);self.assertEqual(v['ev95plus']['raw_value'],50.)
 def test_bad_bat_count_exceeds_denominator_rejected(self):
  r=raw('bat_tracking');r['contact']='201'
  with self.assertRaises(ValueError):normalize('bat_tracking',r)
 def test_out_of_range_rate_not_silently_clipped(self):
  r=raw('batted_ball');r['pull_rate']='1.5';v,issues=normalize('batted_ball',r);self.assertEqual(v['pull_rate']['normalized_value'],1.5);self.assertIsNone(v['pull_rate']['value']);self.assertTrue(issues)
 def test_ev_year_explicit_registration(self):
  s=source('exit_velocity',y=2025);self.assertEqual(core.row_key(raw('exit_velocity'),s)[2],2025)
 def test_source_2026_row_has_no_historical_year_guess(self):
  self.assertEqual(core.row_key(raw('bat_tracking',2026),source('bat_tracking'))[2],2026)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.a=fixture(cls.p);cls.before={n:tree(getattr(cls.a,n)) for n in ['input_dir','matrix','expanded']};cls.report=b.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_complete_backup_source_preservation(self):
  self.assertEqual(tree(self.a.output),tree(Path(self.report['backup'])))
  for n,v in self.before.items():self.assertEqual(v,tree(getattr(self.a,n)))
  self.assertFalse(self.report['models_fitted']);self.assertFalse(self.report['source_counts_replaced'])
 def test_2026_quarantine_and_historical_lags(self):
  h=table(self.a.output/'historical/leaderboard_features.parquet');q=table(self.a.output/'quarantine_2026/leaderboard_features.parquet');self.assertTrue(all(r['source_season']<=2025 for r in h));self.assertTrue(all(r['source_season']==2026 for r in q));r=table(self.a.output/'holdout_leaderboard_features.parquet');self.assertTrue(all(x['source_season']<x['target_season']==2026 for x in r))
 def test_missing_players_and_early_years_stay_null(self):
  r=table(self.a.output/'training_leaderboard_features.parquet');unknown=[x for x in r if x['mlbam_id']=='99' or x['target_season']==2021];self.assertTrue(unknown);self.assertTrue(all(x['value'] is None for x in unknown));self.assertTrue(all('raw_value' not in x and 'normalized_value' not in x for x in r))
 def test_reconciliation_no_automatic_proxy_certification(self):
  r=csvrows(self.a.output/'reconciliation_details.csv');self.assertTrue(any(x['status']=='PROXY_MATCH_NOT_CERTIFICATION' for x in r));self.assertTrue(any(x['status']=='MATCH_WITHIN_ROUNDING_TOLERANCE' for x in r));self.assertTrue(all(x['counts_replaced']=='False' for x in r))
 def test_no_target_labels_opened(self):
  p=self.p/'second';original=Path.open
  def guard(path,*a,**kw):
   if 'labels' in path.name:raise AssertionError('Target labels opened')
   return original(path,*a,**kw)
  with patch.object(Path,'open',guard):b.build(argparse.Namespace(**dict(vars(self.a),output=p)))
 def test_source_tamper_and_duplicate_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   a=fixture(Path(t));p=next(a.input_dir.glob('*.csv'));p.write_text('tamper')
   with self.assertRaises(ValueError):b.build(a)
   self.assertFalse(a.output.exists())
  with tempfile.TemporaryDirectory() as t:
   a=fixture(Path(t));c=load(a.config);s=c['sources'][0];p=a.input_dir/s['file'];r=csvrows(p);b.emit(p,r+[r[0]]);s['expected_sha256']=sha(p);dump(a.config,c)
   with self.assertRaisesRegex(ValueError,'Duplicate source'):b.build(a)
 def test_current_2026_mutation_cannot_change_lag_values(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);b.build(a);c=load(a.config)
   for s in c['sources']:
    if s['family']=='bat_tracking':
     f=a.input_dir/s['file'];r=csvrows(f)
     for x in r:
      if x['year']=='2026':x['avg_bat_speed']='99'
     b.emit(f,r);s['expected_sha256']=sha(f)
   dump(a.config,c);second=p/'second';b.build(argparse.Namespace(**dict(vars(a),output=second)))
   for name in ['training_leaderboard_features.parquet','holdout_leaderboard_features.parquet']:self.assertEqual(table(a.output/name),table(second/name))
 def test_output_guard_and_interruption_cleanup(self):
  with self.assertRaises(FileExistsError):b.build(self.a)
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p)
   with patch.object(b,'finish',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):b.build(a)
   self.assertFalse(a.output.exists());self.assertFalse(list(p.glob('out.staging-*')))
 def test_future_population_context_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   a=fixture(Path(t));r=table(a.matrix/'training_features.parquet');r[0]['max_source_season']=r[0]['target_season'];pq(a.matrix/'training_features.parquet',r);manifest(a.matrix)
   with self.assertRaisesRegex(ValueError,'prior-history'):b.build(a)
   self.assertFalse(a.output.exists())
 def test_no_name_matching_or_population_expansion(self):
  pop=csvrows(self.a.output/'frozen_population_audit.csv');self.assertEqual({r['mlbam_id'] for r in pop},{'10','20','99'});self.assertTrue(all(r['source']=='EXISTING_FROZEN_PRIOR_HISTORY_POPULATION' for r in pop))
if __name__=='__main__':unittest.main()
