import unittest,tempfile,copy,csv,io,importlib.util,shutil
from pathlib import Path
from unittest.mock import patch
import duckdb
from standalone_io_v1_0 import *
from standalone_combined_v1_4 import *
from build_standalone_combined_v1_4 import build
from category_benchmarks_v1_4 import category_values
from evaluate_standalone_combined_v1_4 import evaluate

ROOT=Path(__import__('backtest_standalone_workload_experiments_v1_3').__file__).parent
spec=importlib.util.spec_from_file_location('fixture13',ROOT/'tests/test_standalone_workload_experiments_v1_3.py');f13=importlib.util.module_from_spec(spec);spec.loader.exec_module(f13)

def hitter():return dict(PA=100,AB=80,H=20,**{'1B':14,'2B':3,'3B':1,'HR':2},BB=12,HBP=2,SF=3,SH=1,R=10,RBI=9,SB=2,AVG=.25,OBP=34/97,SLG=31/80,OPS=34/97+31/80)
def pitcher():return dict(OUTS=300,IP=100,H=90,ER=40,BB=30,SO=110,HR=10,W=8,SV=25,HLD=4,QS=10,ERA=3.6,WHIP=1.2)
def refresh(p):
 p=Path(p);(p/'output_sha256.json').unlink();dump(p/'output_sha256.json',tree(p))
def run(p,name='new'):return build(p/'new13',p/'matrix',p/'v12',p/'labels',p/name,p/'backups')
def evaluate_run(p,name='eval'):return evaluate(p/'new',p/'new13',p/'matrix',p/'v12',p/'labels',p/name,p/'backups')

