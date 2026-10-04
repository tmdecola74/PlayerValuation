import csv
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
import sys
from contextlib import closing

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_historical_projection_warehouse_v1_0 import build, clean_id, numbered_headers


class WarehouseTests(unittest.TestCase):
    def fixture(self, root, actual, projected, profile='fangraphs', extra_files=None):
        root = Path(root)
        config_dir = root / 'config'
        config_dir.mkdir()
        shipped = Path(__file__).resolve().parents[1] / 'config'
        cfg = json.loads((shipped / 'warehouse.json').read_text())
        cfg['input_roots'] = {'actuals': str(root), 'projections': str(root)}
        cfg['files'] = [dict(file='actual.csv', root='actuals', kind='actual', source='Actual', player_type='hitter', profile='fangraphs'), dict(file='projection.csv', root='projections', kind='projection', source='Test', season=2025, player_type='hitter', profile=profile)]
        cfg['files'].extend(extra_files or [])
        for name in ['metric_registry.json', 'identity_overrides.json', 'reviewed_aliases.json']:
            (config_dir / name).write_bytes((shipped / name).read_bytes())
        (config_dir / 'duplicate_resolutions.json').write_text('[]')
        (config_dir / 'warehouse.json').write_text(json.dumps(cfg))
        for name, records in [('actual.csv', actual), ('projection.csv', projected)]:
            with (root / name).open('w', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                writer.writerows(records)
        return config_dir / 'warehouse.json'

    def test_id_match_traded_player_and_unmatched_row_conservation(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg = self.fixture(temp, [['Season','Name','Team','PlayerId','MLBAMID','HR','PA'], [2025,'José A','NYY',101,201,22,420]], [['Name','Team','PlayerId','MLBAMID','HR','PA'], ['Jose A','BOS',101,201,30,600], ['Minor Player','FA',102,202,5,0]])
            before = hashlib.sha256((Path(temp)/'projection.csv').read_bytes()).hexdigest()
            report = build(cfg)
            self.assertEqual((report['matched_projection_rows'], report['unmatched_projection_rows'], report['stored_rows']), (1,1,3))
            with closing(sqlite3.connect(Path(temp)/'data/warehouse/historical_projection_warehouse.sqlite')) as db:
                values = db.execute('SELECT metrics_json,raw_json,match_status FROM hitter_projections ORDER BY row_number').fetchall()
                self.assertAlmostEqual(json.loads(values[0][0])['HR_per_PA'], .05)
                self.assertEqual(json.loads(values[0][1])['HR'], '30')
                self.assertNotIn('HR_per_PA',json.loads(values[1][0]))
            self.assertEqual(before, hashlib.sha256((Path(temp)/'projection.csv').read_bytes()).hexdigest())

    def test_rotowire_namespace_does_not_equal_fangraphs(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp, [['Season','Name','Team','PlayerId'],[2025,'Different Player','ATL',100]], [['Player','Team','PlayerID'],['Other Person','ATL',100]], 'rotowire')
            report=build(cfg)
            self.assertEqual(report['matched_projection_rows'],0)

    def test_unique_name_bridge_and_ambiguous_name(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp, [['Season','Name','Team','PlayerId'],[2025,'José Uno','ATL',1],[2025,'Same Name','BOS',2],[2025,'Same Name','NYY',3]], [['Player','Team','PlayerID'],['Jose Uno','FA',123],['Same Name','BOS',124]], 'rotowire')
            report=build(cfg)
            self.assertEqual(report['matched_projection_rows'],1)
            self.assertEqual(report['unmatched_reasons'],{'ambiguous_name':1})

    def test_conflicting_id_edges_block_matches(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId','MLBAMID'],[2025,'A',1,10],[2025,'B',2,10]], [['Name','PlayerId','MLBAMID'],['A',1,10]])
            report=build(cfg)
            self.assertEqual(report['status'],'review_required')
            self.assertEqual(report['matched_projection_rows'],0)
            self.assertEqual(report['identity_conflict_components'],1)

    def test_prospect_alias_requires_anchor_and_agreeing_names(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId','MLBAMID'],[2025,'A',1,10]], [['Name','PlayerId','MLBAMID'],['A','sa123',10]])
            report=build(cfg)
            self.assertEqual(report['matched_projection_rows'],1)
            self.assertEqual(report['accepted_id_alias_components'],1)
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId','MLBAMID'],[2025,'A',1,10]], [['Name','PlayerId','MLBAMID'],['B','sa123',10]])
            report=build(cfg)
            self.assertEqual(report['matched_projection_rows'],0)
            self.assertEqual(report['identity_conflict_components'],1)

    def test_name_collision_in_rotowire_blocks_both_bridges(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId'],[2025,'Same Name',1]], [['Player','PlayerID'],['Same Name',123],['Same Name',124]], 'rotowire')
            report=build(cfg)
            self.assertEqual(report['matched_projection_rows'],0)
            self.assertEqual(report['unmatched_reasons'],{'ambiguous_name':2})

    def test_reviewed_alias_requires_exact_ids_and_preserves_names(self):
        for anchor, expected in [(10,1),(11,0)]:
            with tempfile.TemporaryDirectory() as temp:
                cfg=self.fixture(temp,[['Season','Name','PlayerId','MLBAMID'],[2025,'Dominic',1,10]], [['Name','PlayerId','MLBAMID'],['Dom','sa123',10]])
                entry={'ids':[['fangraphs','1'],['fangraphs','sa123'],['mlbam',str(anchor)]],'verified_by':'owner','reason':'confirmed same player'}
                (cfg.parent/'reviewed_aliases.json').write_text(json.dumps([entry]))
                report=build(cfg)
                self.assertEqual(report['matched_projection_rows'],expected)
                with closing(sqlite3.connect(Path(temp)/'data/warehouse/historical_projection_warehouse.sqlite')) as db:
                    self.assertEqual(db.execute('SELECT name FROM hitter_projections').fetchone()[0],'Dom')

    def test_duplicate_actuals_are_retained_without_join_expansion(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId'],[2025,'A',1],[2025,'A',1]], [['Name','PlayerId'],['A',1]])
            report=build(cfg)
            self.assertEqual(report['stored_rows'],3)
            self.assertEqual(report['unmatched_reasons'],{'duplicate_actual_key':1})
            self.assertEqual(report['status'],'review_required')

    def test_bad_number_missing_season_and_duplicate_headers_survive(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId','HR/FB','HR/FB'],['wrong','A',1,.1,.2]], [['Name','PlayerId','HR'],['A',1,'broken']])
            report=build(cfg)
            self.assertEqual(report['status'],'review_required')
            self.assertEqual(report['parsing_issues'],2)
            with closing(sqlite3.connect(Path(temp)/'data/warehouse/historical_projection_warehouse.sqlite')) as db:
                raw=json.loads(db.execute('SELECT raw_json FROM hitter_actuals').fetchone()[0])
                self.assertEqual(raw['HR/FB__2'],'0.2')

    def test_xlsx_alias_percent_and_baseball_ip(self):
        import openpyxl
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId'],[2025,'A',1]], [['Name','PlayerId'],['A',1]])
            book=openpyxl.Workbook()
            sheet=book.active
            sheet.append(['Player','PlayerID','IP','K','BB%','SV','HLD'])
            sheet.append(['P',123,'10.2',12,'10%',5,7])
            book.save(Path(temp)/'pitcher.xlsx')
            data=json.loads(cfg.read_text())
            data['files'].append(dict(file='pitcher.xlsx',root='projections',kind='projection',source='RotoWire',season=2025,player_type='pitcher',profile='rotowire',ip_notation='baseball'))
            cfg.write_text(json.dumps(data))
            build(cfg)
            with closing(sqlite3.connect(Path(temp)/'data/warehouse/historical_projection_warehouse.sqlite')) as db:
                stats=json.loads(db.execute('SELECT metrics_json FROM pitcher_projections').fetchone()[0])
                self.assertAlmostEqual(stats['IP'],10+2/3)
                self.assertEqual(stats['SO'],12)
                self.assertAlmostEqual(stats['BB%'],.1)
                self.assertEqual(stats['SV_plus_HLD'],12)

    def test_missing_file_and_existing_output_fail_safely(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId'],[2025,'A',1]], [['Name','PlayerId'],['A',1]])
            build(cfg)
            with self.assertRaises(ValueError):build(cfg)
            (Path(temp)/'projection.csv').unlink()
            new=Path(temp)/'new_output'
            with self.assertRaises(FileNotFoundError):build(cfg,new)
            self.assertFalse(new.exists())

    def test_duplicate_selection_keeps_raw_and_suppresses_unresolved_metrics(self):
        with tempfile.TemporaryDirectory() as temp:
            cfg=self.fixture(temp,[['Season','Name','PlayerId'],[2025,'A',1]], [['Name','PlayerId','PA','WAR'],['A',1,1,2],['A',1,100,3]])
            build(cfg)
            with closing(sqlite3.connect(Path(temp)/'data/warehouse/historical_projection_warehouse.sqlite')) as db:
                rows=db.execute('SELECT record_id FROM hitter_projections ORDER BY row_number').fetchall()
            entry={'candidate_record_ids':[r[0] for r in rows],'selected_record_id':rows[1][0], 'verified_by':'owner','reason':'larger PA; WAR unresolved','exclude_metrics':['WAR']}
            (cfg.parent/'duplicate_resolutions.json').write_text(json.dumps([entry]))
            new=Path(temp)/'resolved'
            report=build(cfg,new)
            self.assertEqual(report['status'],'passed_with_metric_exclusions')
            self.assertEqual(report['unresolved_duplicate_groups'],0)
            with closing(sqlite3.connect(new/'historical_projection_warehouse.sqlite')) as db:
                self.assertEqual(db.execute('SELECT COUNT(*) FROM hitter_projections').fetchone()[0],2)
                analytical=db.execute('SELECT metrics_json FROM analytical_hitter_projections').fetchall()
                self.assertEqual(len(analytical),1)
                self.assertEqual(json.loads(analytical[0][0])['PA'],100)
                self.assertNotIn('WAR',json.loads(analytical[0][0]))
                self.assertEqual(db.execute("SELECT json_extract(metrics_json,'$.WAR') FROM hitter_projections ORDER BY row_number").fetchall(),[(2.0,),(3.0,)])
            entry['candidate_record_ids']=['stale',rows[1][0]]
            (cfg.parent/'duplicate_resolutions.json').write_text(json.dumps([entry]))
            with self.assertRaises(ValueError):build(cfg,Path(temp)/'stale')
            self.assertFalse((Path(temp)/'stale').exists())

    def test_id_and_headers(self):
        self.assertEqual(clean_id('sa123'),'sa123')
        self.assertEqual(clean_id('123.0'),'123')
        self.assertEqual(numbered_headers(['FB%','FB%']),['FB%','FB%__2'])


if __name__ == '__main__':
    unittest.main()
