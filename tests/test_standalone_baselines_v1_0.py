import csv,json,math,copy,tempfile,unittest,shutil
from pathlib import Path
from unittest.mock import patch
import duckdb,numpy as np
from standalone_models_v1_0 import *
from standalone_io_v1_0 import sha,tree,table,dump,validate_features
from backtest_standalone_baselines_v1_0 import build,scores
from evaluate_standalone_holdout_v1_0 import evaluate
from compare_standalone_benchmarks_v1_0 import compare,published
ROOT=Path(__file__).resolve().parents[1]

def parquet(p,rows):
 columns=list(rows[0]);csvpath=p.with_suffix('.csv')
 with csvpath.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=columns);w.writeheader();w.writerows(rows)
 types={n:'VARCHAR' if n in ['player_type','mlbam_id','source_cutoff'] else 'DOUBLE' for n in columns};types['target_season']='INTEGER'
 with duckdb.connect() as db:db.read_csv(str(csvpath),header=True,columns=types).write_parquet(str(p))
 csvpath.unlink()
def counts(role,i,y):
 scale=1/2.7 if y==2020 else 1
 if role=='hitter':
  pa=round((210+25*i+4*(y-2016))*scale);ab=round(pa*.85);one=round(ab*.19);two=round(ab*.05);three=round(ab*.005);hr=round(ab*.03)
  return dict(PA=pa,AB=ab,H=one+two+three+hr,**{'1B':one,'2B':two,'3B':three,'HR':hr},BB=round(pa*.08),HBP=round(pa*.01),SF=round(pa*.02),SH=0,R=round(pa*.13),RBI=round(pa*.12),SB=round(pa*.025),G=round(pa/4))
 outs=round((270+15*i+3*(y-2016))*scale);return dict(OUTS=outs,H=round(outs*.3),ER=round(outs*.12),BB=round(outs*.1),SO=round(outs*.35),HR=round(outs*.03),W=round(outs*.02),SV=round(outs*.1) if i>=4 else 0,HLD=round(outs*.02) if i>=4 else 0,QS=round(outs*.05) if i<4 else 0,G=30 if i<4 else 60,GS=30 if i<4 else 0)
def refresh_matrix(p):
 m=p/'matrix/output_sha256.json'
 if m.exists():m.unlink()
 dump(m,tree(p/'matrix'))
def fixture(p,holdout_shift=0):
 (p/'matrix').mkdir();c=json.loads((ROOT/'config/standalone_baselines_v1_0.json').read_text());c.update(minimum_fit_rows=3,minimum_validation_rows=3);dump(p/'config.json',c)
 allmetrics=sorted(set(t.numerator for t in TARGETS)|set(t.denominator for t in TARGETS if t.denominator));allow=c['context_features'][:]
 for lag in [1,2,3]:allow += [f'tracking_era_lag{lag}',f'short_season_lag{lag}']+[f'x_actual_lag{lag}_{m}' for m in allmetrics]+[f'x_statcast_lag{lag}_whiff_pct_value']
 rows=[]
 for y in range(2016,2027):
  for role in ['hitter','pitcher']:
   for i in range(8):
    r=dict(target_season=y,player_type=role,mlbam_id=str(i+1+(100 if role=='pitcher' else 0)),source_cutoff=f'{y-1}-12-31',max_source_season=y-1,history_seasons=min(3,y-2015),age_at_target_estimate=24+i+(y-2016),has_any_actual_history=1,has_any_statcast_history=1)
    for lag in [1,2,3]:
     source=y-lag;present=source>=2015;r[f'source_season_lag{lag}']=source if present else None;r[f'tracking_era_lag{lag}']=(1 if source<2017 else 2 if source<2020 else 3 if source<2024 else 4) if present else None;r[f'short_season_lag{lag}']=int(source==2020) if present else None
     prior=counts(role,i,source) if present else {}
     for m in allmetrics:r[f'x_actual_lag{lag}_{m}']=prior.get(m)
     r[f'x_statcast_lag{lag}_whiff_pct_value']=.2+.01*i if present else None
    actual=counts(role,i,y)
    if y==2026:
     actual={m:v+holdout_shift for m,v in actual.items()}
    if role=='hitter':actual.update(AVG=actual['H']/actual['AB'] if actual['AB'] else None)
    else:actual.update(IP=actual['OUTS']/3,ERA=27*actual['ER']/actual['OUTS'] if actual['OUTS'] else None,WHIP=3*(actual['H']+actual['BB'])/actual['OUTS'] if actual['OUTS'] else None)
    for m in allmetrics+['AVG','IP','ERA','WHIP']:
     r['y_'+m]=actual.get(m);r['y_eligible_'+m]=int(actual.get(m) is not None)
    rows.append(r)
 train=[r for r in rows if r['target_season']<2026];hold=[r for r in rows if r['target_season']==2026];features=[{k:v for k,v in r.items() if not k.startswith('y_')} for r in hold]
 parquet(p/'matrix/training_matrix.parquet',train);parquet(p/'matrix/holdout_features.parquet',features);parquet(p/'matrix/holdout_matrix.parquet',hold)
 dump(p/'matrix/feature_schema.json',{'predictor_allowlist':allow});dump(p/'matrix/label_source_report.json',{'reference_sha256':{'actual_counts.parquet':'fixture_counts','player_seasons.parquet':'fixture_players'}});refresh_matrix(p)
 return c,allow,train,hold

