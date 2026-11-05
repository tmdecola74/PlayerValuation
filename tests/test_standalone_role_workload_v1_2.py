import unittest,tempfile,copy,json,importlib.util
from pathlib import Path
import numpy as np
import duckdb
from standalone_io_v1_0 import *
from standalone_role_workload_v1_2 import *
from role_workload_io_v1_2 import read_labels,verify_join,attribution
from backtest_standalone_role_workload_v1_2 import build
from evaluate_standalone_role_workload_v1_2 import evaluate,workload_benchmarks
from backtest_standalone_baselines_v1_0 import build as build0
from backtest_standalone_opportunity_v1_1 import build as build1
ROOT=Path(__file__).resolve().parents[1]
path=Path(__import__('backtest_standalone_opportunity_v1_1').__file__).parent/'tests/test_standalone_opportunity_v1_1.py'
spec=importlib.util.spec_from_file_location('fixture1',path);f1=importlib.util.module_from_spec(spec);spec.loader.exec_module(f1)
def label_tables(p,rr,hold):
 root=p/'labels';root.mkdir(exist_ok=True)
 for name,rows in [('training_labels',rr),('holdout_labels',hold)]:
  values=[dict(season=r['target_season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],metric=m,label_value=r['y_'+m],eligible=True) for r in rows for m in ['PA','OUTS','G','GS'] if r.get('y_eligible_'+m)];src=root/(name+'.json');dump(src,values);dest=root/(name+'.parquet')
  if dest.exists():dest.unlink()
  with duckdb.connect() as db:db.read_json(str(src),columns={'season':'INTEGER','player_type':'VARCHAR','mlbam_id':'VARCHAR','metric':'VARCHAR','label_value':'DOUBLE','eligible':'BOOLEAN'}).write_parquet(str(dest))
  src.unlink()
 dump(root/'label_build_report.json',dict(primary_source='FROZEN_FANGRAPHS_ACTUALS',reference_sha256={'actual_counts.parquet':'fixture_counts','player_seasons.parquet':'fixture_players'}));m=root/'output_sha256.json'
 if m.exists():m.unlink()
 dump(m,tree(root))
def fixture(p):
 rr,hold,c,allow=f1.fixture(p)
 for r in rr+hold:
  if r['player_type']=='pitcher' and int(r['mlbam_id'])%3==0:
   r['y_GS']=round(r['y_G']*.3)
   for lag in [1,2,3]:
    g=r.get(f'x_actual_lag{lag}_G');r[f'x_actual_lag{lag}_GS']=round(g*.3) if g is not None else None
 for name,rows in [('training_matrix',rr),('holdout_matrix',hold),('holdout_features',[{k:v for k,v in r.items() if not k.startswith('y_')} for r in hold])]:
  (p/'matrix'/(name+'.parquet')).unlink();f1.fm.parquet(p/'matrix'/(name+'.parquet'),rows)
 f1.fm.refresh_matrix(p);build0(p/'matrix',p/'config.json',p/'b0',p/'backups');build1(p/'matrix',p/'b0',p/'opportunity.json',p/'b1',p/'backups');label_tables(p,rr,hold);s=load(ROOT/'config/standalone_role_workload_v1_2.json');s.update(minimum_role_fit_rows=3,minimum_role_class_rows=1,minimum_expert_rows=3,minimum_validation_rows=3,minimum_known_prior_rows=3,minimum_prior_starter_rows=2,softmax_iterations=40);dump(p/'role_config.json',s);return rr,hold,load(p/'b1/frozen_models.json')['models']['config'],allow,s
def run(p,name='new',baseline='b1'):return build(p/'matrix',p/baseline,p/'labels',p/'role_config.json',p/name,p/'backups')
class Tests(unittest.TestCase):
 def test_full_pipeline_oof_preservation_backups_join_and_pools(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);before=tree(p/'b1');actualbefore=tree(p/'labels');r=run(p);self.assertTrue(r['saves_preserved_exactly']);self.assertEqual(tree(p/'b1'),before);self.assertEqual(tree(p/'labels'),actualbefore);self.assertEqual(tree(p/'new'),tree(Path(r['backup'])))
   for x in csvrows(p/'new/role_probability_lineage.csv'):
    if x['latest_role_fit_year']:self.assertLess(int(x['latest_role_fit_year']),int(x['target_season']))
   e=evaluate(p/'new',p/'matrix',p/'labels',p/'b1',p/'evaluation',p/'backups');self.assertFalse(e['models_refitted']);self.assertEqual(tree(p/'evaluation'),tree(Path(e['backup'])));g={}
   for r in csvrows(p/'evaluation/workload_scores.csv'):g.setdefault(tuple(r[k] for k in ['season','player_type','metric','cohort']),set()).add((r['n'],r['membership_sha256']))
   self.assertTrue(all(len(v)==1 for v in g.values()));self.assertEqual(tree(p/'labels'),actualbefore)
 def test_2026_outcome_changes_do_not_change_freeze(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);run(p,'a')
   for r in hold:
    for k,v in list(r.items()):
     if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.5
   (p/'matrix/holdout_matrix.parquet').unlink();f1.fm.parquet(p/'matrix/holdout_matrix.parquet',hold);f1.fm.refresh_matrix(p);label_tables(p,rr,hold);run(p,'b')
   for n in ['frozen_models.json','historical_forecasts.csv','frozen_2026_forecasts.csv','role_predictions.csv']:self.assertEqual((p/'a'/n).read_bytes(),(p/'b'/n).read_bytes())
 def test_later_validation_cannot_change_earlier_forecasts(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);run(p,'a')
   for r in rr:
    if r['target_season']==2025:
     for k,v in list(r.items()):
      if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.2
     if r['player_type']=='pitcher':r['y_GS']=r['y_G'] if int(r['mlbam_id'])%2 else 0
   (p/'matrix/training_matrix.parquet').unlink();f1.fm.parquet(p/'matrix/training_matrix.parquet',rr);f1.fm.refresh_matrix(p);label_tables(p,rr,hold);build0(p/'matrix',p/'config.json',p/'c0',p/'backups');build1(p/'matrix',p/'c0',p/'opportunity.json',p/'c1',p/'backups');run(p,'b','c1');self.assertEqual((p/'a/historical_forecasts.csv').read_bytes(),(p/'b/historical_forecasts.csv').read_bytes())
   def past(name):return [{k:v for k,v in r.items() if k!='actual_role'} for r in csvrows(p/name/'role_predictions.csv') if int(r['season'])<=2025]
   self.assertEqual(past('a'),past('b'))
 def test_softmax_fit_probability_normalization_and_no_target_features(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);m=fit_roles([r for r in rr if r['target_season']<2024],allow,c,s);self.assertEqual(m['status'],'FITTED');testing=[r for r in rr if r['target_season']==2024 and r['player_type']=='pitcher'];_,_,cat,_=predict_roles(m,testing,s);changed=copy.deepcopy(testing)
   for r in changed:r['y_GS']=0;r['y_G']=1
   _,_,other,_=predict_roles(m,changed,s);np.testing.assert_array_equal(cat,other);np.testing.assert_allclose(cat.sum(axis=1),1);self.assertTrue(np.all(cat>=0))
 def test_prior_role_baseline_and_unknown_population(self):
  rows=[dict(player_type='pitcher',x_actual_lag1_G=30,x_actual_lag1_GS=30),dict(player_type='pitcher',x_actual_lag1_G=None,x_actual_lag1_GS=None)];p,c=role_baseline(rows,[.2,.7,.1],.9);self.assertEqual(c,['STARTER','RELIEVER']);np.testing.assert_allclose(p[1],[.2,.7,.1]);self.assertEqual(prior_role(rows[1]),'UNKNOWN')
 def test_role_gates_preserve_prior_accuracy(self):
  s=load(ROOT/'config/standalone_role_workload_v1_2.json');h=[dict(season=y,cohort=cohort,n=100,model_fitted=True,baseline_brier=.3,categorical_brier=.2,baseline_logloss=.5,categorical_logloss=.4,baseline_accuracy=.85,categorical_accuracy=.84,baseline_balanced_accuracy=.7,categorical_balanced_accuracy=.8) for y in [2022,2023] for cohort in ['all','known_prior']];self.assertEqual(choose_role(h,2024,s)['candidate'],'prior_role')
  for r in h:r['categorical_accuracy']=.86
  self.assertEqual(choose_role(h,2024,s)['candidate'],'categorical');self.assertEqual(choose_role(h,2023,s)['candidate'],'prior_role')
 def test_missing_role_class_and_low_support_expert_fallback(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow,s=fixture(p);m=fit_roles([r for r in rr if actual_role(r)=='STARTER'],allow,c,s);self.assertNotEqual(m['status'],'FITTED');testing=[r for r in hold if r['player_type']=='pitcher'];b,bc,cat,cc=predict_roles(m,testing,s);np.testing.assert_array_equal(b,cat);pp=[r for r in rr if r['player_type']=='pitcher'];enhanced=with_probabilities(pp,np.tile([.3,.5,.2],(len(pp),1)));s['minimum_expert_rows']=100000;w=fit_workload(enhanced,allow,c,s);self.assertTrue(all(x['use_pooled'] for x in w['experts'].values()));pred,_=predict_workload(w,with_probabilities(testing,np.tile([.3,.5,.2],(len(testing),1))));self.assertTrue(all(finite(v) for v in pred))
 def test_probability_guard(self):
  for p in [[.5,.5,.5],[float('nan'),0,1],[-.1,.5,.6]]:
   with self.assertRaises(ValueError):with_probabilities([dict(player_type='pitcher')],[p])
 def test_workload_gate_requires_prior_starter_support(self):
  s=load(ROOT/'config/standalone_role_workload_v1_2.json');h=[dict(season=y,cohort='all',n=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2022,2023]];self.assertFalse(choose_workload(h,2024,s)['adopt']);h += [dict(season=y,cohort='prior_starter',n=40,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2022,2023]];self.assertTrue(choose_workload(h,2024,s)['adopt'])
 def test_overlay_preserves_saves_and_rates_and_rejection(self):
  old=dict(OUTS=300,IP=100,H=90,ER=40,BB=30,SO=110,SV=25,ERA=3.6,WHIP=1.2);v=overlay(old,450,True);self.assertEqual(v['SV'],25);self.assertEqual(v['IP'],150);self.assertEqual(v['ERA'],3.6);self.assertAlmostEqual((v['H']+v['BB'])/v['IP'],v['WHIP']);self.assertEqual(overlay(old,900,False),old);self.assertIsNone(overlay(old,0,True)['ERA'])
 def test_actual_join_missing_zero_and_conflict(self):
  r=dict(target_season=2024,player_type='pitcher',mlbam_id='1',y_OUTS=0,y_eligible_OUTS=1);a={(2024,'pitcher','1','OUTS'):0.};verify_join([r],a)
  with self.assertRaises(ValueError):verify_join([r],{})
  r2=copy.deepcopy(r);r2['y_OUTS']=2
  with self.assertRaises(ValueError):verify_join([r2],a)
  pp=[dict(season=2024,player_type='pitcher',mlbam_id='1',method=m,metric='OUTS',prediction=10) for m in ['v1_1','v1_2']];detail,scores,coverage=attribution(pp,[r],{});self.assertIsNone(detail[0]['actual']);self.assertEqual(scores,[]);self.assertEqual(coverage[0]['paired'],0)
 def test_tamper_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);run(p)
   with self.assertRaises(FileExistsError):run(p)
   (p/'matrix/training_matrix.parquet').write_bytes(b'tampered')
   with self.assertRaises(ValueError):run(p,'bad')
   self.assertFalse((p/'bad').exists())
 def test_workload_benchmarks_identical_pools(self):
  pp=[dict(season=2026,player_type='pitcher',mlbam_id='1',method=m,metric='OUTS',prediction=v) for m,v in [('v1_1',300),('v1_2',330)]];a={(2026,'pitcher','1','OUTS'):360};ext={(2026,'pitcher','1','OUTS','Steamer'):(320,'record')};s,p,c=workload_benchmarks(pp,a,ext,{2026:{'Steamer'}});self.assertEqual({r['n'] for r in s if r['metric']=='OUTS'},{1});self.assertTrue(all(r['source_record_id']=='record' for r in p if r['method']=='Steamer'))
if __name__=='__main__':unittest.main()
