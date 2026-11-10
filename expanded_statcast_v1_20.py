"""Frozen-archive expanded Statcast features and availability audit. No fitting."""
import argparse,csv,json,math,shutil
from pathlib import Path
from collections import defaultdict,Counter
import duckdb
from standalone_io_v1_0 import load,dump,sha,start,finish
from standalone_diagnostics_v1_16 import checked,emit
from lagged_statcast_v1_0 import windows,lit,SWINGS,MISSES,era
VERSION='1.20.0'
NUMBERS=['zone','launch_angle','launch_speed_angle','hc_x','hc_y','release_speed','release_spin_rate','release_extension','pfx_x','pfx_z','release_pos_x','release_pos_z']
TEXT=['stand','bb_type','pitch_type']
BAT_FIELDS=['bat_speed','swing_length','attack_angle','attack_direction','swing_path_tilt','squared_up','squared_up_per_swing','squared_up_per_bat_contact','blast','is_competitive']
KNOWN_TYPES=['ground_ball','line_drive','fly_ball','popup']
DEFAULT=dict(version=VERSION,source_min_season=2015,source_max_season=2025,minimum_measurement_coverage=.5,minimum_bbe=30,minimum_barrels=10,minimum_swings=100,minimum_zone_swings=50,minimum_pitches=100,pull_origin_x=125.42,pull_origin_y=198.27,pull_boundary_degrees=15.,fair_cone_degrees=45.,physical_pitch_scope='REGULAR_SEASON_FROZEN_PARQUET_STRICT_KEYS',bat_tracking_policy='AUDIT_ONLY_NO_GUESSED_SQUARED_UP_OR_COMPETITIVE_SWING_CLASSIFICATION')

def config_checked(path):
 c=load(path)
 if c!=DEFAULT:raise ValueError('Fixed v1.20 definitions/controls changed; use a separate version')
 return c

def is_bat_field(n):return n in BAT_FIELDS or n.startswith('bat_') or any(t in n.lower() for t in ['squared','blast','attack_','swing_length','swing_path'])

def qident(name):return '"'+name.replace('"','""')+'"'

