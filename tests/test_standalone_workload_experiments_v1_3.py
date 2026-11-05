import unittest,tempfile,copy,json,importlib.util
from pathlib import Path
from unittest.mock import patch
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import Target
from standalone_workload_experiments_v1_3 import *
from workload_experiments_io_v1_3 import scores,probability_bank
from backtest_standalone_workload_experiments_v1_3 import build
from evaluate_standalone_workload_experiments_v1_3 import evaluate,direction_scores,benchmarks
from backtest_standalone_role_workload_v1_2 import build as build12
from standalone_role_workload_v1_2 import predict_workload,with_probabilities
ROOT=Path(__file__).resolve().parents[1]
path=Path(__import__('backtest_standalone_role_workload_v1_2').__file__).parent/'tests/test_standalone_role_workload_v1_2.py';spec=importlib.util.spec_from_file_location('fixture12',path);f12=importlib.util.module_from_spec(spec);spec.loader.exec_module(f12)
def fixture(p):
 rr,hold,c,allow,s12=f12.fixture(p);build12(p/'matrix',p/'b1',p/'labels',p/'role_config.json',p/'v12',p/'backups');s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');s.update(minimum_change_rows=3,minimum_direction_class_rows=1,direction_iterations=40,minimum_validation_rows=3,minimum_guard_rows=2);dump(p/'experiment.json',s);return rr,hold,c,allow,s

