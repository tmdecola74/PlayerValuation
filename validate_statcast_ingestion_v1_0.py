"""Verify registered window hashes and Parquet counts before feature construction."""
import argparse,json
from contextlib import closing
import duckdb
from statcast_pipeline_v1_0 import config,active,lit

def validate(c,start=None,end=None):
 selected=active(c,start,end);counts=[]
 with duckdb.connect() as db:
  for r in selected:
   n=db.execute('SELECT count(*) FROM read_parquet('+lit(r['parquet_path'])+')').fetchone()[0] if r['parquet_path'] else 0
   if n!=r['rows']:raise ValueError('Parquet/ledger count mismatch: '+r['day'])
   counts.append({'day':r['day'],'rows':n,'pass':True})
 report={'pass':True,'windows':len(selected),'pitch_rows':sum(r['rows'] for r in selected),'empty_windows':sum(not r['rows'] for r in selected),'exact_duplicates_removed':sum(r['exact_duplicates'] for r in selected),'checks':counts}
 (c['_root']/'latest_validation_report.json').write_text(json.dumps(report,indent=2));return report

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='config/statcast_ingestion_v1_0.json');p.add_argument('--start');p.add_argument('--end');a=p.parse_args();r=validate(config(a.config),a.start,a.end)
 print(json.dumps({k:v for k,v in r.items() if k!='checks'},indent=2))
if __name__=='__main__':main()
