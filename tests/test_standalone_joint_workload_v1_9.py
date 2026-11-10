import unittest,tempfile,copy,importlib.util,math
from pathlib import Path
from unittest.mock import patch
import numpy as np
from standalone_io_v1_0 import load,dump,tree,csvrows
from standalone_joint_workload_v1_9 import *
from sb_propensity_audit_v1_9 import features,freeze_bins,audit,observation,correlation,ranks
from joint_io_v1_9 import context,validate,forecast
from backtest_standalone_joint_workload_v1_9 import build
from evaluate_standalone_joint_workload_v1_9 import evaluate
ROOT=Path(__file__).resolve().parents[1];S=load(ROOT/'config/standalone_joint_workload_v1_9.json')
P=Path(__import__('backtest_standalone_refinements_v1_8').__file__).parent
spec=importlib.util.spec_from_file_location('fixture19_previous',P/'tests/test_standalone_refinements_v1_8.py');fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)

def sample(y=2022,p=.5,actual=110):return dict(season=y,mlbam_id='1',prior_role='STARTER',anchor=100.,growth=150.,decline=90.,participation=.8,probability=p,actual=actual)
def run(p,name='new19'):return build(p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/'joint.json',p/name,p/'backups')
def ctx(p):return context(p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
def runeval(p,name='eval19'):return evaluate(p/'new19',p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/name,p/'backups')

class Units(unittest.TestCase):
 def test_joint_solution_matches_independent_quadratic(self):
  ss=[]
  for p in [.1,.2,.4,.6,.8,.9]:ss.append(sample(p=p,actual=.8*(100+p*50*.6-(1-p)*10*1.6)))
  s=dict(S,calibration_prior_rows=3);m=solve_joint(ss,s,2,1000);self.assertTrue(m['supported']);x=np.array([[r['participation']*r['probability']*50,-r['participation']*(1-r['probability'])*10] for r in ss]);y=np.array([r['actual']-.8*100 for r in ss]);pen=3*np.maximum(np.mean(x*x,axis=0),1.);expected=np.linalg.solve(x.T@x+np.diag(pen),x.T@y+pen);self.assertAlmostEqual(m['growth_multiplier'],expected[0],7);self.assertAlmostEqual(m['decline_multiplier'],expected[1],7);self.assertLessEqual(m['penalized_objective_after'],m['penalized_objective_before'])
 def test_capped_objective_and_fixed_probability_prediction(self):
  rr=[dict(sample(p=p,actual=a),anchor=500.,growth=900.,decline=0.) for p,a in [(.1,50),(.3,200),(.7,800),(.9,850)]];s=dict(S,calibration_prior_rows=1);m=solve_joint(rr,s,2,900);self.assertTrue(m['supported']);coef=np.array([m['growth_multiplier'],m['decline_multiplier']]);pred=branches(*[np.array([r[n] for r in rr]) for n in ['anchor','growth','decline','participation','probability']],coef,900);self.assertTrue(all(0<=v<=900 for v in pred));self.assertAlmostEqual(np.mean((pred-np.array([r['actual'] for r in rr]))**2),m['training_MSE_after']);self.assertLessEqual(m['training_MSE_after'],m['training_MSE_before'])
  model=dict(supported=True,pooled=m,experts={role:dict(use_pooled=True) for role in ['STARTER','RELIEVER','SWING','UNKNOWN']});d=dict(baseline=300,candidate=400,supported=True,anchor=500,growth_probability=.7,participation_probability=.8,conditional_growth_OUTS=900,conditional_decline_OUTS=0);x=predict_joint((2026,'pitcher','1'),d,{},model,{'maximum_OUTS':900});self.assertEqual(x['growth_probability'],.7);self.assertEqual(x['participation_probability'],.8)
 def test_prior_only_joint_members_and_missing_activity(self):
  items={};rows={};actual={}
  for y in [2019,2020,2021,2022,2026]:
   k=(y,'pitcher','1');items[k]=dict(baseline=100,candidate=100,supported=True,anchor=100,growth_probability=.4,participation_probability=1.,conditional_growth_OUTS=150,conditional_decline_OUTS=90);rows[k]={};actual[k+('OUTS',)]=90;actual[k+('G',)]=20
  m,rr=fit_joint(items,rows,actual,2022,dict(S,minimum_calibration_rows=1),{'maximum_OUTS':900});self.assertEqual(m['fit_years'],[2019,2021]);self.assertEqual(len(rr),2);del actual[(2021,'pitcher','1','G')];self.assertEqual(len(fit_joint(items,rows,actual,2022,S,{'maximum_OUTS':900})[1]),1)
 def test_solver_bounds_and_zero_information_fallback(self):
  ss=[dict(sample(p=.5,actual=1000),growth=101.,decline=99.) for _ in range(5)];m=solve_joint(ss,dict(S,calibration_prior_rows=1),2,900);self.assertTrue(m['supported']);self.assertEqual(m['growth_multiplier'],3);self.assertEqual(m['decline_multiplier'],0)
  for r in ss:r.update(growth=100.,decline=100.)
  self.assertEqual(solve_joint(ss,S,2,900)['status'],'NO_MAGNITUDE_INFORMATION')
 def test_selection_keeps_2021_and_excludes_future_stress(self):
  h=[dict(season=y,cohort=c,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2019,2020,2021,2026] for c in ['all','prior_starter','prior_reliever']];d=selection(h,2026,S);self.assertTrue(d['adopt']);self.assertEqual(d['gates']['all']['validation_seasons'],[2019,2021]);h[-4]['candidate_mse']=5;self.assertFalse(selection(h,2026,S)['adopt'])
 def test_insufficient_solver_and_source_fallback(self):
  m=solve_joint([],S,2,900);self.assertFalse(m['supported']);d=dict(baseline=100,candidate=200,supported=False);x=predict_joint((2026,'pitcher','1'),d,{},dict(supported=False),{'maximum_OUTS':900});self.assertEqual(x['candidate'],100);self.assertIsNone(x['raw_candidate'])
 def test_SB_missing_zero_denominators_and_no_fabricated_change(self):
  k=(2024,'hitter','1');r=dict(x_actual_lag1_H=20,x_actual_lag1_HR=2,x_actual_lag1_BB=10,x_actual_lag1_HBP=2,x_actual_lag1_SB=0,x_actual_lag1_PA=80);actual={k+(m,):v for m,v in dict(H=20,HR=2,BB=10,HBP=2,SB=0).items()};o=observation(k,r,actual,S);self.assertEqual(o['propensity_change'],0);self.assertIn('low_history',o['cohorts']);self.assertIn('prior_zero_SB',o['cohorts']);del actual[k+('HBP',)];self.assertIsNone(observation(k,r,actual,S)['propensity_change']);actual.update({k+(m,):0 for m in ['H','HR','BB','HBP']});self.assertEqual(observation(k,r,actual,S)['status'],'INSUFFICIENT_PROXY_EXPOSURE')
 def test_SB_frozen_bins_and_rank_ties(self):
  allow=['x_actual_lag1_SB'];rows={(y,'hitter',str(i)):dict(target_season=y,x_actual_lag1_SB=i) for y in [2018,2019,2020,2021,2026] for i in range(5)};a=freeze_bins(rows,allow,S);changed=copy.deepcopy(rows)
  for k,r in changed.items():
   if k[0]>=2021:r['x_actual_lag1_SB']=999
  self.assertEqual(a['2021'],freeze_bins(changed,allow,S)['2021']);self.assertNotIn(2020,a['2026']['fit_years']);self.assertEqual(ranks([2,1,2]),[1.5,0.,1.5]);self.assertAlmostEqual(correlation([1,2,3],[3,2,1]),-1)
 def test_SB_audit_all_years_and_no_features_selected(self):
  rows={};actual={};allow=['x_actual_lag1_SB']
  for y in range(2018,2027):
   for i in range(5):
    k=(y,'hitter',str(i+1));rows[k]=dict(target_season=y,x_actual_lag1_H=20,x_actual_lag1_HR=2,x_actual_lag1_BB=10,x_actual_lag1_HBP=2,x_actual_lag1_SB=i,x_actual_lag1_PA=80)
    for m,v in dict(H=20,HR=2,BB=10,HBP=2,SB=5-i).items():actual[k+(m,)]=v
  s=dict(S,SB_minimum_bin_rows=2);bins=freeze_bins(rows,allow,s);a=audit(rows,actual,allow,s,bins);self.assertEqual({r['season'] for r in a['sb_feature_associations']},set(range(2019,2026)));self.assertTrue(all(not d['feature_selected'] for d in a['sb_feature_stability']));self.assertTrue(all('2021' in d['requested_seasons'] for d in a['sb_feature_stability']))

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);fx.fixture(cls.p);fx.run(cls.p);s=dict(S,minimum_calibration_rows=2,minimum_role_rows=2,minimum_validation_rows=3,minimum_guard_rows=2,SB_minimum_bin_rows=2);dump(cls.p/'joint.json',s);cls.before18=tree(cls.p/'new18');cls.report=run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_pipeline_replay_backups_and_preserved_evidence(self):
  p=self.p;f,items,w=validate(p/'new19',ctx(p));self.assertEqual(tree(p/'new18'),self.before18);self.assertEqual(tree(p/'new19'),tree(Path(self.report['backup'])));self.assertFalse(self.report['SB_replacement_fitted']);self.assertFalse(self.report['evaluation_outcomes_read']);self.assertTrue((p/'new19/transition_2021.csv').exists());c=ctx(p)
  for k,d in items.items():
   if k[1]=='pitcher':self.assertEqual(d['growth_probability'],c['items16'][k]['growth_probability']);self.assertEqual(d['participation_probability'],c['items16'][k]['participation_probability'])
   else:self.assertEqual(d['selected'],c['base15'][k]['SB'])
 def test_historical_build_never_parses_holdout_outcomes(self):
  import standalone_combined_v1_4 as mod
  original=mod.table
  def guarded(path,*a,**kw):
   if Path(path).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('Holdout outcomes read')
   return original(path,*a,**kw)
  with patch.object(mod,'table',side_effect=guarded):run(self.p,'nohold19')
 def test_evaluation_no_fits_and_forecasts_immutable(self):
  before=tree(self.p/'new19')
  with patch('standalone_joint_workload_v1_9.fit_joint',side_effect=AssertionError('refit')):report=runeval(self.p)
  self.assertFalse(report['models_refitted']);self.assertEqual(before,tree(self.p/'new19'));self.assertEqual(tree(self.p/'eval19'),tree(Path(report['backup'])))
 def test_changed_disclosed_labels_cannot_change_model_choices_or_bins(self):
  import evaluate_standalone_joint_workload_v1_9 as mod
  original=mod.read_all_labels
  before=tree(self.p/'new19')
  with patch.object(mod,'read_all_labels',side_effect=lambda root,split:{k:v*1.1 for k,v in original(root,split).items()}):r=runeval(self.p,'changed_eval19')
  self.assertEqual(before,tree(self.p/'new19'));self.assertEqual(r['final_historical_choice'],self.report['final_historical_choice'])
 def test_identical_pools_and_source_tamper_rejected(self):
  groups={}
  for d in csvrows(self.p/'new19/category_scores.csv'):groups.setdefault(tuple(d[k] for k in ['season','player_type','metric','cohort','comparison_group']),set()).add((d['n'],d['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()));target=self.p/'new19/experiment_predictions.csv';old=target.read_bytes()
  try:
   target.write_bytes(old+b'tamper')
   with self.assertRaises(ValueError):validate(self.p/'new19',ctx(self.p))
  finally:target.write_bytes(old)
 def test_SB_no_replacement_fit_or_current_label_bin_selection(self):
  c=ctx(self.p);allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist'];s=load(self.p/'joint.json');bins=freeze_bins(c['rows'],allow,s);r=audit(c['rows'],c['actual_training'],allow,s,bins);changed=dict(c['actual_training'])
  for k in changed:
   if k[0]==2025 and k[-1]=='SB':changed[k]*=2
  r2=audit(c['rows'],changed,allow,s,bins);self.assertEqual(bins,load(self.p/'new19/sb_frozen_feature_bins.json'));self.assertEqual(r['sb_feature_stability'][0]['feature_selected'],False);self.assertEqual(r['sb_feature_associations'][0]['membership_sha256'],r2['sb_feature_associations'][0]['membership_sha256'])
  with patch('standalone_refinements_v1_8.fit_SB',side_effect=AssertionError('New SB replacement fit')):run(self.p,'no_SB_fit19')
 def test_existing_output_and_interruption_cleanup(self):
  with self.assertRaises(FileExistsError):run(self.p)
  with patch('backtest_standalone_joint_workload_v1_9.emit',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run(self.p,'interrupt19')
  self.assertFalse((self.p/'interrupt19').exists());self.assertFalse(list(self.p.glob('interrupt19.staging-*')))
if __name__=='__main__':unittest.main()
