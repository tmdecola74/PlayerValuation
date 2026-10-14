import csv
import hashlib
import json
import math
import sqlite3
import unittest
from collections import defaultdict
from contextlib import closing
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[1]
RESULTS=PROJECT/'outputs/consensus_2026_v1_0'


@unittest.skipUnless((RESULTS/'audit/consensus_report.json').exists(),'Run consensus builder first')
class DeliveredConsensusTests(unittest.TestCase):
    def test_all_projection_players_and_original_record_ids_are_preserved(self):
        report=json.loads((RESULTS/'audit/consensus_report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['source_projection_rows'],21813)
        self.assertEqual(report['hitter_players'],4376);self.assertEqual(report['pitcher_players'],5587)
        self.assertEqual(hashlib.sha256(Path(report['warehouse']).read_bytes()).hexdigest(),report['warehouse_sha256'])
        with closing(sqlite3.connect(PROJECT/'data/warehouse_resolved/historical_projection_warehouse.sqlite')) as db:
            for typ in ['hitter','pitcher']:
                output=json.loads((RESULTS/f'{typ}_consensus.json').read_text(encoding='utf-8'))
                self.assertEqual(len(output),len({r['player_id'] for r in output}))
                incoming={r[0] for r in db.execute(f'SELECT player_id FROM analytical_{typ}_projections WHERE season=2026')}
                self.assertEqual(incoming,{r['player_id'] for r in output})
                expected_records=defaultdict(dict)
                for pid,source,record_id in db.execute(f'SELECT player_id,source,record_id FROM analytical_{typ}_projections WHERE season=2026'):
                    expected_records[pid][source]=record_id
                for r in output:
                    self.assertEqual(expected_records[r['player_id']],r['source_record_ids'])

    def test_rates_match_published_components_and_base_weights_recompute(self):
        for typ in ['hitter','pitcher']:
            output=json.loads((RESULTS/f'{typ}_consensus.json').read_text(encoding='utf-8'))
            for r in output:
                m=r['metrics']
                if typ=='hitter':
                    if m['AB'] is not None and m['AB']>0 and m['H'] is not None:self.assertAlmostEqual(m['AVG'],m['H']/m['AB'])
                    else:self.assertIsNone(m['AVG'])
                    if m['OBP'] is not None and m['SLG'] is not None:self.assertAlmostEqual(m['OPS'],m['OBP']+m['SLG'])
                    else:self.assertIsNone(m['OPS'])
                else:
                    if m['IP'] is not None and m['IP']>0:
                        if m['ER'] is not None:self.assertAlmostEqual(m['ERA'],9*m['ER']/m['IP'])
                        if m['H'] is not None and m['BB'] is not None:self.assertAlmostEqual(m['WHIP'],(m['H']+m['BB'])/m['IP'])
                    else:self.assertIsNone(m['ERA']);self.assertIsNone(m['WHIP'])
                    if m['SV'] is not None and m['HLD'] is not None:self.assertAlmostEqual(m['SV_plus_HLD'],m['SV']+m['HLD'])
                    else:self.assertIsNone(m['SV_plus_HLD'])
        with (RESULTS/'metric_provenance.csv').open(encoding='utf-8-sig',newline='') as stream:
            for r in csv.DictReader(stream):
                if r['method']!='weighted_available_source_mean' or not r['consensus']:continue
                weights=json.loads(r['normalized_weights']);values=json.loads(r['source_values'])
                self.assertAlmostEqual(sum(weights.values()),1)
                self.assertTrue(all(w>0 for w in weights.values()))
                self.assertAlmostEqual(float(r['consensus']),sum(weights[s]*values[s] for s in weights))


if __name__=='__main__':unittest.main()
