import unittest,itertools,random,json,tempfile,csv
from pathlib import Path
from valuation_math_v1_0 import coherent,sgp,Assignment,allocate_cents
from calibrate_league_sgp_v1_0 import calibrate
from team_category_impact_v1_0 import exact_change
from build_league_valuations_v1_0 import value_players,read_eligibility,positions
from import_valuation_eligibility_v1_0 import map_rows

def brute(records,demands,banned=None,forced=None):
 slots=[g for g,n in demands.items() for _ in range(n)];best=-float('inf')
 def recurse(i,used,total):
  nonlocal best
  if i==len(slots):
   if forced is None or forced in used:best=max(best,total)
   return
  for r in records:
   pid=r['player_id']
   if pid==banned or pid in used or slots[i] not in r['eligible_slots']:continue
   recurse(i+1,used|{pid},total+r['raw_sgp'])
 recurse(0,set(),0);return best

class ValuationTests(unittest.TestCase):
 def test_coherent_rates_and_missing_denominators(self):
  h=coherent('hitter',dict(H=50,AB=200,AVG=.999));self.assertEqual(h['AVG'],.25)
  p=coherent('pitcher',dict(ER=20,IP=50,H=40,BB=10,ERA=99,WHIP=99));self.assertEqual(p['ERA'],3.6);self.assertEqual(p['WHIP'],1)
  self.assertIsNone(coherent('pitcher',dict(ER=0,IP=0,H=0,BB=0))['ERA'])
 def test_rate_contributions_use_exposure_and_favorable_direction(self):
  ref=dict(AVG=.25,ERA=4,WHIP=1.3,team_AB=6000,team_IP=1200);slopes=dict(AVG=.002,ERA=.1,WHIP=.02)
  h=sgp('hitter',dict(H=150,AB=500),slopes,ref,{'AVG':{'kind':'rate'}})
  self.assertAlmostEqual(h['AVG'],25/12)
  p=sgp('pitcher',dict(IP=100,ER=30,H=70,BB=20),slopes,ref,{'ERA':{'kind':'rate'},'WHIP':{'kind':'rate'}})
  self.assertAlmostEqual(p['ERA'],130/120);self.assertAlmostEqual(p['WHIP'],40/24)
 def test_optimal_assignment_margins_match_exhaustive_multi_position_rosters(self):
  for seed in range(6):
   rng=random.Random(seed);records=[]
   for i in range(8):
    slots={'C','UT'} if i<3 else {'OF','UT'} if i<6 else {'P'}
    records.append(dict(player_id=str(i),player_type='pitcher' if i>=6 else 'hitter',eligible_slots=slots,raw_sgp=rng.uniform(-5,25)))
   # Same canonical asset has a second role, never a second draft pick.
   records.append(dict(player_id='0',player_type='pitcher',eligible_slots={'P'},raw_sgp=rng.uniform(-5,25)))
   demands={'C':1,'OF':1,'UT':1,'P':1};a=Assignment(records,demands)
   self.assertAlmostEqual(a.objective,brute(records,demands),places=7)
   margins,alternatives,_=a.margins()
   for pid,r in margins.items():self.assertAlmostEqual(r['sgp_above_replacement'],a.objective-brute(records,demands,banned=pid),places=7)
   for r in alternatives:
    # Role-specific inclusion may differ for a dual-role asset; best role equals forced optimum.
    best=max(x['sgp_above_replacement'] for x in alternatives if x['player_id']==r['player_id'])
    self.assertAlmostEqual(best,brute(records,demands,forced=r['player_id'])-a.objective,places=7)
 def test_unique_multi_eligible_player_and_missing_roster_depth(self):
  rows=[dict(player_id='a',player_type='hitter',eligible_slots={'C','UT'},raw_sgp=10)]
  with self.assertRaisesRegex(ValueError,'depth'):Assignment(rows,{'C':1,'UT':1})
 def test_no_replacement_depth_and_future_position_gains_are_rejected(self):
  rows=[dict(player_id='c',player_type='hitter',eligible_slots={'C'},raw_sgp=10),dict(player_id='a',player_type='hitter',eligible_slots={'OF'},raw_sgp=8),dict(player_id='b',player_type='hitter',eligible_slots={'OF'},raw_sgp=7)]
  a=Assignment(rows,{'C':1,'OF':1})
  with self.assertRaisesRegex(ValueError,'replacement path'):a.margins()
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'elig.csv';p.write_text('player_id,player_type,positions,eligibility_season,eligibility_basis_season,source\np,hitter,OF,2026,2026,NFBC\n')
   with self.assertRaisesRegex(ValueError,'prior season'):read_eligibility(p,2026)

 def test_auction_budget_minimum_bids_and_rounding(self):
  rows=[dict(player_id=str(i),player_type='hitter' if i<3 else 'pitcher',sgp_above_replacement=i/7) for i in range(5)]
  cents,factors,budgets=allocate_cents(rows,2,260,1,.67)
  self.assertEqual(sum(cents.values()),52000);self.assertTrue(all(v>=100 for v in cents.values()))
  self.assertEqual(sum(v for k,v in cents.items() if int(k)<3),34840)
 def test_calibration_rejects_2026_and_in_season_sources(self):
  rows=[dict(season=2025,league_id='L',rank=i,points=4-i,R=400+(4-i)*10,AVG=.24+(4-i)*.001,ERA=4-(4-i)*.1) for i in range(1,4)]
  c=calibrate(rows,3,2026,{'R':{},'AVG':{},'ERA':{}},'Prior league',True)
  self.assertAlmostEqual(c['slopes']['R'],10);self.assertAlmostEqual(c['slopes']['ERA'],.1)
  with self.assertRaisesRegex(ValueError,'full-season'):calibrate(rows,3,2026,{'R':{}},'Source',False)
  for r in rows:r['season']=2026
  with self.assertRaisesRegex(ValueError,'future'):calibrate(rows,3,2026,{'R':{}},'Source',True)
 def test_exact_team_changes_recompute_all_denominators(self):
  h=dict(player_id='h',player_type='hitter',metrics=dict(R=80,HR=20,RBI=80,SB=10,H=150,AB=500));p=dict(player_id='p',player_type='pitcher',metrics=dict(W=10,SV=0,SO=150,H=100,BB=40,ER=50,IP=150))
  h2=dict(player_id='h2',player_type='hitter',metrics=dict(R=80,HR=20,RBI=80,SB=10,H=100,AB=300));slopes={k:1 for k in ['R','HR','RBI','SB','W','SV','K','AVG','ERA','WHIP']}
  d=exact_change([h,p],[h2,p],slopes)
  self.assertAlmostEqual(d['before']['AVG'],.3);self.assertAlmostEqual(d['after']['AVG'],1/3);self.assertEqual(d['after_components']['hitter']['AB'],300)
  self.assertEqual(d['category_sgp_change']['ERA'],0)
 def test_position_mapping_never_guesses_missing_or_ambiguous_players(self):
  self.assertEqual(positions('1B/OF'),{'1B','OF'});self.assertEqual(positions('DH'),{'UT'})
  players=[dict(player_type='hitter',player_id='a',name='Same',mlbam_ids=['1']),dict(player_type='hitter',player_id='b',name='Same',mlbam_ids=['2'])]
  mapped,review=map_rows([{'Name':'Same','Pos':'C'}],players,2026,'NFBC','Name','Pos');self.assertEqual(mapped,[]);self.assertEqual(review[0]['reason'],'AMBIGUOUS')
  mapped,review=map_rows([{'Name':'Same','Pos':'C','MID':'1'}],players,2026,'NFBC','Name','Pos','MID');self.assertEqual(mapped[0]['player_id'],'a')
 def test_end_to_end_reference_pool_replacement_rankings_and_budget(self):
  cfg=json.loads((Path(__file__).parents[1]/'config/valuation_nfbc15_v1_0.json').read_text());cfg.update(teams=2,active_slots={'C':1,'OF':1,'UT':1,'P':1},bench_per_team=1)
  players=[];elig={}
  for typ,number in [('hitter',14),('pitcher',7)]:
   for i in range(number):
    pid=typ+str(i)
    m=dict(PA=450+i*3,AB=400+i*3,H=100+i,BB=30,HBP=2,SF=3,**{'1B':65,'2B':20,'3B':2,'HR':13},R=70+i,RBI=60+i,SB=5+i%3) if typ=='hitter' else dict(IP=80+i*10,ER=30+i*3,H=60+i*7,BB=20+i*2,W=4+i,SV=0 if i>1 else 20-i,SO=90+i*10,HLD=0)
    players.append(dict(player_type=typ,player_id=pid,name=pid,metrics=m));elig[(typ,pid)]={'C'} if typ=='hitter' and i<5 else {'OF'} if typ=='hitter' else {'P'}
  cal=dict(target_season=2026,teams=2,full_season=True,source='Synthetic test only',seasons=[2025],slopes={'R':20,'HR':5,'RBI':20,'SB':5,'AVG':.002,'W':2,'SV':5,'K':30,'ERA':.1,'WHIP':.02})
  ranked,excluded,ref,thresholds,iterations,budgets=value_players(players,cfg,elig,cal)
  active=[r for r in ranked if r['selected']];self.assertEqual(len(active),8);self.assertEqual(len({r['player_id'] for r in ranked}),len(ranked))
  self.assertEqual(sum(round(r['auction_value']*100) for r in ranked),52000);self.assertEqual(sum(r['reserve_selected'] for r in ranked),2)
  self.assertTrue(all(r['auction_value']==0 for r in ranked if not r['selected']))
  self.assertAlmostEqual(ref['team_AB'],sum(r['metrics']['AB'] for r in active if r['player_type']=='hitter')/2)
  for cat in ['AVG','ERA','WHIP']:self.assertAlmostEqual(sum(r['category_sgp'].get(cat,0) for r in active),0,places=7)

if __name__=='__main__':unittest.main()
