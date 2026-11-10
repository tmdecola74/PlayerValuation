import unittest,tempfile,argparse,json,copy,shutil
from pathlib import Path
from datetime import date,timedelta
from unittest.mock import patch
import duckdb
import audit_statcast_scope_v1_22 as b
from standalone_io_v1_0 import dump,load,sha,tree,write,csvrows

def manifest(p):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',tree(p))
def pq(path,rows):
 j=path.with_suffix('.json.tmp');dump(j,rows)
 with duckdb.connect() as db:db.read_json(str(j)).write_parquet(str(path))
 j.unlink()
def sample(y):
 return [dict(game_pk=y,at_bat_number=i+1,pitch_number=1,game_date=f'{y}-04-01',game_type='R',batter=10,pitcher=20,type='X',description='hit_into_play',launch_speed=None if i==119 else 100. if i<60 else 80.,launch_angle=20.,launch_speed_angle=None if i==119 else 6 if i<30 else 3,stand='R',bb_type='fly_ball',hc_x=80.,hc_y=100.,events='field_out') for i in range(120)]

def fixture(p):
 lb=p/'leaderboards';m=p/'matrix';e=p/'expanded';archive=p/'archive'
 for root in [lb,m,e,archive]:root.mkdir()
 (lb/'historical').mkdir();(lb/'source_snapshots').mkdir();hist=[];recon=[];flags=[];sources=[];windows=[]
 for y in b.DEFAULT['source_seasons']:
  day=date(y,3,1)
  while day<=date(y,11,1):
   stem=archive/day.isoformat();raw=stem.with_suffix('.csv');pp=stem.with_suffix('.parquet');sp=stem.with_suffix('.schedule.json');active=day.isoformat()==f'{y}-04-01'
   raw.write_text('fixture raw',encoding='utf-8');dump(sp,{'fixture':True})
   if active:pq(pp,sample(y))
   else:pp.write_bytes(b'EMPTY_NOT_SCANNED')
   windows.append(dict(day=day.isoformat(),status='COMPLETE',rows=120 if active else 0,raw_path=str(raw.resolve()),raw_hash=sha(raw),parquet_path=str(pp.resolve()),parquet_hash=sha(pp),schedule_path=str(sp.resolve()),schedule_hash=sha(sp)))
   day+=timedelta(days=1)
 # Future path deliberately absent: the audit must never attempt to hash/open it.
 windows.append(dict(day='2026-04-01',status='COMPLETE',rows=1,parquet_path=str(p/'DO_NOT_OPEN_2026.parquet')))
 dump(m/'source_windows.json',windows);dump(m/'effective_config.json',dict(source_seasons=[2015,2023,2024,2025],holdout_target_season=2026));manifest(m)
 bank={}
 with duckdb.connect() as db:
  for y in b.DEFAULT['source_seasons']:bank.update(b.prepare(db,windows,y,b.DEFAULT))
 for y in b.DEFAULT['source_seasons']:
  for role,pid in [('hitter','10'),('pitcher','20')]:
   source_id=f'{role}_ev_{y}';ar=bank[y,role,pid]
   raw=dict(player_id=pid,attempts='120',ev95plus='60',barrels='30',ev95percent='50.4',brl_percent='25',avg_hit_speed=str(ar['ev']+1),avg_hit_angle='21',anglesweetspotpercent='100')
   path=lb/'source_snapshots'/f'{source_id}.csv';b.emit(path,[raw]);sources.append(dict(source_id=source_id,file=path.name,family='exit_velocity',player_type=role,registered_season=y,sha256=sha(path)))
   for metric,text in raw.items():
    if metric=='player_id':continue
    val=float(text);normal=val/100 if metric in ['ev95percent','brl_percent','anglesweetspotpercent'] else val
    eligible=metric!='ev95percent'
    hist.append(dict(source_season=y,player_type=role,mlbam_id=pid,family='exit_velocity',metric=metric,feature='ev_'+metric,source_id=source_id,raw_text=text,raw_value=val,normalized_value=normal,denominator=120.,eligible=eligible,reason='SOURCE_RELATIONSHIP_REVIEW_REQUIRED' if not eligible else 'AVAILABLE_FIXED_SAMPLE_CONTROL'))
    if metric in b.REPLAY:
     vf,df=b.REPLAY[metric];value=ar[vf];tol=b.DEFAULT['mean_tolerance'] if metric in ['avg_hit_speed','avg_hit_angle'] else b.DEFAULT['rate_tolerance']
     recon.append(dict(source_season=y,player_type=role,mlbam_id=pid,family='exit_velocity',metric=metric,source_id=source_id,export_original=text,export_normalized=normal,export_denominator=120.,archive_value=value,archive_observations=ar[df],archive_bbe=ar['bbe'],value_difference=normal-value,review_tolerance=tol,status='MATCH_WITHIN_ROUNDING_TOLERANCE' if abs(normal-value)<=tol else 'VALUE_DIFFERENCE_SCOPE_UNVERIFIED'))
   flags.append(dict(source_season=y,player_type=role,mlbam_id=pid,source_id=source_id,metric='ev95percent',code='COUNT_RATE_DIFFERENCE_BEYOND_ROUNDING',detail='Preserved original flag',split='historical'))
 # Same-named metrics from different families cannot collide in the decision overlay.
 hist.append(dict(source_season=2025,player_type='hitter',mlbam_id='10',family='bat_tracking',metric='avg_bat_speed',feature='bat_speed',source_id='bat_fixture',raw_text='70',raw_value=70.,normalized_value=70.,denominator=200.,eligible=True,reason='AVAILABLE_FIXED_SAMPLE_CONTROL'))
 pq(lb/'historical/leaderboard_features.parquet',hist);b.emit(lb/'reconciliation_details.csv',recon);b.emit(lb/'normalization_review.csv',flags)
 dump(lb/'leaderboard_build_report.json',dict(version='1.21.0',models_fitted=False,accepted_projection_source_modified=False));dump(lb/'source_inventory.json',dict(sources=sources))
 pq(e/'expanded_features_season.parquet',[dict(source_season=2025,metric='fixture')]);dump(e/'expanded_feature_report.json',dict(version='1.20.0',models_fitted=False,accepted_matrix_modified=False));dump(e/'input_hashes.json',{str((m/'source_windows.json').resolve()):sha(m/'source_windows.json')});manifest(e)
 dump(lb/'input_hashes.json',{str((m/'source_windows.json').resolve()):sha(m/'source_windows.json'),str((e/'expanded_features_season.parquet').resolve()):sha(e/'expanded_features_season.parquet')});manifest(lb)
 cp=p/'config.json';dump(cp,b.DEFAULT)
 return argparse.Namespace(leaderboards=lb,matrix=m,expanded=e,config=cp,output=p/'out',backup_root=p/'backups')