def prepare(db,selected,year,schema,column_audit,bat_audit):
 group=[r for r in selected if int(r['day'][:4])==year];paths=[str(Path(r['parquet_path']).resolve()) for r in group if r['rows']]
 if not paths or len(set(paths))!=len(paths):raise ValueError('No pitches or reused nonempty parquet')
 db.execute('CREATE OR REPLACE VIEW raw AS SELECT * FROM read_parquet(['+','.join(map(lit,paths))+'],union_by_name=true,hive_partitioning=false)')
 cols={r[0]:r[1] for r in db.execute('DESCRIBE raw').fetchall()}
 required={'game_pk','at_bat_number','pitch_number','game_date','game_type','batter','pitcher','description','type'}
 if not required<=set(cols):raise ValueError('Required pitch identity/result fields missing')
 if db.execute('SELECT count(*) FROM raw WHERE game_pk<=0 OR at_bat_number<>trunc(at_bat_number) OR game_pk<>trunc(game_pk) OR pitch_number<>trunc(pitch_number)').fetchone()[0]:raise ValueError('Non-integer physical pitch key')
 dates={str(d):n for d,n in db.execute('SELECT CAST(game_date AS DATE),count(*) FROM raw GROUP BY 1').fetchall()}
 if dates!={r['day']:r['rows'] for r in group if r['rows']}:raise ValueError('Frozen date/count mismatch')
 if db.execute("SELECT count(*) FROM raw WHERE game_type IS DISTINCT FROM 'R' OR batter IS NULL OR pitcher IS NULL OR batter<=0 OR pitcher<=0 OR game_pk IS NULL OR at_bat_number IS NULL OR pitch_number IS NULL OR at_bat_number<=0 OR pitch_number<=0 OR batter<>trunc(batter) OR pitcher<>trunc(pitcher)").fetchone()[0]:raise ValueError('Invalid physical pitch identity/game type')
 if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM raw GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Duplicate physical pitch')
 if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number FROM raw WHERE "type"=\'X\' GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Multiple in-play outcomes in one PA')
 rawcounts=Counter();pqcounts=Counter()
 for r in group:
  if not r['rows']:continue
  with Path(r['raw_path']).open(encoding='utf-8-sig',newline='') as f:
   header=next(csv.reader(f),[])
  if len(header)!=len(set(header)):raise ValueError('Duplicate CSV header')
  rawcounts.update(header)
  # Metadata only: do not rescan file contents for this per-window schema check.
  pqcols=[x[0] for x in db.execute('DESCRIBE SELECT * FROM read_parquet('+lit(r['parquet_path'])+',hive_partitioning=false)').fetchall()]
  pqcounts.update(pqcols)
 for name in sorted(set(NUMBERS+TEXT+BAT_FIELDS)|{n for n in cols if is_bat_field(n)}):
  status='PARQUET_AVAILABLE' if pqcounts[name] else 'RAW_ONLY_SCHEMA_RECOVERY_CANDIDATE' if rawcounts[name] else 'ABSENT_FROM_SAVED_SCHEMA'
  schema.append(dict(source_season=year,column=name,nonempty_windows=len(paths),parquet_windows=pqcounts[name],raw_csv_windows=rawcounts[name],status=status))
  if name in cols and is_bat_field(name):
   n,finite_n=db.execute(f'SELECT count({qident(name)}) , count(*) FILTER(WHERE isfinite(try_cast({qident(name)} AS DOUBLE))) FROM raw').fetchone();bat_audit.append(dict(source_season=year,column=name,datatype=cols[name],non_null_rows=n,finite_numeric_rows=finite_n,production_definition_verified=False))
 expr=[]
 for n in NUMBERS:
  cast=f'try_cast("{n}" AS DOUBLE)' if n in cols else 'NULL::DOUBLE';expr.append(f'CASE WHEN isfinite({cast}) THEN {cast} END AS "{n}"')
 for n in TEXT:expr.append((f"upper(nullif(trim(CAST(\"{n}\" AS VARCHAR)),''))" if n in cols and n=='pitch_type' else f'CAST("{n}" AS VARCHAR)' if n in cols else 'NULL::VARCHAR')+' AS "'+n+'"')
 db.execute('CREATE OR REPLACE TEMP TABLE clean AS SELECT batter,pitcher,"type",description,'+','.join(expr)+' FROM raw')
 # Conservative value validation: invalids become missing and stay auditable, never zeros.
 ranges={'zone':(1,14),'launch_angle':(-90,90),'launch_speed_angle':(1,6),'release_speed':(20,110),'release_spin_rate':(0,5000),'release_extension':(0,12),'pfx_x':(-5,5),'pfx_z':(-5,5),'release_pos_x':(-10,10),'release_pos_z':(0,12)}
 for n in NUMBERS:
  total,valid,minimum,maximum=db.execute(f'SELECT count(*),count("{n}"),min("{n}"),max("{n}") FROM clean').fetchone();bad=0
  if n in ranges:
   lo,hi=ranges[n];condition=f'"{n}" NOT BETWEEN {lo} AND {hi}'+(f' OR "{n}"<>trunc("{n}")' if n in ['zone','launch_speed_angle'] else '')+(f' OR "{n}"=10' if n=='zone' else '')
   bad=db.execute(f'SELECT count(*) FROM clean WHERE {condition}').fetchone()[0];db.execute(f'UPDATE clean SET "{n}"=NULL WHERE {condition}')
  column_audit.append(dict(source_season=year,column=n,pitch_rows=total,finite_before_range=valid,invalid_range_rows=bad,minimum_before_range=minimum,maximum_before_range=maximum))
 return len(paths),sum(r['rows'] for r in group)

