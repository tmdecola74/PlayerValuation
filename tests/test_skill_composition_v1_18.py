import unittest,tempfile,json,argparse,copy
from pathlib import Path
from unittest.mock import patch
from audit_skill_composition_v1_18 import *
from standalone_io_v1_0 import tree,write
from standalone_models_v1_0 import compose

class AuditTests(unittest.TestCase):
 def fixture(self,role='hitter',year=2021):
  k=year,role,'10';r={t.id:.01 for t in SPECS if t.role==role}
  if role=='hitter':r.update(hitter_AB_per_PA=.9,hitter_1B_per_AB=.2,hitter_HR_per_AB=.05);c=dict(r,hitter_PA=500.)
  else:c=dict(r,pitcher_OUTS=300.,pitcher_SV_per_OUTS=.01,pitcher_HLD_per_OUTS=.02)
  a=compose(role,c)
  if role=='pitcher':a['SV_plus_HLD']=a['SV']+a['HLD']
  rates={k+(t.id,):dict(target=t.id,selected_method='accepted_frozen',standard_fit_status='FITTED',statcast_fit_status='FITTED',**{m:rate_of(a,t) for m in METHODS}) for t in SPECS if t.role==role}
  vectors={k+(m,):dict(a) for m in METHODS};actual={k+(m,):v for m,v in a.items() if v is not None};features={k:dict(history_seasons=3,age_at_target_estimate=28)}
  return k,rates,vectors,actual,features
 def rebuild(self,k,rates,vectors,method):
  a=vectors[k+('accepted_frozen',)];r={t.id:rates[k+(t.id,)][method] for t in SPECS if t.role==k[1]};vectors[k+(method,)]=compose_fixed(k[1],a,r,method)[0]
 def test_identical_accepted_rates_not_new(self):
  k,r,v,a,f=self.fixture();c,s,u=trace(r,v,a,f);self.assertTrue(all(x['status']=='ALREADY_REPRODUCES_ACCEPTED' for x in c));self.assertTrue(all(near(x['final_minus_accepted'],0) for x in s))
 def test_hitter_pa_normalization_and_telescope(self):
  k,r,v,a,f=self.fixture();r[k+('hitter_AB_per_PA',)]['statcast_skill']=1.;r[k+('hitter_BB_per_PA',)]['statcast_skill']=.3;self.rebuild(k,r,v,'statcast_skill');c,s,u=trace(r,v,a,f)
  self.assertTrue(any(x['pa_scale']>1 for x in u));hr=next(x for x in s if x['method']=='statcast_skill' and x['metric']=='HR');self.assertLess(hr['coherence_adjustment'],0);self.assertAlmostEqual(hr['raw_squared_error_change']+hr['composition_squared_error_change'],hr['final_squared_error_change'])
 def test_hit_normalization(self):
  k,r,v,a,f=self.fixture()
  for m in ['1B','2B','3B','HR']:r[k+('hitter_'+m+'_per_AB',)]['standard_skill']=.4
  self.rebuild(k,r,v,'standard_skill');c,s,u=trace(r,v,a,f);self.assertTrue(any(x['hit_scale']>1 for x in u))
 def test_pitcher_hr_clip_and_anchors(self):
  k,r,v,a,f=self.fixture('pitcher');r[k+('pitcher_HR_per_OUTS',)]['statcast_skill']=.9;self.rebuild(k,r,v,'statcast_skill');c,s,u=trace(r,v,a,f);self.assertTrue(any(x['pitcher_hr_clipped'] for x in u))
  for x in s:
   if x['metric'] in ['OUTS','IP','SV','HLD','SV_plus_HLD']:self.assertEqual(x['final'],x['accepted'])
 def test_frozen_replay_mismatch_rejected(self):
  k,r,v,a,f=self.fixture();v[k+('standard_skill',)]['HR']+=1
  with self.assertRaisesRegex(ValueError,'replay'):trace(r,v,a,f)
 def test_accepted_implied_rate_mismatch(self):
  k,r,v,a,f=self.fixture();r[k+('hitter_HR_per_AB',)]['accepted_frozen']=.8
  with self.assertRaisesRegex(ValueError,'implied'):trace(r,v,a,f)
 def test_unknown_label_never_zero(self):
  k,r,v,a,f=self.fixture();del a[k+('HR',)];c,s,u=trace(r,v,a,f);hr=[x for x in s if x['metric']=='HR'];self.assertTrue(all(x['actual'] is None and 'final_squared_error_change' not in x for x in hr))
 def test_zero_actual_count_retained(self):
  k,r,v,a,f=self.fixture();a[k+('HR',)]=0;c,s,u=trace(r,v,a,f);self.assertTrue(all('final_squared_error_change' in x for x in s if x['metric']=='HR'))
 def test_missing_skill_vector_fallback_explicit(self):
  k,r,v,a,f=self.fixture();r[k+('hitter_HR_per_AB',)]['standard_skill']=None;c,s,u=trace(r,v,a,f);self.assertTrue(any(x['unsupported_vector'] for x in u));self.assertTrue(any(x['status']=='UNSUPPORTED_RATE' for x in c))
 def test_summary_2021_and_history(self):
  k,r,v,a,f=self.fixture();c,s,u=trace(r,v,a,f);ss=summaries(s,f,a);self.assertTrue(all(x['season']==2021 for x in ss));self.assertTrue(any(x['cohort']=='GE3' for x in ss));self.assertTrue(all(x['n']==1 for x in ss))
 def test_null_rate_denominator(self):
  k,r,v,a,f=self.fixture();a[k+('AB',)]=0;c,s,u=trace(r,v,a,f);self.assertTrue(all(x['actual'] is None for x in s if x['metric']=='AVG'))
 def prepare(self,p):
  import duckdb
  k,r,v,a,f=self.fixture();root=p/'run';labels=p/'labels';matrix=p/'matrix'
  for d in [root,labels,matrix]:d.mkdir()
  rows=[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**x) for t,x in r.items()]
  emit(root/'historical_skill_rates.csv',rows);emit(root/'historical_forecasts.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=m,metric=n,prediction=z) for (*_,m),vv in v.items() for n,z in vv.items()])
  dump(root/'incremental_build_report.json',{'version':'1.17.0'});dump(root/'forecast_freeze.json',tree(root))
  lr=[dict(season=k[0],player_type=k[1],mlbam_id=k[2],metric=n,label_value=z,eligible=True) for (*_,n),z in a.items()];fr=[dict(target_season=k[0],player_type=k[1],mlbam_id=k[2],max_source_season=2020,source_cutoff='2020-12-31',**f[k])]
  for dest,data in [(labels/'training_labels.parquet',lr),(matrix/'training_matrix.parquet',fr)]:
   js=dest.with_suffix('.json');dump(js,data)
   with duckdb.connect() as db:db.read_json(str(js)).write_parquet(str(dest))
   js.unlink()
  dump(matrix/'feature_schema.json',{'predictor_allowlist':[]})
  for d in [labels,matrix]:dump(d/'output_sha256.json',tree(d))
  dump(root/'input_hashes.json',{str(x.resolve()):sha(x) for x in [labels/'training_labels.parquet',matrix/'training_matrix.parquet',matrix/'feature_schema.json']});dump(root/'output_sha256.json',tree(root))
  return argparse.Namespace(run=str(root),labels=str(labels),matrix=str(matrix),output=str(p/'out'),backup_root=str(p/'backups'))
 def test_full_pipeline_backup_and_no_holdout_open(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);args=self.prepare(p);before=tree(p/'run');original=Path.open
   def guarded(path,*a,**kw):
    if 'holdout' in path.name or '2026' in path.name:raise AssertionError('Evaluation file opened')
    return original(path,*a,**kw)
   with patch.object(Path,'open',guarded):report=build(args)
   self.assertFalse(report['models_fitted']);self.assertEqual(before,tree(p/'run'));self.assertEqual(tree(p/'out'),tree(Path(report['backup'])))
   with self.assertRaises(FileExistsError):build(args)
 def test_tamper_no_publication(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);args=self.prepare(p);(p/'run'/'historical_forecasts.csv').write_text('tamper')
   with self.assertRaises(ValueError):build(args)
   self.assertFalse((p/'out').exists())
 def test_interruption_cleans_stage(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);args=self.prepare(p)
   with patch('audit_skill_composition_v1_18.finish',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):build(args)
   self.assertFalse((p/'out').exists());self.assertFalse(list(p.glob('out.staging-*')))
 def test_future_historical_row_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);args=self.prepare(p);root=p/'run';text=(root/'historical_skill_rates.csv').read_text();(root/'historical_skill_rates.csv').write_text(text.replace('2021','2026'))
   with self.assertRaisesRegex(ValueError,'split'):read_inputs(root)
 def test_duplicate_rate_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);args=self.prepare(p);root=p/'run';lines=(root/'historical_skill_rates.csv').read_text().splitlines();(root/'historical_skill_rates.csv').write_text('\n'.join(lines+[lines[1]])+'\n')
   with self.assertRaisesRegex(ValueError,'Duplicate'):read_inputs(root)
 def test_reference_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);args=self.prepare(p);(p/'labels'/'training_labels.parquet').write_bytes(b'tamper')
   with self.assertRaises(ValueError):build(args)
   self.assertFalse((p/'out').exists())
if __name__=='__main__':unittest.main()
