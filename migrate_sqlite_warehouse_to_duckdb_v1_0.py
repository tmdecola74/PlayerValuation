"""Lossless read-only SQLite snapshot -> Parquet-backed DuckDB warehouse."""
import argparse, csv, hashlib, json, shutil, sqlite3, tempfile, time, uuid
from pathlib import Path
from datetime import datetime, timezone
import duckdb


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def ident(s):return '"'+s.replace('"','""')+'"'
def lit(s):return "'"+str(s).replace("'","''")+"'"

def rows_hash(rows):
 # Order-independent multiset hash; duplicates still contribute individually.
 hashes=sorted(hashlib.sha256(json.dumps(list(r),ensure_ascii=False,default=str,separators=(',',':')).encode()).digest() for r in rows)
 return hashlib.sha256(b''.join(hashes)).hexdigest()

def migrate(source, output):
 source=Path(source).resolve(); output=Path(output).resolve()
 if not source.is_file():raise FileNotFoundError(source)
 if output.exists():raise ValueError('Output must not exist; choose a new migration directory')
 if source==output or output in source.parents:raise ValueError('Output must not contain the SQLite input')
 if Path(str(source)+'-wal').exists():raise ValueError('Close SQLite writers and checkpoint WAL before migration')
 started=time.perf_counter()
 print('Validating read-only SQLite source...',flush=True)
 before=sha(source); output.parent.mkdir(parents=True,exist_ok=True)
 stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
 db=None; sql=None; published=False
 try:
  sql=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True);sql.execute('BEGIN')
  if sql.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('SQLite integrity failed')
  if sql.execute('PRAGMA foreign_key_check').fetchall():raise ValueError('SQLite foreign key violations')
  objects=sql.execute("SELECT name,type,sql FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()
  required={'players','player_id_crosswalk','record_selection','hitter_projections','pitcher_projections','hitter_actuals','pitcher_actuals'}
  if not required.issubset({r[0] for r in objects}):raise ValueError('Not the expected reviewed historical warehouse')
  db=duckdb.connect(str(stage/'player_valuation.duckdb'))
  (stage/'parquet').mkdir(); report=[]
  for index,(name,kind,ddl) in enumerate(objects):
   object_started=time.perf_counter()
   print(f'[{index+1}/{len(objects)}] {name}: reading SQLite',flush=True)
   cursor=sql.execute('SELECT * FROM '+ident(name)); columns=[c[0] for c in cursor.description]
   records=cursor.fetchall()
   types=[]
   for i,col in enumerate(columns):
    values=[r[i] for r in records if r[i] is not None]
    if all(isinstance(v,int) for v in values) and values:t='BIGINT'
    elif all(isinstance(v,(int,float)) for v in values) and values:t='DOUBLE'
    elif all(isinstance(v,str) for v in values):t='VARCHAR'
    else:raise ValueError(f'Unsupported mixed/blob SQLite types: {name}.{col}')
    types.append(t)
   filename=f'{index:03d}.parquet';p=stage/'parquet'/filename
   bridge=stage/'bulk_transfer.csv'
   null_token='__PV_NULL_'+uuid.uuid4().hex+'__'
   if any(v==null_token for row in records for v in row):raise ValueError('Null token collision')
   print(f'[{index+1}/{len(objects)}] {name}: bulk export {len(records):,} rows',flush=True)
   with bridge.open('w',newline='',encoding='utf-8') as stream:
    writer=csv.writer(stream)
    writer.writerows([[null_token if v is None else v for v in row] for row in records])
   schema='{'+','.join(lit(c)+':'+lit(t) for c,t in zip(columns,types))+'}'
   if records:
    query='SELECT * FROM read_csv('+lit(bridge.as_posix())+', header=false, auto_detect=false, columns='+schema+', nullstr='+lit(null_token)+", delim=',', quote='\"', escape='\"')"
   else:
    query='SELECT '+','.join('CAST(NULL AS '+t+') AS '+ident(c) for c,t in zip(columns,types))+' WHERE FALSE'
   db.execute('COPY ('+query+') TO '+lit(p.as_posix())+' (FORMAT PARQUET, COMPRESSION ZSTD)')
   bridge.unlink()
   print(f'[{index+1}/{len(objects)}] {name}: verifying values',flush=True)
   db.execute('CREATE VIEW '+ident(name)+' AS SELECT * FROM read_parquet('+lit(p.as_posix())+')')
   actual=db.execute('SELECT * FROM '+ident(name)).fetchall()
   # Numeric type inference can promote SQLite ints to doubles. This warehouse's
   # declared integer columns and view expressions are homogeneous in practice.
   expected_hash=rows_hash(records);actual_hash=rows_hash(actual)
   if records!=actual: # file order is preserved, but comparison fallback is multiset
    if expected_hash!=actual_hash:raise ValueError('Value reconciliation failed: '+name)
   report.append({'object':name,'sqlite_type':kind,'columns':columns,'duckdb_types':types,'rows':len(records),'source_value_hash':expected_hash,'duckdb_value_hash':actual_hash,'parquet_file':'parquet/'+filename,'parquet_sha256':sha(p),'original_sql':ddl,'pass':True})
   report[-1]['elapsed_seconds']=round(time.perf_counter()-object_started,3)
   print(f'[{index+1}/{len(objects)}] {name}: PASS ({report[-1]["elapsed_seconds"]:.2f}s)',flush=True)
  if sha(source)!=before:raise ValueError('SQLite changed during migration')
  db.close();db=None;sql.close();sql=None
  audit={'script_version':'1.0.1_bulk','elapsed_seconds':round(time.perf_counter()-started,3),'created_at':datetime.now(timezone.utc).isoformat(),'source_sqlite':str(source),'source_sha256':before,'source_unchanged':True,'output':str(output),'pass':True,'objects':report,'notes':['SQLite views materialized as snapshot Parquet views.','No identities, metrics or duplicate selections recomputed.','DuckDB views use absolute paths; rerun migration into a new directory after relocation.']}
  (stage/'migration_audit.json').write_text(json.dumps(audit,indent=2),encoding='utf-8')
  shutil.copy2(source,stage/'source_snapshot.sqlite')
  if sha(stage/'source_snapshot.sqlite')!=before or sha(source)!=before:raise ValueError('SQLite snapshot/source hash changed')
  stage.rename(output);published=True
  db=duckdb.connect(str(output/'player_valuation.duckdb'))
  for r in report:
   final=output/r['parquet_file']
   db.execute('CREATE OR REPLACE VIEW '+ident(r['object'])+' AS SELECT * FROM read_parquet('+lit(final.as_posix())+')')
   if db.execute('SELECT count(*) FROM '+ident(r['object'])).fetchone()[0]!=r['rows']:raise ValueError('Published view reconciliation failed')
  db.close();db=None
  return audit
 except BaseException:
  if db is not None:db.close()
  if sql is not None:sql.close()
  shutil.rmtree(output if published else stage,ignore_errors=True)
  raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--sqlite',required=True);p.add_argument('--output',required=True)
 a=p.parse_args();r=migrate(a.sqlite,a.output)
 print(json.dumps({'pass':r['pass'],'objects':len(r['objects']),'output':r['output'],'source_unchanged':r['source_unchanged']},indent=2))
if __name__=='__main__':main()
