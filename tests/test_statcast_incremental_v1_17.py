import unittest,tempfile,argparse,copy,json,importlib.util
from pathlib import Path
from unittest.mock import patch
from standalone_io_v1_0 import load,dump,write,sha,tree,csvrows,table
import statcast_incremental_v1_17 as b
import evaluate_statcast_incremental_v1_17 as e
import standalone_diagnostics_v1_16 as d
from standalone_models_v1_0 import fit,predict
import duckdb

# Self-contained synthetic frozen source shapes, not production data.
def pq(p,rows):
 tmp=p.with_suffix('.tmp.json');dump(tmp,rows)
 with duckdb.connect() as db:db.read_json(str(tmp)).write_parquet(str(p))
 tmp.unlink()
def manifest(p):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',tree(p))
def vector(role):
 return dict(PA=500,AB=450,H=120,**{'1B':85,'2B':20,'3B':5},HR=10,R=60,RBI=50,SB=10,BB=40,HBP=5,SF=5,SH=0,AVG=120/450,OBP=165/500,SLG=180/450,OPS=165/500+180/450) if role=='hitter' else dict(OUTS=450,IP=150,H=130,ER=50,BB=40,SO=140,HR=15,W=10,SV=5,HLD=2,QS=15,ERA=3,WHIP=170/150,SV_plus_HLD=7)
