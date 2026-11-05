"""Frozen-window physical Statcast measurements, with observation/coverage controls."""
import json,math
from pathlib import Path
from datetime import date,timedelta
from collections import defaultdict
import duckdb
from lagged_io_v1_0 import sha,load,integer
SWINGS=['swinging_strike','swinging_strike_blocked','foul','foul_tip','foul_bunt','missed_bunt','hit_into_play','hit_into_play_no_out','hit_into_play_score','swinging_pitchout','foul_pitchout','bunt_foul_tip']
MISSES=['swinging_strike','swinging_strike_blocked','missed_bunt','swinging_pitchout']
MEASURES=['whiff_pct','chase_pct','zone_pct','ev','hardhit_pct','barrel_pct','xwobacon','velocity','spin_rpm','extension_ft']
def lit(x):return "'"+str(x).replace("'","''")+"'"
def era(y):return 1 if y<=2016 else 2 if y<=2019 else 3 if y<=2023 else 4
ERA_NAMES={1:'PRE2017_VELOCITY_PITCHFX_EARLY_STATCAST',2:'2017_2019_STATCAST_TRACKING',3:'2020_2023_HAWKEYE',4:'2024_2025_HAWKEYE_BAT_TRACKING_ERA_NOT_USED'}
def windows(manifest,c):
 rows=load(manifest)
 if not isinstance(rows,list):raise ValueError('Frozen source_windows must be a list')
 selected=[];days=set();watched={str(Path(manifest).resolve()):sha(manifest)}
 for index,r in enumerate(rows,1):
  if index%250==0:print(f'{index:,} frozen windows checked',flush=True)
  d=date.fromisoformat(r['day'])
  if d.year not in c['source_seasons']:continue # Future rows never opened or used.
  if r['day'] in days or r['status']!='COMPLETE':raise ValueError('Duplicate/incomplete frozen window')
  days.add(r['day']);integer(r['rows'],'pitch rows');selected.append(r)
  for col,hcol in [('raw_path','raw_hash'),('parquet_path','parquet_hash'),('schedule_path','schedule_hash')]:
   if not r.get(col) or not r.get(hcol):raise ValueError('Incomplete frozen source evidence')
   p=Path(r[col]).resolve()
   if sha(p)!=r[hcol]:raise ValueError('Frozen window hash mismatch: '+str(p))
   watched[str(p)]=r[hcol]
 expected=set()
 for y in c['source_seasons']:
  d=date.fromisoformat(str(y)+'-'+c['window_start_mmdd']);end=date.fromisoformat(str(y)+'-'+c['window_end_mmdd'])
  while d<=end:expected.add(d.isoformat());d+=timedelta(days=1)
 if days!=expected:raise ValueError('Frozen manifest does not cover configured source windows exactly')
 return selected,watched

