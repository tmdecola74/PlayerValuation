import unittest,tempfile,copy,csv,io,json,importlib.util,shutil
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch
import duckdb
from standalone_io_v1_0 import *
from standalone_combined_v1_4 import vectors,read_all_labels
from standalone_holds_v1_5 import *
from standalone_attribution_v1_5 import *
from holds_io_v1_5 import source_context,overlay,validate_run
from backtest_standalone_holds_attribution_v1_5 import build
from evaluate_standalone_holds_attribution_v1_5 import evaluate,benchmark
from build_standalone_combined_v1_4 import build as build14
ROOT=Path(__file__).resolve().parents[1]
P13=Path(__import__('backtest_standalone_workload_experiments_v1_3').__file__).parent
spec=importlib.util.spec_from_file_location('fixture15_previous',P13/'tests/test_standalone_workload_experiments_v1_3.py');f13=importlib.util.module_from_spec(spec);spec.loader.exec_module(f13)

def labels_full(p,train,hold):
 for name,rr in [('training_labels',train),('holdout_labels',hold)]:
  out=[dict(season=r['target_season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],metric=m[2:],label_value=v,eligible=True) for r in rr for m,v in r.items() if m.startswith('y_') and not m.startswith('y_eligible_') and r.get('y_eligible_'+m[2:])];src=p/'labels'/('temp_'+name+'.json');dump(src,out);dest=p/'labels'/(name+'.parquet');dest.unlink()
  with duckdb.connect() as db:db.read_json(str(src)).write_parquet(str(dest))
  src.unlink()
 refresh(p/'labels')
def refresh(p):
 p=Path(p);m=p/'output_sha256.json'
 if m.exists():m.unlink()
 dump(m,tree(p))
def fixture(p):
 rr,hold,c,allow,s13=f13.fixture(p);labels_full(p,rr,hold);f13.build12(p/'matrix',p/'b1',p/'labels',p/'role_config.json',p/'v12full',p/'backups');f13.run(p,'new13','v12full');build14(p/'new13',p/'matrix',p/'v12full',p/'labels',p/'new14',p/'backups');s=load(ROOT/'config/standalone_holds_attribution_v1_5.json');s.update(minimum_fit_rows=3,minimum_each_occurrence_class=1,minimum_positive_relief_games=1,occurrence_iterations=40,minimum_validation_rows=3,minimum_guard_rows=2,minimum_prior_holds_rows=2);dump(p/'holds.json',s);return rr,hold,c,allow,s

def run(p,name='new15',labels='labels'):return build(p/'new14',p/'new13',p/'matrix',p/'v12full',p/labels,p/'holds.json',p/name,p/'backups')
def runeval(p,name='eval15'):return evaluate(p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/name,p/'backups')

class Units(unittest.TestCase):
 def test_exact_symmetric_identity_and_counterfactuals(self):
  for f,e,a,x in [(20,100,15,150),(0,100,5,80),(7,30,0,20)]:
   d=decomposition(f,e,a,x);self.assertEqual(d['status'],'AVAILABLE');self.assertAlmostEqual(d['error'],d['workload_contribution']+d['skill_contribution']);self.assertAlmostEqual(d['actual_exposure_forecast_rate'],x*f/e)
 def test_pure_workload_and_pure_rate_errors(self):
  d=decomposition(20,200,10,100);self.assertAlmostEqual(d['skill_contribution'],0);self.assertAlmostEqual(d['workload_contribution'],10)
  d=decomposition(20,100,10,100);self.assertAlmostEqual(d['workload_contribution'],0);self.assertAlmostEqual(d['skill_contribution'],10)
 def test_missing_zero_denominators_and_true_zero_counts(self):
  self.assertEqual(decomposition(0,0,0,0)['status'],'ZERO_DENOMINATOR_RATE_UNKNOWN');self.assertIsNone(decomposition(0,0,1,10)['forecast_rate']);self.assertEqual(decomposition(0,10,0,10)['status'],'AVAILABLE');self.assertEqual(decomposition(None,100,2,100)['status'],'MISSING_ELIGIBLE_COUNT_OR_EXPOSURE')
 def test_no_target_label_features_and_target_mutation_invariance(self):
  base=load(Path(__import__('standalone_models_v1_0').__file__).parent/'config/standalone_baselines_v1_0.json');s=load(ROOT/'config/standalone_holds_attribution_v1_5.json');s.update(minimum_fit_rows=3,minimum_each_occurrence_class=1,minimum_positive_relief_games=1,occurrence_iterations=40)
  rr=[];actual={}
  for i in range(12):
   r=dict(target_season=2023,player_type='pitcher',mlbam_id=str(i+1),source_season_lag1=2022,x_actual_lag1_G=60,x_actual_lag1_GS=0,x_actual_lag1_HLD=15 if i%2 else 0,y_G=60,y_GS=0,y_HLD=15 if i%2 else 0,y_eligible_G=1,y_eligible_GS=1,y_eligible_HLD=1,frozen_participation=1,role_probability_STARTER=0.,role_probability_RELIEVER=1.,role_probability_SWING=0.);rr.append(r)
   for m in ['G','GS','HLD']:actual[2023,'pitcher',str(i+1),m]=r['y_'+m]
  m,a=fit_holds(rr,actual,['x_actual_lag1_HLD'],base,s,2024);self.assertTrue(m['supported']);a=predict_holds(m,rr,s);changed=copy.deepcopy(rr)
  for r in changed:r['y_HLD']=999;r['y_G']=999;r['y_GS']=999
  self.assertEqual(a,predict_holds(m,changed,s));self.assertTrue(all(v['raw_candidate_HLD'] is not None and 0<=v['raw_candidate_HLD']<=60 for v in a.values()));self.assertTrue(all(not n.startswith('y_') for n in m['occurrence']['preprocessing']['numeric']))
 def test_unsupported_occurrence_is_not_zero_candidate(self):
  base=load(Path(__import__('standalone_models_v1_0').__file__).parent/'config/standalone_baselines_v1_0.json');s=load(ROOT/'config/standalone_holds_attribution_v1_5.json');r=dict(target_season=2023,player_type='pitcher',mlbam_id='1',y_G=60,y_GS=0,y_HLD=0,y_eligible_G=1,y_eligible_GS=1,y_eligible_HLD=1,frozen_participation=1);a={(2023,'pitcher','1',m):r['y_'+m] for m in ['G','GS','HLD']};b,_=fit_holds([r],a,[],base,s,2024);self.assertFalse(b['supported']);self.assertIsNone(predict_holds(b,[r],s)[2023,'pitcher','1']['raw_candidate_HLD'])
 def test_missing_holds_not_negative_class_and_zero_relief_not_rate(self):
  r=dict(target_season=2023,player_type='pitcher',mlbam_id='1',y_G=30,y_GS=30,y_HLD=None,y_eligible_G=1,y_eligible_GS=1,y_eligible_HLD=0);a={(2023,'pitcher','1','G'):30,(2023,'pitcher','1','GS'):30};x=training_rows([r],a)[0];self.assertEqual(x['y_RELIEF_G'],0);self.assertIsNone(x['y_ANY_HOLD']);self.assertIsNone(x['y_POS_HLD'])
 def test_both_baselines_and_both_prior_guards_required(self):
  s=load(ROOT/'config/standalone_holds_attribution_v1_5.json');h={b:[dict(season=y,cohort=cohort,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2022,2023] for cohort in ['all','prior_relief','prior_holds']] for b in METHODS[:2]};self.assertTrue(choose(h,2024,s)['adopt']);h['frozen_v1_2'][-1]['candidate_mse']=10;self.assertFalse(choose(h,2024,s)['adopt']);self.assertFalse(choose(h,2023,s)['adopt'])
 def test_2020_future_folds_and_unsupported_majority_cannot_select(self):
  s=load(ROOT/'config/standalone_holds_attribution_v1_5.json');h={b:[dict(season=y,cohort=c,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2020,2023,2026] for c in ['all','prior_relief','prior_holds']] for b in METHODS[:2]};self.assertFalse(choose(h,2026,s)['adopt']);self.assertEqual(choose(h,2026,s)['comparisons']['combined_v1_4']['gates']['all']['validation_seasons'],[2023]);
  for pp in h.values():
   for d in pp:d['supported']=0
  self.assertFalse(choose(h,2027,s)['adopt'])
 def test_saves_and_all_nonholds_components_exactly_preserved(self):
  v=dict(OUTS=300,IP=100,H=90,ER=40,BB=30,HR=10,SO=110,W=8,SV=25,HLD=4,QS=10,ERA=3.6,WHIP=1.2,SV_plus_HLD=29);n=overlay(v,12);self.assertEqual(n['SV'],25);self.assertEqual(n['SV_plus_HLD'],37);self.assertTrue(all(n[k]==x for k,x in v.items() if k not in ['HLD','SV_plus_HLD']))
 def test_prior_workload_cohorts_and_actual_role_are_diagnostics(self):
  key=(2026,'pitcher','1');r=dict(x_actual_lag1_G=30,x_actual_lag1_GS=30,x_actual_lag1_OUTS=360);a={key+('G',):50,key+('GS',):0,key+('OUTS',):90};t=tags(key,r,a);self.assertEqual(t['prior_role'],'STARTER');self.assertEqual(t['actual_role'],'RELIEVER');self.assertEqual(t['prior_workload_cohort'],'GE100_IP');self.assertEqual(t['actual_workload_cohort'],'LT40_IP')
 def test_holds_score_pools_and_zero_outcomes(self):
  key=(2026,'pitcher','1');items={key:dict(supported=True,**{m:3. for m in METHODS})};rows={key:{}};rr,cc=holds_scores(items,rows,{key+('HLD',):0},METHODS);allrows=[r for r in rr if r['cohort']=='all_eligible'];self.assertEqual({r['n'] for r in allrows},{1});self.assertEqual(len({r['membership_sha256'] for r in allrows}),1);self.assertEqual(holds_scores(items,rows,{},METHODS)[0],[])
 def test_external_holds_pools_identical(self):
  k=(2026,'pitcher','1');items={k:dict(supported=True,**{m:5 for m in METHODS})};c={'base':{k:{'SV':10}}};a={k+('HLD',):4,k+('SV_plus_HLD',):14};external={k+('HLD','Steamer'):(3,'r'),k+('SV_plus_HLD','Steamer'):(13,'r')};ss,pp,cc=benchmark(items,c,a,external,{2026:{'Steamer'}});self.assertTrue(all(r['n']==1 for r in ss));self.assertEqual(len({r['membership_sha256'] for r in ss}),1)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.rr,cls.hold,cls.base,cls.allow,cls.settings=fixture(cls.p);cls.report=run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_complete_backup_sources_unchanged_and_replay(self):
  p=self.p;self.assertEqual(tree(p/'new15'),tree(Path(self.report['backup'])));self.assertFalse(self.report['evaluation_outcomes_read']);self.assertTrue(self.report['saves_preserved_exactly']);self.assertEqual(len(load(p/'new15/historical_holds_choices.json')),8)
 def test_full_evaluation_integrity_attribution_and_matching_pools(self):
  p=self.p;before={n:tree(p/n) for n in ['new14','new13','v12full','labels','matrix','new15']};r=runeval(p);self.assertFalse(r['models_refitted']);self.assertFalse(r['selection_retuned']);self.assertEqual(tree(p/'eval15'),tree(Path(r['backup'])))
  for n,v in before.items():self.assertEqual(tree(p/n),v)
  group=defaultdict(set)
  for r in csvrows(p/'eval15/holds_scores.csv'):group[r['season'],r['cohort']].add((r['n'],r['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in group.values()))
  for r in csvrows(p/'eval15/count_error_attribution.csv'):
   if r['status']=='AVAILABLE':self.assertAlmostEqual(float(r['error']),float(r['workload_contribution'])+float(r['skill_contribution']),places=8)
  for r in csvrows(p/'eval15/attribution_summary.csv'):self.assertAlmostEqual(float(r['total_mse']),float(r['workload_mse'])+float(r['skill_mse'])+float(r['interaction_mse']),places=7)
 def test_no_holdout_outcome_table_opened_by_builder(self):
  import standalone_combined_v1_4 as co
  import backtest_standalone_holds_attribution_v1_5 as b
  original=co.table
  def guard(path):
   if Path(path).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('Evaluation outcomes opened')
   return original(path)
  with patch('standalone_combined_v1_4.table',side_effect=guard):run(self.p,'no_holdout')
  self.assertEqual((self.p/'new15/frozen_2026_forecasts.csv').read_bytes(),(self.p/'no_holdout/frozen_2026_forecasts.csv').read_bytes())
 def test_2026_label_mutation_cannot_change_models_choices_or_forecasts(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'labels';shutil.copytree(p/'labels',q);rr=table(q/'holdout_labels.parquet')
   for r in rr:r['label_value']*=2
   dump(q/'new.json',rr);(q/'holdout_labels.parquet').unlink()
   with duckdb.connect() as db:db.read_json(str(q/'new.json')).write_parquet(str(q/'holdout_labels.parquet'))
   (q/'new.json').unlink();refresh(q);build(p/'new14',p/'new13',p/'matrix',p/'v12full',q,p/'holds.json',p/'changed',p/'backups')
   for n in ['frozen_models.json','historical_holds_choices.json','frozen_2026_forecasts.csv']:self.assertEqual((p/'new15'/n).read_bytes(),(p/'changed'/n).read_bytes())
 def test_future_target_labels_do_not_change_earlier_fits(self):
  p=self.p;c=source_context(p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels');rr=prepared(c);truth=read_all_labels(p/'labels','training');base=load(p/'v12full/frozen_models.json')['workload_model']['config'];m,_=fit_holds(rr,truth,self.allow,base,self.settings,2024);changed=dict(truth)
  for k in list(changed):
   if k[0]>=2024:changed[k]=999
  n,_=fit_holds(rr,changed,self.allow,base,self.settings,2024);self.assertEqual(m,n)
 def test_hash_tamper_existing_output_and_interrupt_cleanup(self):
  p=self.p
  with self.assertRaises(FileExistsError):run(p)
  with patch('backtest_standalone_holds_attribution_v1_5.fit_holds',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run(p,'interrupted')
  self.assertFalse((p/'interrupted').exists());self.assertFalse(list(p.glob('interrupted.staging-*')))
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'new15';shutil.copytree(p/'new15',q);(q/'holds_predictions.csv').write_text('tampered',encoding='utf-8');c=source_context(p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
   with self.assertRaises(ValueError):validate_run(q,c,read_all_labels(p/'labels','training'))
 def test_prior_positive_rate_aliases_preserve_zero_vs_missing(self):
  p=self.p;c=source_context(p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels');rr=prepared(c)
  for r in rr:
   for lag in [1,2,3]:
    h=r.get(f'x_actual_lag{lag}_HLD');rel=r.get(f'x_actual_lag{lag}_RELIEF_G');v=r.get(f'x_actual_lag{lag}_POS_HLD')
    if h is not None and h>0 and rel is not None and rel>0:self.assertEqual(v,h)
    else:self.assertIsNone(v)
 def test_attribution_outlier_file_and_classification_preserved(self):
  p=self.p;self.assertTrue(csvrows(p/'new15/ratio_outliers.csv'));self.assertEqual(sha(p/'new14/classification_and_probability_inputs.csv'),sha(p/'new15/classification_and_probability_inputs.csv'));self.assertTrue(all(int(r['season'])<2026 for r in csvrows(p/'new15/count_error_attribution.csv')))

 def test_rehashed_changed_save_forecast_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'new15';shutil.copytree(p/'new15',q);path=q/'frozen_2026_forecasts.csv';rr=csvrows(path);r=next(r for r in rr if r['metric']=='SV');r['prediction']=str(float(r['prediction'])+1);write(path,rr,list(rr[0]));f=load(q/'freeze_manifest.json');f[path.name]=sha(path);dump(q/'freeze_manifest.json',f);refresh(q);c=source_context(p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
   with self.assertRaisesRegex(ValueError,'non-holds'):validate_run(q,c,read_all_labels(p/'labels','training'))
 def test_rehashed_inconsistent_selected_hold_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'new15';shutil.copytree(p/'new15',q);path=q/'holds_predictions.csv';rr=csvrows(path);rr[0]['selected_v1_5']=str(float(rr[0]['selected_v1_5'])+1);write(path,rr,list(rr[0]));f=load(q/'freeze_manifest.json');f[path.name]=sha(path);dump(q/'freeze_manifest.json',f);refresh(q);c=source_context(p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
   with self.assertRaisesRegex(ValueError,'selection'):validate_run(q,c,read_all_labels(p/'labels','training'))

if __name__=='__main__':unittest.main()
