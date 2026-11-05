import unittest,tempfile,json,copy,importlib.util
from pathlib import Path
import duckdb
from standalone_io_v1_0 import *
from standalone_opportunity_v1_1 import *
from backtest_standalone_opportunity_v1_1 import build,evidence
from evaluate_standalone_opportunity_v1_1 import evaluate
from backtest_standalone_baselines_v1_0 import build as oldbuild
ROOT=Path(__file__).resolve().parents[1]
fixture_path=Path(__import__('backtest_standalone_baselines_v1_0').__file__).parent/'tests/test_standalone_baselines_v1_0.py'
spec=importlib.util.spec_from_file_location('baseline_fixture',fixture_path);fm=importlib.util.module_from_spec(spec);spec.loader.exec_module(fm)

def fixture(p):
 c,allow,rr,hold=fm.fixture(p)
 for r in rr+hold:
  i=int(r['mlbam_id'])-(101 if r['player_type']=='pitcher' else 1)
  for m in ['G','GS']:
   v=fm.counts(r['player_type'],i,r['target_season']).get(m);r['y_'+m]=v;r['y_eligible_'+m]=int(v is not None)
   for lag in [1,2,3]:
    source=r['source_season_lag'+str(lag)];r[f'x_actual_lag{lag}_{m}']=fm.counts(r['player_type'],i,int(source)).get(m) if source else None
 for m in ['G','GS']:
  for lag in [1,2,3]:
   n=f'x_actual_lag{lag}_{m}'
   if n not in allow:allow.append(n)
 for name,rows in [('training_matrix',rr),('holdout_matrix',hold),('holdout_features',[{k:v for k,v in r.items() if not k.startswith('y_')} for r in hold])]:
  (p/'matrix'/(name+'.parquet')).unlink();fm.parquet(p/'matrix'/(name+'.parquet'),rows)
 dump(p/'matrix/feature_schema.json',{'predictor_allowlist':allow});fm.refresh_matrix(p);cfg=load(ROOT/'config/standalone_opportunity_v1_1.json');cfg.update(minimum_fit_rows=3,minimum_validation_rows=3,participation_minimum_each_class=2);dump(p/'opportunity.json',cfg);oldbuild(p/'matrix',p/'config.json',p/'baseline',p/'backups');return rr,hold,c,allow

