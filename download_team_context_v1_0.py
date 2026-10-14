"""Resumable MLB team-season supplements; unavailable official fields remain null."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,csv,json,math
from urllib.parse import urlencode
import duckdb
from statcast_pipeline_v1_0 import config,retry,request_bytes,sha,lit,lock
METRICS={'hitting':{'games':'gamesPlayed','runs':'runs','pa':'plateAppearances','sb':'stolenBases','cs':'caughtStealing','obp':'obp','slg':'slg'},'pitching':{'games':'gamesPlayed','wins':'wins','saves':'saves','holds':'holds','blown_saves':'blownSaves','save_opportunities':'saveOpportunities','era':'era','whip':'whip'}}
def normalize(payload,season,group):
 rows=[];keys=set()
 if 'stats' not in payload:raise ValueError('Team-stat response missing stats')
 for section in payload['stats']:
  for split in section.get('splits',[]):
   mid=split.get('team',{}).get('id')
   if not mid or mid in keys:raise ValueError('Missing/duplicate team ID')
   keys.add(mid);stats=split['stat']
   row={'season':season,'mlb_team_id':int(mid),'team_name':split['team'].get('name'),'stat_group':group,'raw_stats_json':json.dumps(stats,sort_keys=True)}
   for canonical,source in METRICS[group].items():
    v=stats.get(source);row[canonical]=None if v is None or str(v) in ('','-.--','--') else float(v)
    if row[canonical] is not None and (not math.isfinite(row[canonical]) or row[canonical]<0):raise ValueError('Invalid team numeric statistic: '+source)
   if group=='hitting':
    sb=row['sb'];cs=row['cs'];pa=row['pa'];attempts=sb+cs if sb is not None and cs is not None else None
    row.update(sb_attempts=attempts,sb_success_pct=sb/attempts if attempts else None,sb_attempts_per_pa=attempts/pa if attempts is not None and pa else None)
   rows.append(row)
 if not rows:raise ValueError('No team-season splits returned')
 return rows

def download(c,seasons,fetch=request_bytes):
 root=c['_root']/'team_supplement';report=[]
 with lock(root):
  for season in seasons:
   for group in METRICS:
    folder=root/f'season={season}'/group;manifest=folder/'manifest.json'
    if manifest.exists():
     m=json.loads(manifest.read_text())
     if sha(folder/'source.json')!=m['source_sha256'] or sha(folder/'team_stats.parquet')!=m['parquet_sha256']:raise ValueError('Team supplement hash mismatch')
     print(f'{season} {group}: verified; skipped',flush=True);report.append(m);continue
    folder.mkdir(parents=True,exist_ok=True)
    url='https://statsapi.mlb.com/api/v1/teams/stats?'+urlencode({'stats':'season','group':group,'season':season,'sportIds':1})
    print(f'{season} {group}: downloading team statistics',flush=True)
    raw=retry(url,c,fetch);rows=normalize(json.loads(raw),season,group);(folder/'source.json').write_bytes(raw)
    fields=list(rows[0]);bridge=folder/'transfer.csv'
    with bridge.open('w',newline='',encoding='utf-8') as f:
     w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    with duckdb.connect() as db:
     schema={k:('BIGINT' if k in ('season','mlb_team_id') else 'VARCHAR' if k in ('team_name','stat_group','raw_stats_json') else 'DOUBLE') for k in fields}
     query='SELECT * FROM read_csv('+lit(bridge.as_posix())+',header=true,columns={'+','.join(lit(k)+':'+lit(v) for k,v in schema.items())+'})'
     db.execute('COPY ('+query+') TO '+lit((folder/'team_stats.parquet').as_posix())+' (FORMAT PARQUET,COMPRESSION ZSTD)')
    bridge.unlink();m={'season':season,'group':group,'url':url,'retrieved_at':datetime.now(timezone.utc).isoformat(),'teams':len(rows),'source_sha256':sha(folder/'source.json'),'parquet_sha256':sha(folder/'team_stats.parquet'),'missing_fields':{k:sum(r[k] is None for r in rows) for k in METRICS[group]}}
    tmp=manifest.with_suffix('.tmp');tmp.write_text(json.dumps(m,indent=2));tmp.replace(manifest);report.append(m)
  (root/'team_context_audit.json').write_text(json.dumps(report,indent=2))
 return report

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='config/statcast_ingestion_v1_0.json');p.add_argument('--seasons',nargs='+',type=int,default=[2023,2024,2025,2026]);a=p.parse_args()
 print(json.dumps(download(config(a.config),a.seasons),indent=2))
if __name__=='__main__':main()
