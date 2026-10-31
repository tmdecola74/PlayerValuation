import unittest
from dc_roster_simulator_v1_0 import eligible,lineup,totals,SLOTS

def player(i,slots,raw=1,typ='hitter'):
 return dict(id=str(i),name=str(i),slots=set(slots),known=True,raw=raw,player_type=typ,R='1',HR='1',RBI='1',SB='1',AB='100',H='25',W='1',SV='0',SO='10',IP='10',ER='4',BB='3')
class SimulatorTests(unittest.TestCase):
 def test_multi_position_capacity_and_exact_legal_slots(self):
  roster=[player(i,[s]) for i,s in enumerate(SLOTS)]
  roster.append(player(99,['C','SS','OF'],raw=10))
  active,missing=lineup(roster)
  self.assertEqual(missing,0);self.assertEqual(len({p['id'] for s,p in active}),23)
  self.assertEqual(sorted(s for s,p in active),sorted(SLOTS))
  self.assertEqual(sum(p['id']=='99' for s,p in active),1)
 def test_missing_catcher_is_not_hidden(self):
  active,missing=lineup([player(i,[s]) for i,s in enumerate(SLOTS) if s!='C'])
  self.assertEqual(missing,2)
 def test_ratios_use_components(self):
  h=player(1,['UT']);p=player(2,['P'],typ='pitcher')
  t=totals([('UT',h),('P',p)])
  self.assertEqual(t['AVG'],.25);self.assertEqual(t['ERA'],3.6);self.assertEqual(t['WHIP'],2.8)
 def test_unknown_is_not_projected_zero(self):
  p=player(1,['C']);p['known']=False
  self.assertEqual(lineup([p])[1],23)
  with self.assertRaises(ValueError):totals([('C',p)])
 def test_eligibility_expansion(self):
  self.assertEqual(eligible('1B;2B','hitter'),{'1B','2B','CI','MI','UT'})
  self.assertEqual(eligible('P','pitcher'),{'P'})
if __name__=='__main__':unittest.main()

class StressTests(unittest.TestCase):
 def test_single_absence_identifies_uncovered_catchers(self):
  from dc_roster_simulator_v1_0 import reserve_stress
  roster=[player(i,[s]) for i,s in enumerate(SLOTS)]
  logs=[dict(seed=1,seat=1,team=1,strategy='value',nfbc_player_id=p['id']) for p in roster]
  rows=reserve_stress(roster,logs)
  self.assertEqual(len(rows),23)
  self.assertTrue(all(r['remaining_active_shortfall']==1 for r in rows))
 def test_history_rejects_target_season(self):
  import csv,tempfile
  from pathlib import Path
  from dc_roster_simulator_v1_0 import History
  with tempfile.TemporaryDirectory() as t:
   f=Path(t)/'h.csv';f.write_text('season\n2026\n')
   with self.assertRaisesRegex(ValueError,'leakage'):History(f)
