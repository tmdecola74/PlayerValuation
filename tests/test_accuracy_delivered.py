import csv
import hashlib
import json
import sqlite3
import unittest
from pathlib import Path
from contextlib import closing
from collections import defaultdict

PROJECT=Path(__file__).resolve().parents[1]
RESULTS=PROJECT/'outputs/accuracy_v1_0'


@unittest.skipUnless((RESULTS/'evaluation_report.json').exists(),'Run Stage 2 first')
class DeliveredAccuracyTests(unittest.TestCase):
    def test_report_accounts_for_selected_projections_and_keeps_database_unchanged(self):
        report=json.loads((RESULTS/'evaluation_report.json').read_text(encoding='utf-8'))
        self.assertEqual(report['selected_projection_rows'],53291)
        self.assertEqual(report['matched_projection_rows'],13497)
        self.assertEqual(report['unmatched_projection_rows'],39794)
        self.assertEqual(report['matched_projection_rows']+report['unmatched_projection_rows'],report['selected_projection_rows'])
        self.assertEqual(hashlib.sha256(Path(report['warehouse']).read_bytes()).hexdigest(),report['warehouse_sha256'])
        with closing(sqlite3.connect(PROJECT/'data/warehouse_resolved/historical_projection_warehouse.sqlite')) as db:
            raw=json.loads(db.execute("SELECT metrics_json FROM analytical_hitter_projections WHERE name='Greg Jones' AND season=2025 AND source='OOPSY'").fetchone()[0])
            self.assertTrue(all(k not in raw for k in ['WAR','Off','Def','wRC+']))

    def test_every_common_sample_has_identical_players_and_counts(self):
        samples={}
        with (RESULTS/'cohort_memberships.jsonl').open(encoding='utf-8') as stream:
            for line in stream:
                row=json.loads(line);samples[row['sample_id']]=row
        summaries=defaultdict(list)
        with (RESULTS/'accuracy_summary.csv').open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                sample=samples[row['sample_id']]
                self.assertEqual(int(row['n']),len(sample['player_ids']))
                summaries[row['sample_id']].append(row)
        for sample_id,rows in summaries.items():
            self.assertEqual(sorted(r['source'] for r in rows),sorted(samples[sample_id]['sources']))
            self.assertEqual(len({r['n'] for r in rows}),1)
        # Check membership against paired values instead of trusting counts alone.
        pairs=set()
        with (RESULTS/'evaluation_pairs.csv').open(encoding='utf-8-sig',newline='') as stream:
            for row in csv.DictReader(stream):
                pairs.add((row['player_type'],int(row['season']),row['source'],row['metric'],row['player_id']))
        for sample in samples.values():
            for source in sample['sources']:
                for pid in sample['player_ids']:
                    self.assertIn((sample['player_type'],sample['season'],source,sample['metric'],pid),pairs)


if __name__=='__main__':unittest.main()
