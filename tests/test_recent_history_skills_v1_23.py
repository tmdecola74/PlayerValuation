import unittest,tempfile,argparse,copy,json,csv
from pathlib import Path
from unittest.mock import patch
from collections import defaultdict
import duckdb
import recent_skill_core_v1_23 as c
import recent_skill_inputs_v1_23 as i
import recent_history_skills_v1_23 as b
import evaluate_recent_history_skills_v1_23 as e
from standalone_io_v1_0 import dump,load,sha,tree,write,table,csvrows

def pq(p,rows):
 tmp=p.with_suffix('.tmp.json');dump(tmp,rows)
 with duckdb.connect() as db:db.read_json(str(tmp)).write_parquet(str(p))
 tmp.unlink()
def manifest(p,windows=False):
 (p/'output_sha256.json').unlink(missing_ok=True);dump(p/'output_sha256.json',{n.replace('/','\\') if windows else n:h for n,h in tree(p).items()})
def vector(role):
 return dict(PA=500.,AB=450.,H=120.,**{'1B':85.,'2B':20.,'3B':5.},HR=10.,R=60.,RBI=50.,SB=10.,BB=40.,HBP=5.,SF=5.,SH=0.,AVG=120/450,OBP=165/500,SLG=180/450,OPS=165/500+180/450) if role=='hitter' else dict(OUTS=450.,IP=150.,H=130.,ER=50.,BB=40.,SO=140.,HR=15.,W=10.,SV=5.,HLD=2.,QS=15.,ERA=3.,WHIP=170/150,SV_plus_HLD=7.)
