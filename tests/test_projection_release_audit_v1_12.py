import unittest,tempfile,json,importlib.util,argparse,shutil,copy
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch
import projection_release_audit_v1_12 as a
from standalone_io_v1_0 import tree,load,dump,sha,csvrows
from evaluate_projection_release_v1_11_2 import evaluate
import projection_release_v1_11_1 as release
# Reuse the delivered synthetic prior-release fixtures; no production fitting.
P=Path(release.__file__).parent
spec=importlib.util.spec_from_file_location('fixture112_previous',P/'tests/test_projection_release_v1_11_1.py');previous=importlib.util.module_from_spec(spec);spec.loader.exec_module(previous)

def provenance(weights,values):return dict(method='weighted_available_source_mean',normalized_weights=json.dumps(weights),source_values=json.dumps(values))
def hit_case(hw,sw,hs,ss):
 p={};m={};terms=a.EQUATIONS['hitter']['H_MINUS_HIT_TYPES']
 for n in terms:
  w=hw if n=='H' else sw;v=hs if n=='H' else ss if n=='1B' else {s:0 for s in sw};p[n]=provenance(w,v);m[n]=sum(w[s]*v[s] for s in w)
 return m,p,terms

def label(y,role,pid,m,value,eligible=True):return dict(season=y,player_type=role,mlbam_id=pid,metric=m,label_value=value,eligible=eligible)

class ProvenanceTests(unittest.TestCase):
 def test_source_rounding_scale_is_not_certification(self):
  m,p,t=hit_case({'A':.5,'B':.5},{'A':.5,'B':.5},{'A':10.0001,'B':20},{'A':10,'B':20});d,src=a.decompose(m,p,t)
  self.assertEqual(d['magnitude_band'],'WITHIN_ROUNDING_SCALE_NOT_PROVEN');self.assertFalse(d['rounding_precision_verified']);self.assertAlmostEqual(d['common_source_residual'],.00005);self.assertEqual(d['source_pool_effect'],0);self.assertEqual(len(src),2)
 def test_source_pool_effect(self):
  m,p,t=hit_case({'A':.5,'B':.5},{'A':1},{'A':10,'B':20},{'A':10});d,_=a.decompose(m,p,t);self.assertTrue(d['source_pools_differ']);self.assertAlmostEqual(d['source_pool_effect'],5);self.assertEqual(d['common_weight_effect'],0);self.assertEqual(d['common_source_residual'],0)
 def test_same_pool_weight_effect(self):
  m,p,t=hit_case({'A':.5,'B':.5},{'A':.25,'B':.75},{'A':10,'B':20},{'A':10,'B':20});d,_=a.decompose(m,p,t);self.assertFalse(d['source_pools_differ']);self.assertTrue(d['common_pool_weights_differ']);self.assertEqual(d['source_pool_effect'],0);self.assertAlmostEqual(d['common_weight_effect'],-2.5)
 def test_quarter_hit_residual_traced_to_source_without_repair(self):
  m,p,t=hit_case({'A':.5,'B':.5},{'A':.5,'B':.5},{'A':10.25,'B':20.25},{'A':10,'B':20});original=copy.deepcopy((m,p));d,src=a.decompose(m,p,t);self.assertAlmostEqual(d['common_source_residual'],.25);self.assertEqual((m,p),original);self.assertTrue(all(r['source_difference']==.25 for r in src))
 def test_missing_no_common_and_replay_mismatch_are_explicit(self):
  m,p,t=hit_case({'A':1},{'B':1},{'A':10},{'B':10});self.assertEqual(a.decompose(m,p,t)[0]['status'],'NO_COMMON_CONTRIBUTOR_POOL');p['H']['source_values']='{}';self.assertEqual(a.decompose(m,p,t)[0]['status'],'INCOMPLETE_OR_UNNORMALIZED_PROVENANCE')
  m,p,t=hit_case({'A':1},{'A':1},{'A':10},{'A':10});m['H']=11;self.assertEqual(a.decompose(m,p,t)[0]['status'],'SNAPSHOT_PROVENANCE_REPLAY_MISMATCH')
 def test_pa_remainder_not_treated_as_equality(self):
  m=dict(PA=10.5,AB=10,BB=0,HBP=0,SF=0,SH=0,H=1,**{'1B':1,'2B':0,'3B':0,'HR':0});pp=[dict(season=2026,player_type='hitter',player_id='p1',metric=n,**provenance({'A':1},{'A':v})) for n,v in m.items()]
  eq,src,replay,ratios=a.audit_consensus([dict(season=2026,player_type='hitter',player_id='p1',name='P',metrics=m)],pp,set());row=next(r for r in eq if r['equation']=='PA_MINUS_COMPONENTS');self.assertEqual(row['observed_difference'],.5);self.assertFalse(row['violates_arithmetic'])

