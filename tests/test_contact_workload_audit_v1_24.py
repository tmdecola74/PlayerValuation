import unittest
from contact_workload_audit_v1_24 import BASE, ARMS, CONTACT, choose, contact_only, exposure, hitter_scores, pitcher_diagnostics, role


class AuditTests(unittest.TestCase):
    def hitter(self):
        return dict(PA=550., AB=500., HR=20., BB=40., HBP=5., SF=5., SH=0., R=60., RBI=70., SB=5.,
                    H=130., **{'1B':85.,'2B':23.,'3B':2.}, AVG=.26, OBP=175/550,
                    SLG=217/500, OPS=175/550+217/500)

    def test_exact_anchors_and_rates(self):
        base = self.hitter()
        v, status = contact_only(base, {'1B':.18,'2B':.05,'3B':.01})
        self.assertEqual(status,'FITTED_CONTACT')
        self.assertEqual(v['H'],140)
        self.assertAlmostEqual(v['AVG'],.28)
        self.assertAlmostEqual(v['OPS'],185/550+235/500)
        self.assertTrue(all(v[m]==base[m] for m in base if m not in CONTACT))

    def test_cap_reserves_hr_and_missing_is_fallback(self):
        base = self.hitter()
        v, status = contact_only(base, {'1B':1.,'2B':1.,'3B':1.})
        self.assertEqual(status,'CAPPED_CONTACT')
        self.assertEqual((v['HR'],v['AB'],v['H']),(20,500,500))
        self.assertEqual(contact_only(base, {'1B':0.,'2B':0.,'3B':None}), (base,'UNSUPPORTED_CONTACT_RATE'))
        self.assertEqual(contact_only(base, dict.fromkeys(('1B','2B','3B'),0.))[0]['H'],20)

    def test_gate_ignores_2026_and_requires_recent_support(self):
        scores = [dict(season=y,metric=m,dimension=dim,cohort=c,method=a,n=100,mse=e,mae=e)
                  for y in range(2020,2026) for m in ('AVG','OPS')
                  for dim,c in [('ALL','ALL'),('HISTORY','LOW_HISTORY'),('HISTORY','ESTABLISHED_HISTORY')]
                  for a,e in [(BASE,1.),(ARMS[0],.95),(ARMS[1],.9)]]
        good = choose(scores,2026)
        self.assertEqual(good['selected'],ARMS[1])
        self.assertEqual(choose(scores+[dict(scores[0],season=2026,mse=0)],2026),good)
        self.assertEqual(choose([s for s in scores if s['season']!=2025],2026)['selected'],BASE)

    def test_fitted_pool_excludes_unsupported_arm(self):
        k = (2025,'hitter','1')
        base = self.hitter()
        bank = {(k,m):base for m in (BASE,*ARMS)}
        truth = {k+(m,):x for m,x in base.items()}
        ctx = {k:dict(history_cohort='LOW_HISTORY')}
        support = [dict(season=2025,player_type='hitter',mlbam_id='1',method=m,status='FITTED_CONTACT') for m in ARMS]
        self.assertFalse(hitter_scores(bank,truth,ctx,support[:1],True))
        r = [s for s in hitter_scores(bank,truth,ctx,support,True) if s['metric']=='AVG' and s['dimension']=='ALL']
        self.assertEqual(len(r),3)
        self.assertEqual(len({s['membership_sha256'] for s in r}),1)

    def test_role_and_exposure_boundaries(self):
        self.assertEqual([role(20,x) for x in (0,2,3,10,21,None)],
                         ['RELIEVER','RELIEVER','SWING','STARTER','UNKNOWN','UNKNOWN'])
        self.assertEqual([exposure(x) for x in (None,0,59,60,299,300)],
                         ['UNKNOWN','ZERO','LT20_IP','20_99_IP','20_99_IP','GE100_IP'])

    def test_pitcher_scoring_preserves_saves_and_uses_matched_exposure(self):
        k = (2026,'pitcher','1')
        base = dict(IP=30.,ERA=4.,SV=12.,HLD=3.)
        bank = {(k,BASE):base}
        truth = {k+(m,):x for m,x in [('OUTS',30),('ERA',8.),('G',20),('GS',0)]}
        ctx = {k:dict(prior_role='STARTER',v1_2_selected_role='STARTER')}
        ext = [dict(season='2026',player_type='pitcher',mlbam_id='1',metric='ERA',source='ATC',prediction='5')]
        scores, details, confusion = pitcher_diagnostics(bank,truth,ctx,ext)
        rr = [r for r in scores if r['dimension']=='ACTUAL_EXPOSURE' and r['comparison']=='all_available_benchmarks']
        self.assertEqual({r['cohort'] for r in rr},{'LT20_IP'})
        self.assertEqual({r['method']:r['rmse'] for r in rr},{BASE:4.,'ATC':3.})
        self.assertEqual(len({r['membership_sha256'] for r in rr}),1)
        self.assertEqual(details[0]['IP_error'],20)
        self.assertEqual(details[0]['frozen_SV'],12.)
        self.assertEqual(confusion[0]['actual_role'],'RELIEVER')
        self.assertEqual(bank[k,BASE],base)
        truth[k+('OUTS',)]=0
        self.assertFalse(any(r['metric']=='ERA' for r in pitcher_diagnostics(bank,truth,ctx,ext)[0]))