def aggregates(db,c):
 swing='description IN ('+','.join(map(lit,SWINGS))+')';miss='description IN ('+','.join(map(lit,MISSES))+')'
 # A contact includes fouls/foul tips, in-play contact and bunt contact; matches inherited swing definition.
 known=['ball','blocked_ball','called_strike','hit_by_pitch','pitchout','intent_ball','intentional_ball','automatic_ball','automatic_strike']+SWINGS
 known=list(dict.fromkeys(known));knownsql='description IN ('+','.join(map(lit,known))+')'
 bbe='"type"=\'X\'';bt='bb_type IN ('+','.join(map(lit,KNOWN_TYPES))+')';barrel='launch_speed_angle BETWEEN 1 AND 6'
 angle=f'degrees(atan2(hc_x-{c["pull_origin_x"]},{c["pull_origin_y"]}-hc_y))'
 direction=f'hc_x IS NOT NULL AND hc_y IS NOT NULL AND NOT (hc_x={c["pull_origin_x"]} AND hc_y={c["pull_origin_y"]}) AND {c["pull_origin_y"]}-hc_y>0 AND abs({angle})<={c["fair_cone_degrees"]} AND stand IN (\'L\',\'R\')'
 pull=f'((stand=\'R\' AND {angle}<-{c["pull_boundary_degrees"]}) OR (stand=\'L\' AND {angle}>{c["pull_boundary_degrees"]}))'
 count=lambda cond:f'count(*) FILTER(WHERE {cond})'
 ag={'n':'count(*)','known':count(knownsql),'swings':count(swing),'misses':count(miss),'zone_known':count(knownsql+' AND (zone BETWEEN 1 AND 9 OR zone BETWEEN 11 AND 14)'),'inzone':count(knownsql+' AND zone BETWEEN 1 AND 9'),'outside':count('zone BETWEEN 11 AND 14'),'zone_swings':count(swing+' AND zone BETWEEN 1 AND 9'),'zone_contacts':count(swing+' AND NOT ('+miss+') AND zone BETWEEN 1 AND 9'),'outside_swings':count(swing+' AND zone BETWEEN 11 AND 14'),'outside_contacts':count(swing+' AND NOT ('+miss+') AND zone BETWEEN 11 AND 14'),'zone_known_swings':count(swing+' AND (zone BETWEEN 1 AND 9 OR zone BETWEEN 11 AND 14)'),'called_whiffs':count("description='called_strike' OR "+miss),'bbe':count(bbe),'bt_n':count(bbe+' AND '+bt),'la_n':count(bbe+' AND launch_angle IS NOT NULL'),'la_sum':f'sum(launch_angle) FILTER(WHERE {bbe})','la_mean':f'avg(launch_angle) FILTER(WHERE {bbe})','la_sd':f'stddev_pop(launch_angle) FILTER(WHERE {bbe})','la_p10':f'quantile_cont(launch_angle,.1) FILTER(WHERE {bbe})','la_p50':f'quantile_cont(launch_angle,.5) FILTER(WHERE {bbe})','la_p90':f'quantile_cont(launch_angle,.9) FILTER(WHERE {bbe})','sweet':count(bbe+' AND launch_angle BETWEEN 8 AND 32'),'negative_la':count(bbe+' AND launch_angle<0'),'high_la':count(bbe+' AND launch_angle>=50'),'direction_n':count(bbe+' AND '+direction),'pull_n':count(bbe+' AND '+direction+' AND '+pull),'direction_bt_n':count(bbe+' AND '+direction+' AND '+bt),'pull_air_n':count(bbe+' AND '+direction+' AND '+pull+" AND bb_type IN ('line_drive','fly_ball','popup')"),'direction_air_n':count(bbe+' AND '+direction+" AND bb_type IN ('line_drive','fly_ball','popup')"),'direction_barrel_n':count(bbe+' AND '+direction+' AND '+barrel),'pull_barrel_n':count(bbe+' AND '+direction+' AND '+barrel+' AND '+pull+' AND launch_speed_angle=6'),'barrels_direction_n':count(bbe+' AND '+direction+' AND launch_speed_angle=6'),'barrels_n':count(bbe+' AND launch_speed_angle=6'),'barrel_known_n':count(bbe+' AND '+barrel)}
 for name in KNOWN_TYPES:ag[name]=count(bbe+' AND bb_type='+lit(name))
 for n in ['release_speed','release_spin_rate','release_extension','pfx_x','pfx_z','release_pos_x','release_pos_z']:ag[n+'_n']=f'count({n})';ag[n+'_mean']=f'avg({n})';ag[n+'_sum']=f'sum({n})'
 for role,idcol in [('hitter','batter'),('pitcher','pitcher')]:
  q=f'SELECT {idcol} AS mlbam_id, CASE WHEN grouping(pitch_type)=1 THEN \'ALL\' ELSE coalesce(nullif(trim(pitch_type),\'\'),\'UNKNOWN\') END AS pitch_group,'+','.join(v+' AS "'+k+'"' for k,v in ag.items())+f' FROM clean GROUP BY GROUPING SETS (({idcol}),({idcol},pitch_type))'
  fields=['mlbam_id','pitch_group']+list(ag);result=[dict(zip(fields,row)) for row in db.execute(q).fetchall()];totals={r['mlbam_id']:r['n'] for r in result if r['pitch_group']=='ALL'}
  for r in result:
   r['player_total_n']=totals[r['mlbam_id']];r['air_n']=r['bt_n']-r['ground_ball'];yield role,r

