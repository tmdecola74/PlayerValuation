import unittest
from collections import Counter

from project_2027_statcast_v1_35 import FEATURES, apply, board_index, features, fit


class OverlayTests(unittest.TestCase):
    def test_2026_history_admitted_only_for_2027_and_mask_stays_masked(self):
        r = dict(source_season=2026, player_type='hitter', mlbam_id='42', family='batted_ball',
                 eligible=True, sample_eligible=True, definition_supported=True, sample_basis='EXPORTED_BBE',
                 definition='EXPORTED_FRACTION_OF_ALL_BBE', unit='fraction', denominator=30,
                 minimum_observations=30, value=.2, reason='AVAILABLE_FIXED_SAMPLE_CONTROL')
        rows = [dict(r, metric=m) for m in FEATURES]
        index = board_index(rows, {2026}, Counter())
        self.assertEqual(features(index,2026,'hitter','42'),(None,()))
        self.assertEqual(features(index,2027,'hitter','42')[1],(2026,))
        rows[0].update(eligible=False, reason='SOURCE_RELATIONSHIP_REVIEW_REQUIRED')
        self.assertEqual(features(board_index(rows,{2026},Counter()),2027,'hitter','42'),(None,()))
        with self.assertRaises(ValueError):
            board_index(rows,{2025},Counter())
        with self.assertRaises(ValueError):
            fit({},index,(2026,),2027)

    def test_count_coherence_and_frozen_workload(self):
        h = {'player_type':'hitter','PA':105,'AB':100,'1B':60,'2B':25,'3B':2,'HR':10,
             'BB':4,'HBP':1,'SF':0,'R':12,'RBI':12}
        model = dict(mean=[0]*4,scale=[1]*4,beta=[[1]*3]+[[0]*3]*4)
        candidate,status = apply(h,[0]*4,model)
        self.assertEqual(status,'STATCAST_CHALLENGER')
        self.assertAlmostEqual(candidate['H'],100)
        self.assertEqual([candidate[k] for k in ('PA','AB','HR','R','RBI')],[105,100,10,12,12])
        p = dict(player_type='pitcher',OUTS=300,IP=100,H=90,SO=90,BB=30,
                 ERA=3.4,SV=5,HLD=8,QS=10,hybrid_qs=None)
        c,_ = apply(p,[0]*4,dict(mean=[0]*4,scale=[1]*4,beta=[[.1,-.04]]+[[0,0]]*4))
        self.assertEqual((c['SO'],c['BB'],c['WHIP']),(105,24,1.14))
        self.assertEqual({k:c[k] for k in p if k not in ('SO','BB')},
                         {k:p[k] for k in p if k not in ('SO','BB')})
        self.assertEqual(apply(p,None,model),(p,'MISSING_ELIGIBLE_STATCAST'))

    def test_fit_does_not_use_2026_outcomes(self):
        actual, board = {}, {}
        for i in range(1,121):
            pid=str(i)
            for year,hit in ((2023,30),(2024,34),(2025,35)):
                for metric,v in {'PA':110,'AB':100,'1B':hit,'2B':10,'3B':1}.items():
                    actual[year,'hitter',pid,metric]=v
                for j,m in enumerate(FEATURES):
                    board[year,'hitter',pid,m]=(.15+(i+j)/500,60)
        first=fit(actual,board,(2024,2025),2026)
        actual[2026,'hitter','1','1B']=999
        self.assertIsNotNone(first['hitter']['model'])
        self.assertEqual(first,fit(actual,board,(2024,2025),2026))
