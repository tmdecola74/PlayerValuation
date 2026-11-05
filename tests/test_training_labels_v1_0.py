import copy,csv,json,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import duckdb
from build_training_labels_v1_0 import build,sha,tree
from training_label_rules_v1_0 import COUNTS
ROOT=Path(__file__).resolve().parents[1]

def dump(p,v):p.write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8')
def parquet(path,rows,fields,types):
 with path.with_suffix('.csv').open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 with duckdb.connect() as db:db.read_csv(str(path.with_suffix('.csv')),header=True,columns=types).write_parquet(str(path))
def refresh(root):
 policy=json.loads((root/'reg/modeling_label_policy.json').read_text(encoding='utf-8'))
 policy['expected_reference_hashes']={n:sha(root/'ref'/n) for n in ['actual_counts.parquet','player_seasons.parquet']};dump(root/'reg/modeling_label_policy.json',policy)
 dump(root/'reg/output_sha256.json',{n:sha(root/'reg'/n) for n in ['modeling_label_policy.json','discrepancy_register.json','build_report.json']})
def fixture(root,holdout_h=20):
 (root/'ref').mkdir();(root/'reg').mkdir();cfg=json.loads((ROOT/'config/training_labels_v1_0.json').read_text());cfg['training_seasons']=[2024,2025];dump(root/'config.json',cfg)
 players=[];rows=[]
 for y in [2024,2025,2026]:
  for role,pid in [('hitter','1'),('pitcher','2')]:
   split='holdout' if y==2026 else 'historical';p=dict(season=y,player_type=role,mlbam_id=pid,split=split);players.append(p)
   c={m:0 for m in COUNTS[role]}
   if role=='hitter':c.update(G=20,PA=60,AB=50,H=holdout_h if y==2026 else 20,**{'1B':(holdout_h if y==2026 else 20)-5,'2B':3,'3B':0,'HR':2})
   else:c.update(G=1,OUTS=0 if y==2025 else 22,H=3,ER=1,R=1,SO=7)
   for m,v in c.items():rows.append(p|dict(metric=m,value=v))
 fields=['season','player_type','mlbam_id','split'];types={'season':'INTEGER','player_type':'VARCHAR','mlbam_id':'BIGINT','split':'VARCHAR'}
 parquet(root/'ref/player_seasons.parquet',players,fields,types)
 parquet(root/'ref/actual_counts.parquet',rows,fields+['metric','value'],types|{'metric':'VARCHAR','value':'BIGINT'})
 policy=dict(version='1.0.0',primary_season_label_source='FROZEN_FANGRAPHS_ACTUALS',expected_reference_hashes={},cross_source_component_substitution=False,disputed_metric_action='EXCLUDE_METRIC_AND_DEPENDENT_LABELS',training_max_season=2025,holdout_season=2026)
 dump(root/'reg/modeling_label_policy.json',policy);dump(root/'reg/discrepancy_register.json',[dict(season=2024,player_type='hitter',mlbam_id='1',metric='H',fangraphs_actual=20,case_id='case_fixture')]);dump(root/'reg/build_report.json',{'baseline_discrepancy_rows':1});refresh(root)
 return players,rows,types
