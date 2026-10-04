"""Integration checks against the delivered 22-file build; skipped until built."""
import hashlib
import json
import sqlite3
import unittest
from contextlib import closing
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[1]
WAREHOUSE = next((PROJECT/'data'/name for name in ['warehouse_resolved','warehouse_reviewed','warehouse'] if (PROJECT/'data'/name).exists()), PROJECT/'data/warehouse')
sys.path.insert(0,str(PROJECT))
from build_historical_projection_warehouse_v1_0 import read_rows


@unittest.skipUnless((WAREHOUSE/'historical_projection_warehouse.sqlite').exists(), 'Run builder first')
class DeliveredDataTests(unittest.TestCase):
    @unittest.skipUnless((PROJECT/'data/warehouse_resolved').exists(),'Run resolved build first')
    def test_reviewed_oopsy_selections_and_greg_metric_exclusions(self):
        with closing(sqlite3.connect(WAREHOUSE/'historical_projection_warehouse.sqlite')) as db:
            for typ in ['hitter','pitcher']:
                duplicates=db.execute(f'SELECT COUNT(*) FROM (SELECT season,source,player_id FROM analytical_{typ}_projections GROUP BY season,source,player_id HAVING COUNT(*)>1)').fetchone()[0]
                self.assertEqual(duplicates,0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM record_selection WHERE selection_reason='reviewed_duplicate_not_selected'").fetchone()[0],16)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM hitter_projections WHERE source='OOPSY' AND name='Greg Jones' AND season=2025").fetchone()[0],2)
            stats=json.loads(db.execute("SELECT metrics_json FROM analytical_hitter_projections WHERE source='OOPSY' AND name='Greg Jones' AND season=2025").fetchone()[0])
            for metric in ['WAR','wRC+','Off','Def']:self.assertNotIn(metric,stats)
            self.assertIn('HR',stats)
            for table,exposure in [('hitter_projections','PA'),('pitcher_projections','IP')]:
                for selected in db.execute(f"SELECT p.player_id,s.analytical_metrics_json FROM {table} p JOIN record_selection s USING(record_id) WHERE s.selection_reason='reviewed_duplicate_selected'").fetchall():
                    maximum=db.execute(f"SELECT MAX(json_extract(metrics_json,?)) FROM {table} WHERE player_id=? AND source='OOPSY' AND season=2025",('$.'+exposure,selected[0])).fetchone()[0]
                    self.assertEqual(json.loads(selected[1])[exposure],maximum)

    def test_all_source_rows_roundtrip_and_sources_unchanged(self):
        report=json.loads((WAREHOUSE/'audit/validation_report.json').read_text(encoding='utf-8'))
        cfg=json.loads((WAREHOUSE/'effective_config.json').read_text(encoding='utf-8'))
        specs={s['file']:s for s in cfg['files']}
        with closing(sqlite3.connect(WAREHOUSE/'historical_projection_warehouse.sqlite')) as db:
            total=0
            for run in report['inputs']:
                path=Path(run['original_file'])
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),run['sha256'])
                headers,rows=read_rows(path,specs[path.name])
                self.assertEqual(headers,run['headers'])
                table=run['player_type']+('_projections' if run['kind']=='projection' else '_actuals')
                stored={line:json.loads(raw) for line,raw in db.execute(f'SELECT row_number,raw_json FROM {table} WHERE run_id=?',(run['run_id'],))}
                self.assertEqual(dict(rows),stored)
                total+=len(rows)
            self.assertEqual(total,report['stored_rows'])
            self.assertEqual(total,57855)

    def test_actual_seasons_and_uneven_projection_coverage(self):
        with closing(sqlite3.connect(WAREHOUSE/'historical_projection_warehouse.sqlite')) as db:
            self.assertEqual(dict(db.execute('SELECT season,COUNT(*) FROM hitter_actuals GROUP BY season')),{2024:651,2025:673,2026:662})
            self.assertEqual(dict(db.execute('SELECT season,COUNT(*) FROM pitcher_actuals GROUP BY season')),{2024:840,2025:864,2026:858})
            self.assertEqual(db.execute('SELECT COUNT(*) FROM projection_runs').fetchone()[0],20)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM projection_runs WHERE source='OOPSY' AND season=2024").fetchone()[0],0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM projection_runs WHERE source='Depth Charts'").fetchone()[0],2)

    def test_matched_rows_have_exact_season_player_and_type(self):
        with closing(sqlite3.connect(WAREHOUSE/'historical_projection_warehouse.sqlite')) as db:
            for typ in ['hitter','pitcher']:
                invalid=db.execute(f'''SELECT COUNT(*) FROM {typ}_projections p
                    LEFT JOIN {typ}_actuals a ON p.actual_record_id=a.record_id
                    WHERE p.match_status='matched' AND (a.record_id IS NULL OR
                    p.season!=a.season OR p.player_id!=a.player_id OR
                    p.identity_conflict=1 OR a.identity_conflict=1)''').fetchone()[0]
                self.assertEqual(invalid,0)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(),[])


if __name__=='__main__':
    unittest.main()