def metric_specs(r,c):
 """value, numerator, measured denominator, opportunity denominator, sample floor, definition."""
 def ratio(n,d,o,f,definition='DERIVED_ARCHIVE'):
  return (r[n]/r[d] if r[d] else None,r[n],r[d],r[o],f,definition)
 out={}
 if r['pitch_group']!='ALL':out['pitch_type_usage']=(r['n']/r['player_total_n'],r['n'],r['player_total_n'],r['player_total_n'],c['minimum_pitches'],'PITCH_TYPE_SHARE_INCLUDES_EXPLICIT_UNKNOWN_BUCKET')
 out['whiff_pct']=ratio('misses','swings','swings',c['minimum_swings'])
 out['chase_pct']=ratio('outside_swings','outside','n',c['minimum_pitches'])
 out['zone_contact_pct']=ratio('zone_contacts','zone_swings','zone_known_swings',c['minimum_zone_swings'])
 out['outside_zone_contact_pct']=ratio('outside_contacts','outside_swings','zone_known_swings',c['minimum_zone_swings'])
 # Contact denominator coverage is tracked against all swings, separately from location conditioning.
 out['contact_pct']=((r['swings']-r['misses'])/r['swings'] if r['swings'] else None,r['swings']-r['misses'],r['swings'],r['swings'],c['minimum_swings'],'INHERITED_SWING_CONTACT_EVENTS')
 out['zone_swing_pct']=ratio('zone_swings','inzone','n',c['minimum_pitches'])
 out['outside_zone_swing_pct']=out['chase_pct']
 out['swinging_strike_pct']=ratio('misses','known','n',c['minimum_pitches'])
 out['called_strike_plus_whiff_pct']=ratio('called_whiffs','known','n',c['minimum_pitches'])
 for n,name in [('ground_ball','gb_pct'),('line_drive','ld_pct'),('fly_ball','fb_pct'),('popup','popup_pct')]:out[name]=ratio(n,'bt_n','bbe',c['minimum_bbe'])
 out['air_pct']=((r['bt_n']-r['ground_ball'])/r['bt_n'] if r['bt_n'] else None,r['bt_n']-r['ground_ball'],r['bt_n'],r['bbe'],c['minimum_bbe'],'AIR_LD_FB_POPUP_OVER_CLASSIFIED_BBE')
 for n in ['mean','sd','p10','p50','p90']:out['launch_angle_'+n]=(r['la_'+n],r['la_sum'] if n=='mean' else None,r['la_n'],r['bbe'],c['minimum_bbe'],'VALID_LA_DEGREES_POPULATION_SD_LINEAR_QUANTILES')
 for n,name in [('sweet','launch_angle_8_32_pct'),('negative_la','launch_angle_below_zero_pct'),('high_la','launch_angle_ge50_pct')]:out[name]=ratio(n,'la_n','bbe',c['minimum_bbe'])
 out['pull_proxy_pct']=ratio('pull_n','direction_n','bbe',c['minimum_bbe'],'RESEARCH_COORDINATE_PROXY_NOT_OFFICIAL_SAVANT_MATCH')
 out['pulled_air_proxy_per_bbe']=ratio('pull_air_n','direction_bt_n','bbe',c['minimum_bbe'],'RESEARCH_COORDINATE_PROXY_AIR_LD_FB_POPUP')
 out['pulled_air_proxy_per_air']=ratio('pull_air_n','direction_air_n','air_n',c['minimum_bbe'],'RESEARCH_COORDINATE_PROXY_CONDITIONAL_AIR')
 out['pulled_barrel_proxy_per_bbe']=ratio('pull_barrel_n','direction_barrel_n','bbe',c['minimum_bbe'],'RESEARCH_COORDINATE_PROXY_CLASSIFIED_BARREL')
 out['pulled_barrel_proxy_per_barrel']=ratio('pull_barrel_n','barrels_direction_n','barrels_n',c['minimum_barrels'],'RESEARCH_COORDINATE_PROXY_CONDITIONAL_BARREL')
 for n in ['release_speed','release_spin_rate','release_extension','pfx_x','pfx_z','release_pos_x','release_pos_z']:out[n+'_mean']=(r[n+'_mean'],r[n+'_sum'],r[n+'_n'],r['n'],c['minimum_pitches'],'RAW_CATCHER_PERSPECTIVE_FEET_FOR_MOVEMENT_NOT_IVB')
 return out