class LabelTests(unittest.TestCase):
 def run_build(self,p,out='out'):return build(p/'ref',p/'reg',p/'config.json',p/out,p/'backups')
 def csv(self,p):
  with p.open(encoding='utf-8',newline='') as f:return list(csv.DictReader(f))
 def test_full_materialization_masks_zero_outs_and_complete_backup(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);before=tree(p/'ref');r=self.run_build(p);self.assertEqual(before,tree(p/'ref'));self.assertEqual(tree(p/'out'),tree(Path(r['backup'])))
   train=self.csv(p/'out/training_labels.csv');hold=self.csv(p/'out/holdout_labels.csv');audit=self.csv(p/'out/training_label_audit.csv')
   self.assertTrue(train and hold);self.assertTrue(all(int(x['season'])<=2025 for x in train));self.assertTrue(all(x['season']=='2026' for x in hold))
   self.assertFalse(any(x['season']=='2024' and x['player_type']=='hitter' and x['metric'] in ['H','AVG','SLG','OBP','OPS'] for x in train));self.assertTrue(any(x['metric']=='HR' and x['season']=='2024' for x in train))
   self.assertTrue(any(x['metric']=='SV' and float(x['label_value'])==0 for x in train));self.assertTrue(any(x['metric']=='ERA' and x['season']=='2025' and x['eligible']=='False' and x['label_value']=='' for x in audit))
   self.assertAlmostEqual(float(next(x['label_value'] for x in train if x['metric']=='IP' and x['season']=='2024')),22/3)
   with duckdb.connect() as db:self.assertEqual(db.read_parquet(str(p/'out/training_labels.parquet')).count('*').fetchall()[0][0],len(train))
 def test_holdout_changes_cannot_change_training_labels(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);a=p/'a';b=p/'b';a.mkdir();b.mkdir();fixture(a,20);fixture(b,25);self.run_build(a);self.run_build(b)
   self.assertEqual((a/'out/training_labels.csv').read_bytes(),(b/'out/training_labels.csv').read_bytes());self.assertNotEqual((a/'out/holdout_labels.csv').read_bytes(),(b/'out/holdout_labels.csv').read_bytes());self.assertEqual((a/'out/training_joint_bundles.csv').read_bytes(),(b/'out/training_joint_bundles.csv').read_bytes())
 def test_frozen_hash_and_register_tamper_fail_without_output(self):
  for target in ['ref/actual_counts.parquet','reg/discrepancy_register.json']:
   with tempfile.TemporaryDirectory() as t:
    p=Path(t);fixture(p);(p/target).write_bytes(b'tampered')
    with self.assertRaises(ValueError):self.run_build(p)
    self.assertFalse((p/'out').exists())
 def test_duplicate_or_orphan_counts_and_wrong_split(self):
  for mode in ['duplicate','orphan','split']:
   with tempfile.TemporaryDirectory() as t:
    p=Path(t);players,rows,types=fixture(p)
    if mode=='duplicate':rows.append(rows[0])
    elif mode=='orphan':rows[0]['mlbam_id']='999'
    else:rows[0]['split']='holdout'
    parquet(p/'ref/actual_counts.parquet',rows,['season','player_type','mlbam_id','split','metric','value'],types|{'metric':'VARCHAR','value':'BIGINT'});refresh(p)
    with self.assertRaises(ValueError):self.run_build(p)
 def test_missing_primitive_is_masked_never_zero(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);players,rows,types=fixture(p);rows=[r for r in rows if not(r['season']==2025 and r['player_type']=='hitter' and r['metric']=='HR')];parquet(p/'ref/actual_counts.parquet',rows,['season','player_type','mlbam_id','split','metric','value'],types|{'metric':'VARCHAR','value':'BIGINT'});refresh(p);self.run_build(p)
   x=next(r for r in self.csv(p/'out/training_label_audit.csv') if r['season']=='2025' and r['player_type']=='hitter' and r['metric']=='HR');self.assertEqual(x['eligible'],'False');self.assertEqual(x['label_value'],'')
 def test_missing_registered_case_and_reference_baseline_difference(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);r=json.loads((p/'reg/discrepancy_register.json').read_text());r[0]['fangraphs_actual']=21;dump(p/'reg/discrepancy_register.json',r);refresh(p)
   with self.assertRaises(ValueError):self.run_build(p)
 def test_windows_default_encoding_and_no_overwrite(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);original=Path.read_text
   def windows_read(path,encoding=None,errors=None,**kw):return original(path,encoding=encoding or 'cp1252',errors=errors,**kw)
   with patch.object(Path,'read_text',windows_read):self.run_build(p)
   with self.assertRaises(FileExistsError):self.run_build(p)
 def test_joint_bundle_excludes_any_masked_component(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);self.run_build(p);r=next(x for x in self.csv(p/'out/training_joint_bundles.csv') if x['season']=='2024' and x['player_type']=='hitter');self.assertEqual(r['bundle_eligible'],'False');self.assertEqual(r['bundle_values'],'')
 def test_interruption_cleans_unpublished_stage(self):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t);fixture(p);before=tree(p/'ref')
   with patch('build_training_labels_v1_0.resolve_label',side_effect=KeyboardInterrupt):
    with self.assertRaises(KeyboardInterrupt):self.run_build(p)
   self.assertFalse((p/'out').exists());self.assertFalse(list(p.glob('out.staging-*')));self.assertEqual(before,tree(p/'ref'))
if __name__=='__main__':unittest.main()
