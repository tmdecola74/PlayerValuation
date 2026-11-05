import unittest,tempfile,copy,csv,io,json,importlib.util,shutil
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch
import duckdb
from standalone_io_v1_0 import *
from standalone_growth_sb_v1_6 import *
from growth_sb_io_v1_6 import sources,forecast,validate,replay
from growth_sb_scores_v1_6 import summaries,SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS,direction_scores
from backtest_standalone_growth_sb_v1_6 import build
from evaluate_standalone_growth_sb_v1_6 import evaluate
ROOT=Path(__file__).resolve().parents[1]
P15=Path(__import__('backtest_standalone_holds_attribution_v1_5').__file__).parent
spec=importlib.util.spec_from_file_location('fixture16_previous',P15/'tests/test_standalone_holds_attribution_v1_5.py');f15=importlib.util.module_from_spec(spec);spec.loader.exec_module(f15)

def fixture(p):
 fm=f15.f13.f12.f1.fm;original=fm.counts
 def counts(role,i,y):
  v=original(role,i,y)
  if role=='hitter' and i%2==0:v['SB']=0
  if role=='pitcher':
   scale=.75 if y%2==0 else 1.15
   for m in ['OUTS','H','ER','BB','SO','HR','W','QS']:v[m]=round(v[m]*scale)
  return v
 with patch.object(fm,'counts',side_effect=counts):rr,hold,c,allow,_=f15.fixture(p)
 f15.run(p);s=load(ROOT/'config/standalone_growth_sb_v1_6.json');s.update(minimum_fit_rows=3,minimum_binary_class_rows=1,minimum_expert_rows=3,binary_iterations=40,minimum_positive_SB_opportunities=1,minimum_validation_rows=3,minimum_guard_rows=2);dump(p/'growth_sb.json',s);return rr,hold,c,allow,s