def run(p,name='new',baseline='v12',opportunity='b1'):return build(p/'matrix',p/baseline,p/opportunity,p/'labels',p/'experiment.json',p/name,p/'backups')
class Tests(unittest.TestCase):
 def test_full_pipeline_preservation_backups_common_pools_and_frozen_classification(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);before={name:tree(p/name) for name in ['b0','b1','v12','labels','matrix']};r=run(p);self.assertFalse(r['classification_gate_weakened']);self.assertFalse(r['evaluation_outcomes_read']);self.assertEqual(tree(p/'new'),tree(Path(r['backup'])))
   e=evaluate(p/'new',p/'matrix',p/'v12',p/'labels',p/'evaluation',p/'backups');self.assertTrue(e['saves_preserved_exactly']);self.assertTrue(e['classification_labels_preserved']);self.assertFalse(e['models_refitted']);self.assertEqual(tree(p/'evaluation'),tree(Path(e['backup'])))
   for name in before:self.assertEqual(tree(p/name),before[name])
   g={}
   for r in csvrows(p/'evaluation/evaluation_scores.csv'):g.setdefault(tuple(r[k] for k in ['season','player_type','metric','cohort']),set()).add((r['n'],r['membership_sha256']))
   self.assertTrue(all(len(v)==1 for v in g.values()))
   for r in csvrows(p/'new/workload_predictions.csv'):
    if r['player_type']=='hitter':self.assertEqual(r['frozen_v1_2'],r['selected_probability_experiment'])
   for a in load(p/'new/fit_audit.json'):self.assertTrue(all(y<a['origin'] and y!=2020 for y in a['fit_years']))
 def test_2026_outcomes_do_not_change_frozen_models_forecasts_or_labels(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);run(p,'a')
   for r in hold:
    for k,v in list(r.items()):
     if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.5
   (p/'matrix/holdout_matrix.parquet').unlink();f12.f1.fm.parquet(p/'matrix/holdout_matrix.parquet',hold);f12.f1.fm.refresh_matrix(p);f12.label_tables(p,rr,hold);run(p,'b')
   for n in ['frozen_models.json','historical_forecasts.csv','frozen_2026_forecasts.csv','classification_and_probability_inputs.csv']:self.assertEqual((p/'a'/n).read_bytes(),(p/'b'/n).read_bytes())
 def test_later_validation_cannot_change_earlier_selected_experiments(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);run(p,'a')
   for r in rr:
    if r['target_season']==2025:
     for k,v in list(r.items()):
      if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.2
     if r['player_type']=='pitcher':r['y_GS']=r['y_G'] if int(r['mlbam_id'])%2 else 0
   (p/'matrix/training_matrix.parquet').unlink();f12.f1.fm.parquet(p/'matrix/training_matrix.parquet',rr);f12.f1.fm.refresh_matrix(p);f12.label_tables(p,rr,hold);f12.build0(p/'matrix',p/'config.json',p/'c0',p/'backups');f12.build1(p/'matrix',p/'c0',p/'opportunity.json',p/'c1',p/'backups');build12(p/'matrix',p/'c1',p/'labels',p/'role_config.json',p/'c12',p/'backups');run(p,'b','c12','c1');self.assertEqual((p/'a/historical_forecasts.csv').read_bytes(),(p/'b/historical_forecasts.csv').read_bytes())
 def test_change_model_fits_both_directions_and_prediction_ignores_target_labels(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);training=copy.deepcopy([r for r in rr if r['target_season']<2024])
   for r in training:
    m='PA' if r['player_type']=='hitter' else 'OUTS';a=anchor(r,s)
    if a is not None:r['y_'+m]=a*(.7 if int(r['mlbam_id'])%2 else 1.2);r['y_eligible_'+m]=1
   b,audit=fit_change(training,allow,c,s)
   for role in ['hitter','pitcher']:
    self.assertEqual(b[role]['direction']['status'],'FITTED');self.assertNotIn('role_probability_STARTER',b[role]['direction']['preprocessing']['numeric'])
   testing=[r for r in rr if r['target_season']==2024];first=predict_change(b,testing,s);changed=copy.deepcopy(testing)
   for r in changed:
    for k in list(r):
     if k.startswith('y_') and not k.startswith('y_eligible_') and r[k] is not None:r[k]=99999
   self.assertEqual(first,predict_change(b,changed,s));self.assertTrue(all(0<=v['growth_probability']<=1 for v in first.values()))
 def test_missing_anchor_and_zero_are_distinct(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');r=dict(player_type='hitter',x_actual_lag1_PA=None,source_season_lag1=2024);self.assertIsNone(anchor(r,s));r['x_actual_lag1_PA']=0;self.assertEqual(anchor(r,s),0);r['x_actual_lag1_PA']=100;r['source_season_lag1']=2020;self.assertEqual(anchor(r,s),270)
 def test_conditional_change_labels_missing_exposure_and_zero_out_appearance(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');r=dict(player_type='pitcher',x_actual_lag1_OUTS=30,source_season_lag1=2024,y_OUTS=0,y_eligible_OUTS=1,y_G=1,y_eligible_G=1);a=change_rows([r],'pitcher',s)[0];self.assertEqual(a['change_delta'],-30);r['y_eligible_OUTS']=0;self.assertIsNone(change_rows([r],'pitcher',s)[0]['change_delta']);r['y_eligible_OUTS']=1;r['y_G']=0;self.assertIsNone(change_rows([r],'pitcher',s)[0]['change_delta'])
 def test_ties_are_non_growth_zero_loss(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');r=dict(player_type='hitter',x_actual_lag1_PA=100,y_PA=100,y_eligible_PA=1,y_G=25,y_eligible_G=1);a=change_rows([r],'hitter',s)[0];self.assertEqual(a['y_LOSS'],0);self.assertEqual(a['y_eligible_GAIN'],0)
 def test_one_sign_support_is_not_a_fabricated_change_forecast(self):
  c=load(Path(__import__('standalone_models_v1_0').__file__).parent/'config/standalone_baselines_v1_0.json');s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');rr=[dict(target_season=2023,player_type='hitter',mlbam_id=str(i+1),x_actual_lag1_PA=100,source_season_lag1=2022,y_PA=120,y_eligible_PA=1,y_G=30,y_eligible_G=1) for i in range(4)];b,a=fit_change(rr,[],c,s);pp=predict_change(b,rr,s);self.assertTrue(all(v['conditional_volume'] is None for v in pp.values()));self.assertEqual(b['hitter']['direction']['status'],'TRAINING_FREQUENCY_FALLBACK')
 def test_probability_inputs_change_mixture_without_changing_any_classification(self):
  bundle=dict(target=Target('pitcher','OUTS','OUTS',None,0,900,0).__dict__,config={},pooled={},experts={role:dict(model={'value':v},use_pooled=False) for role,v in zip(['STARTER','RELIEVER','SWING'],[600,120,300])});r=[dict(player_type='pitcher',classification_label='STARTER')]
  def pred(model,rows,t,c):return [model['value']]*len(rows),[model['value']]*len(rows)
  with patch('standalone_role_workload_v1_2.predict',side_effect=pred):
   a,_=predict_workload(bundle,with_probabilities(r,[[1.,0,0]]));b,_=predict_workload(bundle,with_probabilities(r,[[0,1.,0]]));self.assertEqual(a,[600]);self.assertEqual(b,[120]);self.assertEqual(r[0]['classification_label'],'STARTER')
 def test_gates_need_both_comparators_and_prior_guard(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');h=[dict(season=y,cohort=cohort,n=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2022,2023] for cohort in ['all','guard']];self.assertTrue(gates(h,2024,s)['adopt']);self.assertFalse(gates([],2024,s)['adopt']);self.assertFalse(all(g['adopt'] for g in [gates(h,2024,s),gates([],2024,s)]));self.assertFalse(gates(h,2023,s)['adopt'])
 def test_ties_retain_frozen_release_and_2020_cannot_select(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');h=[dict(season=y,cohort=cohort,n=100,baseline_mse=1,candidate_mse=1,baseline_mae=1,candidate_mae=1) for y in [2020,2022,2023] for cohort in ['all','guard']];d=gates(h,2024,s);self.assertFalse(d['adopt']);self.assertNotIn(2020,d['gates']['all']['validation_seasons'])
 def test_overlay_coherent_counts_saves_and_zero_original_fallback(self):
  old=dict(OUTS=300,IP=100,H=90,BB=30,ER=40,SO=110,SV=25,ERA=3.6,WHIP=1.2);v=volume_overlay(old,450,'pitcher');self.assertEqual(v['SV'],25);self.assertEqual(v['IP'],150);self.assertAlmostEqual(9*v['ER']/v['IP'],v['ERA']);self.assertEqual(effective(100,0),0);self.assertEqual(effective(None,100),100);h=dict(PA=100,AB=80,H=20,HR=2,AVG=.25);x=volume_overlay(h,200,'hitter');self.assertEqual(x['AVG'],x['H']/x['AB'])
 def test_common_pools_missing_outcomes_and_true_zero(self):
  r=dict(season=2026,player_type='hitter',mlbam_id='1',**{m:100 for m in METHODS});row=dict(target_season=2026,player_type='hitter',mlbam_id='1');s,p,c=scores([r],[row],{});self.assertEqual(s,[]);s,p,c=scores([r],[row],{(2026,'hitter','1','PA'):0});self.assertEqual({x['n'] for x in s},{1});self.assertEqual(len({x['membership_sha256'] for x in s}),1)
 def test_direction_metrics_have_matched_probability_and_trend_pools(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');r=dict(target_season=2026,player_type='hitter',mlbam_id='1',x_actual_lag1_PA=100,x_actual_lag2_PA=80,source_season_lag1=2025,source_season_lag2=2024);d=dict(season=2026,player_type='hitter',mlbam_id='1',growth_probability=.8,training_growth_frequency=.5);a={(2026,'hitter','1','PA'):120,(2026,'hitter','1','G'):30};ss,p=direction_scores([d],[r],a,s);self.assertAlmostEqual(ss[0]['model_brier'],.04);self.assertEqual(ss[0]['trend_pool_n'],1);self.assertEqual(ss[0]['model_accuracy_on_trend_pool'],1)
 def test_external_workload_pool_same_for_all_arms(self):
  r=dict(season=2026,player_type='pitcher',mlbam_id='1',**{m:300 for m in METHODS});a={(2026,'pitcher','1','OUTS'):330};e={(2026,'pitcher','1','OUTS','Steamer'):(310,'record'),(2026,'pitcher','1','IP','Steamer'):(310/3,'record')};ss,p,c=benchmarks([r],a,e,{2026:{'Steamer'}});self.assertEqual({x['n'] for x in ss if x['player_type']=='pitcher'},{1});self.assertTrue(all(x['source_record_id']=='record' for x in p if x['method']=='Steamer'))
 def test_nonchronological_probability_bank_is_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fields=['season','mlbam_id','method','latest_fit_year','actual_role','predicted_role','prior_role','p_STARTER','p_RELIEVER','p_SWING'];rows=[dict(zip(fields,[2026,'1',method,2025,'NOT_READ','STARTER','STARTER',.8,.1,.1])) for method in ['prior_role','categorical']];write(p/'role_predictions.csv',rows,fields);freeze={'role_predictions_sha256':sha(p/'role_predictions.csv')};bank=probability_bank(p,[dict(target_season=2026,player_type='pitcher',mlbam_id='1')],freeze);self.assertEqual(bank[2026,'1']['prior_role']['predicted_role'],'STARTER');rows[1]['latest_fit_year']=2026;write(p/'role_predictions.csv',rows,fields);freeze['role_predictions_sha256']=sha(p/'role_predictions.csv')
   with self.assertRaises(ValueError):probability_bank(p,[dict(target_season=2026,player_type='pitcher',mlbam_id='1')],freeze)
 def test_change_magnitudes_respect_anchor_and_cap(self):
  s=load(ROOT/'config/standalone_workload_experiments_v1_3.json');role='hitter';bundle={role:dict(config={},direction=dict(coefficients=None,frequency=.5),magnitudes={name:dict(model={},target=Target(role,name,name,None,0,800,0).__dict__) for name in ['GAIN','LOSS']})};r=dict(target_season=2026,player_type=role,mlbam_id='1',source_season_lag1=2025,x_actual_lag1_PA=100)
  with patch('standalone_workload_experiments_v1_3.predict',return_value=([1000],[1000])):v=predict_change(bundle,[r],s)[2026,role,'1']
  self.assertEqual(v['conditional_LOSS'],100);self.assertEqual(v['conditional_GAIN'],700);self.assertEqual(v['conditional_volume'],400)
 def test_tampered_release_and_existing_output_fail_without_publication(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);run(p)
   with self.assertRaises(FileExistsError):run(p)
   (p/'v12/role_predictions.csv').write_text('tampered')
   with self.assertRaises(ValueError):run(p,'bad')
   self.assertFalse((p/'bad').exists())
if __name__=='__main__':unittest.main()
