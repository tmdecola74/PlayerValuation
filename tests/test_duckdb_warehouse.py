import tempfile, unittest
from pathlib import Path
import yaml
from openpyxl import Workbook
from src.warehouse.core import build,initialize,validate,connect,number

class WarehouseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name)
  self.c={'_root':self.root}; self.path=self.root/'hitters.csv'
  self.path.write_text('Name,ID,HR\nA,123,20\nB,456,10\n')
  self.manifest=self.root/'sources.yaml'
  self.spec={'dataset':'projection_hitter','source':'steamer','season':2026,'path':str(self.path),'columns':{'name':'Name','mlbam_id':'ID','HR':'HR'}}
  self.save()
 def tearDown(self):self.tmp.cleanup()
 def save(self):self.manifest.write_text(yaml.safe_dump({'sources':[self.spec]}))
 def test_roundtrip_rerun_and_replace(self):
  self.assertEqual(build(self.c,self.manifest)[0]['rows'],2)
  self.assertTrue(validate(self.c)['pass'])
  self.assertEqual(build(self.c,self.manifest)[0]['status'],'UNCHANGED')
  self.path.write_text('Name,ID,HR\nA,123,25\n')
  build(self.c,self.manifest)
  with connect(self.c) as con:
   self.assertEqual(con.execute('select HR from projection_hitter').fetchall(),[(25.0,)])
   self.assertEqual(con.execute('select count(*) from dataset_version').fetchone()[0],2)
  self.assertTrue(validate(self.c)['pass'])
 def test_duplicate_rejection_preserves_previous(self):
  build(self.c,self.manifest)
  self.path.write_text('Name,ID,HR\nA,123,20\nA,123,10\n')
  with self.assertRaises(ValueError):build(self.c,self.manifest)
  with connect(self.c) as con:self.assertEqual(con.execute('select count(*) from projection_hitter').fetchone()[0],2)
 def test_fangraphs_fallback_and_bad_number(self):
  self.spec['columns']['fangraphs_id']=self.spec['columns'].pop('mlbam_id');self.save()
  build(self.c,self.manifest)
  with connect(self.c) as con:self.assertEqual(con.execute('select player_key from projection_hitter order by player_key').fetchall(),[('FG:123',),('FG:456',)])
  self.path.write_text('Name,ID,HR\nA,123,garbage\n')
  with self.assertRaises(ValueError):build(self.c,self.manifest)
 def test_excel_and_baseball_innings(self):
  w=Workbook();s=w.active;s.title='Pitchers';s.append(['Name','ID','IP']);s.append(['A',123,10.1]);w.save(self.root/'p.xlsx')
  self.spec.update(dataset='actual_pitcher',path=str(self.root/'p.xlsx'),sheet='Pitchers',ip_format='baseball',columns={'name':'Name','mlbam_id':'ID','IP':'IP'});self.save()
  build(self.c,self.manifest)
  with connect(self.c) as con:self.assertAlmostEqual(con.execute('select IP from actual_pitcher').fetchone()[0],10+1/3)
  with self.assertRaises(ValueError):number('10.3','IP',self.spec)
 def test_tampering_detected(self):
  build(self.c,self.manifest)
  with connect(self.c) as con:raw=con.execute('select raw_path from dataset_version').fetchone()[0]
  Path(raw).write_text('tampered')
  self.assertFalse(validate(self.c)['pass'])
 def test_inspection_does_not_initialize(self):
  self.assertEqual(build(self.c,self.manifest,True)[0]['rows'],2)
  self.assertFalse((self.root/'data/database').exists())
 def test_missing_mapping_and_empty_manifest(self):
  self.spec['columns']['HR']='missing';self.save()
  with self.assertRaises(ValueError):build(self.c,self.manifest)
  self.manifest.write_text('sources: []')
  with self.assertRaises(ValueError):build(self.c,self.manifest)

if __name__=='__main__': unittest.main()
