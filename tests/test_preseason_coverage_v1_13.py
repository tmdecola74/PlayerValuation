import unittest,tempfile,copy,json,importlib.util,argparse,shutil,csv
from pathlib import Path
from collections import defaultdict
from unittest.mock import patch
import duckdb
from standalone_io_v1_0 import load,dump,tree,sha,csvrows,write,table
import consensus_policy_v1_13 as policy
import preseason_universe_v1_13 as universe
import build_preseason_coverage_v1_13 as b
import evaluate_preseason_coverage_v1_13 as e
import projection_release_v1_11_1 as release
from projection_release_audit_v1_12 import labels_index
P=Path(release.__file__).parent
spec=importlib.util.spec_from_file_location('previous113_fixture',P/'tests/test_projection_release_v1_11_1.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)
ROOT=Path(__file__).resolve().parents[1]

def hitter():return dict(PA=100,AB=90,H=25,**{'1B':17,'2B':5,'3B':1,'HR':2},BB=6,HBP=1,SF=2,SH=1,R=10,RBI=10,SB=0,AVG=25/90,OBP=32/99,SLG=38/90,OPS=32/99+38/90)
def prov(metrics,weights=None):
 return {m:dict(method='weighted_available_source_mean',normalized_weights=json.dumps(weights or {'A':1}),source_values=json.dumps({s:v for s in (weights or {'A':1})})) for m,v in metrics.items() if v is not None}
def record(metrics,role='hitter'):return dict(season=2026,player_type=role,player_id='p1',name='A',metrics=metrics)

class PolicyTests(unittest.TestCase):
 def test_single_reconciliation_anchors_full_ledger_and_no_original_mutation(self):
  m=hitter();m['1B']=16.5;original=copy.deepcopy(m);out,ledger,case=policy.reconcile(record(m),prov(m),policy.POLICY)
  self.assertEqual(case['status'],'CANDIDATE_AVAILABLE');self.assertEqual(out['1B'],17);self.assertEqual(m,original);self.assertEqual(out['H'],25);self.assertEqual(out['HR'],2);self.assertEqual(out['AB'],90);self.assertEqual(out['SB'],0);self.assertAlmostEqual(out['AVG'],25/90)
  entry=next(r for r in ledger if r['metric']=='1B');self.assertEqual(entry['original_value'],16.5);self.assertEqual(entry['delta'],.5);self.assertTrue(entry['changed'])
 def test_PA_deficit_and_positive_remainder(self):
  m=hitter();m['PA']=99.5;out,ledger,case=policy.reconcile(record(m),prov(m),policy.POLICY);self.assertEqual(out['PA'],100);self.assertTrue(any(r['metric']=='PA' and r['delta']==.5 for r in ledger))
  m['PA']=101;out,_,_=policy.reconcile(record(m),prov(m),policy.POLICY);self.assertEqual(out['PA'],101)
 def test_caps_negative_single_and_source_pool_or_missing_evidence_quarantine(self):
  m=hitter();m['1B']=15;self.assertIsNone(policy.reconcile(record(m),prov(m),policy.POLICY)[0])
  m=hitter();m['H']=1;self.assertIn('NEGATIVE_DERIVED_SINGLE',policy.reconcile(record(m),prov(m),policy.POLICY)[2]['reason'])
  m=hitter();m['PA']=98;self.assertIn('CAP',policy.reconcile(record(m),prov(m),policy.POLICY)[2]['reason'])
  m=hitter();m['1B']=16.5;self.assertIsNone(policy.reconcile(record(m),{},policy.POLICY)[0])
  pp=prov(m);pp['H']=dict(method='weighted_available_source_mean',normalized_weights='{"A":0.5,"B":0.5}',source_values='{"A":25,"B":25}');self.assertIsNone(policy.reconcile(record(m),pp,policy.POLICY)[0])
 def test_pitcher_saves_holds_and_missing_not_zero(self):
  m=dict(IP=100,H=90,BB=30,ER=40,SO=100,HR=10,W=8,SV=0,HLD=5,QS=10,ERA=3.6,WHIP=1.2);out,_,_=policy.reconcile(record(m,'pitcher'),{},policy.POLICY);self.assertEqual(out['SV'],0);self.assertEqual(out['HLD'],5);self.assertEqual(out['SV_plus_HLD'],5)
  m['HLD']=None;out,_,_=policy.reconcile(record(m,'pitcher'),{},policy.POLICY);self.assertIsNone(out['HLD']);self.assertIsNone(out['SV_plus_HLD'])
 def test_numerical_cancellation_preserves_zero_single_without_clipping(self):
  m=hitter();m.update(H=.3,**{'1B':0.,'2B':.1,'3B':.1,'HR':.1});out,ledger,case=policy.reconcile(record(m),prov(m),policy.POLICY);self.assertIsNotNone(out);self.assertEqual(out['1B'],0);self.assertEqual(out['H'],.3)
 def test_policy_tamper_rejected(self):
  pp=dict(policy.POLICY,max_PA_increase=10)
  with self.assertRaises(ValueError):policy.reconcile(record(hitter()),{},pp)

class UniverseTests(unittest.TestCase):
 def test_preseason_coldstarts_included_and_historical_only_not_active(self):
  original=[record(hitter())];features=[];training=[dict(season=2021,player_type='pitcher',mlbam_id='2')];assets=[dict(player_type='hitter',player_id=None,mlbam_id=None,nfbc_player_id='123',name='No mapping')]
  rows,ac,er=universe.assemble_universe(original,[],[],assets,training,features,{'p1':'1','p2':'2'},{'p1':'A','p2':'B'},[]);d={r['universe_id']:r for r in rows};self.assertEqual(d['hitter:p1']['preseason_stratum'],'COLD_START_UNCLASSIFIED_PRESEASON_SOURCE');self.assertFalse(d['pitcher:p2']['preseason_evidence_present']);self.assertEqual(d['hitter:NFBC:123']['preseason_stratum'],'IDENTITY_UNRESOLVED');self.assertEqual(len(ac),1)
 def test_dated_prospect_and_international_schema_and_future_rejection(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'e.csv';row=dict(zip(universe.EVIDENCE_FIELDS,['2026','hitter','p1','1','A','prospect','2026-03-24','2026-03-23','USER_CONFIRMED_PRESEASON_EFFECTIVE','Preseason list','r1','frozen-list.csv','']))
   write(p,[row],universe.EVIDENCE_FIELDS);rr,w=universe.dated_evidence(p,{'p1':'1'},{'p1':'A'});self.assertEqual(rr[0]['preseason_class'],'prospect')
   row['preseason_class']='international_arrival';write(p,[row],universe.EVIDENCE_FIELDS);self.assertEqual(universe.dated_evidence(p,{'p1':'1'},{'p1':'A'})[0][0]['preseason_class'],'international_arrival')
   row['evidence_as_of']='2026-04-01';write(p,[row],universe.EVIDENCE_FIELDS)
   with self.assertRaises(ValueError):universe.dated_evidence(p,{'p1':'1'},{'p1':'A'})
   row['evidence_as_of']='2026-03-23';row['actual_PA']='600';write(p,[row],list(row))
   with self.assertRaises(ValueError):universe.dated_evidence(p,{'p1':'1'},{'p1':'A'})
 def test_target_outcomes_forbidden_and_unseen_actuals_not_added(self):
  with self.assertRaises(ValueError):universe.assemble_universe([],[],[],[],[dict(season=2026,player_type='hitter',mlbam_id='1')],[],{}, {},[])
  features=[dict(target_season=2026,player_type='hitter',mlbam_id='1',max_source_season=2025,source_cutoff='2025-12-31',y_PA=100)]
  with self.assertRaises(ValueError):universe.assemble_universe([],[],[],[],[],features,{}, {},[])
  original=[];before=copy.deepcopy(original);actual=labels_index([dict(season=2026,player_type='hitter',mlbam_id='999',metric='PA',eligible=True,label_value=500)],2026,2026);rows=e.universe_evaluation(original,[],actual);self.assertEqual(original,before);self.assertEqual(rows[0]['preseason_universe_status'],'ABSENT_FROM_FROZEN_PRESEASON_UNIVERSE')
 def test_matched_scores_cohort_boundaries_and_zero_labels(self):
  actual=labels_index([dict(season=2026,player_type='pitcher',mlbam_id='1',metric=m,eligible=True,label_value=v) for m,v in [('IP',40),('ERA',3),('SV',0)]],2026,2026);f={('pitcher','1',m,s):(v,'r') for m,v in [('IP',42),('ERA',3.5),('SV',0)] for s in [e.HOME,e.CANDIDATE,'Steamer']};ss,cc,n=e.score_forecasts(f,actual)
  group=[r for r in ss if r['metric']=='ERA' and r['cohort']=='IP_GE40' and r['comparison_group']=='Steamer_homegrown_candidate_common'];self.assertEqual({r['n'] for r in group},{1});self.assertEqual(len({r['membership_sha256'] for r in group}),1)
  z=next(r for r in ss if r['metric']=='SV' and r['projection_source']==e.HOME and r['comparison_group']=='homegrown_all');self.assertEqual(z['mae'],0)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  old.Pipeline.setUpClass();cls.fixture=old.Pipeline;cls.p=cls.fixture.p;q=cls.p
  from evaluate_projection_release_v1_11_2 import evaluate
  evaluate(q/'release',q/'labels',cls.fixture.warehouse,q/'eval113source',q/'backups')
  cls.args=argparse.Namespace(run=q/'release',labels=q/'labels',matrix=q/'matrix',warehouse=cls.fixture.warehouse,draft_inputs=cls.fixture.market,policy=ROOT/'config/consensus_reconciliation_v1_13.json',preseason_evidence=None,output=q/'new113',backup_root=q/'backups')
  cls.before={n:tree(q/n) for n in ['release','labels','matrix','draft','eval113source']};cls.report=b.build(cls.args)
 @classmethod
 def tearDownClass(cls):old.Pipeline.tearDownClass()
 def test_full_build_preserves_homegrown_originals_and_complete_backup(self):
  q=self.p
  for n,h in self.before.items():self.assertEqual(tree(q/n),h)
  self.assertEqual(tree(q/'new113'),tree(Path(self.report['backup'])));self.assertFalse(self.report['evaluation_outcomes_read']);self.assertFalse(self.report['candidate_adopted']);self.assertEqual(len(load(q/'new113/original_consensus_records.json')),self.report['original_consensus_rows'])
  for role in release.METRICS:
   for ext in ['csv','parquet']:self.assertEqual(sha(q/'new113'/f'homegrown_{role}s_2026.{ext}'),sha(q/'release'/f'homegrown_{role}s_2026.{ext}'))
   self.assertEqual(sha(q/'new113'/f'original_{role}_consensus.json'),sha(q/'release'/f'source_{role}_consensus.json'))
 def test_build_never_opens_holdout_labels_or_2026_evaluation(self):
  args=argparse.Namespace(**vars(self.args));args.output=self.p/'no_target113';read=b.table
  def guard(path):
   if Path(path).name=='holdout_labels.parquet':raise AssertionError('Target label opened')
   return read(path)
  with patch('build_preseason_coverage_v1_13.table',side_effect=guard):b.build(args)
  self.assertEqual(sha(args.output/'preseason_universe.json'),sha(self.p/'new113/preseason_universe.json'));self.assertEqual(sha(args.output/'candidate_projection_records.json'),sha(self.p/'new113/candidate_projection_records.json'))
 def test_holdout_mutation_cannot_change_universe_or_candidate(self):
  q=self.p;root=q/'labels';saved=q/'saved_labels113';shutil.copytree(root,saved)
  try:
   rr=table(root/'holdout_labels.parquet')
   for r in rr:
    if r['label_value'] is not None:r['label_value']*=10
   src=root/'new.json';dump(src,rr);(root/'holdout_labels.parquet').unlink()
   with duckdb.connect() as db:db.read_json(str(src)).write_parquet(str(root/'holdout_labels.parquet'))
   src.unlink();old.old.refresh(root);args=argparse.Namespace(**vars(self.args));args.output=q/'changed113';b.build(args)
   for n in ['preseason_universe.json','candidate_projection_records.json']:self.assertEqual(sha(args.output/n),sha(q/'new113'/n))
  finally:shutil.rmtree(root);shutil.copytree(saved,root)
 def test_separate_evaluation_preserves_universe_identical_pools_and_backup(self):
  q=self.p;before=tree(q/'new113');r=e.evaluate(q/'new113',q/'eval113source',q/'labels',q/'eval113',q/'backups');self.assertEqual(tree(q/'new113'),before);self.assertEqual(tree(q/'eval113'),tree(Path(r['backup'])));self.assertFalse(r['candidate_adopted']);self.assertFalse(r['universe_modified'])
  groups=defaultdict(set)
  for row in csvrows(q/'eval113/exposure_cohort_scores.csv'):groups[row['metric'],row['cohort'],row['comparison_group']].add((row['n'],row['membership_sha256']))
  self.assertTrue(all(len(v)==1 for v in groups.values()))
 def test_recovered_consensus_case_preserves_original_and_scores_published_reference(self):
  q=self.p;source=q/'recovery_consensus';shutil.copytree(self.fixture.cons,source);rr=load(source/'hitter_consensus.json');target=next(r for r in rr if r['player_id']!='prospect' and r['metrics']['1B']>.25);pid=target['player_id'];target['metrics']['1B']-=.25;m=target['metrics'];m['SLG']=(m['1B']+2*m['2B']+3*m['3B']+4*m['HR'])/m['AB'];m['OPS']=m['OBP']+m['SLG'];dump(source/'hitter_consensus.json',rr)
  pp=csvrows(source/'metric_provenance.csv')
  for row in pp:
   if row['player_type']=='hitter' and row['player_id']==pid:
    metric=row['metric'];row.update(method='weighted_available_source_mean',normalized_weights='{"A":1}',source_values=json.dumps({'A':m[metric]}),consensus=m[metric])
  write(source/'metric_provenance.csv',pp,list(dict.fromkeys(k for row in pp for k in row)))
  orig_args=argparse.Namespace(**vars(self.fixture.a));orig_args.consensus=source;orig_args.output=q/'recovery_release';release.build(orig_args)
  args=argparse.Namespace(**vars(self.args));args.run=orig_args.output;args.output=q/'recovered113';before=tree(source);report=b.build(args)
  self.assertEqual(report['recovered_original_quarantine'],1);self.assertEqual(tree(source),before)
  adjustment=next(r for r in csvrows(args.output/'reconciliation_adjustments.csv') if r['player_id']==pid and r['player_type']=='hitter' and r['metric']=='1B');self.assertAlmostEqual(float(adjustment['delta']),.25)
  originals=load(args.output/'original_consensus_records.json');self.assertEqual(next(r['metrics']['1B'] for r in originals if r['player_type']=='hitter' and r['player_id']==pid),m['1B'])
  from evaluate_projection_release_v1_11_2 import evaluate
  evaluate(orig_args.output,q/'labels',self.fixture.warehouse,q/'recovery_original_eval',q/'backups');e.evaluate(args.output,q/'recovery_original_eval',q/'labels',q/'recovered113eval',q/'backups')
  scores=[r for r in csvrows(q/'recovered113eval/matched_scores.csv') if r['player_type']=='hitter' and r['metric']=='1B' and r['comparison_group']=='published_vs_reconciled_matched'];self.assertTrue(all(int(r['n'])>0 for r in scores));self.assertEqual({r['projection_source'] for r in scores},{e.PUBLISHED,e.CANDIDATE});self.assertEqual(len({r['membership_sha256'] for r in scores}),1)
 def test_output_guard_tamper_and_interrupt(self):
  with self.assertRaises(FileExistsError):b.build(self.args)
  args=argparse.Namespace(**vars(self.args));args.output=self.p/'interrupted113'
  with patch('build_preseason_coverage_v1_13.assemble_universe',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):b.build(args)
  self.assertFalse(args.output.exists());self.assertFalse(list(self.p.glob('interrupted113.staging-*')))
  root=self.p/'tampered113';shutil.copytree(self.p/'new113',root);(root/'preseason_universe.json').write_text('[]',encoding='utf-8')
  with self.assertRaises(ValueError):e.evaluate(root,self.p/'eval113source',self.p/'labels',self.p/'bad_eval113',self.p/'backups')

if __name__=='__main__':unittest.main()
