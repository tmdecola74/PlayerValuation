import csv
import io
import unittest

from pitcher_role_hybrid_v1_28 import BASE, HYBRID, METRICS, ROLES, TWO, aggregate, gates


def fixture(broken=False):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['season','task','dimension','cohort','method','n','membership_sha256',*METRICS])
    for y in (2023,2024,2025,2026):
        for method, mses in [(BASE,(100,40,40,40)),(TWO,(120,20,20,20))]:
            for role,n,mse in [('ALL',5,(2*mses[0]+sum(mses[1:]))/5),
                               *zip(ROLES,(2,1,1,1),mses)]:
                sig = 'b' if broken and role=='SWING' and method==TWO else 'a'
                w.writerow([y,'EXPECTED_IP','ALL' if role=='ALL' else 'PRIOR_ROLE',role,
                            method,n,sig*64,mse,1,0,10,10])
    return buf.getvalue().encode()


class HybridTests(unittest.TestCase):
    def test_weights_and_protected_starters(self):
        r = aggregate(fixture(),(2023,2024,2025,2026))
        ix={(v['season'],v['cohort'],v['method']):v['mse'] for v in r}
        self.assertEqual(ix[2025,'STARTER',HYBRID],100)
        self.assertEqual(ix[2025,'UNKNOWN',HYBRID],20)
        self.assertEqual(ix[2025,'ALL',HYBRID],52)
        self.assertTrue(gates(r,2026)['eligible_under_innings_gates'])
        self.assertFalse(gates(r,2025)['eligible_under_innings_gates'])
        self.assertEqual(gates(r,2026),gates([v for v in r if v['season']!=2026],2026))

    def test_unmatched_roles_fail(self):
        with self.assertRaisesRegex(ValueError,'Unmatched'):
            aggregate(fixture(broken=True),(2023,2024,2025,2026))
