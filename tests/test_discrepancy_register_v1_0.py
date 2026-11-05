import copy,json,shutil,tempfile,unittest
from pathlib import Path
from build_discrepancy_register_v1_0 import build,tree
from modeling_labels_v1_0 import decision,resolve_label,resolve_bundle
ROOT=Path(__file__).resolve().parents[1]
POL=ROOT/'config/modeling_label_policy_v1_0.json';CONF=ROOT/'config/play_log_year_confirmation_v1_0.json';EV=ROOT/'evidence/discrepancy_register_v1_0'
class RegisterTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.policy=json.loads(POL.read_text(encoding='utf-8-sig'));cls.rows=json.loads((ROOT/'outputs/discrepancy_register_v1_0/discrepancy_register.json').read_text(encoding='utf-8-sig'));cls.ref=cls.policy['expected_reference_hashes']['actual_counts.parquet']
 def test_real_build_32_cases_classification_backup_and_source_immutable(self):
  before=tree(EV)
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);r=build(EV,POL,CONF,p/'out',p/'backups');self.assertEqual(r['classifications'],{'NOT_RECLASSIFIED_BY_HIT_REVIEW':17,'FANGRAPHS_PLAY_TEXT_VS_EXPORTED_TOTALS':12,'CROSS_PROVIDER_SINGLE_VS_ERROR':3});self.assertEqual(tree(p/'out'),tree(Path(r['backup'])));self.assertEqual(before,tree(EV));self.assertFalse(r['model_ready'])
 def test_stable_ids_and_no_count_replacement(self):
  self.assertEqual(len({r['case_id'] for r in self.rows}),32)
  for r in self.rows:self.assertFalse(r['source_count_modified']);self.assertEqual(r['status'],'UNRESOLVED_DIFFERENCE')
 def test_hitter_dependencies_and_independent_hr(self):
  for m in ['H','1B','2B','AVG','OBP','SLG','OPS','ISO','BABIP']:
   if m=='2B':pid='425794'
   else:pid='670768'
   self.assertFalse(decision(2022 if pid=='670768' else 2016,'hitter',pid,m,self.rows,self.policy)['eligible'])
  self.assertTrue(decision(2022,'hitter','670768','HR',self.rows,self.policy)['eligible'])
 def test_pa_tbf_denominator_and_pitcher_whip(self):
  self.assertFalse(decision(2015,'hitter','581527','K%',self.rows,self.policy)['eligible'])
  self.assertFalse(decision(2015,'pitcher','523260','BB%',self.rows,self.policy)['eligible'])
  self.assertFalse(decision(2022,'pitcher','621249','WHIP',self.rows,self.policy)['eligible'])
  self.assertTrue(decision(2022,'pitcher','621249','ERA',self.rows,self.policy)['eligible'])
 def test_no_cross_source_substitution_and_unknown_metric(self):
  r=resolve_label(2022,'hitter','670768','H',{'H':78},self.rows,self.policy,self.ref);self.assertIsNone(r['value']);self.assertFalse(r['eligible']);self.assertEqual(r['source'],'FROZEN_FANGRAPHS_ACTUALS')
  self.assertFalse(decision(2022,'hitter','1','NEW_METRIC',self.rows,self.policy)['eligible'])
 def test_holdout_forbidden_for_training_and_explicit_evaluation(self):
  self.assertFalse(decision(2026,'hitter','1','HR',self.rows,self.policy)['eligible'])
  self.assertTrue(decision(2026,'hitter','1','HR',self.rows,self.policy,'holdout_evaluation')['eligible'])
  self.assertFalse(decision(2027,'hitter','1','HR',self.rows,self.policy,'holdout_evaluation')['eligible'])
 def test_missing_zero_and_integer_outs(self):
  f=lambda metric,counts:resolve_label(2024,'pitcher','999',metric,counts,self.rows,self.policy,self.ref)
  self.assertEqual(f('SV',{'SV':0})['value'],0)
  self.assertFalse(f('SV',{})['eligible']);self.assertFalse(f('ERA',{'OUTS':0,'ER':0})['eligible']);self.assertAlmostEqual(f('IP',{'OUTS':22})['value'],22/3)
  self.assertFalse(f('SV',{'SV':float('nan')})['eligible'])
 def test_joint_vector_rejected_and_coherent_components(self):
  r=resolve_bundle(2022,'hitter','670768',['H','HR'],{'H':79,'HR':4},self.rows,self.policy,self.ref);self.assertFalse(r['eligible']);self.assertIsNone(r['values'])
  r=resolve_label(2024,'hitter','999','AVG',{'H':8,'AB':5},self.rows,self.policy,self.ref);self.assertFalse(r['eligible'])
  r=resolve_label(2024,'hitter','999','AVG',{'H':8,'AB':20,'1B':1,'2B':1,'3B':0,'HR':1},self.rows,self.policy,self.ref);self.assertFalse(r['eligible'])
 def test_snapshot_guard_and_output_guard(self):
  with self.assertRaises(ValueError):resolve_label(2024,'hitter','1','HR',{'HR':0},self.rows,self.policy,'wrong')
  with tempfile.TemporaryDirectory() as t:
   with self.assertRaises(FileExistsError):build(EV,POL,CONF,t,Path(t)/'b')
 def test_changed_confirmation_and_tampered_evidence_rejected(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);c=json.loads(CONF.read_text(encoding='utf-8-sig'));c['expected_dates'][0]='2026-09-27';(p/'confirmation.json').write_text(json.dumps(c),encoding='utf-8')
   with self.assertRaises(ValueError):build(EV,POL,p/'confirmation.json',p/'out',p/'backups')
   shutil.copytree(EV,p/'evidence');next((p/'evidence/hit_review/results/mlb_game_feeds').glob('449213.json')).write_text('{}',encoding='utf-8')
   with self.assertRaises(ValueError):build(p/'evidence',POL,CONF,p/'out',p/'backups')
   self.assertFalse((p/'out').exists())
 def test_windows_cp1252_default_does_not_decode_utf8_sources(self):
  from unittest.mock import patch
  original_read=Path.read_text
  original_write=Path.write_text
  def windows_read(path,encoding=None,errors=None,**kwargs):
   return original_read(path,encoding=encoding or 'cp1252',errors=errors,**kwargs)
  def windows_write(path,data,encoding=None,errors=None,**kwargs):
   return original_write(path,data,encoding=encoding or 'cp1252',errors=errors,**kwargs)
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)
   with patch.object(Path,'read_text',windows_read),patch.object(Path,'write_text',windows_write):
    r=build(EV,POL,CONF,p/'out',p/'backup')
   self.assertEqual(r['baseline_discrepancy_rows'],32)
   self.assertEqual(r['build_implementation_version'],'1.0.1')
   self.assertEqual(tree(p/'out'),tree(Path(r['backup'])))
   text=(p/'out/discrepancy_register.json').read_text(encoding='utf-8')
   self.assertIn('González',text)
if __name__=='__main__':unittest.main()
