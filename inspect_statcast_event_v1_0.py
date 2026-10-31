"""Read-only extraction of event rows from a frozen reconciliation's source versions."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import duckdb


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()


def inspect(reconciliation,output,event='game_advisory',season=2017):
 source=Path(reconciliation).resolve()/'source_windows.json'
 source_hash=sha(source);windows=json.loads(source.read_text(encoding='utf-8'))
 selected=[r for r in windows if int(r['day'][:4])==season]
 if not selected:raise ValueError('No source windows for requested season')
 out=Path(output).resolve()
 if out.exists():raise FileExistsError('Use a new inspection output folder')
 protected=[source]+[Path(r['parquet_path']).resolve() for r in selected if r.get('parquet_path')]
 if any(out==p or out in p.parents for p in protected):raise ValueError('Output must not contain inputs')
 fields=['game_date','game_pk','at_bat_number','pitch_number','batter','pitcher','balls','strikes','events','description','type','des']
 rows=[];scanned=0
 with duckdb.connect() as db:
  for r in selected:
   path=r.get('parquet_path')
   if not path:continue
   if sha(path)!=r['parquet_hash']:raise ValueError('Frozen source hash mismatch: '+path)
   db.execute("CREATE OR REPLACE VIEW p AS SELECT * FROM read_parquet('"+str(path).replace("'","''")+"',hive_partitioning=false)")
   cols={x[0] for x in db.execute('DESCRIBE p').fetchall()}
   if 'events' not in cols:raise ValueError('Source lacks events column')
   expressions=['"'+f+'"' if f in cols else 'NULL AS "'+f+'"' for f in fields]
   cur=db.execute('SELECT '+','.join(expressions)+' FROM p WHERE events=?',[event])
   for values in cur.fetchall():rows.append(dict(zip(fields,values))|{'source_day':r['day'],'source_run_id':r['run_id'],'parquet_path':path})
   scanned+=1
 if sha(source)!=source_hash:raise ValueError('Source-window snapshot changed')
 out.mkdir(parents=True)
 with (out/'event_rows.csv').open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields+['source_day','source_run_id','parquet_path']);w.writeheader();w.writerows(rows)
 report={'event':event,'season':season,'rows':len(rows),'games':sorted({r['game_pk'] for r in rows}),'parquet_files_checked':scanned,'source_windows_sha256':source_hash,'source_policy':'Frozen versions used by the supplied reconciliation, not a new live ingestion selection','classification':'REVIEW_ONLY_NO_EVENT_RECLASSIFICATION_OR_COUNT_CHANGE'}
 (out/'inspection_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 return report


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--reconciliation',default='outputs/actuals_statcast_reconciliation_v1_0');p.add_argument('--output',default='outputs/actuals_event_inspection_v1_0');p.add_argument('--event',default='game_advisory');p.add_argument('--season',type=int,default=2017)
 a=p.parse_args();print(json.dumps(inspect(a.reconciliation,a.output,a.event,a.season),indent=2))
if __name__=='__main__':main()