def run(p,name='new',baseline='baseline'):return build(p/'matrix',p/baseline,p/'opportunity.json',p/name,p/'backups')
class OpportunityTests(unittest.TestCase):
 def test_full_build_frozen_v1_preserved_backup_and_chronology(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);before=tree(p/'baseline');source=tree(p/'matrix');r=run(p);self.assertEqual(tree(p/'baseline'),before);self.assertEqual(tree(p/'matrix'),source);self.assertEqual(tree(p/'new'),tree(Path(r['backup'])));self.assertFalse(r['evaluation_labels_read']);self.assertIn('BLOCKED',r['model_statuses']['pitcher_ACTIVE']);self.assertIn('reviewed',r['evaluation_disclosure'])
   for a in load(p/'new/fit_chronology.json'):self.assertTrue(all(y<a['origin'] and y!=2020 for y in a['fit_years']))
   e=evaluate(p/'new',p/'matrix',p/'evaluation',p/'backups');self.assertFalse(e['models_refitted']);self.assertEqual(tree(p/'evaluation'),tree(Path(e['backup'])))
   groups={}
   for row in csvrows(p/'evaluation/cohort_scores.csv'):groups.setdefault(tuple(row[k] for k in ['season','player_type','metric','cohort']),set()).add((row['n'],row['membership_sha256']))
   self.assertTrue(all(len(v)==1 for v in groups.values()))
 def test_2026_outcomes_cannot_change_models_or_forecasts(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);run(p,'a');rr=table(p/'matrix/holdout_matrix.parquet')
   for r in rr:
    for k,v in list(r.items()):
     if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.3
   (p/'matrix/holdout_matrix.parquet').unlink();fm.parquet(p/'matrix/holdout_matrix.parquet',rr);fm.refresh_matrix(p);run(p,'b')
   for name in ['frozen_models.json','historical_forecasts.csv','frozen_2026_forecasts.csv']:self.assertEqual((p/'a'/name).read_bytes(),(p/'b'/name).read_bytes())
 def test_later_validation_does_not_change_earlier_predictions(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);run(p,'a');rr=table(p/'matrix/training_matrix.parquet')
   for r in rr:
    if r['target_season']==2025:
     for k,v in list(r.items()):
      if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.5
   (p/'matrix/training_matrix.parquet').unlink();fm.parquet(p/'matrix/training_matrix.parquet',rr);fm.refresh_matrix(p);oldbuild(p/'matrix',p/'config.json',p/'baseline2',p/'backups');run(p,'b','baseline2');self.assertEqual((p/'a/historical_forecasts.csv').read_bytes(),(p/'b/historical_forecasts.csv').read_bytes())
 def test_missing_zero_and_zero_out_appearance(self):
  r=dict(player_type='pitcher',y_OUTS=0,y_eligible_OUTS=1,y_G=1,y_eligible_G=1,y_GS=0,y_eligible_GS=1,y_SV=0,y_eligible_SV=1);self.assertEqual(labels([r])[0]['y_ACTIVE'],1);self.assertEqual(labels([r])[0]['y_ANY_SAVE'],0);r['y_G']=None;r['y_eligible_G']=0;self.assertIsNone(labels([r])[0]['y_ACTIVE']);r['y_G']=0;r['y_eligible_G']=1;self.assertEqual(labels([r])[0]['y_ACTIVE'],0)
 def test_role_boundaries_and_missingness(self):
  for g,gs,result in [(30,25,'STARTER'),(60,0,'RELIEVER'),(50,15,'SWING'),(0,0,'UNKNOWN'),(1,2,'UNKNOWN'),(None,1,'UNKNOWN')]:self.assertEqual(role_of(g,gs),result)
 def test_coherent_scaling_and_rejected_saves_preserved(self):
  old=dict(OUTS=300,IP=100,H=90,ER=40,BB=30,SO=110,HR=10,W=5,SV=7,HLD=0,QS=10,ERA=3.6,WHIP=1.2);choice={'pitcher_volume':{'adopt':True},'pitcher_saves':{'adopt':False}};r=apply(old,{'volume':450,'saves':20},'pitcher',choice);self.assertEqual(r['IP'],150);self.assertEqual(r['SV'],7);self.assertEqual(r['ERA'],3.6);self.assertAlmostEqual(9*r['ER']/r['IP'],r['ERA']);self.assertEqual(old['IP'],100)
 def test_verified_evidence_conflict_tamper_and_future_rejected(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);dump(p/'proof.json',{'scope':'fixture'});fields=['season','player_type','mlbam_id','status','source','evidence_file'];write(p/'confirmed_nonappearance.csv',[dict(zip(fields,[2024,'pitcher','1','CONFIRMED_NO_MLB_APPEARANCE','fixture','proof.json']))],fields);dump(p/'output_sha256.json',tree(p));r=dict(target_season=2024,player_type='pitcher',mlbam_id='1',y_OUTS=None,y_eligible_OUTS=0,y_G=None,y_eligible_G=0);_,n=evidence(p,[r]);self.assertEqual(n,1);r['y_G']=1
   with self.assertRaises(ValueError):evidence(p,[r])
   (p/'proof.json').write_text('tampered')
   with self.assertRaises(ValueError):evidence(p,[r])
 def test_verified_class_support_and_probability_range(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);rr,hold,c,allow=fixture(p);c['participation_minimum_each_class']=2
   for r in rr:
    if int(r['mlbam_id'])%3==0:
     for m in ['G','PA' if r['player_type']=='hitter' else 'OUTS']:r['y_'+m]=0;r['y_eligible_'+m]=1
   b,_=train(rr,allow,c);self.assertTrue(b['models']['pitcher_ACTIVE']['supported']);self.assertTrue(all(0<=v['participation_probability']<=1 for v in forecast(b,hold).values()))
 def test_saves_relevant_gate_required(self):
  c=load(ROOT/'config/standalone_opportunity_v1_1.json');h=[dict(season=y,player_type='pitcher',component='saves',n=100,v1_mse=2,candidate_mse=1,v1_mae=2,candidate_mae=1) for y in [2021,2022]];self.assertFalse(selection(h,'pitcher','saves',c)['adopt']);h += [dict(season=y,player_type='pitcher',component='saves_relevant',n=20,v1_mse=2,candidate_mse=1,v1_mae=2,candidate_mae=1) for y in [2021,2022]];self.assertTrue(selection(h,'pitcher','saves',c)['adopt'])
 def test_ties_baseline_and_2020_exclusion(self):
  c=load(ROOT/'config/standalone_opportunity_v1_1.json');h=[dict(season=y,player_type='pitcher',component='volume',n=100,v1_mse=1,candidate_mse=1,v1_mae=1,candidate_mae=1) for y in [2020,2021,2022]];s=selection(h,'pitcher','volume',c);self.assertFalse(s['adopt']);self.assertEqual(s['validation_seasons'],[2021,2022])
 def test_benchmark_common_pools_and_read_only_warehouse(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);run(p);wh=p/'warehouse';wh.mkdir();path=wh/'test.duckdb'
   with duckdb.connect(str(path)) as db:
    db.execute('CREATE TABLE player_id_crosswalk(player_id VARCHAR,namespace VARCHAR,external_id VARCHAR)')
    for role in ['hitter','pitcher']:
     name='analytical_'+role+'_projections';db.execute('CREATE TABLE '+name+'(season INTEGER,source VARCHAR,player_id VARCHAR,record_id VARCHAR,metrics_json VARCHAR,excluded_metrics_json VARCHAR)')
     for i in range(8):
      pid=role+str(i);mid=str(i+(101 if role=='pitcher' else 1));db.execute('INSERT INTO player_id_crosswalk VALUES (?,?,?)',[pid,'mlbam',mid])
      for y in [2024,2025,2026]:
       v=fm.counts(role,i,y)
       if role=='pitcher':v['IP']=v['OUTS']/3
       for source in ['Steamer','OOPSY']:db.execute('INSERT INTO '+name+' VALUES (?,?,?,?,?,?)',[y,source,pid,source+str(y)+pid,json.dumps(v),'[]'])
   dump(wh/'migration_audit.json',{'pass':True,'objects':[]});before=sha(path);r=evaluate(p/'new',p/'matrix',p/'evaluation',p/'backups',path);self.assertGreater(r['benchmark_rows'],0);self.assertEqual(sha(path),before);groups={}
   for row in csvrows(p/'evaluation/benchmark_scores.csv'):groups.setdefault(tuple(row[k] for k in ['season','player_type','metric','comparison_group']),set()).add((row['n'],row['membership_sha256']))
   self.assertTrue(all(len(v)==1 for v in groups.values()))
 def test_manifest_tamper_and_output_guard(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);run(p)
   with self.assertRaises(FileExistsError):run(p)
   (p/'matrix/training_matrix.parquet').write_bytes(b'tampered')
   with self.assertRaises(ValueError):run(p,'tampered')
   self.assertFalse((p/'tampered').exists())
if __name__=='__main__':unittest.main()
