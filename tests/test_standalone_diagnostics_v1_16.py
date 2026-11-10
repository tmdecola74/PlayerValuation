import unittest,tempfile,csv,json,copy,argparse
from pathlib import Path
from unittest.mock import patch
import duckdb
import standalone_diagnostics_v1_16 as d
from standalone_io_v1_0 import dump,write,sha,tree,load,csvrows

def manifest(p):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',tree(p))
def pq(p,rows):
 with duckdb.connect() as db:
  db.execute('CREATE TABLE t AS SELECT * FROM read_json_auto(?)',[json.dumps(rows)] ) if False else None
  tmp=p.with_suffix('.json');dump(tmp,rows);db.read_json(str(tmp)).write_parquet(str(p));tmp.unlink()
def fixture(p):
 dirs={n:p/n for n in ['release','accepted','matrix','labels','baseline']}
 for v in dirs.values():v.mkdir()
 rows=[];pred=[];lab=[]
 for y in [2019,2020,2021]:
  for role in ['hitter','pitcher']:
   for i in range(2):
    pid=str(i+1);m=dict(PA=500,AB=450,H=120,**{'1B':85,'2B':20,'3B':5},HR=10,R=60,RBI=50,SB=10,BB=40,HBP=5,SF=5,SH=0,AVG=120/450,OBP=165/500,SLG=180/450,OPS=165/500+180/450) if role=='hitter' else dict(OUTS=450,IP=150,H=130,ER=50,BB=40,SO=140,HR=15,W=10,SV=5,HLD=2,QS=15,ERA=3,WHIP=170/150,SV_plus_HLD=7)
    for metric,val in m.items():
     pred.append(dict(season=y,player_type=role,mlbam_id=pid,metric=metric,method='selected_v1_5',prediction=val));lab.append(dict(season=y,player_type=role,mlbam_id=pid,metric=metric,eligible=True,label_value=val))
    rows.append(dict(target_season=y,player_type=role,mlbam_id=pid,max_source_season=y-1,source_cutoff=f'{y-1}-12-31',source_season_lag1=y-1,source_season_lag2=y-2,source_season_lag3=y-3,age_at_target_estimate=24+i*10,history_seasons=3,x_actual_lag1_G=30,x_actual_lag1_GS=25,x_actual_lag1_PA=400,x_actual_lag1_OUTS=400,x_statcast_lag1_speed=90 if i else None))
 allow=['age_at_target_estimate','history_seasons','x_actual_lag1_G','x_actual_lag1_GS','x_actual_lag1_PA','x_actual_lag1_OUTS','x_statcast_lag1_speed'];pq(dirs['matrix']/'training_matrix.parquet',rows);dump(dirs['matrix']/'feature_schema.json',{'predictor_allowlist':allow});pq(dirs['labels']/'training_labels.parquet',lab);dump(dirs['labels']/'label_build_report.json',{'reference_sha256':{'source':'frozen'}})
 write(dirs['accepted']/'historical_forecasts.csv',pred,list(pred[0]));dump(dirs['accepted']/'frozen_models.json',dict(training_labels_sha256=sha(dirs['labels']/'training_labels.parquet'),settings={'minimum_fit_rows':50}))
 bp=[dict(r,method=method,prediction=float(r['prediction'])+(.1 if method=='historical_baseline' else .05)) for r in pred for method in ['historical_baseline','selected_standalone']];write(dirs['baseline']/'historical_forecasts.csv',bp,list(bp[0]));dump(dirs['baseline']/'frozen_models.json',dict(models={'hitter_rate':dict(target='hitter_HR',n_fit=100,fit_target_seasons=[2019,2020,2021],preprocessing=dict(numeric={'x_statcast_lag1_speed':{}},categorical={},dropped=['x_statcast_lag2_speed']))},choices={'hitter_HR':{'candidate':'ridge'}}))
 dump(dirs['release']/'projection_release_report.json',dict(models_fitted=False,choices_changed=False,label_reference_sha256={'source':'frozen'}));dump(dirs['release']/'input_hashes.json',{str(dirs['accepted']/'historical_forecasts.csv'):sha(dirs['accepted']/'historical_forecasts.csv'),str(dirs['matrix']/'training_matrix.parquet'):sha(dirs['matrix']/'training_matrix.parquet')})
 for role in ['hitter','pitcher']:write(dirs['release']/f'homegrown_{role}s_2026.csv',[],['player_id'])
 prov=[dict(player_type='hitter',metric='HR',component_origin='Frozen skill/workload',selected_method='frozen',projection_source='HOMEGROWN_V1_5_ACCEPTED')];write(dirs['release']/'component_provenance.csv',prov,list(prov[0]))
 for path in dirs.values():manifest(path)
 return argparse.Namespace(**dirs,additional_models=[],output=p/'out',backup_root=p/'backups')

