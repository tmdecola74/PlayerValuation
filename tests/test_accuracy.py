import csv
import hashlib
import json
import math
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import closing

import test_warehouse
from build_historical_projection_warehouse_v1_0 import build
from evaluate_historical_projection_accuracy_v1_0 import score, ranks, derive_missing, evaluate


def read_csv(path):
    with path.open(encoding='utf-8-sig',newline='') as stream:
        return list(csv.DictReader(stream))


class AccuracyTests(unittest.TestCase):
    def fixture(self, temp):
        actual=[['Season','Name','PlayerId','PA','HR','OBP','SLG'],
                [2025,'A',1,500,10,.3,.4],[2025,'B',2,400,20,.4,.5],
                [2025,'C',3,50,5,.2,.3],[2025,'D',4,500,8,.3,.4]]
        projection=[['Name','PlayerId','PA','HR','OBP','SLG'],
                    ['A',1,500,12,.3,.4],['B',2,450,18,.4,.5],
                    ['C',3,100,9,.2,.3],['D',4,400,6,.3,.4],['Prospect',99,200,4,.2,.3]]
        cfg=test_warehouse.WarehouseTests().fixture(temp,actual,projection)
        data=json.loads(cfg.read_text())
        data['files'][1]['source']='A'
        data['files'].append(dict(data['files'][1],file='b.csv',source='B'))
        with (Path(temp)/'b.csv').open('w',newline='') as f:
            csv.writer(f).writerows([projection[0],['A',1,500,11,.3,.4],['B',2,350,25,.4,.5],['C',3,80,'',.2,.3]])
        cfg.write_text(json.dumps(data))
        build(cfg)
        settings=dict(warehouse='data/warehouse/historical_projection_warehouse.sqlite',output='outputs/accuracy',
            correlation_min_n=2,ranking_min_n=2,player_types={'hitter':dict(exposure='PA',headline_cohort='regular',
            derive_if_missing={'OPS':{'sum':['OBP','SLG']}},
            cohorts=[dict(name='all',minimum_actual=0,minimum_projected=0),dict(name='regular',minimum_actual=300,minimum_projected=0),
                     dict(name='projected_floor',minimum_actual=300,minimum_projected=400)],
            metric_groups={'fantasy_outcome':['HR','OPS'],'opportunity':['PA'],'skill':['HR_per_PA']})})
        accuracy=cfg.parent/'accuracy.json';accuracy.write_text(json.dumps(settings))
        return accuracy,Path(temp)/settings['warehouse']

    def test_known_error_sign_and_average_tied_ranks(self):
        result=score([(2,1),(3,5)],2)
        self.assertEqual(result['mae'],1.5)
        self.assertAlmostEqual(result['rmse'],math.sqrt(2.5))
        self.assertEqual(result['bias'],-.5)
        self.assertAlmostEqual(result['pearson'],1)
        self.assertAlmostEqual(result['spearman'],1)
        self.assertEqual(ranks([10,10,30]),[1.5,1.5,3])
        self.assertEqual(score([(1,2),(1,3)],2)['correlation_status'],'constant_series')
        self.assertIsNone(score([(1,2)],2)['spearman'])
        self.assertIsNone(score([],2)['mae'])
        self.assertAlmostEqual(score([(3,1),(2,2),(1,3)],3)['spearman'],-1)

    def test_fair_complete_player_sets_thresholds_and_read_only_input(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg,db=self.fixture(temp)
            before=hashlib.sha256(db.read_bytes()).hexdigest()
            report=evaluate(cfg)
            self.assertEqual(report['matched_projection_rows'],7)
            self.assertEqual(report['unmatched_projection_rows'],1)
            self.assertEqual(before,hashlib.sha256(db.read_bytes()).hexdigest())
            out=Path(temp)/'outputs/accuracy'
            rows=read_csv(out/'accuracy_summary.csv')
            common=[r for r in rows if r['metric']=='HR' and r['cohort']=='all' and r['comparison']=='common_all']
            self.assertEqual([int(r['n']) for r in common],[2,2])
            self.assertEqual(len({r['sample_id'] for r in common}),1)
            self.assertEqual([float(r['mae']) for r in common],[2,3])
            self.assertEqual([float(r['bias']) for r in common],[0,3])
            own=[r for r in rows if r['metric']=='HR' and r['cohort']=='all' and r['comparison']=='source_specific']
            self.assertEqual([int(r['n']) for r in own],[4,2])
            floor=[r for r in rows if r['metric']=='HR' and r['cohort']=='projected_floor' and r['comparison']=='common_all']
            self.assertEqual([int(r['n']) for r in floor],[1,1])
            self.assertTrue(all(r['ranking_eligible']=='False' for r in floor))
            pairs=read_csv(out/'evaluation_pairs.csv')
            self.assertFalse(any(r['name']=='Prospect' for r in pairs))
            self.assertTrue(any(r['metric']=='OPS' for r in pairs))
            self.assertTrue(report['derived_metric_values']>0)
            with self.assertRaises(ValueError):evaluate(cfg)

    def test_bad_link_and_duplicate_analytical_key_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg,db=self.fixture(temp)
            with closing(sqlite3.connect(db)) as c:
                c.execute('UPDATE hitter_actuals SET season=2024 WHERE name=?',('A',));c.commit()
            with self.assertRaises(ValueError):evaluate(cfg)
            self.assertFalse((Path(temp)/'outputs/accuracy').exists())
        with tempfile.TemporaryDirectory() as temp:
            cfg,db=self.fixture(temp)
            with closing(sqlite3.connect(db)) as c:
                c.execute('DROP VIEW analytical_hitter_projections')
                c.execute('CREATE VIEW analytical_hitter_projections AS SELECT p.*,s.excluded_metrics_json FROM hitter_projections p JOIN record_selection s USING(record_id) UNION ALL SELECT p.*,s.excluded_metrics_json FROM hitter_projections p JOIN record_selection s USING(record_id)');c.commit()
            with self.assertRaises(ValueError):evaluate(cfg)

    def test_derived_missing_values_do_not_override_or_reintroduce_exclusions(self):
        values={'OBP':.3,'SLG':.4}
        self.assertEqual(derive_missing(values,{'OPS':{'sum':['OBP','SLG']}},['OPS']),[])
        self.assertNotIn('OPS',values)
        values['OPS']=.9
        derive_missing(values,{'OPS':{'sum':['OBP','SLG']}},[])
        self.assertEqual(values['OPS'],.9)


if __name__=='__main__':unittest.main()