def feature_rows(year,role,r,c):
 out=[]
 for metric,(v,num,den,opp,minimum,definition) in metric_specs(r,c).items():
  # Domain opportunity fractions (zone selection, air/barrel selection) are not missingness.
  cn,co=den,opp
  # Conditional contact/pull rates get independent measurement coverage, not selection frequency.
  if metric in ['zone_contact_pct','outside_zone_contact_pct']:cn,co=r['zone_known_swings'],r['swings']
  if metric in ['chase_pct','outside_zone_swing_pct','zone_swing_pct']:cn,co=r['zone_known'],r['n']
  if metric=='pulled_air_proxy_per_air':cn,co=r['direction_bt_n'],r['bbe']
  if metric=='pulled_barrel_proxy_per_barrel':cn,co=r['direction_barrel_n'],r['bbe']
  if metric in ['whiff_pct','chase_pct','zone_contact_pct','outside_zone_contact_pct','contact_pct','zone_swing_pct','outside_zone_swing_pct','swinging_strike_pct','called_strike_plus_whiff_pct'] and co and r['n'] and r['known']/r['n']<cn/co:cn,co=r['known'],r['n']
  coverage=cn/co if co else None
  eligible=v is not None and math.isfinite(v) and den>=minimum and coverage is not None and coverage>=c['minimum_measurement_coverage']
  out.append(dict(source_season=year,player_type=role,mlbam_id=str(int(r['mlbam_id'])),pitch_type=r['pitch_group'],metric=metric,raw_value=v,numerator=num,denominator=den,opportunities=opp,coverage_observations=cn,coverage_opportunities=co,coverage=coverage,eligible=eligible,value=v if eligible else None,minimum_observations=minimum,reason='AVAILABLE_FIXED_CONTROLS' if eligible else 'MISSING_OR_BELOW_FIXED_SAMPLE_COVERAGE',definition=definition,tracking_era=era(year),short_season=year==2020))
 return out

FIELDS=['source_season','player_type','mlbam_id','pitch_type','metric','raw_value','numerator','denominator','opportunities','coverage_observations','coverage_opportunities','coverage','eligible','value','minimum_observations','reason','definition','tracking_era','short_season']

def parquet_from_csv(db,path):
 types={n:'VARCHAR' for n in FIELDS};types.update({n:'DOUBLE' for n in ['raw_value','numerator','denominator','opportunities','coverage_observations','coverage_opportunities','coverage','value']});types.update({n:'INTEGER' for n in ['source_season','minimum_observations','tracking_era']});types.update(eligible='BOOLEAN',short_season='BOOLEAN')
 db.read_csv(str(path),header=True,columns=types).write_parquet(str(path.with_suffix('.parquet')),compression='zstd')

