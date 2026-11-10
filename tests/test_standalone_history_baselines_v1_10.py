import unittest,tempfile,copy,importlib.util
from pathlib import Path
from unittest.mock import patch
from collections import defaultdict
from standalone_io_v1_0 import load,dump,tree,csvrows
from standalone_SB_history_v1_10 import *
from pitcher_history_diagnostics_v1_10 import prior_tags,player,audit
from history_io_v1_10 import context,validate,forecast
from backtest_standalone_history_baselines_v1_10 import build
from evaluate_standalone_history_baselines_v1_10 import evaluate
ROOT=Path(__file__).resolve().parents[1];S=load(ROOT/'config/standalone_history_baselines_v1_10.json')
P=Path(__import__('backtest_standalone_joint_workload_v1_9').__file__).parent
spec=importlib.util.spec_from_file_location('fixture110_previous',P/'tests/test_standalone_joint_workload_v1_9.py');fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)

def fixture(p):
 fx.fx.fixture(p);fx.fx.run(p);s19=load(P/'config/standalone_joint_workload_v1_9.json');s19.update(minimum_calibration_rows=2,minimum_role_rows=2,minimum_validation_rows=3,minimum_guard_rows=2,SB_minimum_bin_rows=2);dump(p/'joint.json',s19);fx.run(p);s=dict(S,minimum_population_rows=2,minimum_validation_rows=3,minimum_guard_rows=2);dump(p/'history.json',s)