class StandaloneTests(unittest.TestCase):
 def fitrun(self,p,out='run'):return build(p/'matrix',p/'config.json',p/out,p/'backups')
 def test_full_build_freeze_evaluate_backup_and_paired_pools(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);before=tree(p/'matrix');r=self.fitrun(p);self.assertFalse(r['holdout_outcomes_read']);self.assertEqual(before,tree(p/'matrix'));self.assertEqual(tree(p/'run'),tree(Path(r['backup'])))
   e=evaluate(p/'run',p/'matrix',p/'evaluation',p/'backups');self.assertFalse(e['models_refitted']);self.assertGreater(e['paired_metric_rows'],0)
   audit=json.loads((p/'run/fit_chronology_audit.json').read_text());self.assertTrue(all(a['latest_fit_year'] is None or a['latest_fit_year']<a['season'] for a in audit))
   with (p/'evaluation/holdout_scores.csv').open() as f:rows=list(csv.DictReader(f))
   for x in rows:
    other=next(y for y in rows if y['metric']==x['metric'] and y['player_type']==x['player_type'] and y['method']!=x['method']);self.assertEqual(x['n'],other['n']);self.assertEqual(x['membership_sha256'],other['membership_sha256'])
 def test_2026_outcomes_cannot_change_frozen_models_or_forecasts(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=p/'a';b=p/'b';a.mkdir();b.mkdir();fixture(a);fixture(b,100);self.fitrun(a);self.fitrun(b)
   for n in ['frozen_models.json','frozen_2026_forecasts.csv','historical_forecasts.csv']:self.assertEqual((a/'run'/n).read_bytes(),(b/'run'/n).read_bytes())
 def test_later_validation_cannot_change_earlier_forecasts(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);fixture(p);self.fitrun(p,'first');rows=table(p/'matrix/training_matrix.parquet')
   for r in rows:
    if r['target_season']==2025:
     for k,v in list(r.items()):
      if k.startswith('y_') and not k.startswith('y_eligible_') and v is not None:r[k]=v*1.5
   (p/'matrix/training_matrix.parquet').unlink();parquet(p/'matrix/training_matrix.parquet',rows);refresh_matrix(p);self.fitrun(p,'second')
   def prior(name):
    with (p/name/'historical_forecasts.csv').open() as f:return [r for r in csv.DictReader(f) if int(r['season'])<=2025]
   self.assertEqual(prior('first'),prior('second'))
 def test_preprocessing_and_coefficients_ignore_validation_labels(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);c,allow,rows,_=fixture(p);target=next(t for t in TARGETS if t.id=='hitter_PA');early=[r for r in rows if r['target_season']<2023];a=fit(early,target,allow,c)
   changed=copy.deepcopy(rows)
   for r in changed:
    if r['target_season']>=2023:r['y_PA']=99999 if r['player_type']=='hitter' else None
   b=fit([r for r in changed if r['target_season']<2023],target,allow,c);self.assertEqual(a,b)
   for r in early:r['x_actual_lag1_PA']=None
   state=fit_transform(early,feature_names(allow,target,c),c);self.assertIn('x_actual_lag1_PA',state['dropped'])
 def test_missing_vs_zero_and_rate_exposure(self):
  t=next(t for t in TARGETS if t.id=='pitcher_SV_per_OUTS');r={'player_type':'pitcher','y_SV':0,'y_eligible_SV':1,'y_OUTS':100,'y_eligible_OUTS':1};self.assertEqual(outcome(r,t),(0,100));r['y_eligible_SV']=0;self.assertIsNone(outcome(r,t));r['y_eligible_SV']=1;r['y_OUTS']=0;self.assertIsNone(outcome(r,t))
 def test_coherent_components_and_zero_denominator(self):
  h={t.id:1 for t in TARGETS if t.role=='hitter'};h['hitter_PA']=100;v=compose('hitter',h);self.assertLessEqual(v['AB']+v['BB']+v['HBP']+v['SF']+v['SH'],100.00001);self.assertAlmostEqual(v['H'],v['1B']+v['2B']+v['3B']+v['HR']);self.assertLessEqual(v['H'],v['AB']);self.assertAlmostEqual(v['AVG'],v['H']/v['AB'])
  q={t.id:0 for t in TARGETS if t.role=='pitcher'};self.assertIsNone(compose('pitcher',q)['ERA'])
 def test_selection_only_earlier_origins_and_ties_fallback(self):
  c=json.loads((ROOT/'config/standalone_baselines_v1_0.json').read_text());t=TARGETS[0];history=[dict(season=y,target=t.id,n=100,baseline_mse=1,ridge_mse=1,baseline_mae=1,ridge_mae=1,ridge_fitted=True) for y in [2018,2019]];self.assertEqual(choose(history,t,c)['candidate'],'historical_baseline')
  for h in history:h['ridge_mse']=.8;h['ridge_mae']=.9
  self.assertEqual(choose(history,t,c)['candidate'],'ridge')
 def test_tamper_cutoff_and_predictor_leak_fail(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);c,allow,rows,_=fixture(p)
   with self.assertRaises(ValueError):validate_features(rows,allow+['y_PA'],True)
   bad=copy.deepcopy(rows);bad[0]['max_source_season']=bad[0]['target_season']
   with self.assertRaises(ValueError):validate_features(bad,allow,True)
   (p/'matrix/training_matrix.parquet').write_bytes(b'tampered')
   with self.assertRaises(ValueError):self.fitrun(p)
 def test_2020_handling_and_baseline_structural_zeros(self):
  c=json.loads((ROOT/'config/standalone_baselines_v1_0.json').read_text());r={'source_season_lag1':2020,'x_actual_lag1_OUTS':100,'x_actual_lag1_SV':0};t=next(t for t in TARGETS if t.id=='pitcher_SV_per_OUTS');self.assertEqual(historical(r,t,.02,c),0);self.assertEqual(prior_value(r,'OUTS',1,c),270)
 def test_read_only_external_benchmark_identical_pools(self):
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);_,_,train,hold=fixture(p);self.fitrun(p)
   labels=p/'labels';labels.mkdir();long=[]
   for r in train+hold:
    for k,v in r.items():
     if k.startswith('y_') and not k.startswith('y_eligible_') and r.get('y_eligible_'+k[2:]):long.append(dict(season=r['target_season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],metric=k[2:],label_value=v,eligible=True))
   with duckdb.connect() as db:
    for name,years in [('training_labels',range(2016,2026)),('holdout_labels',[2026])]:
     data=[r for r in long if r['season'] in years];f=labels/(name+'.json');dump(f,data);db.read_json(str(f)).write_parquet(str(labels/(name+'.parquet')));f.unlink()
   dump(labels/'label_build_report.json',{'reference_sha256':{'actual_counts.parquet':'fixture_counts','player_seasons.parquet':'fixture_players'}});dump(labels/'output_sha256.json',tree(labels))
   wh=p/'warehouse';wh.mkdir();path=wh/'test.duckdb'
   with duckdb.connect(str(path)) as db:
    db.execute('CREATE TABLE player_id_crosswalk(player_id VARCHAR,namespace VARCHAR,external_id VARCHAR)')
    for role in ['hitter','pitcher']:
     db.execute('CREATE TABLE analytical_'+role+'_projections(season INTEGER,source VARCHAR,player_id VARCHAR,record_id VARCHAR,metrics_json VARCHAR,excluded_metrics_json VARCHAR)')
     for i in range(8):
      mid=str(i+1+(100 if role=='pitcher' else 0));pid=role+mid;db.execute('INSERT INTO player_id_crosswalk VALUES (?,?,?)',[pid,'mlbam',mid])
      for y in [2024,2025,2026]:
       values=counts(role,i,y)
       if role=='pitcher':values['IP']=values['OUTS']/3
       for source in (['Steamer'] if y==2024 else ['Steamer','OOPSY']):db.execute('INSERT INTO analytical_'+role+'_projections VALUES (?,?,?,?,?,?)',[y,source,pid,source+str(y)+pid,json.dumps(values),'[]'])
   dump(wh/'migration_audit.json',{'pass':True,'objects':[]});before=sha(path);r=compare(p/'run',labels,path,p/'comparison',p/'backups');self.assertEqual(before,sha(path));self.assertGreater(r['paired_rows'],0);self.assertEqual(r['source_availability']['2024'],['Steamer'])
   with (p/'comparison/benchmark_scores.csv').open() as f:rows=list(csv.DictReader(f))
   groups={}
   for row in rows:groups.setdefault((row['season'],row['player_type'],row['metric'],row['comparison_group']),set()).add((row['n'],row['membership_sha256']))
   self.assertTrue(all(len(v)==1 for v in groups.values()));self.assertEqual(tree(p/'comparison'),tree(Path(r['backup'])))
 def test_benchmark_metric_exclusions_preserve_zero(self):
  v=published({'SV':0,'ERA':3,'H':5,'BB':2,'IP':10},{'ERA'});self.assertEqual(v['SV'],0);self.assertNotIn('ERA',v);self.assertEqual(v['WHIP'],.7)
if __name__=='__main__':unittest.main()
