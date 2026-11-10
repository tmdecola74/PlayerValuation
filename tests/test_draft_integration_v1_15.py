import unittest,tempfile,json,copy,argparse
from pathlib import Path
from unittest.mock import patch
from standalone_io_v1_0 import dump,write,sha,tree,load,csvrows
from projection_release_v1_11_1 import flat,METRICS
import draft_integration_v1_15 as b
import simulate_draft_sources_v1_15 as s
import dc_roster_simulator_v1_3 as sim


def fixture(p):
 root=p/'sources';root.mkdir();assets=[];universe=[];records=[];originals=[];elig=[]
 for role in ['hitter','pitcher']:
  for i in range(4):
   pid=role+str(i);mid=str(100+i+(100 if role=='pitcher' else 0));aid=mid
   m=dict(PA=500,AB=450,H=120,**{'1B':85,'2B':20,'3B':5},HR=10,R=60,RBI=50,SB=10,BB=40,HBP=5,SF=5,SH=0,AVG=120/450,OBP=165/500,SLG=185/450,OPS=.74) if role=='hitter' else dict(IP=150,OUTS=450,H=130,ER=50,BB=40,SO=140,HR=15,W=10,SV=0,HLD=0,QS=15,ERA=3,WHIP=170/150,SV_plus_HLD=0)
   records.append(flat('FROZEN',role,pid,mid,pid,'KNOWN',[],m));originals.append(dict(player_type=role,player_id=pid,metrics=dict(m,GS=25) if role=='pitcher' else m))
   assets.append(dict(nfbc_player_id=aid,player_id=pid,player_type=role,name=pid,positions='P' if role=='pitcher' else 'C',market_ADP=str(int(mid))))
   universe.append(dict(player_type=role,player_id=pid,nfbc_asset_ids_json=json.dumps([aid])))
   elig.append(dict(player_id=pid,player_type=role,positions='P' if role=='pitcher' else 'C',eligibility_season=2026,eligibility_basis_season=2025,source='Frozen NFBC'))
 ap=p/'assets.csv';write(ap,assets,list(assets[0]));dump(root/'preseason_universe.json',universe);dump(root/'original_consensus_records.json',originals);dump(root/'input_hashes.json',{str(ap.resolve()):sha(ap)})
 registry=dict(sources={source:dict(supported=True,record_file=source+'.json') for source in b.SOURCES})
 dump(root/'projection_source_registry.json',registry)
 for source in b.SOURCES:dump(root/(source+'.json'),records)
 dump(root/'source_registry_freeze.json',{n:sha(root/n) for n in ['projection_source_registry.json','homegrown.json','reconciled_consensus.json']});write(root/'nfbc_coverage_priorities.csv',[],['name']);dump(root/'output_sha256.json',tree(root))
 ep=p/'elig.csv';write(ep,elig,list(elig[0]));cfg=dict(league='Tiny NFBC fixture',season=2026,teams=2,active_slots={'C':1,'P':1},bench_per_team=0,auction_budget_per_team=10,minimum_bid=1,hitter_budget_share=.6,minimum_projected_exposure={'hitter':{'AB':1},'pitcher':{'IP':1}},rate_reference_method='historical_calibration',maximum_reference_iterations=5,categories={'hitter':{c:({'kind':'rate'} if c=='AVG' else {'kind':'count','metric':c}) for c in ['R','HR','RBI','SB','AVG']},'pitcher':{c:({'kind':'rate'} if c in ['ERA','WHIP'] else {'kind':'count','metric':'SO' if c=='K' else c}) for c in ['W','SV','K','ERA','WHIP']}})
 cp=p/'profile.json';dump(cp,cfg);cal=p/'cal.json';dump(cal,dict(target_season=2026,teams=2,full_season=True,source='Frozen prior history',seasons=[2023,2024,2025],slopes={c:1 for rr in cfg['categories'].values() for c in rr},rate_reference=dict(AVG=.25,ERA=4,WHIP=1.3,team_AB=500,team_IP=300)))
 args=b.parser().parse_args(['--sources','homegrown','reconciled_consensus']);args.sources_root=root;args.assets=ap;args.eligibility=ep;args.profile=cp;args.calibration=cal;args.output=p/'out';args.backup_root=p/'backups'
 return args,assets,records

