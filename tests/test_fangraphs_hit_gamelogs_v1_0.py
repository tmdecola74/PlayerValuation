import contextlib,io,json,shutil,tempfile,unittest
from pathlib import Path
from audit_fangraphs_hit_gamelogs_v1_0 import audit
ROOT=Path(__file__).resolve().parents[1]
INPUT=ROOT/'investigations/fangraphs_hit_review_v1_0'
class AuditTests(unittest.TestCase):
 def run_audit(self,output,logs=None,feeds=None):
  return audit(logs or INPUT/'results/source_files',INPUT/'prior_mlb_comparison',output,feeds or INPUT/'results/mlb_game_feeds')
 def test_all_15_metrics_located_and_boxes_agree(self):
  with tempfile.TemporaryDirectory() as t:
   r=self.run_audit(Path(t)/'out');self.assertEqual((r['differing_metric_rows'],r['distinct_games']),(15,5));self.assertTrue(r['all_fangraphs_logs_reproduce_original_season_totals']);self.assertFalse(r['counts_modified'])
   self.assertTrue(all(x['difference']==0 for x in r['doubleheader_date_aggregates']));self.assertTrue(all(x['fangraphs_count']==0 and x['mlb_count'] is None for x in r['unmatched_or_ambiguous_dates']))
 def test_wrong_identity_fails_without_output(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);shutil.copytree(INPUT/'results/source_files',root/'logs');p=next((root/'logs').glob('*wainwright*'));p.write_text(p.read_text().replace('425794','999999'))
   with self.assertRaises(ValueError):self.run_audit(root/'out',root/'logs')
   self.assertFalse((root/'out').exists())
 def test_bad_source_sum_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);shutil.copytree(INPUT/'results/source_files',root/'logs');p=next((root/'logs').glob('*henderson*'));lines=p.read_text().splitlines();lines.pop(1);p.write_text('\n'.join(lines)+'\n')
   with self.assertRaises(ValueError):self.run_audit(root/'out',root/'logs')
 def test_tampered_feed_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);shutil.copytree(INPUT/'results/mlb_game_feeds',root/'feeds');next((root/'feeds').glob('*.json')).write_text('{}')
   with self.assertRaises((ValueError,KeyError)):self.run_audit(root/'out',feeds=root/'feeds')
 def test_output_guard(self):
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(FileExistsError):self.run_audit(Path(t))
if __name__=='__main__':unittest.main()