def denominator(metric='ev95percent',rate=.4,n=2,measured=4,total=5,count=2):
 r=dict(source_season=2023,player_type='hitter',mlbam_id='10',metric=metric,source_id='s',export_normalized=rate,archive_value=n/measured if measured else None,archive_observations=measured,archive_bbe=total,value_difference=rate-n/measured if measured else None,review_tolerance=.0005001)
 mm={'attempts':dict(raw_value=total),'ev95plus':dict(raw_value=count),'barrels':dict(raw_value=count)}
 a=dict(bbe=total,hardhit=n,barrels=n,ev_n=measured,barrel_n=measured)
 return b.denominator_row(r,mm,a,b.DEFAULT)

class Units(unittest.TestCase):
 def test_windows_manifest_keys_normalize_without_weakening_hash(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);(root/'historical').mkdir();p=root/'historical'/'example.txt';p.write_text('frozen',encoding='utf-8');dump(root/'output_sha256.json',{'historical\\example.txt':sha(p)})
   watched={};self.assertEqual(b.checked(root,'historical/example.txt',watched),p.resolve());self.assertEqual(b.checked(root,'historical\\example.txt',watched),p.resolve())
   p.write_text('tampered',encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'hash'):b.checked(root,'historical/example.txt',{})
 def test_ambiguous_or_unsafe_manifest_paths_rejected(self):
  with self.assertRaisesRegex(ValueError,'Ambiguous'):b.portable_manifest({'a/b':'one','a\\b':'one'})
  for name in ['../outside','a\\..\\outside','C:\\outside','/outside','a//b']:
   with self.subTest(name=name):
    with self.assertRaisesRegex(ValueError,'Unsafe'):b.portable_manifest({name:'hash'})
 def test_same_numerator_two_denominators(self):
  r=denominator();self.assertEqual(r['status'],'RATE_MATCHES_TOTAL_BBE_ONLY');self.assertEqual(r['archive_rate_measured'],.5);self.assertFalse(r['measured_denominator_matches_export_bbe']);self.assertTrue(r['total_bbe_counts_match']);self.assertFalse(r['counts_replaced'])
 def test_count_difference_never_explained_by_rate_match(self):
  r=denominator(count=3);self.assertEqual(r['status'],'NUMERATOR_DIFFERENCE');self.assertFalse(r['export_count_matches_archive'])
 def test_measured_only_and_unresolved_are_distinct(self):
  self.assertEqual(denominator(rate=.5)['status'],'RATE_MATCHES_MEASURED_ONLY')
  r=denominator(rate=.45);self.assertEqual(r['status'],'RATE_DEFINITION_UNRESOLVED');self.assertEqual(r['compatible_integer_denominator_count'],0)
 def test_zero_event_valid_missing_denominator_not_zero(self):
  r=denominator(rate=0,n=0,count=0);self.assertEqual(r['archive_rate_total_bbe'],0.)
  self.assertIsNone(b.ratio(0,0));self.assertIsNone(b.ratio(None,5))
 def test_fraction_rounding_units_and_candidates_not_membership(self):
  r=denominator(rate=.333,n=1,measured=3,total=3,count=1);self.assertEqual(r['status'],'RATE_MATCHES_BOTH_DENOMINATORS');self.assertEqual(r['compatible_integer_denominator_min'],3)
  self.assertIsNone(b.num('null'));self.assertIsNone(b.num(''))
 def test_top_targets_fixed_by_metric_role_year_and_sample(self):
  rr=[dict(source_season=2023,player_type='hitter',mlbam_id=str(i+1),metric='avg_hit_speed',export_denominator=200 if i else 10,value_difference=100-i,review_tolerance=.05) for i in range(8)]
  t=b.choose_targets(rr,[],b.DEFAULT);self.assertEqual(len(t),5);self.assertNotIn((2023,'hitter','1'),t)
 def test_decisions_do_not_release_held_masks_or_certify_proxy(self):
  h={(2023,'hitter','10'):{('exit_velocity','ev95percent'):dict(family='exit_velocity',eligible=False,feature='hh',source_id='s',reason='SOURCE_RELATIONSHIP_REVIEW_REQUIRED'),('batted_ball','pull_rate'):dict(family='batted_ball',eligible=True,feature='pull',source_id='s',reason='OK')}}
  r=b.decisions(h,[],[]);self.assertTrue(any(x['audit_decision']=='HELD_EXISTING_SAMPLE_OR_DEFINITION_MASK' for x in r));self.assertTrue(any('SEPARATE_FROM_PROXY' in x['audit_decision'] for x in r));self.assertTrue(all(not x['model_fit_approved'] for x in r))

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.a=fixture(cls.p);cls.before={n:tree(getattr(cls.a,n)) for n in ['leaderboards','matrix','expanded']};cls.report=b.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_readonly_backup_replay_and_counts(self):
  self.assertTrue(self.report['archive_replay_verified']);self.assertEqual(self.report['historical_normalization_flags'],6);self.assertEqual(tree(self.a.output),tree(Path(self.report['backup'])))
  for n,t in self.before.items():self.assertEqual(t,tree(getattr(self.a,n)))
  rows=csvrows(self.a.output/'denominator_count_audit.csv');self.assertTrue(all(x['export_count_matches_archive']=='True' for x in rows));self.assertEqual(len(rows),12)
 def test_entire_pipeline_accepts_windows_generated_manifests(self):
  with tempfile.TemporaryDirectory() as t:
   a=fixture(Path(t));before={}
   for root in [a.leaderboards,a.matrix,a.expanded]:
    mp=root/'output_sha256.json';dump(mp,{name.replace('/','\\'):h for name,h in load(mp).items()});before[root]=tree(root)
   result=b.build(a);self.assertEqual(result['build_implementation_version'],'1.22.1');self.assertTrue(result['archive_replay_verified']);self.assertEqual(result['historical_normalization_flags'],6)
   for root,prior in before.items():self.assertEqual(tree(root),prior)
 def test_trace_reconciles_and_preserves_missing_events(self):
  rows=csvrows(self.a.output/'target_event_trace.csv');self.assertEqual(len(rows),720);self.assertEqual(sum(x['ev_observed']=='False' for x in rows),6);self.assertTrue(all(x['hardhit_event']=='' for x in rows if x['ev_observed']=='False'))
  games=csvrows(self.a.output/'target_game_bridge.csv');self.assertEqual(sum(int(x['bbe']) for x in games),len(rows));self.assertTrue(all(int(x['source_season'])<=2025 for x in rows))
 def test_no_future_source_or_outcome_files_opened(self):
  oldopen=Path.open;oldsha=b.sha
  def guard(p,*args,**kw):
   if any(s in str(p) for s in ['DO_NOT_OPEN','holdout','quarantine_2026','labels']):raise AssertionError('Forbidden file opened')
   return oldopen(p,*args,**kw)
  with patch.object(Path,'open',guard):
   r=b.build(argparse.Namespace(**dict(vars(self.a),output=self.p/'guarded')));self.assertFalse(r['source_2026_pitches_read'])
 def test_config_change_and_output_guard(self):
  with self.assertRaises(FileExistsError):b.build(self.a)
  a=argparse.Namespace(**dict(vars(self.a),output=self.p/'badconfig',config=self.p/'bad.json'));dump(a.config,dict(b.DEFAULT,substantial_bbe=20))
  with self.assertRaisesRegex(ValueError,'controls'):b.build(a)
 def test_interruption_cleanup(self):
  a=argparse.Namespace(**dict(vars(self.a),output=self.p/'interrupted'))
  with patch.object(b,'trace_events',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):b.build(a)
  self.assertFalse(a.output.exists());self.assertFalse(list(self.p.glob('interrupted.staging-*')))
 def test_tamper_rejected_without_output(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);sp=next((a.leaderboards/'source_snapshots').glob('*.csv'));sp.write_text('tamper',encoding='utf-8')
   with self.assertRaisesRegex(ValueError,'hash'):b.build(a)
   self.assertFalse(a.output.exists())
 def test_updated_hash_duplicate_pitch_still_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);ww=load(a.matrix/'source_windows.json');r=next(r for r in ww if r['rows']==120);rows=sample(2023);pq(Path(r['parquet_path']),rows+[rows[0]]);r.update(rows=121,parquet_hash=sha(r['parquet_path']))
   with duckdb.connect() as db:
    with self.assertRaisesRegex(ValueError,'Duplicate physical'):b.prepare(db,ww,2023,b.DEFAULT)
 def test_missing_optional_measurements_not_fabricated(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);rows=[{k:v for k,v in r.items() if k not in ['launch_speed','hc_x','hc_y','launch_speed_angle']} for r in sample(2023)];pp=p/'x.parquet';pq(pp,rows)
   with duckdb.connect() as db:
    ar=b.prepare(db,[dict(day='2023-04-01',rows=120,parquet_path=str(pp))],2023,b.DEFAULT)[2023,'hitter','10'];self.assertIsNone(ar['hardhit_rate']);self.assertIsNone(ar['barrel_rate']);self.assertIsNone(ar['pull_rate']);self.assertEqual(ar['bbe'],120)
 def test_physical_replay_mismatch_prevents_publication(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);r=csvrows(a.leaderboards/'reconciliation_details.csv');r[0]['archive_value']='0';b.emit(a.leaderboards/'reconciliation_details.csv',r);manifest(a.leaderboards)
   with self.assertRaisesRegex(ValueError,'reproduce'):b.build(a)
   self.assertFalse(a.output.exists())
 def test_missing_window_and_wrong_source_binding_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);ww=load(a.matrix/'source_windows.json');dump(a.matrix/'source_windows.json',ww[1:]);manifest(a.matrix)
   with self.assertRaisesRegex(ValueError,'Incomplete'):b.build(a)
   self.assertFalse(a.output.exists())
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);dump(a.expanded/'input_hashes.json',{});manifest(a.expanded)
   with self.assertRaisesRegex(ValueError,'binding'):b.build(a)
   self.assertFalse(a.output.exists())
 def test_null_raw_text_matches_blank_export_without_zero_fill(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);lb=p/'lb';lb.mkdir();(lb/'source_snapshots').mkdir();sp=lb/'source_snapshots'/'ev.csv';b.emit(sp,[dict(player_id='10',avg_hit_speed='')]);dump(lb/'source_inventory.json',dict(sources=[dict(family='exit_velocity',registered_season=2023,source_id='s',player_type='hitter',file=sp.name,sha256=sha(sp))]));manifest(lb)
   history={(2023,'hitter','10'):{('exit_velocity','avg_hit_speed'):dict(source_id='s',raw_text=None,raw_value=None)}}
   self.assertEqual(len(b.check_export_snapshots(lb,history,{},b.DEFAULT)),1)
 def test_unknown_normalization_case_not_silently_dropped(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);rr=csvrows(a.leaderboards/'normalization_review.csv');rr[0]['code']='UNSUPPORTED_NEW_CODE';b.emit(a.leaderboards/'normalization_review.csv',rr);manifest(a.leaderboards)
   with self.assertRaisesRegex(ValueError,'Unsupported historical'):b.build(a)
   self.assertFalse(a.output.exists())

if __name__=='__main__':unittest.main()
