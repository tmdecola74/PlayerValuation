import unittest,tempfile,argparse,copy,csv,json
from pathlib import Path
from unittest.mock import patch
import duckdb
import expanded_statcast_v1_20 as b
from standalone_io_v1_0 import load,dump,sha,tree,csvrows,table

def pq(p,rows):
 js=p.with_suffix('.tmp.json');js.write_text(json.dumps(rows,default=str))
 with duckdb.connect() as db:db.read_json(str(js)).write_parquet(str(p))
 js.unlink()
def manifest(p):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',tree(p))
def pitches(y=2021):
 rows=[]
 for i in range(120):
  # 2 in-play contacts, one in-zone miss, one out-of-zone foul, two takes.
  for j,(desc,kind,zone) in enumerate([('hit_into_play','X',5),('hit_into_play','X',12),('swinging_strike','S',5),('foul','S',12),('called_strike','S',5),('ball','B',12)]):
   contact=j<2
   rows.append(dict(game_pk=y,at_bat_number=i*6+j+1,pitch_number=1,game_date=f'{y}-04-01',game_type='R',batter=10,pitcher=20,description=desc,type=kind,zone=zone,stand='R' if j==0 else 'L',bb_type='fly_ball' if j==0 else 'line_drive' if j==1 else None,launch_angle=20. if contact else None,launch_speed_angle=6 if j==0 else 3 if j==1 else None,hc_x=80. if j==0 else 170. if j==1 else None,hc_y=100. if contact else None,pitch_type='FF' if j%2==0 else 'SL',release_speed=95.,release_spin_rate=2300.,release_extension=6.,pfx_x=-.8,pfx_z=1.2,release_pos_x=-2.,release_pos_z=6.))
 return rows

def fixture(p,years=(2020,2021,2025),omit=()):
 m=p/'matrix';m.mkdir();archive=p/'archive';archive.mkdir();windows=[]
 for y in years:
  rows=pitches(y);rp=archive/f'{y}.csv';pp=archive/f'{y}.parquet';sp=archive/f'{y}.schedule.json'
  raw=[dict(r,bat_speed=72.) for r in rows];b.emit(rp,raw);pq(pp,[{k:v for k,v in r.items() if k not in omit} for r in rows]);dump(sp,{'fixture':True})
  windows.append(dict(day=f'{y}-04-01',status='COMPLETE',rows=len(rows),raw_path=str(rp),raw_hash=sha(rp),parquet_path=str(pp),parquet_hash=sha(pp),schedule_path=str(sp),schedule_hash=sha(sp)))
 # Future manifest evidence must never be opened.
 windows.append(dict(day='2026-04-01',status='COMPLETE',rows=1,parquet_path=str(p/'DO_NOT_OPEN_2026.parquet')))
 dump(m/'source_windows.json',windows);dump(m/'effective_config.json',dict(source_seasons=list(years),holdout_target_season=2026,window_start_mmdd='04-01',window_end_mmdd='04-01'));dump(m/'feature_schema.json',dict(predictor_allowlist=[]))
 rows=[]
 for y in [2021,2022,2026]:
  for role,pid in [('hitter','10'),('pitcher','20'),('hitter','99')]:rows.append(dict(target_season=y,player_type=role,mlbam_id=pid,history_seasons=2,age_at_target_estimate=28,max_source_season=y-1,source_cutoff=f'{y-1}-12-31'))
 pq(m/'training_features.parquet',[r for r in rows if r['target_season']<2026]);pq(m/'holdout_features.parquet',[r for r in rows if r['target_season']==2026]);manifest(m);cp=p/'config.json';dump(cp,b.DEFAULT)
 return argparse.Namespace(matrix=m,config=cp,output=p/'out',backup_root=p/'backups'),windows

def aggregates_for(p,rows):
 a,ww=fixture(p,years=(2021,));pp=Path(ww[0]['parquet_path']);pq(pp,rows);ww[0]['parquet_hash']=sha(pp);ww[0]['rows']=len(rows)
 with duckdb.connect() as db:
  b.prepare(db,ww[:1],2021,[],[],[]);return list(b.aggregates(db,b.DEFAULT))