def lag_tables(db,stage,matrix,watched,metrics):
 for split in ['training','holdout']:
  path=checked(matrix,split+'_features.parquet',watched);db.execute('CREATE OR REPLACE TEMP VIEW pop AS SELECT target_season,player_type,CAST(mlbam_id AS VARCHAR) AS mlbam_id,history_seasons,age_at_target_estimate,max_source_season,source_cutoff FROM read_parquet('+lit(path)+')')
  invalid=db.execute("SELECT count(*) FROM pop WHERE target_season IS NULL OR max_source_season>=target_season OR try_cast(source_cutoff AS DATE)>=CAST(CAST(target_season AS VARCHAR)||'-01-01' AS DATE) OR source_cutoff IS NULL OR max_source_season IS NULL OR try_cast(source_cutoff AS DATE) IS NULL OR player_type NOT IN ('hitter','pitcher') OR try_cast(mlbam_id AS BIGINT)<=0 OR try_cast(mlbam_id AS BIGINT) IS NULL"+(' OR target_season<>2026' if split=='holdout' else ' OR target_season NOT BETWEEN 2016 AND 2025')).fetchone()[0]
  if invalid or db.execute('SELECT count(*) FROM (SELECT target_season,player_type,mlbam_id FROM pop GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Invalid/duplicate chronological feature population')
  q='''SELECT p.target_season,p.player_type,p.mlbam_id,p.history_seasons,p.age_at_target_estimate,l.lag,p.target_season-l.lag AS source_season,m.metric,s.value,s.denominator,s.opportunities,s.coverage_observations,s.coverage_opportunities,s.coverage,coalesce(s.eligible,false) AS eligible,coalesce(s.reason,'NO_SOURCE_PLAYER_SEASON') AS reason,s.definition,s.tracking_era FROM pop p CROSS JOIN (VALUES (1),(2),(3)) l(lag) CROSS JOIN metric_names m LEFT JOIN expanded s ON s.source_season=p.target_season-l.lag AND s.player_type=p.player_type AND s.mlbam_id=p.mlbam_id AND s.metric=m.metric'''
  db.execute('COPY ('+q+') TO '+lit(stage/(split+'_expanded_features.parquet'))+" (FORMAT PARQUET,COMPRESSION ZSTD)")
  # Audit candidate availability, never condition the population on target-season outcomes.
  db.execute('CREATE OR REPLACE VIEW lagged AS SELECT * FROM read_parquet('+lit(stage/(split+'_expanded_features.parquet'))+')')
  names=[x[0] for x in db.execute('DESCRIBE SELECT target_season,player_type,lag,metric,count(*) AS population_rows,count(value) AS available_rows,count(*) FILTER(WHERE eligible) AS eligible_rows FROM lagged GROUP BY ALL').fetchall()]
  result=db.execute('SELECT target_season,player_type,lag,metric,count(*) AS population_rows,count(value) AS available_rows,count(*) FILTER(WHERE eligible) AS eligible_rows FROM lagged GROUP BY ALL ORDER BY ALL').fetchall()
  emit(stage/(split+'_lag_availability.csv'),[dict(zip(names,r)) for r in result])

