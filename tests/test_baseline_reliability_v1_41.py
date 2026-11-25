import csv
from pathlib import Path
import tempfile
import unittest
from baseline_reliability_v1_41 import sample,audit_players,audit_benchmarks
from project_2027_v1_31 import FILES
class ReliabilityTests(unittest.TestCase):
    def test_missing_pairs_not_zero_and_component_denominators(self):
        a={(2023,'hitter','1','AB'):100,(2023,'hitter','1','HR'):0,
           (2024,'hitter','1','AB'):20,(2025,'hitter','1','HR'):5}
        r=sample(a,'hitter','1','HR','AB')
        self.assertEqual(r['paired_seasons'],1)
        self.assertEqual(r['raw_denominator'],100)
        self.assertEqual(r['weighted_component_rate'],0)
        self.assertIsNone(r['source_2024_numerator'])
        self.assertIsNone(r['source_2025_denominator'])
    def test_stale_missing_distinct_from_certified_zero_and_zero_out_appearance(self):
        home={'hitter':[],'pitcher':[
          dict(season='2027',player_type='pitcher',mlbam_id=str(i),name='Test',
               weighted_actuals__IP='20',weighted_actuals__ERA='135',weighted_actuals__WHIP='21') for i in (1,2,3)]}
        a={(2023,'pitcher',str(i),'OUTS'):1 for i in (1,2,3)}
        a.update({(2026,'pitcher','2','OUTS'):0,(2026,'pitcher','2','G'):0,
                  (2026,'pitcher','3','OUTS'):0,(2026,'pitcher','3','G'):1})
        h,s,e=audit_players(home,a)
        self.assertEqual(h[0]['latest_participation_status'],'UNKNOWN')
        self.assertEqual(h[1]['latest_participation_status'],'CERTIFIED_NO_APPEARANCE')
        self.assertEqual(h[2]['latest_participation_status'],'KNOWN_APPEARED')
        self.assertTrue(all(r['extreme'] for r in s))
        self.assertTrue(any(r['issue']=='LOW_RECORDED_EXPOSURE' for r in e))
    def test_priority_within_role_and_no_forecast_changes(self):
        h={'hitter':[dict(season='2027',player_type='hitter',mlbam_id=str(i),name='X',
            weighted_actuals__PA=str(i*100),weighted_actuals__AVG='.5',weighted_actuals__OPS='1.5') for i in (1,2)],'pitcher':[]}
        import copy
        before=copy.deepcopy(h)
        _,_,e=audit_players(h,{(2023,'hitter',str(i),'PA'):10 for i in (1,2)})
        self.assertEqual(e[0]['mlbam_id'],'2')
        self.assertEqual(h,before)
    def test_benchmark_absent_blank_zero_and_positive_remain_distinct(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)
            for (s,r),name in FILES.items():
                if r!='pitcher':continue
                with (root/name).open('w',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=['MLBAMID','Name','SV']);w.writeheader()
                    for i,v in enumerate(['','0','2'],1):w.writerow(dict(MLBAMID=i,Name='X',SV=v))
            raw,summary=audit_benchmarks(root)
            self.assertEqual({r['status'] for r in raw},{'COLUMN_ABSENT','BLANK_MISSING','EXPLICIT_ZERO','POSITIVE_VALUE'})
            self.assertTrue(all(r['exported_total'] is None for r in summary if r['metric']=='HLD'))
    def test_duplicate_and_future_identity_fail(self):
        h={'pitcher':[],'hitter':[dict(season='2028',player_type='hitter',mlbam_id='1')]}
        with self.assertRaises(ValueError):audit_players(h,{})
if __name__=='__main__':unittest.main()

class ReplayGuardTests(unittest.TestCase):
    def test_original_component_replay_and_changed_forecast_fails(self):
        from baseline_reliability_v1_41 import verify_baseline
        from project_2027_v1_31 import project,FIELDS
        actual={}
        for y in (2023,2024,2025,2026):
            for metric,value in dict(OUTS=3,H=4,BB=2,ER=5,SO=1,HR=1,W=0,SV=0,HLD=0,QS=0,GS=0,G=1).items():
                actual[y,'pitcher','1',metric]=value
        b=project(actual,'pitcher','1')
        home={'hitter':[],'pitcher':[dict(mlbam_id='1',**{'weighted_actuals__'+m:b[m] for m in FIELDS['pitcher']})]}
        verify_baseline(home,actual)
        home['pitcher'][0]['weighted_actuals__ERA']+=.1
        with self.assertRaises(ValueError):verify_baseline(home,actual)