class CohortTests(unittest.TestCase):
 def test_boundaries_zeros_missing_identical_pools_and_error_partition(self):
  actual=[];comp=[]
  for i,ip in enumerate([0,1,19,20,39,40,99,100]):
   pid=str(i+1);actual.extend([label(2026,'pitcher',pid,'IP',ip),label(2026,'pitcher',pid,'ERA',3.)])
   for source in [a.HOME,'Steamer']:
    comp.append(dict(season='2026',player_type='pitcher',mlbam_id=pid,metric='ERA',projection_source=source,prediction='4' if source==a.HOME else '3.5',name='P',player_id='p'+pid))
  # Missing exposure never becomes zero or enters a cohort.
  actual.append(label(2026,'pitcher','99','ERA',3.));actual=a.labels_index(actual,2026,2026);ss,pp,cc,oo=a.rate_cohorts(comp,actual)
  subset=[r for r in ss if r['metric']=='ERA' and r['comparison_group']=='Steamer_matched'];by={(r['cohort'],r['projection_source']):r for r in subset};self.assertEqual(by['IP_LT20',a.HOME]['n'],2);self.assertEqual(by['IP_20_39',a.HOME]['n'],2);self.assertEqual(by['IP_40_99',a.HOME]['n'],2);self.assertEqual(by['IP_GE100',a.HOME]['n'],1);self.assertEqual(by['ALL_POSITIVE_IP',a.HOME]['n'],7)
  for cohort,_,_ in a.COHORTS['pitcher']:self.assertEqual(by[cohort,a.HOME]['membership_sha256'],by[cohort,'Steamer']['membership_sha256'])
  self.assertFalse(any(r['mlbam_id'] in ['1','99'] for r in pp));self.assertTrue(a.exposure_partition(ss));self.assertTrue(any(r['missing_or_ineligible_exposure']==1 for r in cc if r['metric']=='ERA'))
 def test_duplicate_forecast_or_future_label_rejected(self):
  r=dict(season='2026',player_type='hitter',mlbam_id='1',metric='AVG',projection_source=a.HOME,prediction='.25')
  with self.assertRaises(ValueError):a.rate_cohorts([r,r],{})
  with self.assertRaises(ValueError):a.labels_index([label(2027,'hitter','1','PA',5)],2026,2026)

class MissingTests(unittest.TestCase):
 def test_history_identity_and_coverage_categories_without_debut_claims(self):
  target=a.labels_index([label(2026,'hitter',str(i),'PA',10) for i in range(1,8)],2026,2026)
  prior=a.labels_index([label(2025,'hitter','2','PA',30),label(2022,'hitter','3','PA',10),label(2024,'pitcher','4','OUTS',3)],2015,2025)
  features=[dict(target_season=2026,player_type='hitter',mlbam_id='1',max_source_season=2025,source_cutoff='2025-12-31')]
  rr=a.missing_universe(target,prior,features,[],{'p1':'1','p2':'2'}, {'p1':'One'}, {'6':{'ambigA','ambigB'}});d={r['mlbam_id']:r for r in rr}
  self.assertIn('FORECAST_MISSING',d['1']['classification']);self.assertIn('RECENT_PRIOR',d['2']['classification']);self.assertIn('RETURNER',d['3']['classification']);self.assertIn('OTHER_ROLE',d['4']['classification']);self.assertIn('COLD_START',d['5']['classification']);self.assertIn('AMBIGUOUS',d['6']['identity_status']);self.assertIn('MISSING_WAREHOUSE',d['7']['identity_status']);self.assertTrue(all(r['debut_status'].startswith('NOT_CERTIFIED') for r in rr))
 def test_target_feature_leakage_rejected(self):
  r=dict(target_season=2026,player_type='hitter',mlbam_id='1',max_source_season=2026,source_cutoff='2026-01-01')
  with self.assertRaises(ValueError):a.missing_universe({}, {},[r],[],{}, {},{})

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  previous.Pipeline.setUpClass();cls.fixture=previous.Pipeline;cls.p=cls.fixture.p;q=cls.p
  evaluate(q/'release',q/'labels',cls.fixture.warehouse,q/'audit_evaluation',q/'backups')
  cls.args=argparse.Namespace(run=q/'release',evaluation=q/'audit_evaluation',labels=q/'labels',matrix=q/'matrix',warehouse=cls.fixture.warehouse,output=q/'audit112',backup_root=q/'backups')
  cls.before={n:tree(q/n) for n in ['release','audit_evaluation','labels','matrix']};cls.report=a.build(cls.args)
 @classmethod
 def tearDownClass(cls):previous.Pipeline.tearDownClass()
 def test_full_read_only_outputs_complete_backup_and_disclosure(self):
  for name,v in self.before.items():self.assertEqual(tree(self.p/name),v)
  self.assertEqual(tree(self.p/'audit112'),tree(Path(self.report['backup'])));self.assertFalse(self.report['forecasts_modified']);self.assertFalse(self.report['selection_changed']);self.assertTrue(self.report['previously_reviewed']);self.assertTrue(csvrows(self.p/'audit112/exposure_cohort_scores.csv'));self.assertTrue(csvrows(self.p/'audit112/consensus_primitive_replay.csv'))
 def test_no_model_fit_api_used_and_existing_output_guard(self):
  with self.assertRaises(FileExistsError):a.build(self.args)
  args=argparse.Namespace(**vars(self.args));args.output=self.p/'audit112_no_fit'
  with patch('standalone_holds_v1_5.fit_holds',side_effect=AssertionError('Refitted')):r=a.build(args)
  self.assertFalse(r['models_fitted'])
 def test_hash_and_source_binding_fail_before_publication(self):
  copy_ev=self.p/'audit_eval_tamper';shutil.copytree(self.p/'audit_evaluation',copy_ev);(copy_ev/'player_comparisons.csv').write_text('tampered',encoding='utf-8');args=argparse.Namespace(**vars(self.args));args.evaluation=copy_ev;args.output=self.p/'audit112_bad'
  with self.assertRaises(ValueError):a.build(args)
  self.assertFalse(args.output.exists())
 def test_interruption_cleans_unpublished_output(self):
  args=argparse.Namespace(**vars(self.args));args.output=self.p/'audit112_interrupt'
  with patch('projection_release_audit_v1_12.audit_consensus',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):a.build(args)
  self.assertFalse(args.output.exists());self.assertFalse(list(self.p.glob('audit112_interrupt.staging-*')))

if __name__=='__main__':unittest.main()
