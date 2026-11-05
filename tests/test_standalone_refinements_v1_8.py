import unittest,tempfile,copy,importlib.util,json
from pathlib import Path
from unittest.mock import patch
from standalone_io_v1_0 import load,dump,tree,sha,csvrows
from standalone_refinements_v1_8 import *
from refinement_io_v1_8 import context,validate,forecast
from backtest_standalone_refinements_v1_8 import build,comparison
from evaluate_standalone_refinements_v1_8 import evaluate
ROOT=Path(__file__).resolve().parents[1]
P=Path(__import__('backtest_standalone_growth_sb_v1_6').__file__).parent
spec=importlib.util.spec_from_file_location('fixture18_previous',P/'tests/test_standalone_growth_sb_v1_6.py');fx=importlib.util.module_from_spec(spec);spec.loader.exec_module(fx)
S=load(ROOT/'config/standalone_refinements_v1_8.json')

def fixture(p):
 fx.fixture(p);fx.run(p)
 from audit_standalone_magnitudes_v1_7 import build as audit
 audit(p/'new16',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/'diag17',p/'backups')
 s=dict(S,minimum_calibration_rows=2,minimum_role_calibration_rows=2,minimum_SB_fit_rows=3,minimum_SB_opportunities=1,minimum_validation_rows=3,minimum_guard_rows=2);dump(p/'refine.json',s)