def aggregate(manifest,c):
 selected,watched=windows(manifest,c);out={};audit=[];schemas=[]
 with duckdb.connect() as db:
  for y in c['source_seasons']:
   group=[r for r in selected if int(r['day'][:4])==y];paths=[str(Path(r['parquet_path']).resolve()) for r in group if r['rows']]
   if not paths or len(paths)!=len(set(paths)):raise ValueError('No source pitches or reused nonempty file')
   print(f'{y}: aggregating verified physical measurements',flush=True)
   db.execute('CREATE OR REPLACE VIEW raw AS SELECT * FROM read_parquet(['+','.join(lit(p) for p in paths)+'],union_by_name=true,hive_partitioning=false)')
   cols={r[0] for r in db.execute('DESCRIBE raw').fetchall()}
   required={'game_pk','at_bat_number','pitch_number','game_date','game_type','batter','pitcher','description','type'}
   if not required<=cols:raise ValueError('Missing required pitch keys/physical fields')
   counts={str(d):n for d,n in db.execute('SELECT CAST(game_date AS DATE),count(*) FROM raw GROUP BY 1').fetchall()}
   if counts!={r['day']:r['rows'] for r in group if r['rows']}:raise ValueError('Pitch dates/counts do not reproduce frozen windows')
   invalid=db.execute("SELECT count(*) FROM raw WHERE game_type IS DISTINCT FROM 'R' OR batter IS NULL OR pitcher IS NULL OR batter<=0 OR pitcher<=0 OR game_pk IS NULL OR at_bat_number IS NULL OR pitch_number IS NULL").fetchall()[0][0]
   dup=db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM raw GROUP BY ALL HAVING count(*)>1)').fetchall()[0][0]
   if invalid or dup:raise ValueError('Invalid identities/game types or duplicate physical pitches')
   numbers=['zone','launch_speed','launch_speed_angle','estimated_woba_using_speedangle','release_speed','release_spin_rate','release_extension']
   expr=[]
   for col in numbers:
    schemas.append(dict(season=y,column=col,present=col in cols))
    expr.append((f'CASE WHEN isfinite(try_cast("{col}" AS DOUBLE)) THEN try_cast("{col}" AS DOUBLE) END' if col in cols else 'NULL::DOUBLE')+' AS '+col)
   db.execute('CREATE OR REPLACE VIEW clean AS SELECT batter,pitcher,type,description,'+','.join(expr)+' FROM raw')
   swing='description IN ('+','.join(map(lit,SWINGS))+')';miss='description IN ('+','.join(map(lit,MISSES))+')'
   for role,idcol in [('hitter','batter'),('pitcher','pitcher')]:
    query=f'''SELECT {idcol},count(*) n,
     count(*) FILTER(WHERE {swing}) swings,count(*) FILTER(WHERE {miss}) misses,
     count(*) FILTER(WHERE zone BETWEEN 11 AND 14) outside,
     count(*) FILTER(WHERE {swing} AND zone BETWEEN 11 AND 14) chase,
     count(*) FILTER(WHERE zone BETWEEN 1 AND 14) known_zone,
     count(*) FILTER(WHERE zone BETWEEN 1 AND 9) inzone,
     count(*) FILTER(WHERE type='X') bbe,
     count(launch_speed) FILTER(WHERE type='X') ev_n,
     avg(launch_speed) FILTER(WHERE type='X') ev,
     count(*) FILTER(WHERE type='X' AND launch_speed>=95) hardhit,
     count(launch_speed_angle) FILTER(WHERE type='X' AND launch_speed_angle BETWEEN 1 AND 6) barrel_n,
     count(*) FILTER(WHERE type='X' AND launch_speed_angle=6) barrels,
     count(estimated_woba_using_speedangle) FILTER(WHERE type='X') xw_n,
     avg(estimated_woba_using_speedangle) FILTER(WHERE type='X') xw,
     count(release_speed) velocity_n,avg(release_speed) velocity,
     count(release_spin_rate) spin_n,avg(release_spin_rate) spin,
     count(release_extension) extension_n,avg(release_extension) AS extension_value
     FROM clean GROUP BY {idcol}'''
    fields=['mlbam_id','n','swings','misses','outside','chase','known_zone','inzone','bbe','ev_n','ev','hardhit','barrel_n','barrels','xw_n','xw','velocity_n','velocity','spin_n','spin','extension_n','extension']
    for row in db.execute(query).fetchall():
     r=dict(zip(fields,row));k=(y,role,str(r['mlbam_id']));features={}
     candidates={'whiff_pct':(r['misses']/r['swings'] if r['swings'] else None,r['swings'],r['swings']),
      'chase_pct':(r['chase']/r['outside'] if r['outside'] else None,r['outside'],r['outside']),
      'zone_pct':(r['inzone']/r['known_zone'] if r['known_zone'] else None,r['known_zone'],r['n']),
      'ev':(r['ev'],r['ev_n'],r['bbe']),
      'hardhit_pct':(r['hardhit']/r['ev_n'] if r['ev_n'] else None,r['ev_n'],r['bbe']),
      'barrel_pct':(r['barrels']/r['barrel_n'] if r['barrel_n'] else None,r['barrel_n'],r['bbe']),
      'xwobacon':(r['xw'],r['xw_n'],r['bbe'])}
     if role=='pitcher':candidates.update(velocity=(r['velocity'],r['velocity_n'],r['n']),spin_rpm=(r['spin'],r['spin_n'],r['n']),extension_ft=(r['extension'],r['extension_n'],r['n']))
     for metric,(value,n,possible) in candidates.items():
      coverage=n/possible if possible else None;valid=value is not None and math.isfinite(value) and n>=c['minimum_observations'][metric] and coverage is not None and coverage>=c['minimum_measurement_coverage']
      features[metric]=dict(value=value if valid else None,observations=n,opportunities=possible,coverage=coverage,eligible=valid)
      audit.append(dict(source_season=y,player_type=role,mlbam_id=k[2],measurement=metric,raw_value=value,observations=n,opportunities=possible,coverage=coverage,eligible=valid,tracking_era_code=era(y),reason='AVAILABLE' if valid else 'MISSING_OR_BELOW_FIXED_SAMPLE_COVERAGE'))
     out[k]=features
 return out,audit,schemas,selected,watched
