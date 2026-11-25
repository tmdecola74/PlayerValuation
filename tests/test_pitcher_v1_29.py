import unittest
from collections import Counter

from pitcher_evaluation_v1_29 import outcomes, score, verified_box
from pitcher_baseline_export_2027_v1_29 import export


class EvaluationTests(unittest.TestCase):
    def test_zeros_require_certification_and_identity(self):
        f={i:dict(prior_role='STARTER' if i==1 else 'UNKNOWN',
                  accepted_ip=10,two_part_ip=5) for i in range(1,5)}
        g,o=Counter({1:1,4:1}),Counter({1:0,4:30})
        invalid=list(outcomes(f,{},g,o,{2},False))
        self.assertEqual(score(invalid),[])
        a=list(outcomes(f,{},g,o,{2},True))
        self.assertEqual([r['evaluation_g'] for r in a],[1,0,None,1])
        self.assertEqual([r['evaluation_outs'] for r in a],[0,0,None,30])
        self.assertEqual(a[0]['role_hybrid_ip'],10)
        s=[r for r in score(a) if r['dimension']=='ALL']
        self.assertEqual({r['n'] for r in s},{3})
        self.assertEqual(len({r['membership_sha256'] for r in s}),1)
        self.assertEqual({r['method']:r['sse'] for r in s},
                         {'accepted_ip':200,'two_part_ip':75,'role_hybrid_ip':150})

    def test_boxscore_preserves_zero_out_appearance(self):
        def side(team,ids,lines,ip):
            return {'team':{'id':team},'pitchers':ids,'players':{
                str(i):{'person':{'id':i},'stats':{'pitching':{
                    'gamesPitched':g,'inningsPitched':inn}}} for i,g,inn in lines},
                    'teamStats':{'pitching':{'inningsPitched':ip}}}
        doc={'teams':{'away':side(1,[11,12,13],[(11,1,'0.0'),(12,0,'0.0'),(13,1,'9.0')],'9.0'),
                      'home':side(2,[21],[(21,1,'8.2')],'8.2')}}
        self.assertEqual(verified_box(doc,(1,2)),{11:0,13:27,21:26})


class ExportTests(unittest.TestCase):
    def test_baseline_does_not_use_challenger(self):
        r=dict(season='2027',mlbam_id='10',accepted_ip=180,accepted_so=200,
               accepted_w=12,accepted_qs=15,accepted_gs=30,challenger_ip=90)
        b,c=export([r])
        self.assertEqual((b[0]['IP'],b[0]['SO'],b[0]['W'],b[0]['QS']),(180,200,12,15))
        self.assertNotIn('challenger_ip',b[0])
        self.assertEqual(c[0]['so_if_k_rate_unchanged'],100)
        self.assertEqual(c[0]['w_if_w_rate_unchanged'],6)
        self.assertIsNone(c[0]['qs_if_start_rate_unchanged'])
        self.assertEqual(export([dict(r,challenger_gs=20)])[1][0]['qs_if_start_rate_unchanged'],10)
        with self.assertRaises(ValueError):
            export([dict(r,season='2026')])
