import csv
import json
import tempfile
import unittest
from pathlib import Path
from scan_actuals_discrepancies_v1_0 import build, sha, flags

class ScanTests(unittest.TestCase):
    def fixture(self, root):
        raw = root/'raw.csv'
        raw.write_text('game_pk,at_bat_number,pitch_number,batter,pitcher,events\n1,1,1,10,20,\n1,1,2,10,20,catcher_interf\n1,2,1,11,20,single\n')
        source = root/'source_windows.json'
        source.write_text(json.dumps([dict(day='2016-04-01', status='COMPLETE', raw_path=str(raw), raw_hash=sha(raw))]))
        d = root/'discrepancies.csv'
        d.write_text('season,player_type,mlbam_id,name,metric,final_difference\n2016,hitter,10,Test,PA,-10\n')
        return raw,source,d

    def test_frozen_target_and_backup(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,s,d=self.fixture(root);before=sha(raw)
            r=build(s,d,root/'out',root/'backups')
            self.assertEqual(r['recorded_pa_groups'],1)
            self.assertEqual(r['candidate_games'],1)
            self.assertEqual(sha(raw),before)
            self.assertEqual(sha(root/'out/scan_report.json'),sha(Path(r['backup'])/'scan_report.json'))
            with self.assertRaises(FileExistsError):build(s,d,root/'out',root/'backups')

    def test_tamper_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);raw,s,d=self.fixture(root);raw.write_text('bad')
            with self.assertRaises(ValueError):build(s,d,root/'out',root/'backups')
            self.assertFalse((root/'out').exists())

    def test_missing_terminal_and_change_are_leads(self):
        rows=[dict(batter='10',pitcher='20',pitch_number='1',events=''),dict(batter='11',pitcher='20',pitch_number='3',events='')]
        self.assertEqual(set(flags(rows)),{'NO_RECORDED_TERMINAL_EVENT','PLAYER_CHANGE','PITCH_SEQUENCE_GAP_OR_DUPLICATE'})

if __name__=='__main__':unittest.main()
