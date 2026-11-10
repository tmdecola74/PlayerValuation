import unittest,tempfile,importlib.util,json,shutil,argparse,csv
from pathlib import Path
from unittest.mock import patch
from collections import defaultdict
import duckdb
import projection_release_v1_11_1 as p
from evaluate_projection_release_v1_11_2 import evaluate,evaluation_rows
from standalone_io_v1_0 import dump,load,sha,tree,write,csvrows
import backtest_standalone_holds_attribution_v1_5 as b15
ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('previous_release_fixture',Path(b15.__file__).parent/'tests/test_standalone_holds_attribution_v1_5.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def fake_external(path):
 result={}
 for role in p.METRICS:
  for m in p.METRICS[role]:result[2026,role,'1',m,'Steamer']=(1.,'source_record')
 return result,{2026:{'Steamer'}},[],{str(path):sha(path)}

class Units(unittest.TestCase):
 def test_ratio_components_and_no_rounding(self):
  v=p.consensus_vector('pitcher',dict(IP=100,H=90,BB=30,ER=40,SO=100,HR=10,W=8,SV=20,HLD=4,ERA=99,WHIP=99))
  self.assertEqual(v['OUTS'],300);self.assertEqual(v['ERA'],3.6);self.assertEqual(v['WHIP'],1.2);self.assertEqual(v['SV_plus_HLD'],24)
  with self.assertRaisesRegex(ValueError,'IP/OUTS'):p.consensus_vector('pitcher',dict(IP=100,OUTS=301))
  v=p.consensus_vector('hitter',dict(PA=100,AB=90,H=25,HR=3,R=10,RBI=10,SB=0,AVG=.999))
  self.assertAlmostEqual(v['AVG'],25/90);self.assertIsNone(v['SLG']);self.assertEqual(v['H'],25)
 def test_invalid_counts_and_no_zero_fill(self):
  with self.assertRaises(ValueError):p.consensus_vector('hitter',dict(AB=10,H=20))
  with self.assertRaises(ValueError):p.consensus_vector('hitter',dict(H=4,**{'1B':1,'2B':1,'3B':1,'HR':0}))
  with self.assertRaises(ValueError):p.consensus_vector('pitcher',dict(IP=-1))
  self.assertIsNone(p.consensus_vector('pitcher',dict(IP=0,H=0,BB=0,ER=0))['ERA'])
 def test_matched_pools_zero_actuals_and_missing_not_zero(self):
  r=dict(season=2026,player_type='hitter',projection_source=p.HOME,projection_key='a',player_id='p1',mlbam_id='1',name='A',SB=4,HR=2)
  labels=[dict(season=2026,player_type='hitter',mlbam_id='1',metric='SB',eligible=True,label_value=0),dict(season=2026,player_type='hitter',mlbam_id='1',metric='HR',eligible=False,label_value=None),dict(season=2026,player_type='hitter',mlbam_id='2',metric='SB',eligible=True,label_value=10)]
  individual,scores,pairs,coverage,absent=evaluation_rows([r],labels,{(2026,'hitter','1','SB','Steamer'):(3,'s')})
  score=[x for x in scores if x['metric']=='SB' and x['player_type']=='hitter' and x['comparison_group']=='Steamer_matched'];self.assertEqual({x['n'] for x in score},{1});self.assertEqual(len({x['membership_sha256'] for x in score}),1)
  self.assertEqual(next(x for x in individual if x['metric']=='SB' and x['projection_source']==p.HOME)['error'],4)
  self.assertEqual(next(x for x in individual if x['metric']=='HR')['status'],'MISSING_OR_INELIGIBLE_ACTUAL');self.assertEqual(absent[0]['mlbam_id'],'2')
  labels.append(dict(labels[0]));self.assertRaises(ValueError,evaluation_rows,[r],labels,{})
 def test_signed_out_of_scope_labels_are_audited_not_scored_or_zero_filled(self):
  labels=[dict(season=2026,player_type='pitcher',mlbam_id='1',metric='K-BB%',eligible=True,label_value=-.05),dict(season=2026,player_type='pitcher',mlbam_id='1',metric='SO',eligible=True,label_value=10)]
  rr=[dict(season=2026,player_type='pitcher',mlbam_id='1',player_id='p1',name='A',projection_source=p.HOME,projection_key='p',SO=12)]
  audit=[];rows,scores,pairs,coverage,absent=evaluation_rows(rr,labels,{},audit)
  self.assertEqual(audit[0]['label_value'],-.05);self.assertEqual(audit[0]['metric'],'K-BB%');self.assertEqual(len(audit),1)
  self.assertFalse(any(r['metric']=='K-BB%' for r in rows+pairs+scores));self.assertEqual(next(r['error'] for r in rows if r['metric']=='SO'),2)
 def test_bad_supported_label_remains_strict_and_error_identifies_player_metric(self):
  for value in [-1,None,float('nan'),float('inf')]:
   labels=[dict(season=2026,player_type='pitcher',mlbam_id='123',metric='SO',eligible=True,label_value=value)]
   with self.assertRaisesRegex(ValueError,'MLBAM=123, metric=SO'):evaluation_rows([],labels,{})
 def test_market_review_overrides_stale_mapping_and_same_names_distinct(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);fields=['player_type','nfbc_player_id','player_id','source_player_name','source_team','positions','ADP']
   base=dict(player_type='hitter',nfbc_player_id='10',player_id='stale',source_player_name='Same Name',source_team='ATH',positions='SS',ADP='50')
   write(root/'nfbc15_dc_adp.csv',[base,dict(base,nfbc_player_id='11',player_id='other')],fields);write(root/'nfbc15_dc_eligibility.csv',[dict(base,player_id='correct')],fields);write(root/'nfbc15_dc_eligibility_review.csv',[dict(base,player_id='',nfbc_player_id='12')],fields)
   assets,w=p.market_assets(root,{'correct':'1','other':'2'});self.assertEqual(len(assets),3);self.assertEqual(assets[0]['mlbam_id'],'1');self.assertIsNone(assets[2]['mlbam_id'])
 def test_identity_catalog_never_name_matches_or_merges_multiple_owners(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);dbpath=root/'catalog.duckdb'
   with duckdb.connect(str(dbpath)) as db:
    db.execute('CREATE TABLE players(player_id VARCHAR,preferred_name VARCHAR)');db.execute("INSERT INTO players VALUES ('a','Same'),('b','Same'),('c','Other')");db.execute('CREATE TABLE player_id_crosswalk(player_id VARCHAR,namespace VARCHAR,external_id VARCHAR)');db.execute("INSERT INTO player_id_crosswalk VALUES ('a','mlbam','1'),('b','mlbam','1'),('c','mlbam','2')")
   dump(root/'migration_audit.json',dict(pass_=True,objects=[]));a=load(root/'migration_audit.json');a['pass']=a.pop('pass_');dump(root/'migration_audit.json',a);ids,names,w=p.canonical_catalog(dbpath);self.assertEqual(ids,{'c':'2'})

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.tmp=tempfile.TemporaryDirectory();cls.p=Path(cls.tmp.name);q=cls.p;old.fixture(q);old.run(q)
  c=p.source_context(q/'new14',q/'new13',q/'matrix',q/'v12full',q/'labels');truth=p.read_all_labels(q/'labels','training');f,holds,w=p.validate_run(q/'new15',c,truth)
  cls.c=c;cls.holds=holds;cons=[];metap=[];xref=[];names=[];assets=[]
  ids=sorted({k[2] for k in c['predictions'] if k[0]==2026})
  for mlbam in ids:
   pid='p_'+mlbam;names.append((pid,'Player '+mlbam));xref.append((pid,'mlbam',mlbam))
  for k in sorted(c['predictions']):
   if k[0]!=2026:continue
   role,mlbam=k[1:];pid='p_'+mlbam;v=p.vectors(c,k)['combined_v1_4'];v=p.overlay(v,holds[k]['selected_v1_5']) if role=='pitcher' else v
   cons.append(dict(season=2026,player_type=role,player_id=pid,name='Player '+mlbam,mlbam_ids=[mlbam],teams=['ATH'],metrics=v))
   for m,value in v.items():metap.append(dict(season=2026,player_type=role,player_id=pid,metric=m,consensus=value,method='fixture_weighted_components'))
   assets.append(dict(player_type=role,nfbc_player_id=str(1000+len(assets)),player_id=pid,source_player_name='Player '+mlbam,source_team='ATH',positions='P' if role=='pitcher' else 'SS',ADP=str(50+len(assets))))
  # A market prospect with consensus but no homegrown prior-history row.
  pid='prospect';names.append((pid,'Prospect'));xref.append((pid,'mlbam','999999'));v=p.consensus_vector('hitter',dict(PA=1,AB=.9,H=.2,HR=0,R=0,RBI=0,SB=0));cons.append(dict(season=2026,player_type='hitter',player_id=pid,name='Prospect',mlbam_ids=['999999'],teams=['ATH'],metrics=v))
  for m,value in v.items():metap.append(dict(season=2026,player_type='hitter',player_id=pid,metric=m,consensus=value,method='fixture'))
  assets.append(dict(player_type='hitter',nfbc_player_id='999999',player_id=pid,source_player_name='Prospect',source_team='ATH',positions='SS',ADP='700'))
  cls.cons=q/'consensus';cls.cons.mkdir()
  for role in p.METRICS:dump(cls.cons/(role+'_consensus.json'),[r for r in cons if r['player_type']==role])
  write(cls.cons/'metric_provenance.csv',metap,list(metap[0]));cls.market=q/'draft';cls.market.mkdir()
  for n in ['nfbc15_dc_adp.csv','nfbc15_dc_eligibility.csv']:write(cls.market/n,assets,list(assets[0]))
  write(cls.market/'nfbc15_dc_eligibility_review.csv',[],['player_type','nfbc_player_id','name','reason','ADP'])
  cls.warehouse=q/'warehouse.duckdb'
  with duckdb.connect(str(cls.warehouse)) as db:
   db.execute('CREATE TABLE players(player_id VARCHAR,preferred_name VARCHAR)');db.executemany('INSERT INTO players VALUES (?,?)',names);db.execute('CREATE TABLE player_id_crosswalk(player_id VARCHAR,namespace VARCHAR,external_id VARCHAR)');db.executemany('INSERT INTO player_id_crosswalk VALUES (?,?,?)',xref)
   for role in p.METRICS:
    db.execute('CREATE TABLE analytical_'+role+'_projections(season INTEGER,source VARCHAR,player_id VARCHAR,record_id VARCHAR,metrics_json VARCHAR,excluded_metrics_json VARCHAR)')
    rr=[r for r in cons if r['player_type']==role]
    if rr:db.executemany('INSERT INTO analytical_'+role+'_projections VALUES (?,?,?,?,?,?)',[(2026,s,r['player_id'],s+r['player_id'],json.dumps(r['metrics']),'[]') for r in rr for s in ['Steamer','OOPSY']])
  dump(q/'migration_audit.json',{'pass':True,'objects':[]});cls.a=argparse.Namespace(run15=q/'new15',run14=q/'new14',source=q/'new13',matrix=q/'matrix',baseline=q/'v12full',labels=q/'labels',consensus=cls.cons,warehouse=cls.warehouse,draft_inputs=cls.market,settings=ROOT/'config/projection_release_v1_11.json',output=q/'release',backup_root=q/'backups')
  cls.before={n:tree(q/n) for n in ['new15','new14','new13','labels','matrix','draft','consensus']};cls.report=p.build(cls.a)
 @classmethod
 def tearDownClass(cls):cls.tmp.cleanup()
 def test_full_release_coherence_source_separation_and_backup(self):
  q=self.p;self.assertEqual(tree(q/'release'),tree(Path(self.report['backup'])));self.assertFalse(self.report['evaluation_outcomes_read'])
  rr=load(q/'release/coherent_projection_records.json');self.assertTrue({r['projection_source'] for r in rr}=={p.HOME,p.CONS});self.assertTrue(len(rr)>0)
  for r in rr:
   if r['projection_source']==p.HOME:
    v={m:r.get(m) for m in p.METRICS[r['player_type']]};self.assertEqual(v,p.coherent(r['player_type'],v))
  for n,v in self.before.items():self.assertEqual(tree(q/n),v)
  for role in p.METRICS:
   pc=p.table(q/'release'/f'homegrown_{role}s_2026.parquet');self.assertTrue(pc);self.assertEqual(len(pc),len(csvrows(q/'release'/f'homegrown_{role}s_2026.csv')))
 def test_saves_holds_and_all_frozen_components_exactly_unchanged(self):
  rows=load(self.p/'release/coherent_projection_records.json')
  for r in rows:
   if r['projection_source']!=p.HOME:continue
   k=(2026,r['player_type'],r['mlbam_id']);expected=p.vectors(self.c,k)['combined_v1_4'];expected=p.overlay(expected,self.holds[k]['selected_v1_5']) if k[1]=='pitcher' else expected
   for m,v in expected.items():self.assertEqual(v,r[m])
 def test_no_holdout_labels_opened_and_holdout_mutation_invariant(self):
  a=argparse.Namespace(**vars(self.a));a.output=self.p/'no_labels'
  original=p.table
  def guard(path):
   if Path(path).name=='holdout_labels.parquet':raise AssertionError('Holdout labels opened')
   return original(path)
  with patch('standalone_combined_v1_4.table',side_effect=guard):p.build(a)
  self.assertEqual(sha(a.output/'homegrown_hitters_2026.csv'),sha(self.p/'release/homegrown_hitters_2026.csv'))
  # New reference manifest with only evaluation labels changed; no forecast field may change.
  q=self.p/'changed_labels';shutil.copytree(self.p/'labels',q);rr=p.table(q/'holdout_labels.parquet')
  for r in rr:
   if r['label_value'] is not None:r['label_value']*=2
  src=q/'temp.json';dump(src,rr);(q/'holdout_labels.parquet').unlink()
  with duckdb.connect() as db:db.read_json(str(src)).write_parquet(str(q/'holdout_labels.parquet'))
  src.unlink();old.refresh(q);a.labels=q;a.output=self.p/'changed_release';p.build(a)
  self.assertEqual(sha(a.output/'coherent_projection_records.json'),sha(self.p/'release/coherent_projection_records.json'))
 def test_prospect_missing_components_and_valuation_adapter(self):
  q=self.p;rr=csvrows(q/'release/exceptions.csv');self.assertTrue(any(r['reason']=='POSSIBLE_COLD_START_OR_PROSPECT_REQUIRES_REVIEW' for r in rr));self.assertTrue(any(r.get('player_id')=='prospect' for r in rr));self.assertTrue(all(r['player_id']!='prospect' for r in load(q/'release/consensus_hitter_valuation_input.json')))
  provenance=csvrows(q/'release/component_provenance.csv');self.assertTrue(any(r.get('component_origin')=='v1.2 saves forecast preserved exactly' for r in provenance));self.assertTrue(all(r.get('forecast_sha256') for r in provenance if r['projection_source']==p.HOME))
 def test_stable_loader_source_choice_and_native_valuation_record_shape(self):
  for source in ['homegrown','consensus']:
   rr=p.load_valuation_source(self.p/'release',source);self.assertTrue(rr)
   self.assertTrue(all('metrics' in r and r['player_id'] and r['season']==2026 for r in rr))
   self.assertEqual({r['projection_source'] for r in rr},{p.HOME if source=='homegrown' else p.CONS})
  self.assertRaises(ValueError,p.load_valuation_source,self.p/'release','blend')
 def test_evaluation_real_warehouse_and_identical_matched_memberships(self):
  q=self.p;r=evaluate(q/'release',q/'labels',self.warehouse,q/'eval',q/'backups');self.assertEqual(tree(q/'eval'),tree(Path(r['backup'])));self.assertFalse(r['selection_changed']);self.assertEqual(r['benchmark_sources'],['OOPSY','Steamer'])
  grouped=defaultdict(set)
  for row in csvrows(q/'eval/matched_benchmark_scores.csv'):grouped[row['player_type'],row['metric'],row['comparison_group']].add((row['n'],row['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in grouped.values()));self.assertEqual(tree(q/'release'),tree(Path(self.report['backup'])))
 def test_inconsistent_consensus_quarantined_all_homegrown_preserved_and_evaluation_runs(self):
  q=self.p;root=q/'inconsistent_consensus';shutil.copytree(self.cons,root)
  hitters=load(root/'hitter_consensus.json');target=next(r for r in hitters if r['player_id']!='prospect');target['metrics']['H']+=2;target_id=target['player_id'];dump(root/'hitter_consensus.json',hitters)
  pitchers=load(root/'pitcher_consensus.json');target_p=pitchers[0];target_p['metrics']['OUTS']=target_p['metrics']['IP']*3+5;pitcher_id=target_p['player_id'];dump(root/'pitcher_consensus.json',pitchers)
  a=argparse.Namespace(**vars(self.a));a.consensus=root;a.output=q/'quarantine_release';before=tree(root);report=p.build(a)
  self.assertEqual(report['quarantined_consensus_rows'],2);self.assertEqual(report['status'],'EXPORTED_WITH_CONSENSUS_QUARANTINE_REVIEW_REQUIRED');self.assertEqual(tree(root),before);self.assertEqual(tree(a.output),tree(Path(report['backup'])))
  issues=csvrows(a.output/'consensus_component_exceptions.csv');h=next(r for r in issues if r['player_type']=='hitter');self.assertAlmostEqual(float(h['H_minus_hit_type_sum']),2);self.assertEqual(h['player_id'],target_id)
  self.assertTrue(any('IP/OUTS' in r['validation_error'] for r in issues))
  for role in p.METRICS:self.assertEqual(sha(a.output/f'homegrown_{role}s_2026.csv'),sha(q/'release'/f'homegrown_{role}s_2026.csv'))
  self.assertEqual(len(load(a.output/'quarantined_consensus_records.json')),2)
  for role,pid in [('hitter',target_id),('pitcher',pitcher_id)]:
   self.assertFalse(any(r['player_id']==pid for r in load(a.output/f'consensus_{role}_valuation_input.json')))
   self.assertTrue(any(r['player_id']==pid and r['coverage_status']=='QUARANTINED_INCOHERENT_SOURCE_COMPONENTS' for r in csvrows(a.output/'draft_pool_coverage.csv') if r['projection_source']==p.CONS and r['player_type']==role))
  for role in p.METRICS:self.assertEqual(sha(root/f'{role}_consensus.json'),sha(a.output/f'source_{role}_consensus.json'))
  result=evaluate(a.output,q/'labels',self.warehouse,q/'quarantine_eval',q/'backups');self.assertFalse(result['forecasts_modified'])
 def test_consensus_pa_bound_quarantined_but_homegrown_coherence_still_strict(self):
  root=self.p/'bad_pa_consensus';shutil.copytree(self.cons,root);rr=load(root/'hitter_consensus.json');target=next(r for r in rr if r['player_id']!='prospect');target['metrics']['PA']=0;dump(root/'hitter_consensus.json',rr)
  a=argparse.Namespace(**vars(self.a));a.consensus=root;a.output=self.p/'bad_pa_release';report=p.build(a);self.assertEqual(report['quarantined_consensus_rows'],1)
  detail=csvrows(a.output/'consensus_component_exceptions.csv')[0];self.assertIn('PA components',detail['validation_error']);self.assertLess(float(detail['PA_minus_component_sum']),0)
  v=dict(PA=10,AB=9,H=3,**{'1B':1,'2B':1,'3B':0,'HR':0},AVG=1/3)
  with self.assertRaises(ValueError):p.coherent('hitter',v)
 def test_signed_label_added_to_full_pipeline_does_not_change_scores_or_projections(self):
  q=self.p;root=q/'signed_labels';shutil.copytree(q/'labels',root);rr=p.table(root/'holdout_labels.parquet')
  # Preserve the native label schema, add a new out-of-scope signed eligible label.
  row=dict(next(r for r in rr if r['player_type']=='pitcher'));row.update(metric='K-BB%',label_value=-.05,eligible=True);rr.append(row)
  source=root/'new.json';dump(source,rr);(root/'holdout_labels.parquet').unlink()
  with duckdb.connect() as db:db.read_json(str(source)).write_parquet(str(root/'holdout_labels.parquet'))
  source.unlink();old.refresh(root);before=tree(q/'release')
  baseline=evaluate(q/'release',q/'labels',self.warehouse,q/'scope_baseline',q/'backups');result=evaluate(q/'release',root,self.warehouse,q/'scope_signed',q/'backups')
  self.assertEqual(result['outside_scope_label_rows'],baseline['outside_scope_label_rows']+1);self.assertEqual(tree(q/'release'),before)
  self.assertEqual(sha(q/'scope_baseline/matched_benchmark_scores.csv'),sha(q/'scope_signed/matched_benchmark_scores.csv'));self.assertEqual(tree(q/'scope_signed'),tree(Path(result['backup'])))
 def test_output_guard_tamper_and_interruption_cleanup(self):
  with self.assertRaises(FileExistsError):p.build(self.a)
  a=argparse.Namespace(**vars(self.a));a.output=self.p/'interrupt'
  with patch('projection_release_v1_11_1.export_tables',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):p.build(a)
  self.assertFalse(a.output.exists());self.assertFalse(list(self.p.glob('interrupt.staging-*')))
  copied=self.p/'tamper';shutil.copytree(self.p/'release',copied);(copied/'homegrown_hitters_2026.csv').write_text('tampered',encoding='utf-8')
  with self.assertRaises(ValueError):evaluate(copied,self.p/'labels',self.warehouse,self.p/'bad_eval',self.p/'backups')

if __name__=='__main__':unittest.main()