class UnitTests(unittest.TestCase):
 def test_coherent_scaled_hitter_and_pitcher_ratios_exact_saves(self):
  for role,base,vol in [('hitter',hitter(),175),('pitcher',pitcher(),450)]:
   v=coherent(role,volume_overlay(base,vol,role))
   if role=='hitter':self.assertAlmostEqual(v['AVG'],v['H']/v['AB']);self.assertAlmostEqual(v['OPS'],v['OBP']+v['SLG']);self.assertAlmostEqual(v['H'],sum(v[n] for n in ['1B','2B','3B','HR']))
   else:self.assertEqual(v['SV'],25);self.assertEqual(v['SV_plus_HLD'],31);self.assertEqual(v['IP'],150);self.assertAlmostEqual(v['ERA'],9*v['ER']/v['IP']);self.assertAlmostEqual(v['WHIP'],(v['H']+v['BB'])/v['IP'])
 def test_invalid_component_bound_and_ratio_fail(self):
  for name,value in [('H',81),('AVG',.9),('PA',20)]:
   v=hitter();v[name]=value
   with self.assertRaises(ValueError):coherent('hitter',v)
  v=pitcher();v['HR']=100
  with self.assertRaises(ValueError):coherent('pitcher',v)
 def test_missing_components_and_zero_denominator_not_imputed(self):
  v=hitter();v['H']=None;v['1B']=None;v['AVG']=None;v['OBP']=None;v['SLG']=None;v['OPS']=None;x=coherent('hitter',v);self.assertIsNone(x['AVG'])
  x=coherent('pitcher',volume_overlay(pitcher(),0,'pitcher'));self.assertIsNone(x['ERA']);self.assertIsNone(x['WHIP']);self.assertEqual(x['SV'],25)
 def test_pitcher_change_never_selected(self):
  self.assertEqual(choose_for_role('pitcher',{'pitcher_change':True}),'selected_probability_experiment');self.assertEqual(choose_for_role('hitter',{}),'selected_change_experiment')
 def test_external_combination_requires_both_nonexcluded_components(self):
  self.assertNotIn('SV_plus_HLD',category_values({'SV':20},set()));self.assertEqual(category_values({'SV':20,'HLD':5},set())['SV_plus_HLD'],25)
  for exclusions in [{'HLD'},{'SV'},{'SV_plus_HLD'}]:self.assertNotIn('SV_plus_HLD',category_values({'SV':20,'HLD':5},exclusions))
 def test_label_masks_zero_and_splits(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);rows=[dict(season=2026,player_type='pitcher',mlbam_id='1',metric=m,label_value=v,eligible=e) for m,v,e in [('SV',0,True),('HLD',5,True),('ERA',None,False),('SV_plus_HLD',None,False)]];dump(p/'x.json',rows)
   with duckdb.connect() as db:db.read_json(str(p/'x.json')).write_parquet(str(p/'holdout_labels.parquet'))
   a=read_all_labels(p,'holdout');self.assertEqual(a[2026,'pitcher','1','SV'],0);self.assertNotIn((2026,'pitcher','1','ERA'),a);self.assertNotIn((2026,'pitcher','1','SV_plus_HLD'),a)
   shutil.copyfile(p/'holdout_labels.parquet',p/'training_labels.parquet')
   with self.assertRaises(ValueError):read_all_labels(p,'training')
 def test_all_categories_common_pool_and_benchmark_membership(self):
  c=dict(predictions={(2026,'hitter','1'):{},(2026,'hitter','2'):{}},base={});actual={(2026,'hitter','1','HR'):0,(2026,'hitter','2','HR'):5};external={(2026,'hitter','1','HR','Steamer'):(1,'s1')}
  def vec(c,k):return {m:dict(HR=2) for m in METHODS}
  buf=[io.StringIO() for _ in range(3)];writers=[csv.DictWriter(b,fieldnames=f) for b,f in zip(buf,[SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS])]
  for w in writers:w.writeheader()
  with patch('standalone_combined_v1_4.vectors',side_effect=vec):score_all(c,actual,*writers,external,{2026:{'Steamer'}})
  scores=list(csv.DictReader(io.StringIO(buf[0].getvalue())));ss=[r for r in scores if r['season']=='2026' and r['player_type']=='hitter' and r['metric']=='HR' and r['comparison_group']=='Steamer_paired'];self.assertEqual(len(ss),5);self.assertEqual({r['n'] for r in ss},{'1'});self.assertEqual(len({r['membership_sha256'] for r in ss}),1)
  internal=[r for r in scores if r['season']=='2026' and r['player_type']=='hitter' and r['metric']=='HR' and r['comparison_group']=='internal'];self.assertEqual({r['n'] for r in internal},{'2'})

 def test_all_fantasy_metrics_and_rate_denominators_are_scored(self):
  c=dict(predictions={(2026,'hitter','1'):{},(2026,'pitcher','2'):{}},base={});h=coherent('hitter',hitter());v=coherent('pitcher',pitcher());actual={(2026,role,pid,m):x for role,pid,vector in [('hitter','1',h),('pitcher','2',v)] for m,x in vector.items()}
  def vec(c,k):return {m:dict(h if k[1]=='hitter' else v) for m in METHODS}
  buf=[io.StringIO() for _ in range(3)];ww=[csv.DictWriter(b,fieldnames=f) for b,f in zip(buf,[SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS])]
  for w in ww:w.writeheader()
  with patch('standalone_combined_v1_4.vectors',side_effect=vec):score_all(c,actual,*ww)
  rr=[r for r in csv.DictReader(io.StringIO(buf[0].getvalue())) if r['season']=='2026' and r['cohort']=='all_eligible'];self.assertEqual({r['metric'] for r in rr if r['n']=='1'},set(h)|set(v));self.assertTrue(all(float(r['rmse'])==0 for r in rr if r['n']=='1'))
 def test_missing_label_is_never_reconstructed(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);rows=[dict(season=2026,player_type='pitcher',mlbam_id='1',metric=m,label_value=v,eligible=True) for m,v in [('SV',20),('HLD',5)]];dump(p/'x.json',rows)
   with duckdb.connect() as db:db.read_json(str(p/'x.json')).write_parquet(str(p/'holdout_labels.parquet'))
   self.assertNotIn((2026,'pitcher','1','SV_plus_HLD'),read_all_labels(p,'holdout'))
 def test_external_warehouse_readonly_identity_and_exclusions(self):
  from category_benchmarks_v1_4 import warehouse_forecasts
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);dbpath=p/'w.duckdb'
   with duckdb.connect(str(dbpath)) as db:
    db.execute('CREATE TABLE player_id_crosswalk(player_id VARCHAR,namespace VARCHAR,external_id VARCHAR)');db.execute("INSERT INTO player_id_crosswalk VALUES ('a','mlbam','1')")
    for role in ['hitter','pitcher']:
     db.execute('CREATE TABLE analytical_'+role+'_projections(season INTEGER,source VARCHAR,player_id VARCHAR,record_id VARCHAR,metrics_json VARCHAR,excluded_metrics_json VARCHAR)')
    db.execute('INSERT INTO analytical_pitcher_projections VALUES (2026,?,?,?,?,?)',['Steamer','a','record1',json.dumps(dict(SV=20,HLD=5,IP=100,ER=40,H=90,BB=30)),json.dumps(['SV_plus_HLD'])])
   dump(p/'migration_audit.json',dict(pass_=True));dump(p/'migration_audit.json',{'pass':True,'objects':[]});before=sha(dbpath);external,available,issues,w=warehouse_forecasts(dbpath);self.assertEqual(sha(dbpath),before);self.assertEqual(external[2026,'pitcher','1','SV','Steamer'],(20.,'record1'));self.assertNotIn((2026,'pitcher','1','SV_plus_HLD','Steamer'),external);self.assertFalse(issues)

class PipelineTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.temp=tempfile.TemporaryDirectory();cls.p=Path(cls.temp.name);f13.fixture(cls.p);f13.run(cls.p,'new13');cls.report=run(cls.p)
 @classmethod
 def tearDownClass(cls):cls.temp.cleanup()
 def test_complete_backup_readonly_and_source_selection(self):
  p=self.p;self.assertEqual(tree(p/'new'),tree(Path(self.report['backup'])));self.assertFalse(self.report['evaluation_outcomes_read']);self.assertFalse(self.report['selection_retuned'])
  rows=csvrows(p/'new/component_lineage.csv');self.assertTrue(all(r['selected_component']==('selected_change_experiment' if r['player_type']=='hitter' else 'selected_probability_experiment') for r in rows));self.assertTrue(all(r['saves_preserved']=='True' for r in rows))
 def test_evaluation_common_pools_backup_and_no_refit(self):
  p=self.p;before={n:tree(p/n) for n in ['new','new13','v12','matrix','labels']};r=evaluate_run(p);self.assertFalse(r['models_refitted']);self.assertFalse(r['pitcher_change_used_in_combined']);self.assertEqual(tree(p/'eval'),tree(Path(r['backup'])))
  for n,v in before.items():self.assertEqual(tree(p/n),v)
  g={}
  for r in csvrows(p/'eval/category_scores.csv'):g.setdefault(tuple(r[n] for n in ['season','player_type','metric','cohort','comparison_group']),set()).add((r['n'],r['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in g.values()))
 def test_build_does_not_open_2026_outcomes(self):
  p=self.p
  from standalone_combined_v1_4 import table as actual_table
  def guard(path):
   if Path(path).name in ['holdout_labels.parquet','holdout_matrix.parquet']:raise AssertionError('2026 outcomes opened')
   return actual_table(path)
  with patch('standalone_combined_v1_4.table',side_effect=guard):r=run(p,'no_holdout_read')
  self.assertFalse(r['evaluation_outcomes_read']);self.assertEqual((p/'new/frozen_2026_forecasts.csv').read_bytes(),(p/'no_holdout_read/frozen_2026_forecasts.csv').read_bytes())
 def test_2026_label_change_cannot_change_combined_forecasts(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'labels';shutil.copytree(p/'labels',q);rr=table(q/'holdout_labels.parquet')
   for r in rr:r['label_value']*=2
   dump(q/'changed.json',rr);(q/'holdout_labels.parquet').unlink()
   with duckdb.connect() as db:db.read_json(str(q/'changed.json')).write_parquet(str(q/'holdout_labels.parquet'))
   (q/'changed.json').unlink();refresh(q);build(p/'new13',p/'matrix',p/'v12',q,p/'changed_holdout',p/'backups');self.assertEqual((p/'new/frozen_2026_forecasts.csv').read_bytes(),(p/'changed_holdout/frozen_2026_forecasts.csv').read_bytes());self.assertEqual((p/'new/frozen_composition.json').read_bytes(),(p/'changed_holdout/frozen_composition.json').read_bytes())
 def test_tamper_rejected_and_existing_output_guard(self):
  p=self.p
  with self.assertRaises(FileExistsError):run(p)
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'source';shutil.copytree(p/'new13',q);(q/'workload_predictions.csv').write_text('tampered',encoding='utf-8')
   with self.assertRaises(ValueError):build(q,p/'matrix',p/'v12',p/'labels',p/'bad',p/'backups')
   self.assertFalse((p/'bad').exists())
 def test_rehashed_nonchronological_selection_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'source';shutil.copytree(p/'new13',q);v=load(q/'rolling_choices.json');v[0]['probability_experiment']['adopt']=True;dump(q/'rolling_choices.json',v);refresh(q)
   with self.assertRaisesRegex(ValueError,'gate replay'):build(q,p/'matrix',p/'v12',p/'labels',p/'bad_gate',p/'backups')
 def test_duplicate_full_vector_even_rehashed_is_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'source';shutil.copytree(p/'new13',q);path=q/'historical_forecasts.csv';rr=csvrows(path);rr.append(rr[0]);write(path,rr,list(rr[0]));freeze=load(q/'freeze_manifest.json');freeze['historical_forecasts.csv']=sha(path);dump(q/'freeze_manifest.json',freeze);refresh(q)
   with self.assertRaisesRegex(ValueError,'duplicate'):build(q,p/'matrix',p/'v12',p/'labels',p/'bad_dup',p/'backups')
 def test_interrupt_cleans_unpublished_stage(self):
  p=self.p
  with patch('build_standalone_combined_v1_4.vectors',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):run(p,'interrupted')
  self.assertFalse((p/'interrupted').exists());self.assertEqual(list(p.glob('interrupted.staging-*')),[])
 def test_research_candidate_and_classifications_preserved(self):
  p=self.p;rr=csvrows(p/'new/pitcher_change_research_only.csv');self.assertTrue(rr);self.assertEqual({r['method'] for r in rr},{'pitcher_change_research_only'});self.assertEqual(sha(p/'new/classification_and_probability_inputs.csv'),sha(p/'new13/classification_and_probability_inputs.csv'))

 def test_rehashed_future_fit_audit_is_rejected(self):
  p=self.p
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'source';shutil.copytree(p/'new13',q);a=load(q/'fit_audit.json');a[0]['fit_years']=[a[0]['origin']];dump(q/'fit_audit.json',a);refresh(q)
   with self.assertRaisesRegex(ValueError,'chronology'):build(q,p/'matrix',p/'v12',p/'labels',p/'bad_fit',p/'backups')
 def test_missing_rehashed_combined_metric_rejected(self):
  p=self.p
  from evaluate_standalone_combined_v1_4 import validate_combined
  with tempfile.TemporaryDirectory() as t:
   q=Path(t)/'combined';shutil.copytree(p/'new',q);path=q/'frozen_2026_forecasts.csv';a=csvrows(path);write(path,a[1:],list(a[0]));freeze=load(q/'freeze_manifest.json');freeze[path.name]=sha(path);dump(q/'freeze_manifest.json',freeze);refresh(q);c=context(p/'new13',p/'matrix',p/'v12',p/'labels')
   with self.assertRaisesRegex(ValueError,'Incomplete'):validate_combined(q,c)

if __name__=='__main__':unittest.main()
