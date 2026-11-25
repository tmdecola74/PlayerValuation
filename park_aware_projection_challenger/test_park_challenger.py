import sys,csv,json,math,hashlib,unittest
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,str(Path('work').resolve()))
import park_challenger as pc
O=Path('outputs/park_aware_challenger_run2')
class TestParkChallenger(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.forecasts=pc.read(O/'historical_forecasts.csv');cls.scores=pc.read(O/'historical_scores.csv')
 def test_baseline_numeric_replay(self):
  previous=pc.read(pc.ROOT/'outputs/projection_phase_v1_42/historical_player_predictions.csv')
  old={(r['season'],r['player_type'],r['mlbam_id']):r for r in previous}
  n=0
  for r in self.forecasts:
   if r['arm']!='MLB_ONLY':continue
   src=old[r['origin'],r['role'],r['mlbam_id']]
   for c in pc.FIELDS[r['role']]:
    x=pc.val(r[c]);y=pc.val(src['skill__'+c])
    self.assertEqual(x is None,y is None)
    if x is not None:self.assertTrue(math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-10),(r['origin'],r['mlbam_id'],c,x,y))
   n+=1
  self.assertEqual(n,11946)
 def test_vectors_anchors_and_fallbacks(self):
  groups=defaultdict(dict)
  for r in self.forecasts:groups[r['origin'],r['role'],r['mlbam_id']][r['arm']]=r
  for (y,role,pid),rr in groups.items():
   self.assertEqual(set(rr),set(pc.ARMS));base=rr['MLB_ONLY']
   mutable={'1B','2B','3B','HR','H','AVG','OBP','SLG','OPS'} if role=='hitter' else {'H','ER','BB','SO','HR','ERA','WHIP'}
   for r in rr.values():
    v={c:pc.val(r[c]) for c in pc.FIELDS[role]};pc.phase.verify_vector(v,role)
    for c in pc.FIELDS[role]:
     if c not in mutable or r['supported']=='False':self.assertEqual(r[c],base[c])
 def test_paired_membership_and_score_replay(self):
  groups=defaultdict(set)
  for r in self.scores:groups[tuple(r[c] for c in ['season','role','metric','cohort','pool'])].add((r['membership_sha256'],r['n']))
  self.assertTrue(all(len(v)==1 for v in groups.values()))
 def test_chronology_and_immutable_sources(self):
  for r in pc.read(O/'fitted_context_models.csv'):self.assertLess(int(r['max_target_year']),int(r['origin']))
  for p,h in json.loads((O/'source_manifest.json').read_text()).items():self.assertEqual(pc.digest(p),h)
  self.assertEqual({int(r['origin']) for r in self.forecasts},{2022,2023,2024,2025})
 def test_synthetic_context_and_minimum_support(self):
  pp=[dict(pid=str(i),w=100,x=.1,y=.12+.05*((i%3)-1),logpf=.1*((i%3)-1),league='L',target=2022) for i in range(60)]
  fit=pc.fitted(pp)
  self.assertAlmostEqual(fit['factor'],1.2)
  self.assertGreater(fit['beta'],0)
  self.assertIsNone(pc.fitted(pp[:29]))
  self.assertIsNone(pc.val(''));self.assertEqual(pc.val('0'),0)
 def test_existing_gates_applied(self):
  gates=json.loads((O/'adoption_gates.json').read_text());final=[r for r in gates if r['origin']==2026]
  self.assertEqual(len(final),6)
  for r in final:
   self.assertEqual(r['years'],[2023,2024,2025])
   if r['comparison']=='PARK_vs_MINOR':self.assertFalse(r['eligible'])
 def test_independent_MSE_recalculation(self):
  from recent_skill_inputs_v1_23 import labels
  actual=labels(pc.ROOT/'outputs/training_labels_v1_0/training_labels.parquet')
  s=next(r for r in self.scores if r['pool']=='SUPPORTED' and r['cohort']=='ALL' and r['metric']=='AVG' and r['arm']=='MLB_PLUS_MINOR_PARK')
  rr=[r for r in self.forecasts if r['origin']==s['season'] and r['role']==s['role'] and r['supported']=='True' and r['arm']==s['arm']]
  errors=[float(r['AVG'])-actual[int(s['season']),'hitter',r['mlbam_id'],'AVG'] for r in rr if (int(s['season']),'hitter',r['mlbam_id'],'AVG') in actual]
  self.assertEqual(len(errors),int(s['n']))
  self.assertAlmostEqual(sum(e*e for e in errors)/len(errors),float(s['mse']))

if __name__=='__main__':unittest.main(verbosity=2)