def fixture(p):
 roots={n:p/n for n in ['reference','matrix','labels','expanded','supplement','audit']}
 for root in roots.values():root.mkdir()
 rows=[];hold=[];hist=[];future=[];labs=[];hl=[];ex=[];bat=[];ars=[];allow=['age_at_target_estimate']
 for role in c.METRICS:
  for lag in [1,2,3]:
   for m in c.METRICS[role]+['G','GS']:allow.append(f'x_actual_lag{lag}_{m}')
   for m in c.CLASSIC[role]:
    for suffix in ['value','observations','eligible','coverage']:allow.append(f'x_statcast_lag{lag}_{m}_{suffix}')
 allow=sorted(set(allow))
 for y in range(2016,2027):
  for role in c.METRICS:
   for n in range(12):
    pid=str(n+1+(100 if role=='pitcher' else 0));v=vector(role);r={name:None for name in allow};r.update(target_season=y,player_type=role,mlbam_id=pid,max_source_season=y-1,source_cutoff=f'{y-1}-12-31',age_at_target_estimate=25.+n)
    for lag in [1,2,3]:
     r['source_season_lag'+str(lag)]=y-lag
     for m in c.METRICS[role]+['G','GS']:r[f'x_actual_lag{lag}_{m}']=None if n<4 and lag>1 else v.get(m,30.)
     for m in c.CLASSIC[role]:
      for suffix,value in [('value',90.+n),('observations',100.),('eligible',1),('coverage',1.)]:r[f'x_statcast_lag{lag}_{m}_{suffix}']=None if n<4 and lag>1 else value
     for m in ['gb_pct','launch_angle_sd','zone_contact_pct']:
      ok=y-lag>=2015;ex.append(dict(target_season=y,player_type=role,mlbam_id=pid,lag=lag,source_season=y-lag,metric=m,value=.5 if ok else None,denominator=100.,eligible=ok,coverage=1.))
     ok=2023<=y-lag<=2025
     for m in c.BAT:bat.append(dict(target_season=y,player_type=role,mlbam_id=pid,lag=lag,source_season=y-lag,feature='savant_bat_tracking_'+m,family='bat_tracking',value=70.+n if ok else None,denominator=200.,eligible=ok))
    (hold if y==2026 else rows).append(r)
    for m,value in v.items():
     (hl if y==2026 else labs).append(dict(season=y,player_type=role,mlbam_id=pid,metric=m,eligible=True,label_value=value))
     if y>=2019:(future if y==2026 else hist).append(dict(season=y,player_type=role,mlbam_id=pid,metric=m,method='accepted_frozen',prediction=value))
 for y in range(2015,2026):
  for n in range(12):
   for m in c.PTMETRICS:ars.append(dict(source_season=y,player_type='pitcher',mlbam_id=str(101+n),metric=m,pitch_type='FF',eligible=True,value=.6 if m=='pitch_type_usage' else .2 if m=='whiff_pct' else 95.,denominator=500.))
 # Real label tables include eligible signed metrics outside the experiment's scoring targets.
 for y in range(2016,2027):
  for role,pid in [('hitter','1'),('pitcher','101')]:
   (hl if y==2026 else labs).append(dict(season=y,player_type=role,mlbam_id=pid,metric='K-BB%',eligible=True,label_value=-.02))
 m=roots['matrix'];pq(m/'training_matrix.parquet',rows);pq(m/'holdout_features.parquet',hold);dump(m/'feature_schema.json',dict(predictor_allowlist=allow));dump(m/'source_windows.json',[])
 lab=roots['labels'];pq(lab/'training_labels.parquet',labs);pq(lab/'holdout_labels.parquet',hl);dump(lab/'label_build_report.json',dict(reference_sha256={'fixture':'frozen'}))
 ref=roots['reference'];b.emit(ref/'historical_forecasts.csv',hist);b.emit(ref/'frozen_2026_forecasts.csv',future);dump(ref/'incremental_build_report.json',dict(version='1.17.0',accepted_forecasts_modified=False,evaluation_outcomes_read=False));dump(ref/'input_hashes.json',{str(path.resolve()):sha(path) for path in [m/'training_matrix.parquet',m/'holdout_features.parquet',m/'feature_schema.json',lab/'training_labels.parquet',lab/'label_build_report.json']});dump(ref/'forecast_freeze.json',{name:sha(ref/name) for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv','incremental_build_report.json']})
 ep=roots['expanded'];pq(ep/'expanded_features_season.parquet',[dict(fixture='frozen')]);pq(ep/'pitch_type_features_season.parquet',ars);dump(ep/'expanded_feature_report.json',dict(version='1.20.0',models_fitted=False,accepted_matrix_modified=False));dump(ep/'input_hashes.json',{str(path.resolve()):sha(path) for path in [m/'source_windows.json',m/'holdout_features.parquet']})
 sp=roots['supplement'];(sp/'historical').mkdir();pq(sp/'historical/leaderboard_features.parquet',[dict(fixture='frozen')]);dump(sp/'leaderboard_build_report.json',dict(version='1.21.0',accepted_projection_source_modified=False));dump(sp/'input_hashes.json',{str(path.resolve()):sha(path) for path in [m/'source_windows.json',m/'holdout_features.parquet',ep/'expanded_features_season.parquet']})
 ap=roots['audit'];dump(ap/'scope_audit_report.json',dict(version='1.22.0',archive_replay_verified=True,forecasts_modified=False));dump(ap/'input_hashes.json',{str(path.resolve()):sha(path) for path in [m/'source_windows.json',ep/'expanded_features_season.parquet',sp/'historical/leaderboard_features.parquet']})
 for split in ['training','holdout']:
  pq(ep/(split+'_expanded_features.parquet'),[r for r in ex if (r['target_season']==2026)==(split=='holdout')]);pq(sp/(split+'_leaderboard_features.parquet'),[r for r in bat if (r['target_season']==2026)==(split=='holdout')])
 for root in roots.values():manifest(root,True)
 warehouse=p/'warehouse';warehouse.mkdir();wp=warehouse/'player_valuation.duckdb'
 with duckdb.connect(str(wp)) as db:
  db.execute('CREATE TABLE player_id_crosswalk(player_id VARCHAR,namespace VARCHAR,external_id VARCHAR)');db.execute('CREATE TABLE players(player_id VARCHAR,preferred_name VARCHAR)')
  for role in c.METRICS:
   db.execute('CREATE TABLE analytical_'+role+'_projections(season INTEGER,source VARCHAR,player_id VARCHAR,record_id VARCHAR,metrics_json VARCHAR,excluded_metrics_json VARCHAR)')
   for n in range(12):
    mid=str(n+1+(100 if role=='pitcher' else 0));pid='p_'+mid;db.execute('INSERT INTO player_id_crosswalk VALUES (?,?,?)',[pid,'mlbam',mid]);db.execute('INSERT INTO players VALUES (?,?)',[pid,'Player '+mid])
    for source in ['Steamer','OOPSY','ATC','Depth Charts']:
     vv=vector(role);db.execute('INSERT INTO analytical_'+role+'_projections VALUES (?,?,?,?,?,?)',[2026,source,pid,source+'_'+mid,json.dumps(vv),json.dumps(['HLD'] if source=='ATC' else [])])
 dump(warehouse/'migration_audit.json',dict(pass_=True));dump(warehouse/'migration_audit.json',{'pass':True})
 raw=p/'raw';raw.mkdir();(raw/'steamerhitters2026pre.csv').write_text('fixture projection',encoding='utf-8');(raw/'oopsypitchers2027pre.csv').write_text('FUTURE_NOT_OPENED',encoding='utf-8')
 cfg=p/'config.json';dump(cfg,c.DEFAULT)
 return argparse.Namespace(**roots,warehouse=wp,benchmark_dir=raw,config=cfg,output=p/'out',backup_root=p/'backups')

class Units(unittest.TestCase):
 def test_signed_non_scoring_labels_ignored_and_audited(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'labels.parquet';rr=[dict(season=2025,player_type='pitcher',mlbam_id='1',metric='K-BB%',eligible=True,label_value=-.03),dict(season=2025,player_type='pitcher',mlbam_id='1',metric='H',eligible=True,label_value=0.)];pq(p,rr);audit=[];bank=i.labels(p,scope_audit=audit)
   self.assertEqual(bank,{(2025,'pitcher','1','H'):0.});self.assertTrue(any(r['status']=='IGNORED_NONSCORING_METRIC' and r['negative_values_observed']==1 and not r['used_as_label'] for r in audit))
   rr[0]['label_value']=-100.;pq(p,rr);self.assertEqual(bank,i.labels(p))
 def test_negative_scoring_count_still_rejected_with_identity(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'labels.parquet';pq(p,[dict(season=2025,player_type='hitter',mlbam_id='1',metric='HR',eligible=True,label_value=-1.)])
   with self.assertRaisesRegex(ValueError,"Invalid eligible scoring label.*HR"):i.labels(p)
 def test_ignored_metric_cannot_bypass_split_or_duplicate_guards(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'labels.parquet';r=dict(season=2026,player_type='pitcher',mlbam_id='1',metric='K-BB%',eligible=True,label_value=-.03);pq(p,[r])
   with self.assertRaisesRegex(ValueError,'split'):i.labels(p)
   pq(p,[r,r])
   with self.assertRaisesRegex(ValueError,'duplicate'):i.labels(p,2026)
 def test_exposure_weighted_recency_and_missing_not_zero(self):
  self.assertEqual(c.weighted([(1.,100.),(0.,100.),(None,None)],c.WEIGHTS['recent'])[0],.6);self.assertIsNone(c.weighted([(None,None)]*3,[3,2,1])[0]);self.assertEqual(c.weighted([(0.,100.)],[1])[0],0.)
 def test_recent_2026_window_and_role_feature_separation(self):
  r=dict(target_season=2026,player_type='hitter',mlbam_id='1',age_at_target_estimate=27.,x_actual_lag1_HR=30.,x_actual_lag1_AB=300.,x_actual_lag2_HR=0.,x_actual_lag2_AB=300.,x_actual_lag3_HR=0.,x_actual_lag3_AB=300.,x_actual_lag4_HR=999.)
  std,ex,bat=c.make_features(r,{}, {},{},'recent');self.assertEqual(std['actual_HR_per_AB'],.05);self.assertFalse(any('arsenal' in n for n in ex));self.assertTrue(all(v is None for n,v in bat.items() if n.startswith('bat_') and not n.endswith(('_observations','_lags'))));self.assertFalse(bat['__bat_available'])
 def test_coherent_group_keeps_every_anchor_exact(self):
  for role in c.METRICS:
   old=vector(role);den=old['AB' if role=='hitter' else 'OUTS'];v,ok=c.compose(role,old,{m:old[m]/den*1.2 for m in c.TARGETS[role]});self.assertTrue(ok);c.coherent(role,v);self.assertTrue(all(v[m]==old[m] for m in old if m not in c.CHANGED[role]))
 def test_unsupported_components_fall_back_not_zero(self):
  v=vector('hitter');self.assertEqual(c.compose('hitter',v,{})[0],v);bad=dict(v,BB=None,OBP=None,OPS=None);self.assertFalse(c.compose('hitter',bad,{m:.1 for m in c.TARGETS['hitter']})[1])
 def test_gate_only_earlier_folds_and_bat_never_selected(self):
  h=[]
  for y in [2021,2022,2023,2024,2025]:
   for cohort in ['ALL','LOW_HISTORY','ESTABLISHED_HISTORY']:
    for m in c.GATE_METRICS['hitter']:
     errors={'accepted_frozen':dict(mse=4.,mae=2.)}
     for arm in c.ARMS:errors[arm]=dict(mse=1. if arm=='expanded_recent' else 2.,mae=1.)
     h.append(dict(season=y,player_type='hitter',cohort=cohort,metric=m,n=100,errors=errors,supported={arm:True for arm in c.ARMS}))
  before=c.gate(h,'hitter',2026,c.DEFAULT);self.assertEqual(before['selected'],'expanded_recent');self.assertNotIn('bat_recent_exploratory',before['candidates']);self.assertEqual(before,c.gate(h+[dict(r,season=2026) for r in h],'hitter',2026,c.DEFAULT))
  self.assertEqual(c.gate([],'hitter',2021,c.DEFAULT)['selected'],'accepted_frozen')
 def test_known_signal_is_fit_on_earlier_targets_and_fold_preprocessing(self):
  accepted={};actual={};features={}
  for n in range(100):
   k=2020,'hitter',str(n+1);accepted[k]=vector('hitter');actual[k+('AB',)]=450.;actual[k+('HR',)]=10.+n*.2;features[k]={'signal':float(n)}
  k=2021,'hitter','200';accepted[k]=vector('hitter');features[k]={'signal':50.};model,preds=c.fit_residual(list(actualkey for actualkey in accepted if actualkey[0]==2020),[k],features,accepted,actual,'hitter','HR',2021,c.DEFAULT);self.assertEqual(model['fit_target_seasons'],[2020]);self.assertEqual(model['status'],'FITTED');self.assertGreater(preds[k],10/450)
  prior=copy.deepcopy(model);features[k]['signal']=999.;model2,_=c.fit_residual([kk for kk in accepted if kk[0]==2020],[k],features,accepted,actual,'hitter','HR',2021,c.DEFAULT);self.assertEqual(prior,model2)
 def test_windows_manifest_and_collision_guard(self):
  self.assertEqual(c.portable({'historical\\x':'h'}),{'historical/x':'h'})
  with self.assertRaises(ValueError):c.portable({'a/b':'h','a\\b':'h'})
 def test_missing_measurement_mask_before_imputation(self):
  r=dict(target_season=2026,player_type='hitter',mlbam_id='1',age_at_target_estimate=25.,x_statcast_lag1_ev_value=99.,x_statcast_lag1_ev_observations=300.,x_statcast_lag1_ev_eligible=0,x_statcast_lag1_ev_coverage=1.)
  standard,_,_=c.make_features(r,{}, {},{},'recent');self.assertIsNone(standard['classic_ev']);self.assertEqual(standard['classic_ev_observations'],0)
 def test_fold_common_preprocessing_identical_between_feature_arms(self):
  rows=[dict(x=float(n),missing=None if n%2 else 1.,new=float(n%3)) for n in range(60)];left=c.preprocess(rows,['x','missing'],c.DEFAULT);right=c.preprocess(rows,['x','missing','new'],c.DEFAULT)
  self.assertEqual(left['numeric']['x'],right['numeric']['x']);self.assertEqual(left['numeric']['missing'],right['numeric']['missing'])
 def test_rates_exclude_zero_denominator_but_keep_zero_numerator(self):
  k=2026,'hitter','1';rates=[dict(season=2026,player_type='hitter',mlbam_id='1',metric='HR',denominator='AB',prediction=.1,accepted_rate=.2,method='expanded_recent')];ctx={k:dict(recent_history_seasons=2)}
  self.assertTrue(b.rate_scores(rates,{k+('AB',):10.,k+('HR',):0.},ctx));self.assertEqual(b.rate_scores(rates,{k+('AB',):0.,k+('HR',):0.},ctx),[])
 def test_addon_future_and_unmasked_values_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'a.parquet';base=dict(target_season=2026,player_type='hitter',mlbam_id='1',lag=1,source_season=2025,metric='gb_pct',value=.5,denominator=100.,eligible=False,coverage=1.)
   pq(p,[base])
   with self.assertRaisesRegex(ValueError,'Unmasked'):i.addon(p,'expanded')
   pq(p,[dict(base,target_season=2027,source_season=2026,eligible=True)])
   with self.assertRaisesRegex(ValueError,'chronology'):i.addon(p,'expanded')
 def test_bat_fitted_control_uses_identical_supported_population(self):
  accepted={};actual={};control={};bat={}
  for n in range(100):
   k=2024,'hitter',str(n+1);accepted[k]=vector('hitter');actual[k+('AB',)]=450.;actual[k+('HR',)]=10.+n*.1;control[k]=dict(common=1.,__bat_available=n<60);bat[k]=dict(control[k],bat_speed=float(n))
  k=2025,'hitter','200';accepted[k]=vector('hitter');control[k]=dict(common=1.,__bat_available=True);bat[k]=dict(control[k],bat_speed=30.)
  train=[kk for kk in accepted if kk[0]==2024];a,p0=c.fit_residual(train,[k],control,accepted,actual,'hitter','HR',2025,c.DEFAULT,True);b,p1=c.fit_residual(train,[k],bat,accepted,actual,'hitter','HR',2025,c.DEFAULT,True)
  self.assertEqual(a['status'],'FITTED');self.assertEqual(b['status'],'FITTED');self.assertEqual(a['n_fit'],60);self.assertEqual(a['fit_membership_sha256'],b['fit_membership_sha256']);self.assertEqual(a['preprocessing']['numeric']['common'],b['preprocessing']['numeric']['common'])
  bat[k]['__bat_available']=False;_,pred=c.fit_residual(train,[k],bat,accepted,actual,'hitter','HR',2025,c.DEFAULT,True);self.assertIsNone(pred[k])
 def test_extreme_hit_rates_normalized_and_pitcher_hr_bound(self):
  a=vector('hitter');v,ok=c.compose('hitter',a,{m:1. for m in c.TARGETS['hitter']});self.assertEqual(v['H'],a['AB']);c.coherent('hitter',v)
  a=vector('pitcher');rates={m:.1 for m in c.TARGETS['pitcher']};rates['HR']=.5;v,ok=c.compose('pitcher',a,rates);self.assertEqual(v['H'],v['HR']);self.assertEqual(v['SV'],a['SV']);c.coherent('pitcher',v)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);cls.a=fixture(cls.p);cls.before={n:tree(getattr(cls.a,n)) for n in ['reference','matrix','labels','expanded','supplement','audit']};cls.report=b.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_build_backup_and_no_accepted_source_change(self):
  self.assertEqual(tree(self.a.output),tree(Path(self.report['backup'])))
  for n,t in self.before.items():self.assertEqual(t,tree(getattr(self.a,n)))
  self.assertFalse(self.report['evaluation_outcomes_read']);self.assertFalse(self.report['new_source_promoted']);self.assertTrue(csvrows(self.a.output/'transition_2021_scores.csv'))
  self.assertEqual(self.report['build_implementation_version'],'1.23.1');self.assertEqual(self.report['ignored_non_scoring_label_rows'],20);self.assertTrue(csvrows(self.a.output/'training_label_scope_audit.csv'))
 def test_frozen_anchors_and_2026_source_years(self):
  rows=csvrows(self.a.output/'frozen_2026_forecasts.csv');bank=defaultdict(dict)
  for r in rows:bank[r['player_type'],r['mlbam_id'],r['method']][r['metric']]=c.number(r['prediction'])
  for (role,pid,method),v in bank.items():
   a=bank[role,pid,'accepted_frozen'];self.assertTrue(all(v[m]==a[m] for m in a if m not in c.CHANGED[role]));c.coherent(role,v)
  self.assertTrue(all(r['source_years']=='2023|2024|2025' and r['older_player_history_fallback']=='False' for r in csvrows(self.a.output/'component_provenance_2026.csv')))
 def test_chronology_and_short_arm_matched_training(self):
  rr=csvrows(self.a.output/'fold_fit_chronology.csv');index={(r['origin'],r['player_type'],r['method'],r['metric']):r for r in rr}
  for r in rr:
   self.assertTrue(all(y<int(r['origin']) for y in json.loads(r['fit_target_seasons'])))
   if r['method']=='bat_recent_exploratory':self.assertEqual(r['fit_membership_sha256'],index[r['origin'],r['player_type'],'bat_control_recent',r['metric']]['fit_membership_sha256']);self.assertTrue(all(y>=2024 for y in json.loads(r['fit_target_seasons'])))
 def test_matched_historical_memberships(self):
  groups=defaultdict(set)
  for r in csvrows(self.a.output/'historical_scores.csv'):groups[tuple(r[n] for n in ['season','player_type','metric','cohort_dimension','cohort','comparison_group'])].add((r['n'],r['membership_sha256']))
  self.assertTrue(all(len(g)==1 for g in groups.values()))
 def test_benchmarks_inventory_exclusions_and_future_raw_not_opened(self):
  rr=csvrows(self.a.output/'benchmark_inventory.csv');self.assertTrue(all(r['status']=='AVAILABLE' for r in rr if r['season']=='2026'));self.assertTrue(all(r['status']=='NOT_REGISTERED_IN_WAREHOUSE' for r in rr if r['season']=='2023'))
  pp=csvrows(self.a.output/'frozen_benchmark_predictions.csv');self.assertFalse(any(r['source']=='ATC' and r['metric']=='HLD' for r in pp));raw=csvrows(self.a.output/'benchmark_raw_file_inventory.csv');self.assertTrue(any(r['status']=='FUTURE_FILE_NOT_OPENED' and r['sha256']=='' for r in raw))
 def test_separate_evaluation_no_fit_same_pools_and_backup(self):
  a=argparse.Namespace(run=self.a.output,labels=self.a.labels,output=self.p/'evaluation',backup_root=self.p/'backups');before=tree(self.a.output)
  with patch.object(b,'fit_residual',side_effect=AssertionError('Evaluation fitted')):r=e.evaluate(a)
  self.assertEqual(r['ignored_non_scoring_label_rows'],2);self.assertTrue(csvrows(a.output/'evaluation_label_scope_audit.csv'))
  self.assertFalse(r['models_fitted']);self.assertEqual(before,tree(self.a.output));self.assertEqual(tree(a.output),tree(Path(r['backup'])))
  groups=defaultdict(set)
  for row in csvrows(a.output/'matched_benchmark_scores.csv'):groups[tuple(row[n] for n in ['player_type','metric','comparison_group','cohort_dimension','cohort'])].add((row['n'],row['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()))
 def test_holdout_outcomes_never_opened_and_mutation_invariant(self):
  original=Path.open
  def guard(p,*args,**kw):
   if 'holdout_labels' in p.name or '2027pre' in p.name:raise AssertionError('Future outcome/source file opened')
   return original(p,*args,**kw)
  hp=self.a.labels/'holdout_labels.parquet';before=hp.read_bytes()
  try:
   hp.write_bytes(b'NOT A READABLE PARQUET');a=copy.copy(self.a);a.output=self.p/'blind'
   with patch.object(Path,'open',guard):b.build(a)
   for name in ['frozen_choices_2026.json','frozen_models_2026.json','frozen_2026_forecasts.csv']:self.assertEqual(sha(a.output/name),sha(self.a.output/name))
  finally:hp.write_bytes(before)
 def test_output_and_config_guards(self):
  with self.assertRaises(FileExistsError):b.build(self.a)
  a=copy.copy(self.a);a.output=self.p/'bad';a.config=self.p/'bad.json';dump(a.config,dict(c.DEFAULT,ridge_alpha=2.))
  with self.assertRaises(ValueError):b.build(a)
 def test_interruption_cleans_stage(self):
  a=copy.copy(self.a);a.output=self.p/'interrupted'
  with patch.object(b,'fit_residual',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):b.build(a)
  self.assertFalse(a.output.exists());self.assertFalse(list(self.p.glob('interrupted.staging-*')))
 def test_frozen_forecast_tamper_blocks_evaluation(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);target=p/'copy';import shutil;shutil.copytree(self.a.output,target);(target/'frozen_2026_forecasts.csv').write_text('tamper',encoding='utf-8');a=argparse.Namespace(run=target,labels=self.a.labels,output=p/'eval',backup_root=p/'backups')
   with self.assertRaisesRegex(ValueError,'hash'):e.evaluate(a)
   self.assertFalse(a.output.exists())
 def test_duplicate_benchmark_ownership_is_explicit_not_name_matched(self):
  with tempfile.TemporaryDirectory() as t:
   import shutil
   p=Path(t);wp=p/'w.duckdb';shutil.copyfile(self.a.warehouse,wp);dump(p/'migration_audit.json',{'pass':True})
   with duckdb.connect(str(wp)) as db:db.execute("INSERT INTO player_id_crosswalk VALUES ('duplicate_owner','mlbam','1')")
   preds,inv,issues,raw=i.benchmark_snapshot(wp,p/'missing',{});self.assertTrue(any(r['reason']=='MISSING_OR_AMBIGUOUS_MLBAM' for r in issues));self.assertFalse(any(r['mlbam_id']=='1' for r in preds));self.assertTrue(any(r['mlbam_id']=='2' for r in preds))

if __name__=='__main__':unittest.main()
