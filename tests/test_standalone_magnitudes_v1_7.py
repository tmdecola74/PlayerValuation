import unittest,tempfile,importlib.util,copy
from pathlib import Path
from unittest.mock import patch
from standalone_magnitude_diagnostics_v1_7 import *
from magnitude_stability_v1_7 import stability
from audit_standalone_magnitudes_v1_7 import build
from standalone_io_v1_0 import load,tree
P=Path(__import__('backtest_standalone_growth_sb_v1_6').__file__).parent
spec=importlib.util.spec_from_file_location('fixture17_previous',P/'tests/test_standalone_growth_sb_v1_6.py');fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)
S={'source_2020_multiplier':2.7,'maximum_OUTS':900,'prior_SB_floor':10}
def pitcher(year=2024,a=180):
 k=(year,'pitcher','1');r={'x_actual_lag1_OUTS':100,'source_season_lag1':year-1,'x_actual_lag1_G':20,'x_actual_lag1_GS':20};an=anchor(r,S);d=dict(anchor=an,baseline=120,candidate=130,selected=120,raw_candidate=130,growth_probability=.5,conditional_growth_OUTS=200,conditional_decline_OUTS=60,participation_probability=1,supported=True,support_status='SUPPORTED');actual={k+('OUTS',):a,k+('G',):20};return k,d,r,actual
class Units(unittest.TestCase):
 def test_growth_and_decline_magnitudes(self):
  k,d,r,a=pitcher();x=pitcher_row(k,d,r,a,S);self.assertEqual(x['predicted_magnitude_OUTS'],100);self.assertEqual(x['observed_magnitude_OUTS'],80);self.assertEqual(x['magnitude_error_OUTS'],20)
  a[k+('OUTS',)]=80;x=pitcher_row(k,d,r,a,S);self.assertEqual(x['observed_branch'],'DECLINE_OR_FLAT');self.assertEqual(x['magnitude_error_OUTS'],20)
 def test_probability_participation_fallback_identity(self):
  k,d,r,a=pitcher();d.update(participation_probability=.8,raw_candidate=104,candidate=120,supported=False);x=pitcher_row(k,d,r,a,S);self.assertAlmostEqual(sum(x[n] for n in ['branch_count_error_OUTS','direction_mixing_effect_OUTS','participation_effect_OUTS','fallback_effect_OUTS']),-60);self.assertEqual(x['component_status'],'AVAILABLE');pitcher_summary([x])
 def test_missing_activity_not_zero(self):
  k,d,r,a=pitcher();del a[k+('G',)];x=pitcher_row(k,d,r,a,S);self.assertIsNone(x['magnitude_error_OUTS']);self.assertEqual(x['candidate_error_OUTS'],-50)
 def test_2021_anchor_visible_and_tamper_rejected(self):
  k,d,r,a=pitcher(2021);x=pitcher_row(k,d,r,a,S);self.assertEqual(x['anchor_OUTS'],270);self.assertEqual(x['prior_observed_OUTS'],100);d['anchor']=100
  with self.assertRaises(ValueError):pitcher_row(k,d,r,a,S)
 def test_probability_edges_and_annual_seasons(self):
  k,d,r,a=pitcher();d['growth_probability']=1;d['raw_candidate']=200;d['candidate']=200;x=pitcher_row(k,d,r,a,S);self.assertEqual(pitcher_summary([x])[2][0]['probability_bin_lower'],.9);choices=[dict(season=y,pitcher={'adopt':False},hitter={'adopt':False}) for y in range(2019,2027)];annual,roll=stability([x],[],choices,2025);self.assertEqual({z['season'] for z in annual},set(range(2019,2026)));self.assertTrue(all('2021' in z['requested_seasons'] for z in roll))
 def test_sb_identity_missing_zero_and_established_outliers(self):
  k=(2024,'hitter','2');r={'x_actual_lag1_SB':15,'x_actual_lag1_PA':400};b=dict(H=100,HR=20,BB=15,HBP=5,PA=500);d=dict(baseline=10,candidate=20,selected=10,raw_candidate=20,projected_onbase_proxy=100,positive_SB_rate=.25,any_SB_probability=.8,supported=True,support_status='SUPPORTED');a={k+(m,):v for m,v in dict(H=80,HR=10,BB=25,HBP=5,PA=400,SB=15).items()};rr=sb_rows(k,d,r,b,a,S)
  for z in rr:self.assertAlmostEqual(z['error'],z['PA_contribution']+z['onbase_yield_contribution']+z['propensity_contribution'])
  ss,tt=sb_summary(rr);self.assertEqual(len({z['membership_sha256'] for z in ss if z['cohort']=='all'}),1);self.assertTrue(largest_sb_misses(rr));del a[k+('HBP',)];rr=sb_rows(k,d,r,b,a,S);self.assertIsNone(rr[0]['actual_onbase_proxy']);self.assertEqual(rr[0]['error'],-5);self.assertTrue(largest_sb_misses(rr));self.assertEqual(sb_summary(rr),([],[]))
  a.update({k+(m,):0 for m in ['H','HR','BB','HBP','SB']});rr=sb_rows(k,d,r,b,a,S);self.assertEqual(rr[0]['status'],'ZERO_DENOMINATOR_RATE_UNKNOWN');self.assertEqual(rr[0]['error'],10)
class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);fx.fixture(cls.p);fx.run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def runbuild(self,name,include=False):
  p=self.p;return build(p/'new16',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/name,p/'backups',include)
 def test_historical_readonly_complete_backup_and_no_fits(self):
  p=self.p;before=tree(p/'new16')
  with patch('standalone_growth_sb_v1_6.fit_models',side_effect=AssertionError('refit forbidden')):r=self.runbuild('audit17')
  self.assertFalse(r['models_fitted']);self.assertEqual(before,tree(p/'new16'));self.assertEqual(tree(p/'audit17'),tree(Path(r['backup'])));self.assertFalse(r['include_2026']);self.assertNotIn('frozen_models.json',tree(p/'audit17'))
  with self.assertRaises((ValueError,FileExistsError)):self.runbuild('audit17')
 def test_historical_does_not_parse_holdout_outcomes(self):
  import standalone_combined_v1_4 as combined
  original=combined.table
  def guarded(path,*args,**kwargs):
   if Path(path).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('Holdout outcomes parsed')
   return original(path,*args,**kwargs)
  with patch.object(combined,'table',side_effect=guarded):self.runbuild('no_holdout17')
 def test_interrupt_cleans_stage_and_source_tamper_rejected(self):
  with patch('audit_standalone_magnitudes_v1_7.emit',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):self.runbuild('interrupted17')
  self.assertFalse((self.p/'interrupted17').exists())
  target=self.p/'new16/experiment_predictions.csv';data=target.read_bytes()
  try:
   target.write_bytes(data+b'changed')
   with self.assertRaises(ValueError):self.runbuild('tampered17')
   self.assertFalse((self.p/'tampered17').exists())
  finally:target.write_bytes(data)
 def test_disclosed_evaluation_separate(self):
  r=self.runbuild('eval17',True);self.assertTrue(r['include_2026']);self.assertFalse(r['selection_changed']);self.assertEqual(load(self.p/'eval17/source_rolling_choices_v1_6.json'),load(self.p/'new16/rolling_choices.json'))
if __name__=='__main__':unittest.main()