def run(p,name='new110'):return build(p/'new19',p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/'history.json',p/name,p/'backups')
def ctx(p):return context(p/'new19',p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
def runeval(p,name='eval110'):return evaluate(p/'new110',p/'new19',p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/name,p/'backups')
def lag(r,i,sb,opp):
 p=f'x_actual_lag{i}_';r.update({p+'SB':sb,p+'H':opp,p+'HR':0,p+'BB':0,p+'HBP':0,'source_season_lag'+str(i):2026-i})

class Units(unittest.TestCase):
 def test_exposure_aware_weighted_formula_and_zero_last_rate(self):
  r={};lag(r,1,0,10);lag(r,2,20,100);lag(r,3,5,50);base=dict(SB=4,H=100,HR=10,BB=10,HBP=0);model=dict(supported=True,population_rate=.1);d=prediction((2026,'hitter','1'),r,base,model,S);expected=(3*0+2*20+5+100*.1)/(3*10+2*100+50+100);self.assertAlmostEqual(d['multiyear_rate'],expected);self.assertAlmostEqual(d['candidate'],100*expected);self.assertEqual(d['last_season'],0);self.assertTrue(d['last_supported']);self.assertEqual(d['usable_lags'],3)
 def test_missing_history_population_only_and_missing_proxy_fallback(self):
  model=dict(supported=True,population_rate=.1);base=dict(SB=7,H=100,HR=10,BB=10,HBP=0);d=prediction((2026,'hitter','1'),{},base,model,S);self.assertTrue(d['population_only']);self.assertEqual(d['candidate'],10);self.assertEqual(d['last_season'],7);self.assertFalse(d['last_supported']);base['HBP']=None;d=prediction((2026,'hitter','1'),{},base,model,S);self.assertFalse(d['supported']);self.assertEqual(d['candidate'],7)
 def test_population_prior_earlier_only_zero_SB_and_masks(self):
  actual={}
  for y in [2019,2020,2021,2022,2026]:
   for m,v in dict(H=20,HR=2,BB=10,HBP=2,SB=0 if y==2019 else 3).items():actual[(y,'hitter','1',m)]=v
  s=dict(S,minimum_population_rows=2);model,members=population(actual,2022,s);self.assertEqual(model['fit_years'],[2019,2021]);self.assertEqual(model['n'],2);self.assertEqual(model['SB_sum'],3);self.assertAlmostEqual(model['population_rate'],3/60);del actual[(2021,'hitter','1','HBP')];model,members=population(actual,2022,s);self.assertFalse(model['supported']);self.assertEqual(model['n'],1)
 def test_2020_lag_samples_not_rescaled_for_rate_reliability(self):
  r={};lag(r,1,3,30);r['source_season_lag1']=2020;d=prediction((2021,'hitter','1'),r,dict(SB=4,H=100,HR=0,BB=0,HBP=0),dict(supported=True,population_rate=.05),S);self.assertEqual(d['weighted_proxy'],90);self.assertEqual(d['weighted_SB'],9)
 def test_two_comparator_guards_and_chronology(self):
  rr=[dict(season=y,cohort=cc,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2019,2020,2021,2026] for cc in ['all','prior_runner','prior_zero_SB','low_history']];h=dict(accepted=copy.deepcopy(rr),last_season=copy.deepcopy(rr));d=selection(h,2026,S);self.assertTrue(d['adopt']);self.assertEqual(d['accepted_gates']['all']['validation_seasons'],[2019,2021]);h['last_season'][8]['candidate_mse']=5;self.assertFalse(selection(h,2026,S)['adopt'])
 def test_prior_patterns_normalization_unknowns_and_role_transition(self):
  r=dict(x_actual_lag1_OUTS=100,x_actual_lag2_OUTS=400,x_actual_lag3_OUTS=450,source_season_lag1=2020,x_actual_lag1_G=30,x_actual_lag1_GS=0,x_actual_lag2_G=30,x_actual_lag2_GS=30);d=prior_tags(r,S);self.assertEqual(d['prior_normalized_OUTS_lag1'],270);self.assertFalse(d['prior_reduction']);self.assertEqual(d['prior_role_transition'],'STARTER_TO_RELIEVER');r['source_season_lag1']=2024;self.assertTrue(prior_tags(r,S)['prior_reduction']);del r['x_actual_lag1_OUTS'];d=prior_tags(r,S);self.assertTrue(d['gap_in_recorded_history']);self.assertEqual(d['prior_workload_pattern'],'NO_RECORDED_LAG1')
 def test_return_and_actual_role_are_retrospective_only(self):
  k=(2025,'pitcher','1');r=dict(x_actual_lag1_OUTS=90,x_actual_lag2_OUTS=400,x_actual_lag3_OUTS=450,x_actual_lag1_G=30,x_actual_lag1_GS=0,x_actual_lag2_G=30,x_actual_lag2_GS=30);c=dict(rows={k:r},base15={k:{'OUTS':150}},items16={k:{'candidate':160}},items18={k:{'candidate':170}},items19={k:{'candidate':180,'selected':150}});a={k+('OUTS',):400,k+('G',):30,k+('GS',):30};d=player(k,c,a,S);self.assertEqual(d['retrospective_return_pattern'],'RETURNED_TOWARD_OLDER_WORKLOAD');self.assertEqual(d['actual_role_transition'],'RELIEVER_TO_STARTER');tags=prior_tags(r,S);a[k+('OUTS',)]=50;self.assertEqual(prior_tags(r,S),tags);self.assertEqual(player(k,c,a,S)['retrospective_return_pattern'],'REMAINED_BELOW_OLDER_WORKLOAD')
 def test_branch_ranges_remain_missing_when_unknown(self):
  k=(2025,'pitcher','1');c=dict(rows={k:{}},base15={k:{'OUTS':150}},items16={k:dict(candidate=160,anchor=100,conditional_growth_OUTS=200,conditional_decline_OUTS=50)},items18={k:{'candidate':170}},items19={k:{'candidate':180,'selected':150}});actual={k+('OUTS',):300};d=player(k,c,actual,S);self.assertTrue(d['actual_above_growth']);self.assertEqual(d['observed_branch'],'GROWTH');self.assertAlmostEqual(d['observed_branch_error_IP'],-100/3);del c['items16'][k]['anchor'];self.assertIsNone(player(k,c,actual,S)['actual_above_growth'])
 def test_SB_overlay_and_pitcher_preservation(self):
  k=(2026,'hitter','1');v=dict(PA=100,AB=80,H=20,**{'1B':14,'2B':3,'3B':1,'HR':2},BB=10,HBP=2,SF=3,SH=1,SB=4,AVG=.25,OBP=32/95,SLG=31/80,OPS=32/95+31/80);c={'base15':{k:v}};d=dict(baseline=4,candidate=9,last_season=2,selected=9);x=forecast(c,k,d,'selected_SB_experiment');self.assertEqual(x['SB'],9);self.assertTrue(all(x[n]==z for n,z in v.items() if n!='SB'))

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);fixture(cls.p);cls.before19=tree(cls.p/'new19');cls.report=run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_replay_preservation_full_backup_and_all_years(self):
  p=self.p;f,items,w=validate(p/'new110',ctx(p));self.assertEqual(tree(p/'new19'),self.before19);self.assertEqual(tree(p/'new110'),tree(Path(self.report['backup'])));self.assertFalse(self.report['pitcher_models_fitted']);self.assertFalse(self.report['evaluation_outcomes_read']);self.assertEqual({r['season'] for r in csvrows(p/'new110/pitcher_history_summary.csv')},set(map(str,range(2019,2026))));self.assertTrue((p/'new110/pitcher_history_players.csv').exists())
 def test_default_no_holdout_or_new_pitcher_fits(self):
  import standalone_combined_v1_4 as mod
  original=mod.table
  def guarded(path,*a,**kw):
   if Path(path).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('Holdout outcomes parsed')
   return original(path,*a,**kw)
  with patch.object(mod,'table',side_effect=guarded),patch('standalone_joint_workload_v1_9.fit_joint',side_effect=AssertionError('New pitcher fit')):run(self.p,'nohold110')
 def test_evaluation_no_population_refit_and_disclosed_invariance(self):
  before=tree(self.p/'new110')
  with patch('standalone_SB_history_v1_10.population',side_effect=AssertionError('Refit')):r=runeval(self.p)
  self.assertFalse(r['models_refitted']);self.assertEqual(tree(self.p/'eval110'),tree(Path(r['backup'])));self.assertEqual(before,tree(self.p/'new110'))
  import evaluate_standalone_history_baselines_v1_10 as mod
  orig=mod.read_all_labels
  with patch.object(mod,'read_all_labels',side_effect=lambda root,split:{k:v*1.1 for k,v in orig(root,split).items()}):r2=runeval(self.p,'changed110')
  self.assertEqual(r['final_historical_choice'],r2['final_historical_choice']);self.assertEqual(before,tree(self.p/'new110'))
 def test_identical_score_pools_and_pitcher_values(self):
  groups={}
  for d in csvrows(self.p/'new110/category_scores.csv'):groups.setdefault(tuple(d[k] for k in ['season','player_type','metric','cohort','comparison_group']),set()).add((d['n'],d['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()));c=ctx(self.p);f,items,w=validate(self.p/'new110',c)
  for k,d in items.items():
   if k[1]=='pitcher':
    for m in METHODS:self.assertEqual(forecast(c,k,d,m),c['base15'][k])
 def test_existing_output_tamper_and_interrupt_cleanup(self):
  with self.assertRaises(FileExistsError):run(self.p)
  with patch('backtest_standalone_history_baselines_v1_10.emit',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run(self.p,'interrupt110')
  self.assertFalse((self.p/'interrupt110').exists());self.assertFalse(list(self.p.glob('interrupt110.staging-*')));p=self.p/'new110/experiment_predictions.csv';old=p.read_bytes()
  try:
   p.write_bytes(old+b'tamper')
   with self.assertRaises(ValueError):validate(self.p/'new110',ctx(self.p))
  finally:p.write_bytes(old)
if __name__=='__main__':unittest.main()
