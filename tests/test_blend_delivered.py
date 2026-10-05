import csv
import hashlib
import json
import unittest
from collections import defaultdict
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
RESULTS=PROJECT/'outputs/blend_backtest_v1_0'


@unittest.skipUnless((RESULTS/'backtest_report.json').exists(),'Run blend backtest first')
class DeliveredBlendTests(unittest.TestCase):
    def test_weights_and_frozen_chronology(self):
        report=json.loads((RESULTS/'backtest_report.json').read_text())
        self.assertEqual(hashlib.sha256(Path(report['warehouse']).read_bytes()).hexdigest(),report['warehouse_sha256'])
        groups=defaultdict(list)
        with (RESULTS/'fold_weights.csv').open(encoding='utf-8-sig') as stream:
            for r in csv.DictReader(stream):groups[(r['sample_id'],r['method'])].append(r)
        for rows in groups.values():
            self.assertAlmostEqual(sum(float(r['weight']) for r in rows),1)
            self.assertTrue(all(float(r['weight'])>=0 for r in rows))
            for r in rows:
                if r['provenance']=='neutral_share_incomplete_history':self.assertAlmostEqual(float(r['weight']),1/len(rows))
                if r['method']=='fitted_rmse_ridge':self.assertTrue(json.loads(r['optimizer'])['converged'])
        with (RESULTS/'sample_memberships.jsonl').open() as stream:
            for line in stream:
                sample=json.loads(line)
                self.assertTrue(all(r['season']<sample['test_season'] for r in sample['training_player_seasons']))
                self.assertTrue(all(y<sample['test_season'] for y in sample['train_seasons']))

    def test_every_forecast_recomputes_and_methods_use_same_test_players(self):
        weights=defaultdict(dict)
        with (RESULTS/'fold_weights.csv').open(encoding='utf-8-sig') as stream:
            for r in csv.DictReader(stream):weights[(r['sample_id'],r['method'])][r['source']]=float(r['weight'])
        players=defaultdict(lambda:defaultdict(set))
        with (RESULTS/'heldout_predictions.csv').open(encoding='utf-8-sig') as stream:
            for r in csv.DictReader(stream):
                key=(r['sample_id'],r['method']);sources=json.loads(r['source_predictions'])
                predicted=sum(weights[key][s]*v for s,v in sources.items())
                self.assertAlmostEqual(predicted,float(r['predicted']),places=10)
                self.assertAlmostEqual(float(r['predicted'])-float(r['actual']),float(r['error']),places=10)
                players[r['sample_id']][r['method']].add(r['player_id'])
        for methods in players.values():
            equal=methods['equal']
            self.assertTrue(all(pids==equal for pids in methods.values()))
        with (RESULTS/'category_assessments.csv').open(encoding='utf-8-sig') as stream:
            for r in csv.DictReader(stream):self.assertEqual(json.loads(r['heldout_years']),[2025,2026])


if __name__=='__main__':unittest.main()
