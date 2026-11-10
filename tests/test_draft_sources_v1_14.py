import unittest,tempfile,copy,json,argparse,importlib.util,shutil
from pathlib import Path
from unittest.mock import patch
from collections import defaultdict
from standalone_io_v1_0 import load,dump,sha,tree,write,csvrows
import reconciliation_audit_v1_14 as audit
import coverage_priorities_v1_14 as priorities
import entry_branch_v1_14 as branch
import build_draft_sources_v1_14 as b
import draft_source_registry_v1_14 as registry
import build_preseason_coverage_v1_13 as producer
from consensus_policy_v1_13 import POLICY,reconcile,CANDIDATE
from projection_release_v1_11_1 import flat
P=Path(producer.__file__).parent
spec=importlib.util.spec_from_file_location('previous114_fixture',P/'tests/test_preseason_coverage_v1_13.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old)

def fixture_audit(root):
 m=old.hitter();m['1B']-=.5;m['PA']-=.5;original=old.record(m);prov=old.prov(m);result,ledger,case=reconcile(original,prov,POLICY);row=flat(CANDIDATE,'hitter','p1','1','A','KNOWN',['ATH'],result);path=root/'ledger.csv';ph='policyhash'
 for r in ledger:r.update(player_type='hitter',player_id='p1',policy_sha256=ph)
 write(path,ledger,list(ledger[0]));pp={('hitter','p1',n):r for n,r in prov.items()};return [original],[row],path,pp,ph

class AuditTests(unittest.TestCase):
 def test_independent_replay_anchors_caps_ledger_and_maxima(self):
  with tempfile.TemporaryDirectory() as t:
   args=fixture_audit(Path(t));report,summary,fail=audit.audit(*args);self.assertTrue(report['audit_pass']);self.assertFalse(fail);self.assertGreater(report['published_anchor_checks'],0);self.assertEqual(report['material_repair_provenance_checks'],2);self.assertAlmostEqual(next(r['maximum_absolute_delta'] for r in summary if r['metric']=='1B'),.5)
 def test_anchor_change_is_rejected_independent_of_reported_delta(self):
  with tempfile.TemporaryDirectory() as t:
   orig,rows,path,pp,ph=fixture_audit(Path(t));rows[0]['H']+=1;report,summary,fail=audit.audit(orig,rows,path,pp,ph);self.assertFalse(report['audit_pass']);self.assertTrue(any(r['reason']=='PUBLISHED_ANCHOR_NOT_PRESERVED_EXACTLY' for r in fail))
 def test_tampered_delta_and_missing_ledger_row_fail(self):
  with tempfile.TemporaryDirectory() as t:
   args=fixture_audit(Path(t));rr=csvrows(args[2]);rr[0]['delta']='99';write(args[2],rr,list(rr[0]));self.assertFalse(audit.audit(*args)[0]['audit_pass']);write(args[2],rr[1:],list(rr[0]));self.assertTrue(any(r['reason']=='MISSING_LEDGER_ROW' for r in audit.audit(*args)[2]))
 def test_excess_count_change_and_pool_difference_fail(self):
  with tempfile.TemporaryDirectory() as t:
   orig,rows,path,pp,ph=fixture_audit(Path(t));rows[0]['PA']+=2;pp['hitter','p1','H'].update(normalized_weights='{"A":0.5,"B":0.5}',source_values='{"A":25,"B":25}');r,ss,fail=audit.audit(orig,rows,path,pp,ph);self.assertFalse(r['audit_pass']);self.assertTrue(any(x['reason']=='COUNT_CHANGE_OUTSIDE_FIXED_POLICY' for x in fail));self.assertTrue(any(x['reason']=='MATERIAL_REPAIR_CHANGED_SOURCE_POOL_OR_WEIGHTS' for x in fail))

class PriorityTests(unittest.TestCase):
 def row(self,pid,role='hitter',ready=False):return dict(universe_id=role+':'+pid,player_type=role,player_id=pid,mlbam_id=pid,name=pid,preseason_stratum='COLD_START_UNCLASSIFIED_PRESEASON_SOURCE',homegrown_forecast_present=ready,homegrown_basic_valuation_ready=ready,reconciled_candidate_basic_valuation_ready=True,preseason_evidence_present=True)
 def test_ADP_first_then_published_workload_no_actuals(self):
  u=[self.row('1'),self.row('2'),self.row('3',ready=True)];assets=[dict(player_type='hitter',nfbc_player_id=str(i),universe_id='hitter:'+str(i),market_ADP=str(adp)) for i,adp in [(1,20),(2,10),(3,5)]];originals=[dict(player_type='hitter',player_id=str(i),metrics=dict(PA=pa)) for i,pa in [(1,600),(2,100)]];market,non,unknown=priorities.priorities(u,assets,originals,[]);self.assertEqual([x['nfbc_player_id'] for x in market],['2','1']);self.assertEqual(market[0]['projected_workload'],100);self.assertTrue(all(x['workload_source']=='ORIGINAL_PUBLISHED_PRESEASON_CONSENSUS' for x in market))
 def test_unmapped_homegrown_identities_are_excluded_separately(self):
  rows=[dict(player_type='hitter',player_id=None,mlbam_id=str(i),name='Unknown '+str(i),projection_source='HOME',teams='[]') for i in [1,2]]
  players,excluded=registry.eligible_records(rows,'nfbc5x5');self.assertEqual(players,[]);self.assertEqual(len(excluded),2);self.assertTrue(all(r['reason']=='MISSING_CANONICAL_ID' for r in excluded))
 def test_nonmarket_thresholds_do_not_drop_unknown_universe_rows(self):
  u=[self.row('1'),self.row('2','pitcher'),self.row('3')];before=copy.deepcopy(u);original=[dict(player_type='hitter',player_id='1',metrics=dict(PA=100)),dict(player_type='pitcher',player_id='2',metrics=dict(IP=20))];m,n,unknown=priorities.priorities(u,[],original,[]);self.assertEqual(len(n),2);self.assertEqual(len(unknown),1);self.assertEqual(u,before)

class BranchTests(unittest.TestCase):
 def pop(self,y,pid=None):return dict(origin_season=str(y),player_type='hitter',mlbam_id=pid or str(y),branch_class='prospect',as_of_date=f'{y-1}-12-31',date_of_birth='1998-01-01',source='dated-population',source_record_id='p'+str(y),evidence_reference='archive.csv',retrieved_at='2026-11-01T00:00:00Z',vintage_basis='RETROSPECTIVE_EVENT_TIME_ONLY')
 def test_historical_folds_exclude_future_and_2026_retain_2021(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'p.csv';write(p,[self.pop(y) for y in range(2016,2027)],branch.POPULATION);rows,folds,report,w=branch.intake(p);f=next(x for x in folds if x['origin']==2021);self.assertTrue(f['transition_2021_retained']);self.assertIn(2020,json.loads(f['training_population_origins_json']));self.assertTrue(all(y<f['origin'] for y in json.loads(f['training_population_origins_json'])));self.assertTrue(all(2026 not in json.loads(x['training_population_origins_json']) for x in folds));self.assertFalse(report['fit_ready']);self.assertFalse(report['models_fitted'])
 def test_future_metadata_and_outcome_columns_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'p.csv';r=self.pop(2026);r['as_of_date']='2026-03-25';write(p,[r],branch.POPULATION)
   with self.assertRaises(ValueError):branch.intake(p)
   r=self.pop(2026);r['actual_PA']='600';write(p,[r],list(r))
   with self.assertRaises(ValueError):branch.intake(p)
 def test_history_orphans_target_events_fractional_outs_and_blanks(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'p.csv';h=Path(t)/'h.csv';write(p,[self.pop(2021)],branch.POPULATION);r=dict(origin_season='2021',player_type='hitter',mlbam_id='2021',event_season='2020',event_end_date='2020-10-01',as_of_date='2020-12-31',source_type='minor_league',competition='AA',metric='PA',value='',source='minor-archive',source_record_id='s1',evidence_reference='archive.csv',retrieved_at='2026-11-01T00:00:00Z',vintage_basis='RETROSPECTIVE_EVENT_TIME_ONLY');write(h,[r],branch.HISTORY);rows,folds,report,w=branch.intake(p,h);self.assertEqual(next(x for x in folds if x['origin']==2021)['rows_with_numeric_history'],0)
   r['value']='3.1';write(h,[r],branch.HISTORY)
   with self.assertRaises(ValueError):branch.intake(p,h)
   r['value']='3';r['event_season']='2021';r['event_end_date']='2021-01-01';write(h,[r],branch.HISTORY)
   with self.assertRaises(ValueError):branch.intake(p,h)
   r['event_season']='2020';r['event_end_date']='2020-10-01';r['mlbam_id']='999';write(h,[r],branch.HISTORY)
   with self.assertRaises(ValueError):branch.intake(p,h)
 def test_cutoff_override_cannot_be_postseason(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'c.csv';write(p,[dict(origin_season='2021',cutoff_date='2021-12-31',source='claim',evidence_reference='archive')],branch.CUTOFFS)
   with self.assertRaises(ValueError):branch.intake(cutoffs=p)

class Pipeline(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  old.Pipeline.setUpClass();cls.fixture=old.Pipeline;cls.p=cls.fixture.p;q=cls.p;cls.args=argparse.Namespace(source=q/'new113',accepted_release=q/'release',policy=cls.fixture.args.policy,branch_population=None,branch_history=None,branch_context=None,branch_cutoffs=None,output=q/'new114',backup_root=q/'backups');cls.before={n:tree(q/n) for n in ['new113','release','labels','matrix','draft']};cls.report=b.build(cls.args)
 @classmethod
 def tearDownClass(cls):old.Pipeline.tearDownClass()
 def test_promotion_complete_backup_unchanged_home_and_previous_releases(self):
  q=self.p;self.assertTrue(self.report['reconciliation_supported']);self.assertTrue(self.report['ledger_audit']['audit_pass']);self.assertEqual(tree(q/'new114'),tree(Path(self.report['backup'])))
  for n,h in self.before.items():self.assertEqual(tree(q/n),h)
  for role in ['hitter','pitcher']:
   for ext in ['csv','parquet']:self.assertEqual(sha(q/'new114'/f'homegrown_{role}s_2026.{ext}'),sha(q/'release'/f'homegrown_{role}s_2026.{ext}'))
 def test_explicit_source_loader_profiles_and_no_reference_fallback(self):
  root=self.p/'new114'
  for source in ['homegrown','reconciled_consensus']:
   for profile in ['nfbc5x5','yahoo6x6']:
    players,excluded=registry.load_draft_source(root,source,profile);self.assertTrue(players);self.assertEqual(len({r['projection_source'] for r in players}),1)
  with self.assertRaises(ValueError):registry.load_draft_source(root,'original_published_reference')
  with self.assertRaises(ValueError):registry.load_draft_source(root,'blend')
 def test_no_holdout_or_evaluation_opened_no_fit(self):
  args=argparse.Namespace(**vars(self.args));args.output=self.p/'blind114'
  with patch('standalone_io_v1_0.table',side_effect=AssertionError('Label table opened')):r=b.build(args)
  self.assertFalse(r['evaluation_outcomes_read']);self.assertFalse(r['models_fitted']);self.assertEqual(sha(args.output/'nfbc_coverage_priorities.csv'),sha(self.p/'new114/nfbc_coverage_priorities.csv'))
 def test_rehashed_bad_ledger_fails_closed_and_loader_wont_fallback(self):
  q=self.p;source=q/'badproducer113';shutil.copytree(q/'new113',source);path=source/'reconciliation_component_ledger.csv';rows=csvrows(path);rows[0]['delta']='99';write(path,rows,list(rows[0]));freeze=load(source/'forecast_and_universe_freeze.json');freeze[path.name]=sha(path);dump(source/'forecast_and_universe_freeze.json',freeze);(source/'output_sha256.json').unlink();dump(source/'output_sha256.json',tree(source));args=argparse.Namespace(**vars(self.args));args.source=source;args.output=q/'failed114';r=b.build(args);self.assertFalse(r['reconciliation_supported']);self.assertFalse((args.output/'reconciled_consensus_projection_records.json').exists());self.assertTrue(csvrows(args.output/'reconciliation_audit_failures.csv'))
  with self.assertRaises(ValueError):registry.load_draft_source(args.output,'reconciled_consensus')
  self.assertTrue(registry.load_draft_source(args.output,'homegrown')[0])
 def test_existing_output_tamper_and_interrupt_cleanup(self):
  with self.assertRaises(FileExistsError):b.build(self.args)
  args=argparse.Namespace(**vars(self.args));args.output=self.p/'interrupt114'
  with patch('build_draft_sources_v1_14.priorities',side_effect=KeyboardInterrupt):
   with self.assertRaises(KeyboardInterrupt):b.build(args)
  self.assertFalse(args.output.exists());self.assertFalse(list(self.p.glob('interrupt114.staging-*')))
  root=self.p/'badregistry114';shutil.copytree(self.p/'new114',root);(root/'projection_source_registry.json').write_text('{}',encoding='utf-8')
  with self.assertRaises(ValueError):registry.load_draft_source(root,'homegrown')

if __name__=='__main__':unittest.main()