class Pipeline(unittest.TestCase):
 def test_full_readonly_build_pair_memberships_and_2021(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);before={n:tree(v) for n,v in vars(a).items() if isinstance(v,Path) and v.exists()};r=d.build(a);self.assertFalse(r['models_fitted']);self.assertFalse(r['evaluation_outcomes_read']);self.assertEqual(tree(a.output),tree(Path(r['backup'])));self.assertTrue(csvrows(a.output/'transition_2021.csv'));self.assertTrue(csvrows(a.output/'statcast_measurement_availability.csv'))
   scores=csvrows(a.output/'historical_scores.csv');groups={}
   for row in scores:
    if row['comparison_group']!='INDIVIDUAL_ELIGIBLE':groups.setdefault(tuple(row[k] for k in ['season','player_type','metric','cohort_dimension','cohort','comparison_group']),set()).add((row['n'],row['membership_sha256']))
   self.assertTrue(all(len(v)==1 for v in groups.values()))
   for n,v in before.items():self.assertEqual(tree(getattr(a,n)),v)
 def test_holdout_files_never_opened_and_mutation_invariant(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);hold=a.labels/'holdout_labels.parquet';hold.write_bytes(b'not parquet');r=d.build(a);old=sha(a.output/'historical_scores.csv');hold.write_bytes(b'changed target outcomes');a.output=p/'other';d.build(a);self.assertEqual(old,sha(a.output/'historical_scores.csv'))
 def test_tamper_and_target_forecast_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);f=a.accepted/'historical_forecasts.csv';f.write_text('tampered',encoding='utf-8')
   with self.assertRaises(ValueError):d.build(a)
   self.assertFalse(a.output.exists())
 def test_interrupt_cleans_staging_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p)
   with patch.object(d,'emit',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):d.build(a)
   self.assertFalse(a.output.exists());self.assertFalse(list(p.glob('out.staging-*')));d.build(a)
   with self.assertRaises(FileExistsError):d.build(a)

