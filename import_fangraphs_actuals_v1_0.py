"""Import FanGraphs actuals into a NEW reference package; never edit warehouses."""
import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path
import duckdb
from actuals_scoring_v1_0 import *


def build(hitters,pitchers,output,backup_root='backups',holdout_season=2026):
 sources=[Path(hitters).resolve(),Path(pitchers).resolve()]
 fingerprints={str(p):sha(p) for p in sources}
 records=[];issues=[]
 for path,role in zip(sources,['hitter','pitcher']):
  loaded,problems=load_fangraphs(path,role);records+=loaded;issues+=problems
 years=sorted({r['season'] for r in records})
 if any(y>holdout_season for y in years):raise ValueError('Actual season after configured holdout; supply a later holdout explicitly')
 out,stage=stage_output(output,sources,backup_root)
 try:
  (stage/'source_files').mkdir()
  for path,role in zip(sources,['hitters','pitchers']):shutil.copy2(path,stage/'source_files'/(role+'.csv'))
  players=[];counts=[];rates=[];raw=[]
  for r in records:
   split='holdout' if r['season']==holdout_season else 'historical'
   players.append({k:r[k] for k in ['season','player_type','mlbam_id','fangraphs_id','name','team','age','source_row']}|{'split':split})
   for m,v in r['counts'].items():counts.append(dict(season=r['season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],metric=m,value=v,split=split))
   for m,v in r['derived_rates'].items():rates.append(dict(season=r['season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],metric=m,value=v,split=split))
   raw.append(dict(season=r['season'],player_type=r['player_type'],mlbam_id=r['mlbam_id'],source_row=r['source_row'],raw_json=json.dumps(r['raw'],ensure_ascii=False),split=split))
  csv_out(stage/'player_seasons.csv',players,['season','player_type','mlbam_id','fangraphs_id','name','team','age','source_row','split'])
  csv_out(stage/'actual_counts.csv',counts,['season','player_type','mlbam_id','metric','value','split'])
  csv_out(stage/'derived_rates.csv',rates,['season','player_type','mlbam_id','metric','value','split'])
  csv_out(stage/'source_rows.csv',raw,['season','player_type','mlbam_id','source_row','raw_json','split'])
  csv_out(stage/'import_review.csv',issues,['season','player_type','mlbam_id','check','detail'])
  with duckdb.connect(str(stage/'actuals_reference.duckdb')) as db:
   for table in ['player_seasons','actual_counts','derived_rates','source_rows']:
    # CSV is explicitly typed; MLBAM/season integers and FanGraphs IDs strings.
    columns={'season':'INTEGER','player_type':'VARCHAR','mlbam_id':'BIGINT'}
    if table=='player_seasons':columns.update(fangraphs_id='VARCHAR',name='VARCHAR',team='VARCHAR',age='INTEGER',source_row='INTEGER',split='VARCHAR')
    elif table in ('actual_counts','derived_rates'):columns.update(metric='VARCHAR',value='BIGINT' if table=='actual_counts' else 'DOUBLE',split='VARCHAR')
    else:columns.update(source_row='INTEGER',raw_json='VARCHAR',split='VARCHAR')
    types='{'+','.join(lit(k)+':'+lit(v) for k,v in columns.items())+'}'
    db.execute('CREATE TABLE '+ident(table)+' AS SELECT * FROM read_csv('+lit(stage/(table+'.csv'))+',header=true,columns='+types+')')
    db.execute('COPY '+ident(table)+' TO '+lit(stage/(table+'.parquet'))+' (FORMAT PARQUET, COMPRESSION ZSTD)')
   db.execute("CREATE VIEW historical_counts AS SELECT * FROM actual_counts WHERE split='historical'")
   db.execute("CREATE VIEW holdout_counts AS SELECT * FROM actual_counts WHERE split='holdout'")
   db.execute('CHECKPOINT')
  # Cross-role totals are independent reference checks, not Statcast reconciliation.
  totals=defaultdict(Counter)
  for r in records:totals[r['season'],r['player_type']].update(r['counts'])
  cross=[]
  for y in years:
   for metric in ['H','HR','BB','IBB','SO','HBP']:
    a=totals[y,'hitter'][metric];b=totals[y,'pitcher'][metric]
    cross.append(dict(season=y,metric=metric,hitter_total=a,pitcher_total=b,difference=a-b,status='MATCH' if a==b else 'REVIEW'))
  csv_out(stage/'reference_cross_role_totals.csv',cross,['season','metric','hitter_total','pitcher_total','difference','status'])
  unchanged=all(sha(p)==h for p,h in fingerprints.items())
  if not unchanged:raise ValueError('Source changed during import')
  report=dict(version=VERSION,status='IMPORTED_REFERENCE_NOT_STATCAST_RECONCILED',built_at=now(),source='User-supplied retrospective FanGraphs actuals; not independently certified MLB totals',source_sha256=fingerprints,source_files_unchanged=True,holdout_season=holdout_season,historical_max_season=holdout_season-1,row_counts=dict(Counter(r['player_type'] for r in records)),seasons=years,review_rows=len(issues),cross_role_mismatches=sum(r['status']!='MATCH' for r in cross),zero_out_pitcher_rows=sum(r['player_type']=='pitcher' and r['counts']['OUTS']==0 for r in records),reference_scope_warning='Cross-role differences and absence of zero-out pitcher rows may indicate export scope omissions; investigate with MLB game evidence rather than treating every difference as missing Statcast.',age_basis='FanGraphs supplied season Age; not birth date and not independently verified',rate_policy='Derived from integer components; undefined zero-denominator rates remain null',model_ready=False)
  dump(stage/'import_report.json',report)
  backup=finish_output(stage,out,backup_root)
  return report|{'output':str(out),'backup':backup}
 except BaseException:
  shutil.rmtree(stage,ignore_errors=True);raise


def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--hitters',required=True);p.add_argument('--pitchers',required=True);p.add_argument('--output',default='data/actuals_reference_v1_0');p.add_argument('--backup-root',default='backups');p.add_argument('--holdout-season',type=int,default=2026)
 a=p.parse_args();print(json.dumps(build(a.hitters,a.pitchers,a.output,a.backup_root,a.holdout_season),indent=2))
if __name__=='__main__':main()