def run(p,name='new16',labels=None):return build(p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',labels or p/'labels',p/'growth_sb.json',p/name,p/'backups')
def context(p):return sources(p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels')
def runeval(p,name='eval16'):return evaluate(p/'new16',p/'new15',p/'new14',p/'new13',p/'matrix',p/'v12full',p/'labels',p/name,p/'backups')

class Units(unittest.TestCase):
 def test_opportunity_proxy_and_missing_components(self):
  self.assertEqual(opportunity(dict(H=100,HR=20,BB=40,HBP=5)),125);self.assertIsNone(opportunity(dict(H=100,HR=20,BB=None,HBP=5)))
  with self.assertRaises(ValueError):opportunity(dict(H=10,HR=20,BB=0,HBP=0))
 def test_anchor_missing_zero_and_2020_normalization(self):
  s=load(ROOT/'config/standalone_growth_sb_v1_6.json');r=dict(x_actual_lag1_OUTS=None,source_season_lag1=2020);self.assertIsNone(anchor(r,s));r['x_actual_lag1_OUTS']=0;self.assertEqual(anchor(r,s),0);r['x_actual_lag1_OUTS']=100;self.assertEqual(anchor(r,s),270)
 def test_frozen_holds_saves_and_separate_arms(self):
  key=(2026,'pitcher','1');v=dict(OUTS=300,IP=100,H=90,ER=40,BB=30,HR=10,SO=110,W=8,QS=10,SV=25,HLD=12,SV_plus_HLD=37,ERA=3.6,WHIP=1.2);c={'base15':{key:v}};d=dict(baseline=300,candidate=450,selected=450);x=forecast(c,key,d,'selected_workload_experiment');self.assertEqual(x['HLD'],12);self.assertEqual(x['SV'],25);self.assertEqual(x['SV_plus_HLD'],37);self.assertEqual(x['IP'],150);self.assertAlmostEqual(x['ERA'],9*x['ER']/x['IP']);self.assertEqual(forecast(c,key,d,'selected_SB_experiment'),v)
 def test_SB_overlay_never_changes_playing_time_or_other_counts(self):
  key=(2026,'hitter','1');v=dict(PA=100,AB=80,H=20,**{'1B':14,'2B':3,'3B':1,'HR':2},BB=12,HBP=2,SF=3,SH=1,R=10,RBI=9,SB=2,AVG=.25,OBP=34/97,SLG=31/80,OPS=34/97+31/80);c={'base15':{key:v}};d=dict(baseline=2,candidate=8,selected=8);out=forecast(c,key,d,'selected_SB_experiment');self.assertEqual(out['SB'],8);self.assertTrue(all(out[m]==x for m,x in v.items() if m!='SB'));self.assertEqual(forecast(c,key,d,'selected_workload_experiment'),v)
 def test_workload_and_SB_gates_require_their_prior_cohorts(self):
  s=load(ROOT/'config/standalone_growth_sb_v1_6.json')
  for role,cohorts_ in [('pitcher',['all','prior_starter','prior_reliever']),('hitter',['all','prior_runner','prior_zero_SB'])]:
   h=[dict(season=y,cohort=cc,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2022,2023] for cc in cohorts_];self.assertTrue(selection(h,2024,role,s)['adopt']);h[-1]['candidate_mse']=10;self.assertFalse(selection(h,2024,role,s)['adopt']);self.assertFalse(selection(h,2023,role,s)['adopt'])
 def test_2020_and_future_labels_never_select(self):
  s=load(ROOT/'config/standalone_growth_sb_v1_6.json');h=[dict(season=y,cohort=c,n=100,supported=100,baseline_mse=2,candidate_mse=1,baseline_mae=2,candidate_mae=1) for y in [2020,2023,2026] for c in ['all','prior_starter','prior_reliever']];v=selection(h,2026,'pitcher',s);self.assertFalse(v['adopt']);self.assertEqual(v['gates']['all']['validation_seasons'],[2023])
 def test_unsupported_class_is_not_a_fabricated_zero(self):
  c=load(Path(__import__('standalone_models_v1_0').__file__).parent/'config/standalone_baselines_v1_0.json');s=load(ROOT/'config/standalone_growth_sb_v1_6.json');r=dict(target_season=2023,y_GROW=1,y_eligible_GROW=1);m=binary([r],'GROW',[],c,s);self.assertEqual(m['status'],'UNSUPPORTED_CLASSES');self.assertEqual(binary_predict(m,[r],c),[None])
 def test_role_probability_mixture_controls_growth_without_actual_role(self):
  from standalone_models_v1_0 import Target
  c=load(Path(__import__('standalone_models_v1_0').__file__).parent/'config/standalone_baselines_v1_0.json');s=load(ROOT/'config/standalone_growth_sb_v1_6.json');parts={}
  for name in ['GROWTH_LOG','DECLINE_LOG']:parts[name]=dict(target=Target('pitcher',name,name,None,0,7,0).__dict__,pooled={'value':0},experts={r:dict(use_pooled=False,model={'value':math.log(2) if name=='GROWTH_LOG' and r=='STARTER' else 0.}) for r in ROLES})
  m={'pitcher':dict(config=c,occurrence={},parts=parts,supported=True)};r=dict(target_season=2026,player_type='pitcher',mlbam_id='1',x_actual_lag1_OUTS=100,source_season_lag1=2025,frozen_participation=1,role_probability_STARTER=1,role_probability_RELIEVER=0,role_probability_SWING=0);base={(2026,'pitcher','1'):{'OUTS':100}}
  def pred(model,rr,t,c):return [model['value']]*len(rr),[model['value']]*len(rr)
  with patch('standalone_growth_sb_v1_6.predict',side_effect=pred),patch('standalone_growth_sb_v1_6.binary_predict',return_value=[1.]):
   a=predict_models(m,[r],base,s);r['role_probability_STARTER']=0;r['role_probability_RELIEVER']=1;b=predict_models(m,[r],base,s)
  self.assertAlmostEqual(a[2026,'pitcher','1']['candidate'],201);self.assertAlmostEqual(b[2026,'pitcher','1']['candidate'],100)

 def test_external_pools_are_identical_and_true_zero_actuals_kept(self):
  keys=[(2026,'hitter',str(i)) for i in [1,2]];c={'rows':{k:{} for k in keys}};items={k:{} for k in keys};actual={keys[0]+('SB',):0,keys[1]+('SB',):3};external={keys[0]+('SB','Steamer'):(1.,'record1')};buf=[io.StringIO() for _ in range(3)];ww=[csv.DictWriter(b,fieldnames=f) for b,f in zip(buf,[SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS])]
  for w in ww:w.writeheader()
  with patch('growth_sb_scores_v1_6.forecast',return_value={'SB':2.}):summaries(c,items,actual,*ww,external,{2026:{'Steamer'}})
  rr=list(csv.DictReader(io.StringIO(buf[0].getvalue())));rr=[r for r in rr if r['season']=='2026' and r['player_type']=='hitter' and r['metric']=='SB' and r['cohort']=='all_eligible'];internal=[r for r in rr if r['comparison_group']=='internal'];external_rows=[r for r in rr if r['comparison_group']=='Steamer_paired'];self.assertEqual({r['n'] for r in internal},{'2'});self.assertEqual({r['n'] for r in external_rows},{'1'});self.assertEqual(len(external_rows),len(SCORE_METHODS)+1);self.assertEqual(len({r['membership_sha256'] for r in external_rows}),1)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.rr,cls.hold,cls.base,cls.allow,cls.settings=fixture(cls.p);cls.report=run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_pipeline_backup_and_support(self):
  p=self.p;self.assertEqual(tree(p/'new16'),tree(Path(self.report['backup'])));self.assertFalse(self.report['evaluation_outcomes_read']);self.assertTrue(self.report['holds_preserved_exactly']);self.assertTrue(all(self.report['final_model_support'].values()));self.assertFalse(self.report['experiments_combined'])
 def test_evaluation_no_refit_complete_backup_common_pools(self):
  p=self.p;before={n:tree(p/n) for n in ['new15','new14','new13','v12full','matrix','labels','new16']};r=runeval(p);self.assertFalse(r['models_refitted']);self.assertFalse(r['selection_retuned']);self.assertEqual(tree(p/'eval16'),tree(Path(r['backup'])))
  for n,v in before.items():self.assertEqual(tree(p/n),v)
  g=defaultdict(set)
  for d in csvrows(p/'eval16/category_scores.csv'):g[tuple(d[n] for n in ['season','player_type','metric','cohort','comparison_group'])].add((d['n'],d['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in g.values()))
 def test_no_2026_outcomes_opened_during_build(self):
  import standalone_combined_v1_4 as co
  original=co.table
  def guard(path):
   if Path(path).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('2026 outcomes opened')
   return original(path)
  with patch('standalone_combined_v1_4.table',side_effect=guard):run(self.p,'no_holdout')
  self.assertEqual((self.p/'new16/frozen_2026_forecasts.csv').read_bytes(),(self.p/'no_holdout/frozen_2026_forecasts.csv').read_bytes())
 def test_2026_labels_cannot_change_models_choices_or_forecasts(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'labels';shutil.copytree(p/'labels',q);rr=table(q/'holdout_labels.parquet')
   for r in rr:r['label_value']*=2
   dump(q/'x.json',rr);(q/'holdout_labels.parquet').unlink()
   with duckdb.connect() as db:db.read_json(str(q/'x.json')).write_parquet(str(q/'holdout_labels.parquet'))
   (q/'x.json').unlink();f15.refresh(q);run(p,'changed_holdout',q)
   for n in ['frozen_models.json','rolling_choices.json','historical_forecasts.csv','frozen_2026_forecasts.csv']:self.assertEqual((p/'new16'/n).read_bytes(),(p/'changed_holdout'/n).read_bytes())
 def test_future_validation_labels_cannot_change_earlier_fit(self):
  p=self.p;c=context(p);rows=prepared(c,self.settings);base=load(p/'v12full/frozen_models.json')['workload_model']['config'];m,_=fit_models(rows,c['actual_training'],self.allow,base,self.settings,2024);a=dict(c['actual_training'])
  for k in list(a):
   if k[0]>=2024:a[k]=99999
  n,_=fit_models(rows,a,self.allow,base,self.settings,2024);self.assertEqual(m,n)
 def test_prediction_does_not_read_target_labels(self):
  p=self.p;c=context(p);f=load(p/'new16/frozen_models.json');rr=[r for r in prepared(c,self.settings) if r['target_season']==2026];a=predict_models(f['models'],rr,c['base15'],self.settings);other=copy.deepcopy(rr)
  for r in other:
   for m in ['OUTS','GS','G','SB','H','HR','BB','HBP']:r['y_'+m]=99999;r['y_eligible_'+m]=1
  self.assertEqual(a,predict_models(f['models'],other,c['base15'],self.settings))
 def test_preprocessing_names_and_expert_fit_chronology(self):
  f=load(self.p/'new16/frozen_models.json')
  for role,model in f['models'].items():
   self.assertTrue(all(not n.startswith('y_') for n in model['occurrence']['preprocessing']['numeric']));self.assertNotIn('fit_role',model['occurrence']['preprocessing']['numeric'])
  for a in load(self.p/'new16/fit_audit.json'):self.assertTrue(all(y<a['origin'] and y!=2020 for y in a['fit_years']))
 def test_missing_prior_and_zero_baseline_fallback(self):
  p=self.p;c=context(p);f=load(p/'new16/frozen_models.json');r=next(r for r in prepared(c,self.settings) if r['target_season']==2026 and r['player_type']=='pitcher');key=(2026,'pitcher',r['mlbam_id']);r['x_actual_lag1_OUTS']=None;d=predict_models({'pitcher':f['models']['pitcher']},[r],c['base15'],self.settings)[key];self.assertFalse(d['supported']);self.assertEqual(d['candidate'],c['base15'][key]['OUTS']);r['x_actual_lag1_OUTS']=0;b=copy.deepcopy(c['base15']);b[key]['OUTS']=0;d=predict_models({'pitcher':f['models']['pitcher']},[r],b,self.settings)[key];self.assertFalse(d['supported']);self.assertEqual(d['candidate'],0)
 def test_missing_SB_primitive_not_imputed_to_zero(self):
  p=self.p;c=context(p);f=load(p/'new16/frozen_models.json');r=next(r for r in prepared(c,self.settings) if r['target_season']==2026 and r['player_type']=='hitter');k=(2026,'hitter',r['mlbam_id']);b=copy.deepcopy(c['base15']);b[k]['HBP']=None;d=predict_models({'hitter':f['models']['hitter']},[r],b,self.settings)[k];self.assertFalse(d['supported']);self.assertIsNone(d['raw_candidate']);self.assertEqual(d['candidate'],b[k]['SB'])
 def test_output_guard_and_interrupt_stage_cleanup(self):
  p=self.p
  with self.assertRaises(FileExistsError):run(p)
  with patch('backtest_standalone_growth_sb_v1_6.fit_models',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run(p,'interrupted')
  self.assertFalse((p/'interrupted').exists());self.assertFalse(list(p.glob('interrupted.staging-*')))
 def test_tampering_and_rehashed_selection_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'run';shutil.copytree(p/'new16',q);path=q/'experiment_predictions.csv';rr=csvrows(path);rr[0]['selected']=str(float(rr[0]['selected'])+1);write(path,rr,list(rr[0]));f=load(q/'freeze_manifest.json');f[path.name]=sha(path);dump(q/'freeze_manifest.json',f);f15.refresh(q)
   with self.assertRaisesRegex(ValueError,'Selection'):validate(q,context(p))
 def test_rehashed_frozen_hold_change_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'run';shutil.copytree(p/'new16',q);path=q/'frozen_2026_forecasts.csv';rr=csvrows(path);d=next(d for d in rr if d['metric']=='HLD');d['prediction']=str(float(d['prediction'])+1);write(path,rr,list(rr[0]));f=load(q/'freeze_manifest.json');f[path.name]=sha(path);dump(q/'freeze_manifest.json',f);f15.refresh(q)
   with self.assertRaisesRegex(ValueError,'overlay'):validate(q,context(p))

 def test_masked_training_primitive_is_not_backfilled(self):
  p=self.p;c=context(p);rr=prepared(c,self.settings);truth=dict(c['actual_training']);r=next(r for r in rr if r['player_type']=='hitter' and r['target_season']==2023 and r['y_SB']>0);k=(2023,'hitter',r['mlbam_id'],'HBP');truth.pop(k);r['y_HBP']=None;r['y_eligible_HBP']=0;base=load(p/'v12full/frozen_models.json')['workload_model']['config'];m,_=fit_models(rr,truth,self.allow,base,self.settings,2024);rr2=copy.deepcopy(rr);r2=next(x for x in rr2 if x['player_type']=='hitter' and x['target_season']==2023 and x['mlbam_id']==r['mlbam_id']);r2['y_HBP']=0;r2['y_eligible_HBP']=1
  with self.assertRaisesRegex(ValueError,'mask/value'):fit_models(rr2,truth,self.allow,base,self.settings,2024)
  self.assertGreater(m['hitter']['model']['n_fit'],0)
 def test_sparse_role_experts_use_pooled_models(self):
  p=self.p;c=context(p);s=dict(self.settings);s['minimum_expert_rows']=999999;base=load(p/'v12full/frozen_models.json')['workload_model']['config'];m,a=fit_models(prepared(c,s),c['actual_training'],self.allow,base,s,2024);self.assertTrue(all(v['use_pooled'] for part in m['pitcher']['parts'].values() for v in part['experts'].values()))
 def test_growth_and_decline_counts_are_bounded(self):
  p=self.p;c=context(p);f=load(p/'new16/frozen_models.json');rr=[r for r in prepared(c,self.settings) if r['target_season']==2026];pp=predict_models(f['models'],rr,c['base15'],self.settings)
  for k,d in pp.items():
   if d['supported']:
    self.assertGreaterEqual(d['raw_candidate'],0);self.assertLessEqual(d['raw_candidate'],self.settings['maximum_OUTS'] if k[1]=='pitcher' else self.settings['maximum_SB'])
 def test_rehashed_missing_full_vector_row_is_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'run';shutil.copytree(p/'new16',q);path=q/'frozen_2026_forecasts.csv';rr=csvrows(path);write(path,rr[1:],list(rr[0]));f=load(q/'freeze_manifest.json');f[path.name]=sha(path);dump(q/'freeze_manifest.json',f);f15.refresh(q)
   with self.assertRaisesRegex(ValueError,'Incomplete full'):validate(q,context(p))

if __name__=='__main__':unittest.main()