def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 c=config_checked(a.config);matrix=Path(a.matrix).resolve();watched={str(Path(a.config).resolve()):sha(a.config)}
 manifest=checked(matrix,'source_windows.json',watched);base=load(checked(matrix,'effective_config.json',watched));schema_path=checked(matrix,'feature_schema.json',watched)
 if not base['source_seasons'] or len(base['source_seasons'])!=len(set(base['source_seasons'])) or any(not c['source_min_season']<=y<=c['source_max_season'] for y in base['source_seasons']) or base['holdout_target_season']!=2026:raise ValueError('Unsupported source/evaluation chronology')
 print('Verifying frozen archive versions and hashes; 2026 source pitches excluded...',flush=True)
 selected,hashes=windows(manifest,base);watched.update(hashes)
 out,backups,stage=start(a.output,a.backup_root,[matrix,a.config]+[Path(r['parquet_path']) for r in selected]+[Path(r['raw_path']) for r in selected]+[Path(r['schedule_path']) for r in selected])
 schema=[];columns=[];bat=[];annual=[];availability=defaultdict(Counter);metricset=set();nrows=0;pitchrows=0
 try:
  with duckdb.connect() as db, (stage/'expanded_features_season.csv').open('w',encoding='utf-8',newline='') as of, (stage/'pitch_type_features_season.csv').open('w',encoding='utf-8',newline='') as pf:
   writers=[csv.DictWriter(f,fieldnames=FIELDS) for f in [of,pf]]
   for w in writers:w.writeheader()
   for y in base['source_seasons']:
    print(f'{y}: auditing columns and deriving contact/elevation/pitch-type measures...',flush=True)
    nfiles,n=prepare(db,selected,y,schema,columns,bat);pitchrows+=n
    for role,r in aggregates(db,c):
     rows=feature_rows(y,role,r,c);overall=r['pitch_group']=='ALL'
     for row in rows:
      if overall:
       writers[0].writerow(row);metricset.add(row['metric']);ctr=availability[y,role,row['metric']];ctr['player_seasons']+=1;ctr['eligible_player_seasons']+=int(row['eligible']);ctr['observations']+=row['denominator'];ctr['opportunities']+=row['opportunities'];ctr['coverage_observations']+=row['coverage_observations'];ctr['coverage_opportunities']+=row['coverage_opportunities'];nrows+=1
      elif row['metric'] in ['pitch_type_usage','release_speed_mean','release_spin_rate_mean','release_extension_mean','pfx_x_mean','pfx_z_mean','release_pos_x_mean','release_pos_z_mean','whiff_pct','chase_pct','zone_contact_pct','outside_zone_contact_pct','called_strike_plus_whiff_pct','gb_pct','air_pct','launch_angle_mean']:
       writers[1].writerow(row)
     if overall:annual.append(dict(source_season=y,player_type=role,mlbam_id=str(int(r['mlbam_id'])),pitch_rows=r['n'],recognized_descriptions=r['known'],unrecognized_descriptions=r['n']-r['known'],swings=r['swings'],bbe=r['bbe'],classified_bbe=r['bt_n'],zone_known=r['zone_known'],direction_measured_bbe=r['direction_n']))
    # No physical pitch rows retained across years.
  with duckdb.connect() as db:
   for path in [stage/'expanded_features_season.csv',stage/'pitch_type_features_season.csv']:parquet_from_csv(db,path)
   db.execute('CREATE VIEW expanded AS SELECT * FROM read_parquet('+lit(stage/'expanded_features_season.parquet')+')')
   db.execute('CREATE TEMP TABLE metric_names(metric VARCHAR)');db.executemany('INSERT INTO metric_names VALUES (?)',[(m,) for m in sorted(metricset)])
   lag_tables(db,stage,matrix,watched,metricset)
  availability_rows=[dict(source_season=y,player_type=role,metric=m,**v,eligible_fraction=v['eligible_player_seasons']/v['player_seasons'] if v['player_seasons'] else None,pooled_measurement_coverage=v['coverage_observations']/v['coverage_opportunities'] if v['coverage_opportunities'] else None) for (y,role,m),v in sorted(availability.items())]
  for name,rows in [('schema_availability',schema),('numeric_value_audit',columns),('bat_tracking_field_inventory',bat),('player_season_context',annual),('feature_availability_by_season',availability_rows),('transition_2021_availability',[r for r in availability_rows if r['source_season']==2021])]:emit(stage/(name+'.csv'),rows)
  requests=[]
  for y in [2023,2024,2025]:
   for role in ['hitter','pitcher']:
    requests.append(dict(source_season=y,player_type=role,source_url='https://baseballsavant.mlb.com/leaderboard/bat-tracking',required_export='Regular-season player-level CSV; MLBAM IDs; competitive swing/contact counts; squared-up counts and per-swing/per-contact rates; bat speed; fast-swing rate; blasts; swing length',date_scope='SECOND_HALF_ONLY_VERIFY_EXACT_DATES' if y==2023 else 'FULL_REGULAR_SEASON_VERIFY_COVERAGE',purpose='SEPARATE_BAT_TRACKING_RESEARCH_BRANCH',status='CHECK_SAVED_RAW_FIRST_THEN_EXPORT_MISSING_METRICS_VERIFY_DEFINITIONS',as_of_policy='Preserve actual download date separately from historical event period; retrospective retrieval is not archived preseason availability'))
  for y in base['source_seasons']:
   requests.append(dict(source_season=y,player_type='both',source_url='https://baseballsavant.mlb.com/leaderboard/batted-ball',required_export='Official batted-ball profile with player IDs, BBE, Pull AIR%, GB/LD/FB/PU for proxy validation',date_scope='FULL_REGULAR_SEASON',purpose='VALIDATE_COORDINATE_PULL_PROXY',status='RECOMMENDED_DEFINITION_RECONCILIATION_BEFORE_MODEL_USE',as_of_policy='Retrospective event-period reference'))
  emit(stage/'supplemental_download_plan.csv',requests)
  dump(stage/'feature_contract.json',dict(version=VERSION,settings=c,source='Frozen prior physical pitches; no official outcome counts reconstructed',feature_unit='Fractions 0..1; angles degrees; movement/extension feet; velocity mph; spin rpm',definition_status='Pull metrics are research coordinate proxies, not certified Savant definitions',lag_join='Existing frozen training/holdout feature population; prior source season only; long format; absent history remains null',new_metric_names=sorted(metricset),existing_equivalents={'whiff_pct':'whiff_pct','chase_pct':'chase_pct','outside_zone_swing_pct':'chase_pct','release_speed_mean':'velocity','release_spin_rate_mean':'spin_rpm','release_extension_mean':'extension_ft'},lag_value_policy='raw_value and numerator withheld from lag add-ons; audit CSV/Parquet retain them separately',source_columns_audited=NUMBERS+TEXT,bat_tracking='Audited field availability only; no squared-up/blast calculation or import',K_minus_BB='Not derived from pitch terminal events; retain eligible prior actual SO/BB/PA/TBF from the existing actuals branch',predictor_policy='Only value and explicit coverage/sample metadata are candidate predictors; raw_value, numerator and raw audit fields are not an imputation bypass; future fold preprocessing required',accepted_matrix_modified=False))
  report=dict(version=VERSION,status='EXPANDED_FEATURES_BUILT_AVAILABILITY_REVIEW_REQUIRED',source_seasons=base['source_seasons'],frozen_windows=len(selected),pitch_rows=pitchrows,overall_feature_rows=nrows,metrics=len(metricset),raw_only_recoverable_column_seasons=sum(r['status']=='RAW_ONLY_SCHEMA_RECOVERY_CANDIDATE' for r in schema),bat_tracking_field_rows=len(bat),models_fitted=False,forecasts_modified=False,accepted_matrix_modified=False,target_outcomes_read=False,source_2026_pitches_read=False,inputs_unchanged=True,model_ready=False,limitations=['Saved archive hashes/schema/coverage only; no independent schedule or official-season-total certification.', 'Pull direction is a fixed coordinate proxy; official leaderboard reconciliation required.', 'Coverage/sample thresholds are fixed research controls, not optimized and not proof of physical comparability.', 'Whiff/chase definitions inherit the prior pipeline; zone contact uses its recognized contact events.', 'Conditional denominators and measurement coverage are distinct; consult metric definition and audit counts.', 'Raw pfx movement is catcher-perspective feet, not induced vertical break or handedness-normalized movement.', 'Bat tracking requires supplemental exports and definition verification; 2023 availability is partial.', 'Long feature add-ons are not yet wired into a fitted model; do not feed raw audit fields as predictors.', 'Retrospectively retrieved sources; all 2026 outcomes excluded. 2020/2021 retained.'])
  dump(stage/'expanded_feature_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(matrix='outputs/standalone_lagged_features_v1_0',config='config/expanded_statcast_v1_20.json',output='outputs/expanded_statcast_v1_20',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