class Metrics(unittest.TestCase):
 def test_zone_contact_swinging_strike_and_pull_handedness(self):
  with tempfile.TemporaryDirectory() as t:
   ar=aggregates_for(Path(t),pitches());r=next(r for role,r in ar if role=='hitter' and r['pitch_group']=='ALL');f={x['metric']:x for x in b.feature_rows(2021,'hitter',r,b.DEFAULT)}
   self.assertAlmostEqual(f['zone_contact_pct']['value'],.5);self.assertAlmostEqual(f['outside_zone_contact_pct']['value'],1.);self.assertAlmostEqual(f['whiff_pct']['value'],.25);self.assertAlmostEqual(f['chase_pct']['value'],2/3);self.assertAlmostEqual(f['pull_proxy_pct']['value'],1.);self.assertAlmostEqual(f['pulled_air_proxy_per_bbe']['value'],1.)
   self.assertAlmostEqual(f['pulled_barrel_proxy_per_bbe']['value'],.5);self.assertAlmostEqual(f['pulled_barrel_proxy_per_barrel']['value'],1.)
 def test_launch_distribution_and_air_definition(self):
  with tempfile.TemporaryDirectory() as t:
   ar=aggregates_for(Path(t),pitches());r=next(r for role,r in ar if role=='hitter' and r['pitch_group']=='ALL');f={x['metric']:x for x in b.feature_rows(2021,'hitter',r,b.DEFAULT)}
   self.assertAlmostEqual(f['launch_angle_mean']['value'],20.);self.assertAlmostEqual(f['launch_angle_sd']['value'],0.);self.assertAlmostEqual(f['air_pct']['value'],1.);self.assertAlmostEqual(f['fb_pct']['value'],.5)
 def test_pitch_type_usage_sums_to_one_and_raw_movement_units(self):
  with tempfile.TemporaryDirectory() as t:
   ar=aggregates_for(Path(t),pitches());rows=[x for role,r in ar if role=='pitcher' and r['pitch_group']!='ALL' for x in b.feature_rows(2021,role,r,b.DEFAULT)]
   self.assertAlmostEqual(sum(x['value'] for x in rows if x['metric']=='pitch_type_usage'),1.)
   self.assertTrue(all(abs(x['value']+.8)<1e-12 for x in rows if x['metric']=='pfx_x_mean'))
 def test_invalid_and_missing_measurements_not_zero(self):
  with tempfile.TemporaryDirectory() as t:
   r=pitches()
   for x in r:x['launch_angle']=999.;x['zone']=10;x['hc_x']=None
   ar=aggregates_for(Path(t),r);v=next(v for role,v in ar if role=='hitter' and v['pitch_group']=='ALL');f={x['metric']:x for x in b.feature_rows(2021,'hitter',v,b.DEFAULT)}
   for m in ['launch_angle_mean','zone_contact_pct','pull_proxy_pct']:self.assertIsNone(f[m]['value']);self.assertIsNone(f[m]['raw_value'])
 def test_zero_measured_event_rate_valid(self):
  with tempfile.TemporaryDirectory() as t:
   r=pitches()
   for x in r:
    if x['description']=='swinging_strike':x['description']='foul'
   ar=aggregates_for(Path(t),r);v=next(v for role,v in ar if role=='hitter' and v['pitch_group']=='ALL');f={x['metric']:x for x in b.feature_rows(2021,'hitter',v,b.DEFAULT)};self.assertEqual(f['whiff_pct']['value'],0.)
 def test_conditional_coverage_not_event_frequency(self):
  with tempfile.TemporaryDirectory() as t:
   ar=aggregates_for(Path(t),pitches());v=next(v for role,v in ar if role=='hitter' and v['pitch_group']=='ALL');f={x['metric']:x for x in b.feature_rows(2021,'hitter',v,b.DEFAULT)}
   self.assertEqual(f['zone_contact_pct']['coverage'],1.);self.assertEqual(f['chase_pct']['coverage'],1.);self.assertNotEqual(f['zone_contact_pct']['denominator'],f['zone_contact_pct']['coverage_opportunities'])
 def test_duplicate_physical_pitches_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=pitches();r.append(dict(r[0]))
   with self.assertRaisesRegex(ValueError,'Duplicate physical'):aggregates_for(Path(t),r)
 def test_two_inplay_outcomes_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   r=pitches();r[1]['at_bat_number']=r[0]['at_bat_number'];r[1]['pitch_number']=2
   with self.assertRaisesRegex(ValueError,'Multiple in-play'):aggregates_for(Path(t),r)
 def test_missing_optional_columns_keep_bases_unknown(self):
  with tempfile.TemporaryDirectory() as t:
   r=[{k:v for k,v in x.items() if k not in ['bb_type','launch_angle','hc_x','hc_y']} for x in pitches()];ar=aggregates_for(Path(t),r);v=next(v for role,v in ar if role=='hitter' and v['pitch_group']=='ALL');f={x['metric']:x for x in b.feature_rows(2021,'hitter',v,b.DEFAULT)}
   self.assertIsNone(f['air_pct']['value']);self.assertIsNone(f['launch_angle_mean']['value']);self.assertEqual(f['air_pct']['denominator'],0)

 def test_unknown_pitch_labels_coalesce_to_one_bucket(self):
  with tempfile.TemporaryDirectory() as t:
   r=pitches()
   for i,x in enumerate(r):x['pitch_type']=None if i%2 else ' '
   ar=aggregates_for(Path(t),r);rows=[x for role,x in ar if role=='pitcher' and x['pitch_group']!='ALL'];self.assertEqual(len(rows),1);self.assertEqual(rows[0]['pitch_group'],'UNKNOWN')

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.a,cls.w=fixture(cls.p);cls.before=tree(cls.a.matrix);cls.report=b.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_complete_backup_readonly_and_2021_retained(self):
  self.assertEqual(self.before,tree(self.a.matrix));self.assertEqual(tree(self.a.output),tree(Path(self.report['backup'])));self.assertFalse(self.report['models_fitted']);self.assertTrue(csvrows(self.a.output/'transition_2021_availability.csv'))
 def test_source_lags_and_null_population_never_invent_zero(self):
  r=table(self.a.output/'training_expanded_features.parquet');self.assertTrue(all(x['source_season']==x['target_season']-x['lag'] for x in r));unknown=[x for x in r if x['mlbam_id']=='99'];self.assertTrue(unknown);self.assertTrue(all(x['value'] is None for x in unknown));self.assertTrue(all(x['target_season']<=2025 for x in r))
  r=table(self.a.output/'holdout_expanded_features.parquet');self.assertTrue(all(x['target_season']==2026 and x['source_season']<=2025 for x in r))
 def test_bat_tracking_raw_only_and_no_guessed_features(self):
  r=csvrows(self.a.output/'schema_availability.csv');self.assertTrue(any(x['column']=='bat_speed' and x['status']=='RAW_ONLY_SCHEMA_RECOVERY_CANDIDATE' for x in r));contract=load(self.a.output/'feature_contract.json');self.assertFalse(any('squared' in m for m in contract['new_metric_names']));self.assertEqual(len(csvrows(self.a.output/'supplemental_download_plan.csv')),9)
 def test_raw_only_geometry_recoverable_without_download(self):
  with tempfile.TemporaryDirectory() as t:
   a,w=fixture(Path(t),years=(2021,),omit=('hc_x',));b.build(a);r=csvrows(a.output/'schema_availability.csv');self.assertTrue(any(x['column']=='hc_x' and x['status']=='RAW_ONLY_SCHEMA_RECOVERY_CANDIDATE' for x in r));f=csvrows(a.output/'expanded_features_season.csv');self.assertTrue(all(x['value']=='' for x in f if x['metric']=='pull_proxy_pct'))
 def test_no_labels_or_future_archive_opened(self):
  with tempfile.TemporaryDirectory() as t:
   a,w=fixture(Path(t));original=Path.open
   def guard(path,*args,**kwargs):
    if 'labels' in path.name or 'DO_NOT_OPEN_2026' in path.name:raise AssertionError('Forbidden source read')
    return original(path,*args,**kwargs)
   with patch.object(Path,'open',guard):b.build(a)
 def test_tampered_source_rejected_without_output(self):
  with tempfile.TemporaryDirectory() as t:
   a,w=fixture(Path(t));Path(w[0]['raw_path']).write_text('tamper')
   with self.assertRaises(ValueError):b.build(a)
   self.assertFalse(a.output.exists())
 def test_output_guard_and_fixed_config(self):
  with self.assertRaises(FileExistsError):b.build(self.a)
  with tempfile.TemporaryDirectory() as t:
   a,w=fixture(Path(t));dump(a.config,dict(b.DEFAULT,minimum_bbe=1))
   with self.assertRaises(ValueError):b.build(a)
 def test_interruption_cleans_stage(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,w=fixture(p)
   with patch.object(b,'finish',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):b.build(a)
   self.assertFalse(a.output.exists());self.assertFalse(list(p.glob('out.staging-*')))
 def test_future_context_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   a,w=fixture(Path(t),years=(2021,));r=table(a.matrix/'training_features.parquet');r[0]['max_source_season']=r[0]['target_season'];pq(a.matrix/'training_features.parquet',r);manifest(a.matrix)
   with self.assertRaisesRegex(ValueError,'chronological'):b.build(a)
   self.assertFalse(a.output.exists())
 def test_no_raw_value_imputation_bypass_in_lag_addons(self):
  r=table(self.a.output/'training_expanded_features.parquet');self.assertTrue(all('raw_value' not in x and 'numerator' not in x for x in r))
 def test_present_bat_fields_are_audited_not_used(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,w=fixture(p,years=(2021,));r=pitches();r=[dict(x,bat_speed=75.,squared_up=1.) for x in r];pq(Path(w[0]['parquet_path']),r);w[0]['parquet_hash']=sha(w[0]['parquet_path']);dump(a.matrix/'source_windows.json',w);manifest(a.matrix);b.build(a)
   bat=csvrows(a.output/'bat_tracking_field_inventory.csv');self.assertTrue(any(x['column']=='squared_up' and int(x['finite_numeric_rows'])==720 for x in bat));self.assertFalse(any('squared' in x['metric'] for x in table(a.output/'training_expanded_features.parquet')))
if __name__=='__main__':unittest.main()