def run(p,name='new18'):return build(p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/'refine.json',p/name,p/'backups')
def ctx(p):return context(p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
def runeval(p,name='eval18'):return evaluate(p/'new18',p/'new16',p/'diag17',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/name,p/'backups')

class Units(unittest.TestCase):
 def test_multiplier_shrinks_to_one_and_bounds(self):
  s=dict(S,minimum_calibration_rows=2,calibration_prior_rows=2);m=slope([(10,20),(10,20)],s,2);self.assertAlmostEqual(m['multiplier'],1.5);self.assertFalse(slope([(0,10)],s,1)['supported']);self.assertEqual(slope([(1,1000)],s,1)['multiplier'],3)
 def test_calibration_prior_folds_only_and_prior_role(self):
  items={};rows={};actual={}
  for y in [2019,2020,2021,2022,2026]:
   for i,a in [(1,150),(2,50)]:
    k=(y,'pitcher',str(i));items[k]=dict(supported=True,anchor=100,conditional_growth_OUTS=120,conditional_decline_OUTS=80);rows[k]=dict(x_actual_lag1_G=20,x_actual_lag1_GS=20);actual[k+('OUTS',)]=a;actual[k+('G',)]=20
  s=dict(S,minimum_calibration_rows=1);m,members=fit_calibration(items,rows,actual,2022,s);self.assertEqual(m['fit_years'],[2019,2021]);self.assertEqual(len(members),4);self.assertTrue(all(r['prior_role']=='STARTER' for r in members));self.assertEqual(fit_calibration(items,rows,actual,2021,s)[0]['fit_years'],[2019])
 def test_fixed_probabilities_and_branch_math(self):
  s=dict(S);model=dict(supported=True,pooled={'growth':{'multiplier':2},'decline':{'multiplier':.5}},experts={b:{r:{'use_pooled':True} for r in ['STARTER','RELIEVER','SWING','UNKNOWN']} for b in ['growth','decline']});d=dict(baseline=100,anchor=100,growth_probability=.6,participation_probability=.8,conditional_growth_OUTS=150,conditional_decline_OUTS=60,supported=True,candidate=80);r=dict(x_actual_lag1_G=20,x_actual_lag1_GS=20);x=calibrated(d,r,model,s,{'maximum_OUTS':900});self.assertEqual(x['growth_probability'],.6);self.assertEqual(x['participation_probability'],.8);self.assertEqual(x['conditional_growth_OUTS'],200);self.assertEqual(x['conditional_decline_OUTS'],80);self.assertAlmostEqual(x['candidate'],121.6);d['supported']=False;self.assertEqual(calibrated(d,r,model,s,{'maximum_OUTS':900})['candidate'],100)
 def test_low_history_and_established_guards(self):
  s=S;r=dict(x_actual_lag1_SB=12,x_actual_lag1_PA=80);self.assertIn('prior_runner',cohort_names('hitter',r,s));self.assertIn('low_history',cohort_names('hitter',r,s));self.assertIn('low_history',cohort_names('hitter',{},s));self.assertIn('prior_zero_SB',cohort_names('hitter',{'x_actual_lag1_SB':0},s))
  hh=[dict(season=y,cohort=c,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2022,2023] for c in ['all','prior_runner','prior_zero_SB','low_history']];self.assertTrue(selection(hh,2024,'hitter',s)['adopt']);hh[-1]['candidate_mse']=4;self.assertFalse(selection(hh,2024,'hitter',s)['adopt']);self.assertFalse(selection([h for h in hh if h['cohort']!='low_history'],2024,'hitter',s)['adopt'])
 def test_2020_and_future_never_select(self):
  h=[dict(season=y,cohort=c,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2020,2021,2026] for c in ['all','prior_starter','prior_reliever']];x=selection(h,2026,'pitcher',S);self.assertFalse(x['adopt']);self.assertEqual(x['gates']['all']['validation_seasons'],[2021])
 def test_SB_rate_uses_zeros_and_eligible_proxy(self):
  rows=[];actual={}
  for i in range(4):
   r=dict(target_season=2023,player_type='hitter',mlbam_id=str(i+1));vals=dict(PA=100,H=20,HR=2,BB=10,HBP=2,SB=0 if i<2 else 4)
   for n,v in vals.items():r['y_'+n]=v;r['y_eligible_'+n]=1;actual[(2023,'hitter',str(i+1),n)]=v
   rows.append(r)
  c=load(Path(__import__('standalone_models_v1_0').__file__).parent/'config/standalone_baselines_v1_0.json');s=dict(S,minimum_SB_fit_rows=3)
  old=load(P/'config/standalone_growth_sb_v1_6.json');m=fit_SB(rows,actual,[],c,old,s,2024);self.assertEqual(m['model']['n_fit'],4);self.assertAlmostEqual(m['model']['population_value'],2/30);self.assertEqual(m['fit_years'],[2023]);self.assertEqual(fit_SB(rows,actual,[],c,old,s,2023)['model']['n_fit'],0)
 def test_SB_missing_proxy_fallback_and_zero_rate(self):
  model={'supported':True,'model':{},'target':Target('hitter','RATE','SB','SB_ONBASE',1,3,100).__dict__,'config':{}};r=dict(target_season=2026,player_type='hitter',mlbam_id='1');k=(2026,'hitter','1');v={k:dict(PA=100,H=20,HR=2,BB=10,HBP=None,SB=4)};old={k:{'candidate':3}}
  with patch('standalone_refinements_v1_8.predict',return_value=([0.],[0.])):
   x=sb_predict(model,[r],v,S,old)[k];self.assertFalse(x['supported']);self.assertEqual(x['candidate'],4);v[k]['HBP']=2;x=sb_predict(model,[r],v,S,old)[k];self.assertTrue(x['supported']);self.assertEqual(x['candidate'],0)
  v[k].update(AB=80,**{'1B':14,'2B':3,'3B':1},SF=3,SH=1,AVG=.25,OBP=32/95,SLG=31/80,OPS=32/95+31/80);c={'base15':v};d=dict(baseline=4,candidate=10,selected=10);out=forecast(c,k,d,'selected_SB_experiment');self.assertEqual(out['SB'],10);self.assertTrue(all(out[m]==z for m,z in v[k].items() if m!='SB'))
 def test_separate_overlays_preserve_saves_holds_and_hitter_counts(self):
  k=(2026,'pitcher','1');base=dict(OUTS=300,IP=100,H=90,ER=40,BB=30,HR=10,SO=110,W=8,QS=10,SV=25,HLD=12,SV_plus_HLD=37,ERA=3.6,WHIP=1.2);c={'base15':{k:base}};d=dict(baseline=300,candidate=450,selected=450);v=forecast(c,k,d,'selected_workload_experiment');self.assertEqual([v[m] for m in ['SV','HLD','SV_plus_HLD']],[25,12,37]);self.assertEqual(v['IP'],150);self.assertAlmostEqual(v['ERA'],v['ER']*9/v['IP']);self.assertEqual(forecast(c,k,d,'selected_SB_experiment'),base)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);fixture(cls.p);cls.before16=tree(cls.p/'new16');cls.before17=tree(cls.p/'diag17');cls.report=run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_pipeline_backup_and_reproduction(self):
  p=self.p;c=ctx(p);f,items,w=validate(p/'new18',c);self.assertEqual(tree(p/'new16'),self.before16);self.assertEqual(tree(p/'diag17'),self.before17);self.assertEqual(tree(p/'new18'),tree(Path(self.report['backup'])));self.assertFalse(self.report['evaluation_outcomes_read']);self.assertEqual(set(int(x) for x in load(p/'new18/origin_models.json')),set(range(2019,2027)));self.assertTrue((p/'new18/transition_2021.csv').exists())
  for r in csvrows(p/'new18/calibration_fit_members.csv'):self.assertLess(int(r['season']),int(r['origin']));self.assertNotEqual(r['season'],'2020')
  for d in items.values():
   if d['metric']=='OUTS':self.assertTrue(d['growth_probability'] is None or 0<=d['growth_probability']<=1)
 def test_default_build_does_not_parse_holdout_outcomes(self):
  import standalone_combined_v1_4 as mod
  orig=mod.table
  def guarded(p,*a,**kw):
   if Path(p).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('holdout read')
   return orig(p,*a,**kw)
  with patch.object(mod,'table',side_effect=guarded):run(self.p,'nohold18')
 def test_frozen_evaluation_no_fit_and_source_preserved(self):
  before=tree(self.p/'new18')
  with patch('standalone_refinements_v1_8.fit_SB',side_effect=AssertionError('refit')),patch('standalone_refinements_v1_8.fit_calibration',side_effect=AssertionError('refit')):r=runeval(self.p)
  self.assertFalse(r['models_refitted']);self.assertEqual(before,tree(self.p/'new18'));self.assertEqual(tree(self.p/'eval18'),tree(Path(r['backup'])))
 def test_current_labels_cannot_change_fit_or_choices(self):
  p=self.p;c=ctx(p);s=load(p/'refine.json');actual=c['actual_training'];modified=dict(actual)
  for k in modified:
   if k[0]>=2025:modified[k]=modified[k]*2
  a=fit_calibration(c['items16'],c['rows'],actual,2025,s);b=fit_calibration(c['items16'],c['rows'],modified,2025,s);self.assertEqual(a,b)
  models=load(p/'new18/origin_models.json');self.assertNotIn(2025,models['2025']['hitter']['fit_years']);self.assertNotIn(2026,models['2026']['hitter']['fit_years'])
 def test_disclosed_label_changes_do_not_change_forecasts_or_choices(self):
  import evaluate_standalone_refinements_v1_8 as ev
  original=ev.read_all_labels
  def changed(root,split):return {k:v*1.1 for k,v in original(root,split).items()}
  before=tree(self.p/'new18')
  with patch.object(ev,'read_all_labels',side_effect=changed):report=runeval(self.p,'changed_eval18')
  self.assertEqual(before,tree(self.p/'new18'));self.assertEqual(report['final_historical_choices'],self.report['final_historical_choices'])
 def test_identical_category_pools_and_fixed_direction_values(self):
  pp=csvrows(self.p/'new18/category_scores.csv');groups={}
  for d in pp:groups.setdefault((d['season'],d['player_type'],d['metric'],d['cohort'],d['comparison_group']),set()).add((d['n'],d['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()));c=ctx(self.p);f,items,w=validate(self.p/'new18',c)
  for k,d in items.items():
   if k[1]=='pitcher':self.assertEqual(d['growth_probability'],c['items16'][k]['growth_probability']);self.assertEqual(d['participation_probability'],c['items16'][k]['participation_probability'])
 def test_output_guard_interrupt_and_source_tamper(self):
  with self.assertRaises(FileExistsError):run(self.p)
  with patch('backtest_standalone_refinements_v1_8.emit',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run(self.p,'interrupt18')
  self.assertFalse((self.p/'interrupt18').exists());self.assertFalse(list(self.p.glob('interrupt18.staging-*')))
  p=self.p/'new18/experiment_predictions.csv';old=p.read_bytes()
  try:
   p.write_bytes(old+b'tampered')
   with self.assertRaises(ValueError):validate(self.p/'new18',ctx(self.p))
  finally:p.write_bytes(old)
if __name__=='__main__':unittest.main()
