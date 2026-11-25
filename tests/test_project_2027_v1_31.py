import unittest
from project_2027_v1_31 import project, compare, sensitivity


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


class ReplayTests(unittest.TestCase):
    def test_zero_start_qs_is_zero_but_missing_start_qs_is_unknown(self):
        a={(2026,'pitcher','1','OUTS'):30}
        self.assertIsNone(project(a,'pitcher','1')['QS'])
        a[2026,'pitcher','1','GS']=0
        self.assertEqual(project(a,'pitcher','1')['QS'],0)

    def test_same_baseline_inputs_and_no_lookahead(self):
        from project_2027_v1_31 import replay
        a={(y,'pitcher','1','OUTS'):30*(y-2018) for y in range(2019,2027)}
        seen={}
        def features(k,v,actual,_):
            y=k[0]
            self.assertTrue(all(y-4<=x[0]<y for x in actual))
            seen[y]=v['OUTS']/3
            return [seen[y]], 'STARTER' if y==2023 else 'UNKNOWN', None
        def forecast(k,v,x,role,status,model):
            self.assertEqual(k[0],model)
            return dict(prior_role=role,two_part_ip=x[0]/2,probability=.5,conditional_ip=x[0])
        rows,cov=replay(a,{str(y):y for y in range(2023,2027)},features,forecast)
        self.assertEqual(seen,{2023:30,2024:40,2025:50,2026:60})
        self.assertEqual(cov[-1]['scored'],1)
        all23=[r for r in rows if r['season']==2023 and r['dimension']=='ALL']
        self.assertEqual([r['mse'] for r in all23],[400,400])
        self.assertTrue(all(r['reporting_only']==(r['season']==2026) for r in rows))

    def test_gap_sort_and_cut_names_and_zero_history(self):
        from project_2027_v1_31 import ranked_gaps, cuts
        s={('depth_charts','pitcher'):{'1':dict(name='One',IP=50),'2':dict(name='Two',IP=100),
                                      '3':dict(name='Three',IP=None)},
           ('steamer','pitcher'):{}}
        p=dict(IP=100,hybrid_ip=50,SO=120,W=8,QS=10,GS=20,mlbam_id='1',prior_role='SWING')
        home={('pitcher','1'):p}
        cov,_=compare(home,s)
        self.assertEqual([r['mlbam_id'] for r in ranked_gaps(cov,s)],['2','3'])
        row=cuts(home,{(2026,'pitcher','1','OUTS'):0},s)[0]
        self.assertEqual((row['player_name'],row['prior_year_ip'],row['rank']),('One',0,1))