class Units(unittest.TestCase):
 def test_model_future_and_outcome_predictor_rejected(self):
  with self.assertRaises(ValueError):d.model_inventory({'fit_target_seasons':[2026]},'x')
  with self.assertRaises(ValueError):d.model_inventory({'preprocessing':{'numeric':{'y_PA':{}}}},'x')
 def test_model_retained_vs_dropped_not_adoption(self):
  rows=d.model_inventory({'preprocessing':{'numeric':{'x_statcast_lag1_a':{}},'dropped':['x_statcast_lag2_a']}},'x');self.assertEqual([r['preprocessing_status'] for r in rows],['numeric','dropped']);self.assertTrue(all('NOT_PROOF' in r['scope'] for r in rows))
 def test_future_and_duplicate_forecast_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'f.csv';row=dict(season=2026,player_type='hitter',mlbam_id='1',metric='PA',method='selected_v1_5',prediction=500);write(p,[row],list(row))
   with self.assertRaises(ValueError):d.forecasts(p,{'selected_v1_5':'accepted_v1_5'})
   row['season']=2021;write(p,[row,row],list(row))
   with self.assertRaises(ValueError):d.forecasts(p,{'selected_v1_5':'accepted_v1_5'})
 def test_missing_labels_zero_actuals_and_matched_pools(self):
  bank={(2021,'hitter','1','HR','accepted_v1_5'):2,(2021,'hitter','1','HR','baseline'):1,(2021,'hitter','2','HR','accepted_v1_5'):10};truth={(2021,'hitter','1','HR'):0};ss,cc,oo=d.score(bank,truth,{});self.assertTrue(ss);self.assertTrue(all(r['n']==1 for r in ss));self.assertEqual(next(r['actual'] for r in oo),0);self.assertTrue(any(r['status']=='MISSING_OR_EXCLUDED_LABEL' for r in cc))
 def test_rate_denominator_not_fabricated(self):
  ss,cc,oo=d.score({(2021,'pitcher','1','ERA','accepted_v1_5'):3},{(2021,'pitcher','1','ERA'):4},{});self.assertFalse(ss)
 def test_measurement_coverage_separate_years_and_missing_not_zero(self):
  rows=[dict(target_season=y,player_type='hitter',x_statcast_lag1_a=v) for y,v in [(2020,None),(2021,90)]];r=d.measurement_audit(rows,['x_statcast_lag1_a']);self.assertEqual([x['finite_rows'] for x in r],[0,1]);self.assertIsNone(r[0]['minimum'])
 def test_prior_unknown_not_nonparticipation_and_2020_flag(self):
  k=(2021,'pitcher','1');rows=d.workload_context({k:{'OUTS':300}},{k:{'x_actual_lag1_OUTS':None,'x_actual_lag2_OUTS':400,'source_season_lag1':2020}},{k+('OUTS',):350});self.assertEqual(rows[0]['history_pattern'],'RECENT_UNKNOWN_WITH_OLDER_HISTORY');self.assertTrue(rows[0]['prior_2020_observed_workload']);self.assertIsNone(rows[0]['observed_change'])

if __name__=='__main__':unittest.main()

class AdditionalGuards(unittest.TestCase):
 def test_future_matrix_cutoff_and_outcome_allowlist_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=fixture(p);rows=d.table(a.matrix/'training_matrix.parquet');rows[0]['max_source_season']=rows[0]['target_season'];rows=[dict(r,source_cutoff=str(r['source_cutoff'])) for r in rows];path=p/'bad.parquet';pq(path,rows);allow=load(a.matrix/'feature_schema.json')['predictor_allowlist']
   with self.assertRaises(ValueError):d.feature_index(path,allow)
   with self.assertRaises(ValueError):d.feature_index(a.matrix/'training_matrix.parquet',allow+['y_PA'])
 def test_signed_unscored_label_is_not_a_scored_count(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'labels.parquet';pq(p,[dict(season=2021,player_type='pitcher',mlbam_id='1',metric='K-BB%',eligible=True,label_value=-.1),dict(season=2021,player_type='pitcher',mlbam_id='1',metric='W',eligible=True,label_value=0)]);actual,excluded=d.label_index(p);self.assertEqual(actual,{(2021,'pitcher','1','W'):0.0})
 def test_comparison_summary_equal_season_and_2021(self):
  ss=[]
  for year,n,error in [(2020,1,10),(2021,9,0)]:ss.append(dict(season=year,player_type='hitter',metric='HR',cohort_dimension='ALL',cohort='ALL',method='accepted_v1_5',comparison_group='accepted_vs_baseline',n=n,rmse=error,mae=error))
  row=d.comparison_summary(ss)[0];self.assertAlmostEqual(row['pooled_rmse'],10**.5);self.assertAlmostEqual(row['equal_season_rmse'],50**.5);self.assertTrue(row['transition_2021_included']);self.assertFalse(row['selection_performed'])
