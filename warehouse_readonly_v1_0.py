"""Read-only SQLite/DuckDB access for the migrated evaluator copies."""
from pathlib import Path
import hashlib,json,sqlite3

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as stream:
  for chunk in iter(lambda:stream.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()

class Row(dict):
 def __getitem__(self,key):
  return tuple(self.values())[key] if isinstance(key,int) else super().__getitem__(key)

class Result:
 def __init__(self,columns,rows):self.rows=[Row(zip(columns,r)) for r in rows]
 def __iter__(self):return iter(self.rows)
 def fetchall(self):return self.rows
 def fetchone(self):return self.rows[0] if self.rows else None

class DuckReader:
 def __init__(self,path):
  import duckdb
  self.path=Path(path);self.db=duckdb.connect(str(path),read_only=True)
 def execute(self,query,parameters=()):
  if query.strip().lower()=='pragma integrity_check':
   # Validate the immutable external payload as well as opening the catalog.
   audit_path=self.path.parent/'migration_audit.json'
   if not audit_path.exists():raise ValueError('DuckDB migration audit missing')
   audit=json.loads(audit_path.read_text(encoding='utf-8'))
   if not audit.get('pass'):raise ValueError('Migration audit did not pass')
   for obj in audit['objects']:
    p=self.path.parent/obj['parquet_file']
    if sha(p)!=obj['parquet_sha256']:raise ValueError('Parquet hash mismatch: '+obj['object'])
    count=self.db.execute('SELECT count(*) FROM "'+obj['object'].replace('"','""')+'"').fetchone()[0]
    if count!=obj['rows']:raise ValueError('DuckDB view count mismatch: '+obj['object'])
   return Result(['integrity_check'],[('ok',)])
  head=query.lstrip().split(None,1)[0].upper()
  if head not in ('SELECT','WITH'):raise ValueError('Only read queries allowed')
  cursor=self.db.execute(query,parameters)
  return Result([c[0] for c in cursor.description],cursor.fetchall())
 def close(self):self.db.close()

def open_warehouse(path):
 path=Path(path).resolve()
 if not path.is_file():raise FileNotFoundError(path)
 if path.suffix.lower()=='.duckdb':return DuckReader(path)
 conn=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
 return conn
