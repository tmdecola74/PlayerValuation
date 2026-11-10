import unittest,tempfile,argparse,copy,json,shutil
from pathlib import Path
from unittest.mock import patch
import coherent_skill_groups_v1_19 as b
import evaluate_coherent_skill_groups_v1_19 as ev
from standalone_io_v1_0 import load,dump,sha,tree,csvrows
from standalone_combined_v1_4 import coherent

# Standalone fixture helpers: no dependency on tests from earlier ZIPs.
def pq(p,rows):
 import duckdb
 tmp=p.with_suffix('.json');dump(tmp,rows)
 with duckdb.connect() as db:db.read_json(str(tmp)).write_parquet(str(p))
 tmp.unlink()
def manifest(p):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',tree(p))
def accepted(role):
 return dict(PA=500.,AB=450.,H=120.,**{'1B':85.,'2B':20.,'3B':5.},HR=10.,R=60.,RBI=50.,SB=10.,BB=40.,HBP=5.,SF=5.,SH=0.,AVG=120/450,OBP=165/500,SLG=180/450,OPS=165/500+180/450) if role=='hitter' else dict(OUTS=450.,IP=150.,H=130.,ER=50.,BB=40.,SO=140.,HR=15.,W=10.,SV=5.,HLD=2.,QS=15.,ERA=3.,WHIP=170/150,SV_plus_HLD=7.)
def perfect_history(role='hitter',years=(2019,2020,2021),ratio=.95):
 rows=[]
 for y in years:
  for cohort in ['ALL','LOW_HISTORY','ESTABLISHED_HISTORY']:
   for m in b.GROUPS[role]['metrics']:
    r=dict(season=y,player_type=role,cohort=cohort,metric=m,n=40,accepted_frozen_mse=1.,accepted_frozen_mae=1.)
    for arm in b.ARMS:r[arm+'_mse']=ratio;r[arm+'_mae']=.97
    rows.append(r)
 return rows

def fixture(p):
 root=p/'source';labels=p/'labels';matrix=p/'matrix'
 for d in [root,labels,matrix]:d.mkdir()
 from statcast_incremental_v1_17 import SPECS,rate_of,METHODS
 rates=[];vectors=[];future_rates=[];future_vectors=[];labs=[];hlabs=[];features=[];hold=[]
 for y in range(2019,2027):
  for role in b.GROUPS:
   for i in range(2):
    k=y,role,str(i+1);a=accepted(role)
    for t in SPECS:
     if t.role!=role:continue
     rr=dict(season=y,player_type=role,mlbam_id=k[2],target=t.id,selected_method='accepted_frozen',standard_fit_status='FITTED',statcast_fit_status='FITTED',**{m:rate_of(a,t) for m in METHODS});(future_rates if y==2026 else rates).append(rr)
    for m,v in a.items():
     for method in METHODS:(future_vectors if y==2026 else vectors).append(dict(season=y,player_type=role,mlbam_id=k[2],method=method,metric=m,prediction=v))
     (hlabs if y==2026 else labs).append(dict(season=y,player_type=role,mlbam_id=k[2],metric=m,label_value=v,eligible=True))
    (hold if y==2026 else features).append(dict(target_season=y,player_type=role,mlbam_id=k[2],max_source_season=y-1,source_cutoff=str(y-1)+'-12-31',source_season_lag1=y-1,source_season_lag2=y-2,source_season_lag3=y-3,history_seasons=i+1,age_at_target_estimate=28.,x_actual_lag1_G=30.,x_actual_lag1_GS=25.))
 for name,rows in [('historical_skill_rates',rates),('historical_forecasts',vectors),('frozen_2026_skill_rates',future_rates),('frozen_2026_forecasts',future_vectors)]:b.emit(root/(name+'.csv'),rows)
 pq(labels/'training_labels.parquet',labs);pq(labels/'holdout_labels.parquet',hlabs);dump(labels/'label_build_report.json',dict(reference_sha256={'fixture':'reference'}));pq(matrix/'training_matrix.parquet',features);pq(matrix/'holdout_features.parquet',hold);dump(matrix/'feature_schema.json',{'predictor_allowlist':[]})
 for d in [labels,matrix]:manifest(d)
 dump(root/'incremental_build_report.json',dict(version='1.17.0',evaluation_outcomes_read=False));dump(root/'forecast_freeze.json',tree(root));dump(root/'input_hashes.json',{str(f.resolve()):sha(f) for d in [labels,matrix] for f in d.iterdir() if f.name!='output_sha256.json'});manifest(root)
 cp=p/'config.json';dump(cp,b.DEFAULT)
 return argparse.Namespace(run=root,labels=labels,matrix=matrix,config=cp,output=p/'out',backup_root=p/'backups')

