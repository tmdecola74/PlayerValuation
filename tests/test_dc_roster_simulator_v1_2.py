import unittest
from dc_roster_simulator_v1_2 import (SLOTS,lineup,constrained_lineup,completion_plan,robust_coverage,pitching_choice,totals,production_reports,baseline_comparison)

def player(i,slots,typ='hitter',raw=1,ip=150):
 slots=set(slots)
 if typ=='hitter':
  slots.add('UT')
  if slots&{'1B','3B'}:slots.add('CI')
  if slots&{'2B','SS'}:slots.add('MI')
 return dict(id=str(i),name=str(i),adp=100+i,slots=set(slots),known=True,raw=raw,value=raw,player_type=typ,R='1',HR='1',RBI='1',SB='1',AB='100',PA='110',H='25',W='1',SV='0',SO='10',IP=str(ip),ER='4',BB='3',GS='20')
def covered():
 r=[player(i,[s],typ='pitcher' if s=='P' else 'hitter') for i,s in enumerate(SLOTS)]
 for i,s in enumerate(['C','1B','2B','3B','SS','OF','P'],30):r.append(player(i,[s],typ='pitcher' if s=='P' else 'hitter'))
 return r
class ConstraintTests(unittest.TestCase):
 def test_independent_innings_constraint_changes_pitching_selection(self):
  r=covered()
  for p in r:
   if p['player_type']=='pitcher':p['IP']='50';p['raw']=20
  r.extend(player(i,['P'],typ='pitcher',raw=1,ip=180) for i in range(60,69))
  old,_=lineup(r);self.assertLess(totals(old)['IP'],950)
  active,missing,ok=constrained_lineup(r)
  self.assertTrue(ok);self.assertEqual(missing,0);self.assertEqual(sum(s=='P' for s,p in active),9)
  self.assertGreaterEqual(totals(active)['IP'],950)
 def test_infeasible_innings_not_fabricated(self):
  r=covered()
  for p in r:
   if p['player_type']=='pitcher':p['IP']='50'
  self.assertIsNone(pitching_choice(r));self.assertFalse(constrained_lineup(r)[2])
 def test_completion_plan_repairs_catcher_gap_with_actual_pick(self):
  r=covered();r=[p for p in r if p['id']!='30']
  self.assertFalse(robust_coverage(r))
  q=player(90,['C']);plan=completion_plan(r,[q])
  self.assertEqual([p['id'] for p in plan],['90']);self.assertTrue(robust_coverage(r+plan))
 def test_market_only_catcher_cannot_hide_missing_production(self):
  r=[p for p in covered() if p['id']!='30'];q=player(90,['C']);q['known']=False
  self.assertIsNone(completion_plan(r,[q]))
 def test_multi_position_reassignment_not_fixed_position_counts(self):
  r=covered();r=[p for p in r if p['id'] not in ['31','32','33','34','35']]
  # Flexible reserves support any single loss through reassignments.
  r.append(player(90,['1B','2B','3B','SS','OF','CI','MI','UT']))
  self.assertTrue(robust_coverage(r));self.assertEqual(completion_plan(r,[]),[])
 def test_same_reserve_cannot_fill_two_holes(self):
  r=covered();r=[p for p in r if 'C' not in p['slots']]
  r.append(player(90,['C','OF']))
  self.assertFalse(robust_coverage(r));self.assertIsNone(completion_plan(r,[]))
 def test_reserve_metrics_not_added_to_active(self):
  r=covered();logs=[dict(seed=1,seat=1,team=1,strategy='value',nfbc_player_id=p['id']) for p in r]
  pitching,reserves,inventory=production_reports(r,logs)
  self.assertEqual(pitching[0]['active_IP'],1350)
  self.assertEqual(reserves[0]['reserve_IP'],150)
  self.assertEqual(len(inventory),7)
 def test_complete_roster_needs_no_repair_and_does_not_mutate(self):
  r=covered();before=[p['id'] for p in r]
  self.assertEqual(completion_plan(r,[]),[]);self.assertEqual(before,[p['id'] for p in r])
if __name__=='__main__':unittest.main()

class OptimalityTests(unittest.TestCase):
 def test_pitching_solution_matches_exhaustive_feasible_subsets(self):
  import itertools
  pitchers=[player(i,['P'],typ='pitcher',raw=20-i,ip=50+12*i) for i in range(11)]
  expected=max(sum(p['raw'] for p in group) for group in itertools.combinations(pitchers,9) if sum(float(p['IP']) for p in group)>=950)
  chosen=pitching_choice(pitchers)
  self.assertEqual(sum(p['raw'] for p in chosen),expected)
 def test_nine_pitchers_must_supply_the_innings_not_ten(self):
  pitchers=[player(i,['P'],typ='pitcher',ip=100) for i in range(10)]
  self.assertEqual(sum(float(p['IP']) for p in pitchers),1000)
  self.assertIsNone(pitching_choice(pitchers))

class CompositionTests(unittest.TestCase):
 def test_both_requested_splits_pass(self):
  from dc_roster_simulator_v1_2 import composition_ok
  for pitchers in [22,23]:
   r=[player(i,['P'],typ='pitcher') for i in range(pitchers)]+[player(i+100,['OF']) for i in range(50-pitchers)]
   self.assertTrue(composition_ok(r))
 def test_other_splits_fail(self):
  from dc_roster_simulator_v1_2 import composition_ok
  for pitchers in [21,24]:
   r=[player(i,['P'],typ='pitcher') for i in range(pitchers)]+[player(i+100,['OF']) for i in range(50-pitchers)]
   self.assertFalse(composition_ok(r))
 def test_cap_filters_during_actual_draft(self):
  from dc_roster_simulator_v1_2 import composition_candidates
  pitcher=player(100,['P'],typ='pitcher');hitter=player(101,['OF'])
  pfull=[player(i,['P'],typ='pitcher') for i in range(23)]
  hfull=[player(i,['OF']) for i in range(28)]
  self.assertEqual(composition_candidates(pfull,[pitcher,hitter]),[hitter])
  self.assertEqual(composition_candidates(hfull,[pitcher,hitter]),[pitcher])

class CompletionCapTests(unittest.TestCase):
 def test_innings_repair_cannot_exceed_pitcher_cap(self):
  r=covered()
  for p in r:
   if p['player_type']=='pitcher':p['IP']='20'
  for i in range(100,113):r.append(player(i,['P'],typ='pitcher',ip=20))
  self.assertEqual(sum(p['player_type']=='pitcher' for p in r),23)
  available=[player(i,['P'],typ='pitcher',ip=200) for i in range(200,209)]
  self.assertIsNone(completion_plan(r,available))

class SavesReportTests(unittest.TestCase):
 def test_reserve_saves_do_not_satisfy_active_target(self):
  from dc_roster_simulator_v1_2 import saves_target_report
  results=[dict(seed=1,seat=1,strategy='value',total_pitchers=23,total_hitters=27,SV=20,SV_historical_percentile=.1)]
  reserves=[dict(seed=1,seat=1,strategy='value',reserve_SV=100)]
  report=saves_target_report(results,reserves,70)
  self.assertFalse(report[0]['meets_80th_SV_target']);self.assertEqual(report[0]['active_SV_minus_target'],-50)
