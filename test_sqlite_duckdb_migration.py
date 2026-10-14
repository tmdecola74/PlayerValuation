import unittest,tempfile,sqlite3,json
from pathlib import Path
from contextlib import closing
import duckdb
from migrate_sqlite_warehouse_to_duckdb_v1_0 import migrate,sha
class MigrationTests(unittest.TestCase):
 def fixture(self,root):
  p=root/'warehouse.sqlite'
  with closing(sqlite3.connect(p)) as c, c:
   for table in ('players','player_id_crosswalk','record_selection','hitter_projections','pitcher_projections','hitter_actuals','pitcher_actuals'):
    c.execute(f'CREATE TABLE {table}(record_id TEXT, value INTEGER, metrics_json TEXT)')
    c.executemany(f'INSERT INTO {table} VALUES (?,?,?)',[('a',0,'{"HR":0}'),('a',None,'{"HR":null}'),('b',5,'{}')])
   c.execute('CREATE VIEW analytical_hitter_projections AS SELECT * FROM hitter_projections WHERE value IS NOT NULL')
  return p
 def test_all_rows_views_and_source_preserved(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=self.fixture(root);before=sha(p);out=root/'migration';r=migrate(p,out)
   self.assertTrue(r['pass']);self.assertEqual(sha(p),before)
   with duckdb.connect(str(out/'player_valuation.duckdb'),read_only=True) as c:
    self.assertEqual(c.execute('select count(*) from hitter_projections').fetchone()[0],3)
    self.assertEqual(c.execute('select count(*) from analytical_hitter_projections').fetchone()[0],2)
    self.assertEqual(c.execute('select count(*) from hitter_projections where value=0').fetchone()[0],1)
   with self.assertRaises(ValueError):migrate(p,out)
 def test_bad_schema_no_output(self):
  with tempfile.TemporaryDirectory() as t:
   root=Path(t);p=root/'x.sqlite'
   with closing(sqlite3.connect(p)) as c, c:c.execute('create table x(a text)')
   with self.assertRaises(ValueError):migrate(p,root/'out')
   self.assertFalse((root/'out').exists())
if __name__=='__main__':unittest.main()