def fixture(p):
 dirs={n:p/n for n in ['release','accepted','matrix','labels','baseline']}
 for v in dirs.values():v.mkdir()
 rows=[];hold=[];hist=[];future=[];labs=[];hl=[];allow=['age_at_target_estimate','history_seasons','x_actual_lag1_G','x_actual_lag1_GS','x_actual_lag1_PA','x_actual_lag1_AB','x_actual_lag1_OUTS']
 for m in ['ev','velocity']:
  for suffix in ['value','eligible','observations','coverage']:allow.append('x_statcast_lag1_'+m+'_'+suffix)
 for y in range(2016,2027):
  for role in ['hitter','pitcher']:
   for i in range(2):
    pid=str(i+1);v=vector(role);r=dict(target_season=y,player_type=role,mlbam_id=pid,max_source_season=y-1,source_cutoff=f'{y-1}-12-31',source_season_lag1=y-1,source_season_lag2=y-2,source_season_lag3=y-3,age_at_target_estimate=24+i*10,history_seasons=i+1,x_actual_lag1_G=30,x_actual_lag1_GS=25,x_actual_lag1_PA=400,x_actual_lag1_AB=350,x_actual_lag1_OUTS=400)
    for m in ['ev','velocity']:
     for suffix,value in [('value',90+i),('eligible',1),('observations',100),('coverage',.9)]:r['x_statcast_lag1_'+m+'_'+suffix]=value
    (hold if y==2026 else rows).append(r)
    for m,val in v.items():
     (hl if y==2026 else labs).append(dict(season=y,player_type=role,mlbam_id=pid,metric=m,eligible=True,label_value=val))
     if y>=2019:(future if y==2026 else hist).append(dict(season=y,player_type=role,mlbam_id=pid,method='selected_v1_5',metric=m,prediction=val))
 for name,rr in [('training_matrix',rows),('holdout_features',hold)]:pq(dirs['matrix']/(name+'.parquet'),rr)
 dump(dirs['matrix']/'feature_schema.json',{'predictor_allowlist':allow});pq(dirs['labels']/'training_labels.parquet',labs);pq(dirs['labels']/'holdout_labels.parquet',hl);dump(dirs['labels']/'label_build_report.json',dict(reference_sha256={'actuals':'fixed'}))
 for name,rr in [('historical_forecasts',hist),('frozen_2026_forecasts',future)]:write(dirs['accepted']/(name+'.csv'),rr,list(rr[0]))
 dump(dirs['accepted']/'frozen_models.json',dict(training_labels_sha256=sha(dirs['labels']/'training_labels.parquet')))
 config=dict(lag_weights=[.5,.3,.2],volume_metrics=['PA','AB','OUTS','G','GS'],source_2020_volume_multiplier=2.7,context_features=['age_at_target_estimate','history_seasons','has_any_statcast_history'],actual_features={'hitter':['PA','AB','G'],'pitcher':['OUTS','G','GS']},structural_zero_baseline_counts=['SV','HLD','QS'],exclude_playing_time_target_seasons=[2020])
 dump(dirs['baseline']/'frozen_models.json',dict(config=config));dump(dirs['release']/'projection_release_report.json',dict(label_reference_sha256={'actuals':'fixed'},models_fitted=False))
 dump(dirs['release']/'input_hashes.json',{str(path):sha(path) for path in [dirs['accepted']/'historical_forecasts.csv',dirs['accepted']/'frozen_2026_forecasts.csv',dirs['accepted']/'frozen_models.json',dirs['matrix']/'training_matrix.parquet',dirs['matrix']/'holdout_features.parquet',dirs['matrix']/'feature_schema.json']})
 for v in dirs.values():manifest(v)
 settings=copy.deepcopy(b.DEFAULT_SETTINGS);settings.update(minimum_fit_rows=3,minimum_gate_rows=1,minimum_guard_rows=1,minimum_gate_folds=2);cp=p/'settings.json';dump(cp,settings)
 return argparse.Namespace(**dirs,config=cp,output=p/'out',backup_root=p/'backups')

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.a=fixture(cls.p);cls.before={n:tree(getattr(cls.a,n)) for n in ['release','accepted','matrix','labels','baseline']};cls.report=b.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_fixed_workload_saves_holds_and_complete_backup(self):
  self.assertEqual(tree(self.a.output),tree(Path(self.report['backup'])))
  for n,v in self.before.items():self.assertEqual(tree(getattr(self.a,n)),v)
  rows=csvrows(self.a.output/'frozen_2026_forecasts.csv');anchor={}
  for r in rows:
   if r['metric'] in (['PA'] if r['player_type']=='hitter' else ['OUTS','IP','SV','HLD','SV_plus_HLD']):anchor.setdefault((r['mlbam_id'],r['player_type'],r['metric']),set()).add(r['prediction'])
  self.assertTrue(all(len(v)==1 for v in anchor.values()));self.assertFalse(self.report['evaluation_outcomes_read']);self.assertFalse(self.report['new_source_promoted'])
 def test_fit_memberships_fold_preprocessing_and_2021_retained(self):
  rows=csvrows(self.a.output/'fold_fit_chronology.csv');groups={}
  for r in rows:
   self.assertTrue(all(y<int(r['origin']) for y in json.loads(r['fit_target_seasons'])));groups.setdefault((r['origin'],r['target']),set()).add((r['n_fit'],r['fit_membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()));self.assertTrue(csvrows(self.a.output/'transition_2021_rates.csv'));self.assertTrue(csvrows(self.a.output/'transition_2021_counts.csv'))
  inventory=csvrows(self.a.output/'fold_predictor_inventory.csv');self.assertFalse(any(r['feature'].startswith('x_statcast') for r in inventory if r['method']=='standard_skill'));self.assertFalse(any('velocity' in r['feature'] for r in inventory if r['target'].startswith('hitter_')))
 def test_identical_rate_comparison_pools(self):
  groups={}
  for r in csvrows(self.a.output/'historical_rate_scores.csv'):groups.setdefault(tuple(r[n] for n in ['season','player_type','metric','cohort_dimension','cohort','comparison_group']),set()).add((r['n'],r['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()))
 def test_holdout_mutation_cannot_change_fit_choices_or_forecasts(self):
  a=copy.copy(self.a);a.output=self.p/'blind';hp=a.labels/'holdout_labels.parquet';original=hp.read_bytes()
  try:
   hp.write_bytes(b'unreadable outcome file')
   with patch.object(b,'table',wraps=b.table) as reader:
    b.build(a);self.assertFalse(any(str(c.args[0]).endswith('holdout_labels.parquet') for c in reader.call_args_list))
   for n in ['frozen_models.json','rolling_choices.json','frozen_2026_forecasts.csv']:self.assertEqual(sha(a.output/n),sha(self.a.output/n))
  finally:hp.write_bytes(original)
 def test_separate_evaluation_cannot_fit_or_change_frozen_outputs(self):
  a=argparse.Namespace(run=self.a.output,labels=self.a.labels,matrix=self.a.matrix,output=self.p/'eval',backup_root=self.p/'backups');before=tree(self.a.output)
  with patch.object(b,'fit',side_effect=AssertionError('Evaluation fitted model')):r=e.evaluate(a)
  self.assertFalse(r['models_fitted']);self.assertEqual(before,tree(self.a.output));self.assertEqual(tree(a.output),tree(Path(r['backup'])))
 def test_existing_output_and_interrupt_cleanup(self):
  with self.assertRaises(FileExistsError):b.build(self.a)
  a=copy.copy(self.a);a.output=self.p/'interrupted'
  with patch.object(b,'fit',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):b.build(a)
  self.assertFalse(a.output.exists());self.assertFalse(list(self.p.glob('interrupted.staging-*')))

class Units(unittest.TestCase):
 def test_features_role_appropriate_and_no_statcast_in_standard(self):
  allow=['age_at_target_estimate','history_seasons','x_actual_lag1_PA','x_statcast_lag1_ev_value','x_statcast_lag1_velocity_value','has_any_statcast_history'];standard,advanced=b.feature_sets(allow,'hitter');self.assertFalse(any(n.startswith('x_statcast') for n in standard));self.assertIn('x_statcast_lag1_ev_value',advanced);self.assertNotIn('x_statcast_lag1_velocity_value',advanced);self.assertNotIn('has_any_statcast_history',standard)
 def test_measurements_masked_not_zero_imputed(self):
  r=dict(target_season=2021,player_type='hitter',x_statcast_lag1_ev_value=95,x_statcast_lag1_ev_eligible=0,x_statcast_lag1_ev_observations=5,x_statcast_lag1_ev_coverage=.8);rows,audit=b.masked_features([r],list(r));self.assertIsNone(rows[0]['x_statcast_lag1_ev_value']);self.assertEqual(r['x_statcast_lag1_ev_value'],95);self.assertEqual(audit[0]['finite_values_masked'],1)
 def test_gate_ignores_current_future_and_2026_outcomes(self):
  t=b.SPECS[0];s=copy.deepcopy(b.DEFAULT_SETTINGS);s.update(minimum_gate_folds=2,minimum_gate_rows=1,minimum_guard_rows=1);rr=[]
  for y in [2019,2020]:
   for cohort in ['ALL','LOW_HISTORY','ESTABLISHED_HISTORY']:rr.append(dict(season=y,target=t.id,cohort=cohort,n=50,models_fitted=True,accepted_frozen_mse=4,standard_skill_mse=2,statcast_skill_mse=1,accepted_frozen_mae=2,standard_skill_mae=1,statcast_skill_mae=.5))
  choice=b.decide(rr,t,2021,s);self.assertEqual(choice['selected'],'statcast_skill');later=[dict(r,season=2021,statcast_skill_mse=1000) for r in rr]+[dict(r,season=2026) for r in rr];self.assertEqual(choice,b.decide(rr+later,t,2021,s));self.assertFalse(b.decide([],t,2021,s)['incremental_statcast']['adopt'])
 def test_unsupported_recomposition_retains_accepted(self):
  old=vector('pitcher');v,ledger=b.compose_fixed('pitcher',old,{},'standard_skill');self.assertEqual(v,old);self.assertIn('UNSUPPORTED',ledger[0]['reason'])
 def test_coherent_counts_and_exact_anchors(self):
  for role in ['hitter','pitcher']:
   old=vector(role);rates={t.id:b.rate_of(old,t)*1.05 for t in b.SPECS if t.role==role};v,ledger=b.compose_fixed(role,old,rates,'statcast_skill');self.assertTrue(ledger);self.assertEqual(v['PA' if role=='hitter' else 'OUTS'],old['PA' if role=='hitter' else 'OUTS'])
   if role=='pitcher':self.assertEqual(v['SV'],old['SV']);self.assertEqual(v['HLD'],old['HLD'])
 def test_test_year_label_cannot_change_preprocessing(self):
  t=next(t for t in b.SPECS if t.role=='hitter');config=dict(minimum_fit_rows=3,lag_weights=[.5,.3,.2],volume_metrics=[],source_2020_volume_multiplier=2.7,context_features=['age_at_target_estimate'],actual_features={'hitter':[]},structural_zero_baseline_counts=[],ridge_alpha=1,clip_z=8,maximum_exposure_weight=600,exclude_playing_time_target_seasons=[]);rows=[dict(target_season=y,player_type='hitter',age_at_target_estimate=25,y_AB=300,y_PA=350,y_eligible_AB=1,y_eligible_PA=1) for y in [2016,2017,2018,2019]];before=fit([r for r in rows if r['target_season']<2019],t,['age_at_target_estimate'],config);rows[-1]['y_AB']=1;after=fit([r for r in rows if r['target_season']<2019],t,['age_at_target_estimate'],config);self.assertEqual(before,after)

if __name__=='__main__':unittest.main()

class SignalAndGuardTests(unittest.TestCase):
 def test_known_statcast_signal_improves_paired_skill_prediction(self):
  t=next(t for t in b.SPECS if t.name=='HR_per_AB');config=dict(minimum_fit_rows=10,lag_weights=[.5,.3,.2],volume_metrics=[],source_2020_volume_multiplier=2.7,context_features=['age_at_target_estimate'],actual_features={'hitter':[]},structural_zero_baseline_counts=[],ridge_alpha=1.,clip_z=8,maximum_exposure_weight=600,exclude_playing_time_target_seasons=[])
  rows=[dict(target_season=2018,player_type='hitter',age_at_target_estimate=25,x_statcast_lag1_ev_value=80+i%40,y_HR=20+2*(i%40),y_AB=400,y_eligible_HR=1,y_eligible_AB=1) for i in range(120)];common=['age_at_target_estimate'];aug=common+['x_statcast_lag1_ev_value'];m0=fit(rows,t,common,config);m1=fit(rows,t,aug,config);test=[dict(r,target_season=2019) for r in rows];_,p0=predict(m0,test,t,config);_,p1=predict(m1,test,t,config);err=lambda pred:sum((p-r['y_HR']/r['y_AB'])**2 for p,r in zip(pred,test));self.assertLess(err(p1),err(p0));self.assertEqual(m0['preprocessing']['numeric']['age_at_target_estimate'],m1['preprocessing']['numeric']['age_at_target_estimate'])
 def test_missing_guard_support_blocks_adoption(self):
  t=b.SPECS[0];s=copy.deepcopy(b.DEFAULT_SETTINGS);s.update(minimum_gate_folds=1,minimum_gate_rows=1,minimum_guard_rows=1);rr=[dict(season=2020,target=t.id,cohort='ALL',n=100,models_fitted=True,accepted_frozen_mse=4,standard_skill_mse=2,statcast_skill_mse=1,accepted_frozen_mae=2,standard_skill_mae=1,statcast_skill_mae=.5)];self.assertEqual(b.decide(rr,t,2021,s)['selected'],'accepted_frozen')
 def test_zero_exposure_does_not_invent_skill_rates(self):
  v=vector('pitcher');v.update(OUTS=0,IP=0,H=0,ER=0,BB=0,SO=0,HR=0,W=0,SV=0,HLD=0,QS=0,ERA=None,WHIP=None,SV_plus_HLD=0);self.assertIsNone(b.rate_of(v,next(t for t in b.SPECS if t.role=='pitcher')))

class ChronologyAndIntegrity(unittest.TestCase):
 def test_current_origin_labels_do_not_change_current_fold(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);b.build(a);original=sha(a.output/'fold_models_2025.json');rows=table(a.labels/'training_labels.parquet')
   for r in rows:
    if r['season']==2025 and r['player_type']=='hitter' and r['metric']=='HR':r['label_value']+=1
   pq(a.labels/'training_labels.parquet',rows);manifest(a.labels);model=load(a.accepted/'frozen_models.json');model['training_labels_sha256']=sha(a.labels/'training_labels.parquet');dump(a.accepted/'frozen_models.json',model);manifest(a.accepted);bind=load(a.release/'input_hashes.json');bind[str(a.accepted/'frozen_models.json')]=sha(a.accepted/'frozen_models.json');dump(a.release/'input_hashes.json',bind);manifest(a.release);a.output=p/'changed';b.build(a);self.assertEqual(original,sha(a.output/'fold_models_2025.json'))
 def test_tamper_fails_before_publication(self):
  with tempfile.TemporaryDirectory() as t:
   a=fixture(Path(t));(a.accepted/'historical_forecasts.csv').write_text('tampered',encoding='utf-8')
   with self.assertRaises(ValueError):b.build(a)
   self.assertFalse(a.output.exists())
 def test_future_holdout_predictor_is_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   a=fixture(Path(t));rows=table(a.matrix/'holdout_features.parquet');rows=[dict(r,source_cutoff=str(r['source_cutoff']),y_HR=99) for r in rows];pq(a.matrix/'holdout_features.parquet',rows);manifest(a.matrix);bind=load(a.release/'input_hashes.json');bind[str(a.matrix/'holdout_features.parquet')]=sha(a.matrix/'holdout_features.parquet');dump(a.release/'input_hashes.json',bind);manifest(a.release)
   with self.assertRaises(ValueError):b.build(a)

class StatisticPairTests(unittest.TestCase):
 def test_statistic_pair_excludes_unshared_rate_support(self):
  bank={(2021,'hitter','1','AVG','standard_skill'):.25,(2021,'hitter','1','AVG','statcast_skill'):.26,(2021,'hitter','2','AVG','standard_skill'):None,(2021,'hitter','2','AVG','statcast_skill'):.4};actual={(2021,'hitter','1','AVG'):.27,(2021,'hitter','1','AB'):300,(2021,'hitter','2','AVG'):.3,(2021,'hitter','2','AB'):200};ss=b.paired_statistic_scores(bank,actual,{});self.assertTrue(ss);self.assertTrue(all(r['n']==1 for r in ss));self.assertEqual({r['method'] for r in ss},{'standard_skill','statcast_skill'});self.assertTrue(all(r['comparison_group']=='standard_vs_statcast' for r in ss))
