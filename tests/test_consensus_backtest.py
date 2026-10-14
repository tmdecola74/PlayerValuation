import csv
import json
import math
import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from backtest_consensus_projections_v1_0 import alternatives, leaves, qualifies, actual_value
from evaluate_historical_projection_accuracy_v1_0 import score

ROOT=Path(__file__).resolve().parents[1]


class ConsensusBacktestTests(unittest.TestCase):
    def setUp(self):
        self.cfg=json.loads((ROOT/'config/consensus_projections.json').read_text(encoding='utf-8'))

    def test_common_pool_excludes_incomplete_source_and_preserves_zero(self):
        records=[dict(source='A',metrics={'H':30,'AB':100,'AVG':.3}),
                 dict(source='B',metrics={'H':0,'AB':50,'AVG':0}),
                 dict(source='C',metrics={'H':30,'AVG':.4})]
        direct,common,spread,sources=alternatives('AVG',records,self.cfg['player_types']['hitter'],{'A':1,'B':1,'C':1})
        self.assertAlmostEqual(direct,.7/3)
        self.assertAlmostEqual(common,30/150)
        self.assertEqual(sources,['A','B'])
        self.assertEqual(spread['source_count'],3)

    def test_recursive_ops_requires_all_primitive_components(self):
        settings=self.cfg['player_types']['hitter']
        self.assertEqual(leaves('OPS',settings),{'H','BB','HBP','AB','SF','1B','2B','3B','HR'})
        record=dict(source='A',metrics={'H':30,'AB':100,'BB':10,'HBP':0,'SF':0,'1B':20,'2B':5,'3B':0,'HR':5})
        incomplete=dict(source='B',metrics={'H':50,'AB':100,'BB':20,'HBP':0,'SF':0,'HR':10})
        _,value,_,sources=alternatives('OPS',[record,incomplete],settings,{'A':1,'B':1})
        self.assertEqual(sources,['A'])
        self.assertAlmostEqual(value,40/110+50/100)

    def test_zero_actual_saves_kept_but_zero_actual_exposure_excluded(self):
        cohort={'minimum_actual':0,'projected_any_sv_minimum':5}
        records=[dict(metrics={'SV':5})]
        self.assertTrue(qualifies({'IP':10,'SV':0},{'IP':50},records,cohort,'IP'))
        self.assertFalse(qualifies({'IP':0,'SV':0},{'IP':50},records,cohort,'IP'))
        self.assertFalse(qualifies({'IP':10},{'IP':50},[dict(metrics={'SV':None})],cohort,'IP'))

    def test_missing_actual_does_not_become_zero_and_ops_fallback(self):
        settings=self.cfg['player_types']['hitter']
        self.assertIsNone(actual_value('AVG',{},settings))
        self.assertAlmostEqual(actual_value('OPS',{'OBP':.3,'SLG':.4},settings),.7)


class DeliveredBacktestTests(unittest.TestCase):
    def test_scores_membership_and_pairing_independently_recompute(self):
        out=ROOT/'outputs/consensus_backtest_v1_0'
        if not (out/'backtest_report.json').exists():self.skipTest('Complete backtest first')
        with (out/'predictions.csv').open(encoding='utf-8-sig',newline='') as stream:
            rows=list(csv.DictReader(stream))
        index={(r['player_type'],r['season'],r['metric'],r['player_id']):r for r in rows}
        with (out/'sample_membership.csv').open(encoding='utf-8-sig',newline='') as stream:
            members={r['sample_id']:r for r in csv.DictReader(stream)}
        with (out/'paired_comparisons.csv').open(encoding='utf-8-sig',newline='') as stream:
            comparisons=list(csv.DictReader(stream))
        for r in comparisons:
            membership=members[r['sample_id']];ids=json.loads(membership['player_ids'])
            self.assertEqual(len(ids),int(r['n']))
            selected=[index[(r['player_type'],r['season'],r['metric'],pid)] for pid in ids]
            for p in selected:self.assertIn(r['cohort'],json.loads(p['cohorts']))
            for method,prefix in [('stage3','stage3'),(r['comparator'],'comparator')]:
                pairs=[(float(p[method]),float(p['actual'])) for p in selected]
                if pairs:
                    mae=sum(abs(a-b) for a,b in pairs)/len(pairs)
                    rmse=math.sqrt(sum((a-b)**2 for a,b in pairs)/len(pairs))
                    self.assertAlmostEqual(mae,float(r[prefix+'_mae']))
                    self.assertAlmostEqual(rmse,float(r[prefix+'_rmse']))

    def test_all_forecasts_equal_exact_stage3_exports(self):
        out=ROOT/'outputs/consensus_backtest_v1_0'
        if not (out/'backtest_report.json').exists():self.skipTest('Complete backtest first')
        expected={}
        for season in (2024,2025,2026):
            for typ in ('hitter','pitcher'):
                for p in json.loads((out/f'consensus_{season}/{typ}_consensus.json').read_text(encoding='utf-8')):
                    expected[(typ,str(season),p['player_id'])]=p
        with (out/'predictions.csv').open(encoding='utf-8-sig',newline='') as stream:
            for r in csv.DictReader(stream):
                p=expected[(r['player_type'],r['season'],r['player_id'])]
                self.assertEqual(float(r['stage3']),p['metrics'][r['metric']])
                self.assertEqual(json.loads(r['source_records']),p['source_record_ids'])

    def test_disagreement_flags_recompute_from_original_source_values(self):
        out=ROOT/'outputs/consensus_backtest_v1_0'
        if not (out/'backtest_report.json').exists():self.skipTest('Complete backtest first')
        metrics={}
        db=sqlite3.connect((ROOT/'data/warehouse_resolved/historical_projection_warehouse.sqlite').as_uri()+'?mode=ro',uri=True)
        try:
            for typ in ('hitter','pitcher'):
                for record_id,raw in db.execute(f'SELECT record_id,metrics_json FROM analytical_{typ}_projections'):
                    metrics[record_id]=json.loads(raw)
        finally:db.close()
        with (out/'predictions.csv').open(encoding='utf-8-sig',newline='') as stream:
            for r in csv.DictReader(stream):
                values=[metrics[rid].get(r['metric']) for rid in json.loads(r['source_records']).values()]
                values=[v for v in values if isinstance(v,(int,float)) and math.isfinite(v)]
                high=False
                if len(values)>=2:
                    mean=sum(values)/len(values)
                    if mean:
                        cv=math.sqrt(sum((v-mean)**2 for v in values)/len(values))/abs(mean)
                        high=cv>=.25
                self.assertEqual(r['high_disagreement']=='True',high)


if __name__=='__main__':unittest.main()