class Pipeline(unittest.TestCase):
 def test_native_valuation_both_sources_budget_freeze_backup(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,assets,records=fixture(p);before=tree(a.sources_root);r=b.build(a);self.assertEqual(before,tree(a.sources_root));self.assertEqual(tree(a.output),tree(Path(r['backup'])));self.assertFalse(r['models_fitted']);self.assertFalse(r['evaluation_outcomes_read'])
   for x in r['sources']:
    self.assertEqual(x['ranked_players'],8);self.assertEqual(sum(x['budget_cents'].values()),2000)
   self.assertEqual(r['sources'][0]['missing_role_rows'],4);self.assertEqual(r['sources'][1]['missing_role_rows'],0)
   p1=load(a.output/'homegrown/simulation_pool.json');self.assertTrue(all(not x['known'] for x in p1 if x['player_type']=='pitcher'));self.assertFalse(r['branch']['fit_ready']);self.assertTrue((a.output/'coverage_branch/historical_collection_plan.csv').exists())
 def test_source_specific_roles_enable_homegrown_without_changing_stats(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,assets,records=fixture(p);rp=p/'roles.csv';rows=[dict(projection_source_choice='homegrown',player_id=x['player_id'],GS=25,as_of_date='2026-03-24',source='Frozen home role forecast',evidence_reference='frozen GS archive',vintage_basis='USER_CONFIRMED_PRESEASON_EFFECTIVE') for x in assets if x['player_type']=='pitcher'];write(rp,rows,b.ROLE_FIELDS);a.roles=rp;r=b.build(a);self.assertEqual(r['sources'][0]['simulation_known'],8)
   pool=load(a.output/'homegrown/simulation_pool.json');lookup={r['player_id']:r for r in records}
   for x in pool:
    for m in METRICS[x['player_type']]:
     if m in x and m in lookup[x['player_id']] and m not in ['OPS','OBP','SLG']:self.assertAlmostEqual(x[m],lookup[x['player_id']][m])
 def test_stale_market_identity_or_tamper_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,assets,rec=fixture(p);assets[0]['player_id']='other';write(a.assets,assets,list(assets[0]))
   with self.assertRaises(ValueError):b.build(a)
   self.assertFalse(a.output.exists())
 def test_new_output_and_interrupt_cleanup(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,_,_=fixture(p)
   with patch.object(b,'prepare_branch',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):b.build(a)
   self.assertFalse(a.output.exists());self.assertFalse(list(p.glob('out.staging-*')));b.build(a)
   with self.assertRaises(FileExistsError):b.build(a)
 def test_unsupported_source_no_fallback(self):
  with tempfile.TemporaryDirectory() as t:
   a,_,_=fixture(Path(t));a.sources=['blend']
   with self.assertRaises(ValueError):b.build(a)
 def test_independent_insufficient_depth_is_reported(self):
  with tempfile.TemporaryDirectory() as t:
   a,_,_=fixture(Path(t));cfg=load(a.profile);cfg['active_slots']['C']=3;dump(a.profile,cfg);r=b.build(a);self.assertTrue(all(x['status']=='INSUFFICIENT_SOURCE_ROSTER_DEPTH' for x in r['sources']))
 def test_simulation_blocked_pool_is_backed_up(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,_,_=fixture(p);b.build(a);h=p/'history.csv';history(h);sa=s.parser().parse_args(['--sources','homegrown','reconciled_consensus']);sa.integration=a.output;sa.historical=h;sa.output=p/'sim';sa.backup_root=p/'backups';r=s.build(sa);self.assertEqual(r['simulations'],0);self.assertTrue(all(x['status']=='BLOCKED_INPUTS' for x in r['statuses']));self.assertEqual(tree(sa.output),tree(Path(r['backup'])))

def history(p):
 rows=[dict(season=2025,IP=1200,AB=7000,**{c:(1.2 if c=='WHIP' else 3.7 if c=='ERA' else .26 if c=='AVG' else 100) for c in sim.CATS})];write(p,rows,list(rows[0]))

class Units(unittest.TestCase):
 def test_role_future_and_cross_source_validation(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'roles.csv';row=dict(projection_source_choice='homegrown',player_id='p1',GS=20,as_of_date='2026-03-25',source='frozen',evidence_reference='archive',vintage_basis='USER_CONFIRMED_PRESEASON_EFFECTIVE');write(p,[row],b.ROLE_FIELDS)
   with self.assertRaises(ValueError):b.role_inputs(p)
   row['as_of_date']='2026-03-24';write(p,[row],b.ROLE_FIELDS);roles,w=b.role_inputs(p);self.assertIn(('homegrown','p1'),roles);self.assertNotIn(('reconciled_consensus','p1'),roles)
 def test_native_simulator_ratios_and_multi_position(self):
  players=[]
  for i,slot in enumerate(sim.SLOTS):
   role='pitcher' if slot=='P' else 'hitter';p=dict(id=str(i),player_id=str(i),name=str(i),player_type=role,known=True,raw=1,value=1,slots={slot},R=50,HR=10,RBI=40,SB=5,AB=400,H=100,W=10,SV=20,SO=120,IP=150,ER=50,BB=40,GS=25)
   if slot in ['1B','CI']:p['slots']|={'1B','CI','UT'}
   players.append(p)
  chosen,short=sim.lineup(players);self.assertEqual(short,0);tot=sim.totals(chosen);self.assertEqual(tot['AVG'],.25);self.assertEqual(tot['ERA'],3);self.assertAlmostEqual(tot['WHIP'],140/150)
 def test_history_2026_forbidden(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'history.csv';history(p);rr=csvrows(p);rr[0]['season']='2026';write(p,rr,list(rr[0]));
   with self.assertRaises(ValueError):sim.History(p)
 def test_known_unknown_market_assets_never_zero_filled(self):
  assets=[dict(nfbc_player_id='1',player_id='p1',player_type='hitter',name='No forecast',market_ADP=100)];pool,ex=b.pool_from_values([],assets,None,{('hitter','p1'):{'C'}},{},'homegrown');self.assertEqual(len(pool),1);self.assertFalse(pool[0]['known']);self.assertNotIn('HR',pool[0]);self.assertEqual(ex[0]['reason'],'NO_VALUED_PROJECTION_IN_SELECTED_SOURCE')

if __name__=='__main__':unittest.main()

class SourceIsolation(unittest.TestCase):
 def test_unsupported_component_does_not_borrow_other_source(self):
  with tempfile.TemporaryDirectory() as t:
   a,assets,rec=fixture(Path(t));root=Path(a.sources_root);home=load(root/'homegrown.json');home[0]['HR']=None;dump(root/'homegrown.json',home);freeze=load(root/'source_registry_freeze.json');freeze['homegrown.json']=sha(root/'homegrown.json');dump(root/'source_registry_freeze.json',freeze);(root/'output_sha256.json').unlink();dump(root/'output_sha256.json',tree(root));r=b.build(a);self.assertEqual(r['sources'][0]['source_exclusions'],1);self.assertEqual(r['sources'][1]['source_exclusions'],0);self.assertEqual(r['sources'][1]['ranked_players'],8)
 def test_simulator_pairing_and_same_market_order_adapter(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,assets,rec=fixture(p);b.build(a)
   # Wrapper orchestration fixture: native v1.3 solver is tested separately.
   for source in b.SOURCES:
    vp=a.output/source/'valuation_context.json';vc=load(vp);vc['profile'].update(teams=15,active_slots={x:sim.SLOTS.count(x) for x in set(sim.SLOTS)},bench_per_team=27);dump(vp,vc)
    cp=a.output/source/'coverage_report.json';cov=load(cp);cov['missing_role_rows']=0;dump(cp,cov);pool=[dict(id=str(i),slots=['P'],known=False,adp=i+1,player_type='pitcher',name=str(i)) for i in range(750)];dump(a.output/source/'simulation_pool.json',pool)
   (a.output/'output_sha256.json').unlink();dump(a.output/'output_sha256.json',tree(a.output));hp=p/'history.csv';history(hp);sa=s.parser().parse_args(['--sources','homegrown','reconciled_consensus']);sa.integration=a.output;sa.historical=hp;sa.output=p/'sim';sa.backup_root=p/'backups';calls=[]
   def fake(players,hist,seed,seat,strategy):
    calls.append((seed,seat,strategy,[p['id'] for p in players]));return dict(seed=seed,seat=seat+1,strategy=strategy,all_constraints_pass=True,**{c:100 for c in sim.CATS}),[],[],[]
   with patch.object(s.sim,'draft',side_effect=fake),patch.object(s.sim,'production_reports',return_value=([],[],[])),patch.object(s.sim,'reserve_stress',return_value=[]),patch.object(s.sim,'save_depth_roster',return_value=[]),patch.object(s.sim,'closer_acquisitions',return_value=[]):r=s.build(sa)
   self.assertEqual(r['simulations'],4);self.assertEqual(r['paired_source_rows'],2);self.assertEqual(calls[:2],calls[2:]);self.assertFalse(r['evaluation_outcomes_read'])

class FrozenBridgeFix(unittest.TestCase):
 def test_blank_asset_id_resolves_only_with_exact_frozen_evidence(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,assets,rec=fixture(p);u=load(Path(a.sources_root)/'preseason_universe.json');u[0].update(universe_id='hitter:hitter0',mlbam_id='100');dump(Path(a.sources_root)/'preseason_universe.json',u);assets[0].update(player_id='',mlbam_id='100',universe_id='hitter:hitter0');resolved,audit=b.resolve_market_assets(a.sources_root,assets);self.assertEqual(resolved[0]['player_id'],'hitter0');self.assertEqual(assets[0]['player_id'],'');self.assertEqual(audit[0]['resolution_method'],'FROZEN_NFBC_MEMBERSHIP_AND_EXACT_MLBAM_BRIDGE')
   assets[0]['mlbam_id']='999'
   with self.assertRaises(ValueError):b.resolve_market_assets(a.sources_root,assets)
 def test_name_or_universe_index_alone_cannot_resolve(self):
  with tempfile.TemporaryDirectory() as t:
   a,assets,rec=fixture(Path(t));assets[0]['player_id']=''
   with self.assertRaises(ValueError):b.resolve_market_assets(a.sources_root,assets)
   assets[0].update(player_id='wrong',name='hitter0',mlbam_id='100',universe_id='hitter:hitter0')
   with self.assertRaises(ValueError):b.resolve_market_assets(a.sources_root,assets)
 def test_production_shape_bridge_pipeline_preserves_reference_and_backup(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a,assets,rec=fixture(p);root=Path(a.sources_root);u=load(root/'preseason_universe.json');u[0].update(universe_id='hitter:hitter0',mlbam_id='100');dump(root/'preseason_universe.json',u);assets[0].update(player_id='',mlbam_id='100',universe_id='hitter:hitter0');fields=list(dict.fromkeys(k for r in assets for k in r));write(a.assets,assets,fields);dump(root/'input_hashes.json',{str(Path(a.assets).resolve()):sha(a.assets)});(root/'output_sha256.json').unlink();dump(root/'output_sha256.json',tree(root));before=tree(root);source_sha=sha(a.assets);r=b.build(a);self.assertEqual(r['frozen_market_identity_bridges'],1);self.assertEqual(before,tree(root));self.assertEqual(source_sha,sha(a.assets));self.assertEqual(tree(a.output),tree(Path(r['backup'])))
 def test_unmapped_and_duplicate_memberships_stay_explicit(self):
  with tempfile.TemporaryDirectory() as t:
   a,assets,rec=fixture(Path(t));u=load(Path(a.sources_root)/'preseason_universe.json');u[0]['player_id']=None;assets[0]['player_id']='';dump(Path(a.sources_root)/'preseason_universe.json',u);r,audit=b.resolve_market_assets(a.sources_root,assets);self.assertIsNone(r[0]['player_id']);self.assertIsNone(audit[0]['resolved_player_id'])
   with self.assertRaises(ValueError):b.resolve_market_assets(a.sources_root,assets+[assets[0]])

class TwoWayAssetFix(unittest.TestCase):
 def test_repeated_nfbc_id_two_roles_selects_only_valued_canonical_role(self):
  assets=[dict(nfbc_player_id='1',player_type=role,player_id='same',name='Two way',market_ADP='5') for role in ['hitter','pitcher']];ranked=[dict(player_type='pitcher',player_id='same')];unique,excluded=b.unique_market_assets(assets,ranked);self.assertEqual(len(unique),1);self.assertEqual(unique[0]['player_type'],'pitcher');self.assertEqual(excluded[0]['reason'],'TWO_WAY_NONSELECTED_ROLE_ONE_NFBC_ASSET')
 def test_repeated_nfbc_id_conflicts_and_both_selected_rejected(self):
  assets=[dict(nfbc_player_id='1',player_type=role,player_id='same',name='Two way',market_ADP='5') for role in ['hitter','pitcher']]
  with self.assertRaises(ValueError):b.unique_market_assets(assets,[dict(player_type=r,player_id='same') for r in ['hitter','pitcher']])
  assets[1]['player_id']='different'
  with self.assertRaises(ValueError):b.unique_market_assets(assets,[])
 def test_two_way_without_forecast_is_explicit_not_guessed(self):
  assets=[dict(nfbc_player_id='1',player_type=role,player_id='same',name='Two way',market_ADP='5') for role in ['hitter','pitcher']];unique,ex=b.unique_market_assets(assets,[]);self.assertFalse(unique);self.assertEqual(len(ex),2)
 def test_frozen_domain_allows_same_nfbc_id_for_two_distinct_role_rows(self):
  with tempfile.TemporaryDirectory() as t:
   a,assets,rec=fixture(Path(t));root=Path(a.sources_root);u=load(root/'preseason_universe.json');u[4].update(player_id=u[0]['player_id'],nfbc_asset_ids_json=u[0]['nfbc_asset_ids_json']);assets[4].update(player_id=assets[0]['player_id'],nfbc_player_id=assets[0]['nfbc_player_id']);dump(root/'preseason_universe.json',u);resolved,audit=b.resolve_market_assets(root,assets);self.assertEqual(len(resolved),8);self.assertEqual(resolved[0]['nfbc_player_id'],resolved[4]['nfbc_player_id'])