class GroupTests(unittest.TestCase):
 def test_hitter_group_only_fixed_AB_and_hit_normalization(self):
  a=accepted('hitter');r={t:.4 for t in b.GROUPS['hitter']['targets']};v,meta=b.group_vector('hitter',a,r);self.assertAlmostEqual(v['H'],a['AB']);self.assertEqual(meta['hit_scale'],1.6)
  for m in a:
   if m not in b.GROUPS['hitter']['changed']:self.assertEqual(a[m],v[m])
  coherent('hitter',v)
 def test_pitcher_group_freezes_hr_workload_saves_holds(self):
  a=accepted('pitcher');v,meta=b.group_vector('pitcher',a,{'pitcher_H_per_OUTS':0.,'pitcher_BB_per_OUTS':.1});self.assertEqual(v['H'],a['HR']);self.assertEqual(meta['hit_floor_adjustment'],15.)
  for m in a:
   if m not in b.GROUPS['pitcher']['changed']:self.assertEqual(a[m],v[m])
 def test_missing_group_falls_back_never_zero(self):
  a=accepted('hitter');v,meta=b.group_vector('hitter',a,{});self.assertEqual(a,v);self.assertFalse(meta['supported'])
 def test_config_edits_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'c.json';c=dict(b.DEFAULT,minimum_folds=1);dump(p,c)
   with self.assertRaises(ValueError):b.settings(p)
 def test_positive_gate_and_tie_prefers_standard(self):
  d=b.gate(perfect_history(),'hitter',2022,b.DEFAULT);self.assertEqual(d['selected'],'group_standard')
 def test_no_incremental_change_is_rejected(self):
  d=b.gate(perfect_history(ratio=1.),'hitter',2022,b.DEFAULT);self.assertEqual(d['selected'],'accepted_frozen')
 def test_current_and_future_errors_cannot_change_choice(self):
  hist=perfect_history();a=b.gate(hist,'hitter',2022,b.DEFAULT);hist+=perfect_history(years=(2022,2026),ratio=100.);self.assertEqual(a,b.gate(hist,'hitter',2022,b.DEFAULT))
 def test_2021_insufficient_folds_retains_accepted(self):
  d=b.gate(perfect_history(years=(2019,2020)),'hitter',2021,b.DEFAULT);self.assertEqual(d['selected'],'accepted_frozen')
 def test_recent_regression_rejects_aggregate_winner(self):
  h=perfect_history(years=(2019,2020,2021,2022),ratio=.7)
  for r in h:
   if r['season']>=2021:
    for arm in b.ARMS:r[arm+'_mse']=1.03
  self.assertEqual(b.gate(h,'hitter',2023,b.DEFAULT)['selected'],'accepted_frozen')
 def test_missing_recent_year_not_silently_skipped(self):
  h=perfect_history(years=(2019,2020,2021))
  self.assertEqual(b.gate(h,'hitter',2023,b.DEFAULT)['selected'],'accepted_frozen')
 def test_low_history_guard_required(self):
  h=[r for r in perfect_history() if r['cohort']!='LOW_HISTORY'];self.assertEqual(b.gate(h,'hitter',2022,b.DEFAULT)['selected'],'accepted_frozen')
 def test_individual_stat_guard_rejects(self):
  h=perfect_history(ratio=.5)
  for r in h:
   if r['metric']=='HR':
    for arm in b.ARMS:r[arm+'_mse']=1.04
  self.assertEqual(b.gate(h,'hitter',2022,b.DEFAULT)['selected'],'accepted_frozen')
 def test_zero_reference_error_no_division_or_promotion(self):
  h=perfect_history()
  for r in h:r['accepted_frozen_mse']=0.
  self.assertEqual(b.gate(h,'hitter',2022,b.DEFAULT)['selected'],'accepted_frozen')
 def test_roles_select_independently(self):
  h=perfect_history()+perfect_history('pitcher',ratio=1.);self.assertEqual(b.gate(h,'hitter',2022,b.DEFAULT)['selected'],'group_standard');self.assertEqual(b.gate(h,'pitcher',2022,b.DEFAULT)['selected'],'accepted_frozen')

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.a=fixture(cls.p);cls.before={n:tree(getattr(cls.a,n)) for n in ['run','labels','matrix']};cls.report=b.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def evalargs(self,p):return argparse.Namespace(run=self.a.output,source_run=self.a.run,labels=self.a.labels,matrix=self.a.matrix,output=p/'eval',backup_root=p/'evalbackups')
 def test_complete_backup_source_immutability_and_no_promotion(self):
  self.assertEqual(tree(self.a.output),tree(Path(self.report['backup'])))
  for n,v in self.before.items():self.assertEqual(v,tree(getattr(self.a,n)))
  self.assertFalse(self.report['new_source_promoted']);self.assertFalse(self.report['accepted_forecasts_modified'])
 def test_2021_recent_and_paired_memberships(self):
  rows=csvrows(self.a.output/'historical_scores.csv');self.assertTrue(csvrows(self.a.output/'transition_2021.csv'));self.assertTrue(csvrows(self.a.output/'recent_2023_2025.csv'));pools={}
  for r in rows:
   if r['comparison_group']!='INDIVIDUAL_ELIGIBLE':pools.setdefault((r['season'],r['player_type'],r['metric'],r['cohort_dimension'],r['cohort'],r['comparison_group']),set()).add((r['n'],r['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in pools.values()))
 def test_frozen_choices_before_eval_forecasts_and_no_holdout_labels(self):
  p=self.p/'rerun';original=Path.open
  def guard(path,*a,**kw):
   if 'holdout' in path.name:raise AssertionError('Holdout opened during development')
   return original(path,*a,**kw)
  with patch.object(Path,'open',guard):r=b.build(argparse.Namespace(**dict(vars(self.a),output=p)))
  self.assertTrue(r['choices_frozen_before_2026_forecast_access']);self.assertEqual(self.report['frozen_choices_sha256'],r['frozen_choices_sha256'])
 def test_eval_no_fitting_and_same_frozen_choices(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);before=tree(self.a.output)
   with patch.object(b,'gate',side_effect=AssertionError('Selection during evaluation')):r=ev.evaluate(self.evalargs(p))
   self.assertFalse(r['choices_changed']);self.assertEqual(before,tree(self.a.output));self.assertEqual(tree(p/'eval'),tree(Path(r['backup'])))
 def test_output_and_tamper_guard(self):
  with self.assertRaises(FileExistsError):b.build(self.a)
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);(a.run/'historical_forecasts.csv').write_text('tamper')
   with self.assertRaises(ValueError):b.build(a)
   self.assertFalse(a.output.exists())
 def test_interruption_removes_stage(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p)
   with patch.object(b,'finish',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):b.build(a)
   self.assertFalse(a.output.exists());self.assertFalse(list(p.glob('out.staging-*')))
 def test_holdout_outcome_mutation_cannot_change_development(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);first=b.build(a);pq(a.labels/'holdout_labels.parquet',[dict(season=2026,player_type='hitter',mlbam_id='1',metric='HR',label_value=9999.,eligible=True)])
   # Update only the external manifest. Development must never open this changed file.
   manifest(a.labels);second=b.build(argparse.Namespace(**dict(vars(a),output=p/'second')))
   self.assertEqual(first['frozen_choices_sha256'],second['frozen_choices_sha256']);self.assertEqual((a.output/'historical_forecasts.csv').read_bytes(),(p/'second'/'historical_forecasts.csv').read_bytes());self.assertEqual((a.output/'frozen_2026_forecasts.csv').read_bytes(),(p/'second'/'frozen_2026_forecasts.csv').read_bytes())
 def test_gate_metric_pool_requires_all_labels_and_both_fitted_arms(self):
  k=(2021,'hitter','1');aa={k:accepted('hitter')};cc={k+(arm,):accepted('hitter') for arm in b.ARMS};sp={k+(arm,):dict(supported=True,group_models_fitted=True) for arm in b.ARMS};actual={k+(m,):aa[k][m] for m in b.GROUPS['hitter']['metrics']};actual[k+('AB',)]=450.
  rows=b.evidence(2021,'hitter',aa,cc,sp,actual,{k:dict(history_seasons=3)})
  self.assertTrue(rows);self.assertEqual(len({r['membership_sha256'] for r in rows}),1)
  del actual[k+('HR',)];self.assertEqual(b.evidence(2021,'hitter',aa,cc,sp,actual,{}),[])
  actual[k+('HR',)]=0.;self.assertTrue(b.evidence(2021,'hitter',aa,cc,sp,actual,{}))
  sp[k+('group_statcast',)]['group_models_fitted']=False;self.assertEqual(b.evidence(2021,'hitter',aa,cc,sp,actual,{}),[])
if __name__=='__main__':unittest.main()
