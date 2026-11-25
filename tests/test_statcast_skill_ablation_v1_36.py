import unittest
from statcast_skill_ablation_v1_36 import ARMS, FEATURES, fit, score, adjust


class AblationTests(unittest.TestCase):
    def test_known_feature_signal_and_identical_scoring_pools(self):
        board,actual={},{}
        for y in (2023,2024,2025):
            for i in range(120):
                p=str(i+1)
                for m,v in {'OUTS':300,'SO':40+i*(y-2023),'BB':30,'H':90}.items():
                    actual[y,'pitcher',p,m]=v
                for j,m in enumerate(FEATURES):
                    board[y,'pitcher',p,m]=(i/120 if j==0 else .2,40)
        model=fit(actual,board,(2024,),2025)
        rows=[r for r in score(actual,board,2025,model)
              if (r['metric'],r['pool'],r['projected_workload_band'])==('SO','FEATURE_SUPPORTED','ALL')]
        by={r['method']:r for r in rows}
        self.assertEqual(set(by),set(ARMS))
        self.assertEqual({r['n'] for r in rows},{120})
        self.assertEqual(len({r['membership_sha256'] for r in rows}),1)
        self.assertLess(by['statcast_full']['rmse'],by['residual_only']['rmse'])
        self.assertAlmostEqual(by['without_gb_rate']['rmse'],by['residual_only']['rmse'])
        with self.assertRaises(ValueError):
            fit(actual,board,(2026,),2027)

    def test_frozen_categories_and_fallback(self):
        for b,coef in [
            (dict(player_type='pitcher',IP=100,OUTS=300,SO=100,BB=40,WHIP=1.2,hybrid_qs=None),[.2]),
            (dict(player_type='hitter',AB=100,PA=105,**{'1B':45,'2B':23,'3B':8},
                  HR=15,BB=4,HBP=1,SF=0),[.4,.4])]:
            model=dict(mean=[0]*4,scale=[1]*4,arms={'residual_only':[coef]})
            out=adjust(b,[0]*4,model,'residual_only')
            for k in ('PA','AB','1B','HR','IP','OUTS','BB','WHIP','hybrid_qs'):
                self.assertEqual(b.get(k),out.get(k))
            if b['player_type']=='hitter':
                self.assertLessEqual(out['H'],b['AB']+1e-10)
            else:
                self.assertEqual(out['SO'],130)
            self.assertEqual(adjust(b,None,model,'residual_only'),b)
