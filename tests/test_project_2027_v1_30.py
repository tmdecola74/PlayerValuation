import unittest
from project_2027_v1_30 import project, compare, sensitivity


class ProjectionTests(unittest.TestCase):
    def test_certified_zero_vs_missing_and_future(self):
        a={(2023,'pitcher','1','OUTS'):300,(2026,'pitcher','1','OUTS'):0,
           (2023,'pitcher','1','SO'):100,(2027,'pitcher','1','OUTS'):999}
        p=project(a,'pitcher','1')
        self.assertEqual(p['IP'],20)
        self.assertEqual(p['SO'],20)
        self.assertEqual(p['confirmed_zero_exposure_years'],'2026')
        self.assertIsNone(p['QS'])
        del a[2026,'pitcher','1','OUTS']
        self.assertEqual(project(a,'pitcher','1')['IP'],100)

    def test_coherence_and_role_keyed_comparison(self):
        a={(2026,'hitter','1',m):v for m,v in dict(PA=500,AB=450,BB=40,HBP=4,
            SF=4,SH=2,HR=20,**{'1B':75,'2B':25,'3B':5}).items()}
        h=project(a,'hitter','1')
        self.assertEqual(h['H'],125)
        self.assertAlmostEqual(h['AVG'],125/450)
        self.assertAlmostEqual(h['OPS'],h['OBP']+h['SLG'])
        cov,diff=compare({('hitter','1'):h},{('steamer','hitter'):{'1':{'name':'A','PA':350}}})
        self.assertEqual(cov[0]['status'],'MATCHED')
        self.assertEqual(diff[0]['delta'],150)

    def test_no_challenger_qs_from_ip_alone(self):
        r=sensitivity(dict(IP=100,hybrid_ip=50,SO=120,W=8,QS=10,GS=20,mlbam_id='1',prior_role='SWING'))
        self.assertEqual(r['so_at_fixed_rate'],60)
        self.assertEqual(r['w_at_fixed_rate'],4)
        self.assertIsNone(r['hybrid_qs'])
