"""Frozen denominator/count reconciliation and targeted physical-event scope audit. No fitting."""
import argparse,csv,math,json,shutil
from pathlib import Path,PureWindowsPath
from collections import Counter,defaultdict
from datetime import date,timedelta
import duckdb
from standalone_io_v1_0 import load,dump,sha,start,finish,write

VERSION='1.22.0'
IMPLEMENTATION_VERSION='1.22.1'
DEFAULT=dict(version=VERSION,source_seasons=[2023,2024,2025],substantial_bbe=100,top_per_metric_role_season=5,
 rate_tolerance=.0005001,mean_tolerance=.0500001,pull_tolerance=.02,
 trace_metrics=['avg_hit_speed','avg_hit_angle','anglesweetspotpercent','pull_rate','pull_air_rate'],
 pull_origin_x=125.42,pull_origin_y=198.27,pull_boundary_degrees=15.,fair_cone_degrees=45.,
 policy='AUDIT_ONLY_NO_SOURCE_SUBSTITUTION_NO_MODEL_FIT')
COUNT_METRICS={'ev95percent':('ev95plus','hardhit','ev_n'),'brl_percent':('barrels','barrels','barrel_n')}
REPLAY={'avg_hit_speed':('ev','ev_n'),'avg_hit_angle':('la','la_n'),
 'anglesweetspotpercent':('sweet_rate','la_n'),'ev95percent':('hardhit_rate','ev_n'),
 'brl_percent':('barrel_rate','barrel_n'),'pull_rate':('pull_rate','direction_n'),
 'pull_air_rate':('pull_air_rate','direction_bt_n')}

def lit(x):return "'"+str(x).replace("'","''")+"'"
def emit(p,rows):write(p,rows,list(dict.fromkeys(k for r in rows for k in r)) or ['status'])
def num(v):
 if v is None or str(v).strip().lower() in ['','null','none','nan','n/a','na','--']:return None
 x=float(v)
 if not math.isfinite(x):raise ValueError('Nonfinite audit value')
 return x
def ratio(n,d):return n/d if n is not None and d is not None and d>0 else None
def close(a,b,tol=1e-8):return a is None and b is None or a is not None and b is not None and abs(a-b)<=tol
def key(r):return int(r['source_season']),r['player_type'],str(r['mlbam_id'])
def portable_manifest(manifest):
 normalized={}
 for name,value in manifest.items():
  portable=name.replace('\\','/')
  if PureWindowsPath(name).drive or portable.startswith('/') or any(p in ('','.', '..') for p in portable.split('/')):raise ValueError('Unsafe frozen manifest path: '+name)
  if portable in normalized:raise ValueError('Ambiguous frozen manifest path: '+portable)
  normalized[portable]=value
 return normalized
def checked(root,name,watched):
 root=Path(root).resolve();mp=root/'output_sha256.json';manifest=portable_manifest(load(mp));name=name.replace('\\','/');p=(root/name).resolve()
 if root not in p.parents or name not in manifest or sha(p)!=manifest[name]:raise ValueError('Frozen hash/path failure: '+str(p))
 watched[str(mp)]=sha(mp);watched[str(p)]=sha(p);return p
def readcsv(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))

def check_export_snapshots(lb,history,watched,c):
 inventory=load(checked(lb,'source_inventory.json',watched));seen=set();sources=[]
 for s in inventory['sources']:
  if s['family']!='exit_velocity' or s['registered_season'] not in c['source_seasons']:continue
  path=checked(lb,'source_snapshots/'+Path(s['file']).name,watched)
  if sha(path)!=s['sha256']:raise ValueError('Raw export snapshot differs from registration')
  for raw in readcsv(path):
   k=(s['registered_season'],s['player_type'],str(int(raw['player_id'])))
   if k in seen:raise ValueError('Duplicate raw EV export player')
   seen.add(k);rr={m:h for (f,m),h in history.get(k,{}).items() if f=='exit_velocity'}
   if not rr or any(h['source_id']!=s['source_id'] or raw.get(m)!=(h['raw_text'] or '') or not close(num(raw.get(m)),h['raw_value']) for m,h in rr.items()):raise ValueError('Raw EV export differs from frozen normalized table')
  sources.append(dict(source_id=s['source_id'],registered_season=s['registered_season'],player_type=s['player_type'],file=path.name,sha256=sha(path)))
 if seen!={k for k,mm in history.items() if any(f=='exit_velocity' for f,m in mm)}:raise ValueError('Historical raw EV snapshot coverage differs')
 return sources

def selected_windows(matrix,watched,c):
 manifest=checked(matrix,'source_windows.json',watched);base=load(checked(matrix,'effective_config.json',watched))
 if base.get('holdout_target_season')!=2026 or not set(c['source_seasons'])<=set(base['source_seasons']):raise ValueError('Source chronology differs')
 selected=[];seen=set();paths=set()
 for r in load(manifest):
  # Check year before any source file access. No 2026 pitch/hash/schedule opens.
  y=int(r['day'][:4])
  if y not in c['source_seasons']:continue
  d=date.fromisoformat(r['day'])
  if r['day'] in seen or r['status']!='COMPLETE' or not date(y,3,1)<=d<=date(y,11,1) or int(r['rows'])!=r['rows'] or r['rows']<0:raise ValueError('Invalid/duplicate frozen window')
  seen.add(r['day'])
  for stem in ['raw','parquet','schedule']:
   p=Path(r[stem+'_path']).resolve();h=r[stem+'_hash']
   if str(p) in paths or sha(p)!=h:raise ValueError('Reused source path or source hash mismatch')
   paths.add(str(p));watched[str(p)]=h
  selected.append(r)
  if len(selected)%250==0:print(f'{len(selected):,} historical daily windows verified...',flush=True)
 expected=set()
 for y in c['source_seasons']:
  d=date(y,3,1)
  while d<=date(y,11,1):expected.add(d.isoformat());d+=timedelta(days=1)
 if seen!=expected:raise ValueError('Incomplete historical daily window coverage')
 return selected,manifest

def prepare(db,windows,year,c):
 group=[r for r in windows if int(r['day'][:4])==year];paths=[r['parquet_path'] for r in group if r['rows']]
 if not paths:raise ValueError('No nonempty historical windows')
 db.execute('CREATE OR REPLACE VIEW raw AS SELECT * FROM read_parquet(['+','.join(map(lit,paths))+'],union_by_name=true,hive_partitioning=false,filename=true)')
 cols={r[0] for r in db.execute('DESCRIBE raw').fetchall()}
 required={'game_pk','at_bat_number','pitch_number','game_date','game_type','batter','pitcher','type','description'}
 if not required<=cols:raise ValueError('Missing physical pitch identity fields')
 invalid="game_type IS DISTINCT FROM 'R' OR "+' OR '.join(f'{n} IS NULL OR try_cast({n} AS DOUBLE) IS NULL OR NOT isfinite(try_cast({n} AS DOUBLE)) OR {n}<=0 OR {n}<>trunc({n})' for n in ['game_pk','at_bat_number','pitch_number','batter','pitcher'])
 if db.execute('SELECT count(*) FROM raw WHERE '+invalid).fetchone()[0]:raise ValueError('Invalid pitch key/role/game type')
 if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM raw GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Duplicate physical pitches')
 if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number FROM raw WHERE "type"=\'X\' GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Multiple BBE in a PA')
 dates={str(d):n for d,n in db.execute('SELECT CAST(game_date AS DATE),count(*) FROM raw GROUP BY 1').fetchall()}
 if dates!={r['day']:r['rows'] for r in group if r['rows']}:raise ValueError('Frozen date/row counts differ')
 expr=[]
 for n in ['launch_speed','launch_angle','launch_speed_angle','hc_x','hc_y','hit_location','estimated_woba_using_speedangle']:
  v=f'try_cast("{n}" AS DOUBLE)' if n in cols else 'NULL::DOUBLE'
  expr.append(f'CASE WHEN isfinite({v}) THEN {v} END AS "{n}"')
 for n in ['stand','bb_type','events']:
  expr.append((f'CAST("{n}" AS VARCHAR)' if n in cols else 'NULL::VARCHAR')+' AS "'+n+'"')
 db.execute('CREATE OR REPLACE TEMP TABLE bbe0 AS SELECT game_pk,at_bat_number,pitch_number,CAST(game_date AS VARCHAR) AS game_date,batter,pitcher,description,filename,'+','.join(expr)+' FROM raw WHERE "type"=\'X\'')
 # Classic EV deliberately inherits finite-only scope; invalid physical values are reported, not silently removed.
 x=c['pull_origin_x'];y=c['pull_origin_y'];angle=f'degrees(atan2(hc_x-{x},{y}-hc_y))'
 direction=f'hc_x IS NOT NULL AND hc_y IS NOT NULL AND NOT(hc_x={x} AND hc_y={y}) AND {y}-hc_y>0 AND abs({angle})<={c["fair_cone_degrees"]} AND stand IN (\'L\',\'R\')'
 db.execute('CREATE OR REPLACE TEMP TABLE bbe1 AS SELECT *,CASE WHEN launch_angle BETWEEN -90 AND 90 THEN launch_angle END AS valid_la,CASE WHEN launch_speed_angle BETWEEN 1 AND 6 AND launch_speed_angle=trunc(launch_speed_angle) THEN launch_speed_angle END AS valid_class,'+angle+' AS spray_angle,coalesce('+direction+',false) AS direction_known FROM bbe0')
 db.execute('CREATE OR REPLACE TEMP TABLE bbe AS SELECT *,coalesce(direction_known AND ((stand=\'R\' AND spray_angle<-'+str(c['pull_boundary_degrees'])+') OR (stand=\'L\' AND spray_angle>'+str(c['pull_boundary_degrees'])+')),false) AS pulled,coalesce(bb_type IN (\'ground_ball\',\'line_drive\',\'fly_ball\',\'popup\'),false) AS type_known FROM bbe1')
 bank={}
 for role,idcol in [('hitter','batter'),('pitcher','pitcher')]:
  q=f'''SELECT CAST({idcol} AS BIGINT) mlbam_id,count(*) bbe,count(launch_speed) ev_n,avg(launch_speed) ev,
   count(*) FILTER(WHERE launch_speed>=95) hardhit,
   count(*) FILTER(WHERE launch_speed_angle BETWEEN 1 AND 6) barrel_n,count(*) FILTER(WHERE launch_speed_angle=6) barrels,
   count(valid_la) la_n,avg(valid_la) la,count(*) FILTER(WHERE valid_la BETWEEN 8 AND 32) sweet,
   count(*) FILTER(WHERE direction_known) direction_n,count(*) FILTER(WHERE pulled) pull_n,
   count(*) FILTER(WHERE direction_known AND type_known) direction_bt_n,
   count(*) FILTER(WHERE pulled AND bb_type IN ('line_drive','fly_ball','popup')) pull_air_n,
   count(*) FILTER(WHERE launch_speed<0 OR launch_speed>130) invalid_ev,
   count(*) FILTER(WHERE launch_angle IS NOT NULL AND valid_la IS NULL) invalid_la,
   count(*) FILTER(WHERE launch_speed_angle IS NOT NULL AND valid_class IS NULL) invalid_class
   FROM bbe GROUP BY 1'''
  cur=db.execute(q);names=[x[0] for x in cur.description]
  for row in cur.fetchall():
   a=dict(zip(names,row));pid=str(a.pop('mlbam_id'));a.update(hardhit_rate=ratio(a['hardhit'],a['ev_n']),barrel_rate=ratio(a['barrels'],a['barrel_n']),sweet_rate=ratio(a['sweet'],a['la_n']),pull_rate=ratio(a['pull_n'],a['direction_n']),pull_air_rate=ratio(a['pull_air_n'],a['direction_bt_n']))
   bank[year,role,pid]=a
 return bank

def denominator_row(r,metrics,a,c):
 m=r['metric'];countmetric,nfield,dfield=COUNT_METRICS[m];count=num(metrics[countmetric]['raw_value']);export_bbe=num(metrics['attempts']['raw_value']);rate=num(r['export_normalized']);n=a[nfield] if a else None;measured=a[dfield] if a else None;total=a['bbe'] if a else None
 rate_measured=ratio(n,measured);rate_total=ratio(n,total);rate_exportbbe=ratio(n,export_bbe);tol=c['rate_tolerance']
 counts_agree=count is not None and n is not None and count==n
 measured_match=rate is not None and rate_measured is not None and close(rate,rate_measured,tol)
 total_match=rate is not None and rate_total is not None and close(rate,rate_total,tol)
 raw_rel=ratio(count,export_bbe);normalization_flag=rate is not None and raw_rel is not None and not close(rate,raw_rel,tol)
 status='MISSING_EXPORT_OR_ARCHIVE' if any(v is None for v in [rate,count,export_bbe,n,measured,total]) else 'NUMERATOR_DIFFERENCE' if not counts_agree else 'BBE_SCOPE_DIFFERENCE' if total!=export_bbe else 'RATE_MATCHES_BOTH_DENOMINATORS' if measured_match and total_match else 'RATE_MATCHES_TOTAL_BBE_ONLY' if total_match else 'RATE_MATCHES_MEASURED_ONLY' if measured_match else 'RATE_DEFINITION_UNRESOLVED'
 # Prior 52 accounting residuals are selected exactly from the old report, independently of new raw reconstruction.
 old_value=num(r['archive_value']);old_obs=num(r['archive_observations']);old_total=num(r['archive_bbe']);old_delta=num(r['value_difference'])
 old_rescaled=old_value*old_obs/old_total if old_value is not None and old_obs is not None and old_total else None
 old_flag=old_delta is not None and abs(old_delta)>num(r['review_tolerance'])
 residual=bool(old_flag and rate is not None and old_rescaled is not None and not close(rate,old_rescaled,tol))
 # Integer denominator candidates compatible with displayed rounding, not inferred event membership.
 candidates=[]
 if count is not None and rate is not None and export_bbe is not None:
  candidates=[d for d in range(max(1,int(count)),int(export_bbe)+1) if close(count/d,rate,tol)]
 return dict(**{k:r[k] for k in ['source_season','player_type','mlbam_id','metric','source_id']},name=metrics['attempts'].get('name'),export_count=count,export_rate=rate,export_bbe=export_bbe,archive_numerator=n,archive_measured_denominator=measured,archive_total_bbe=total,archive_rate_measured=rate_measured,archive_rate_total_bbe=rate_total,archive_rate_export_bbe=rate_exportbbe,export_count_over_bbe=raw_rel,numerator_difference=count-n if count is not None and n is not None else None,export_vs_measured_rate_difference=rate-rate_measured if rate is not None and rate_measured is not None else None,export_vs_total_rate_difference=rate-rate_total if rate is not None and rate_total is not None else None,total_bbe_counts_match=total==export_bbe if total is not None else False,measured_denominator_matches_export_bbe=measured==export_bbe if measured is not None else False,export_count_matches_archive=counts_agree,original_normalization_flag=normalization_flag,prior_accounting_residual=residual,compatible_integer_denominator_count=len(candidates),compatible_integer_denominator_min=min(candidates) if candidates else None,compatible_integer_denominator_max=max(candidates) if candidates else None,status=status,counts_replaced=False)

def choose_targets(recon,denoms,c):
 targets=defaultdict(set)
 for r in denoms:
  if r['original_normalization_flag']:targets[key(r)].add('EXPORTED_COUNT_RATE_FLAG')
  if r['prior_accounting_residual']:targets[key(r)].add('PRIOR_ACCOUNTING_RESIDUAL_'+r['metric'])
  if r['status'] in ['NUMERATOR_DIFFERENCE','BBE_SCOPE_DIFFERENCE','RATE_DEFINITION_UNRESOLVED']:targets[key(r)].add(r['status']+'_'+r['metric'])
 groups=defaultdict(list)
 for r in recon:
  if r['metric'] not in c['trace_metrics'] or num(r['export_denominator']) is None or num(r['export_denominator'])<c['substantial_bbe'] or num(r['value_difference']) is None:continue
  if abs(num(r['value_difference']))<=num(r['review_tolerance']):continue
  groups[int(r['source_season']),r['player_type'],r['metric']].append(r)
 for g,rows in groups.items():
  for r in sorted(rows,key=lambda r:(-abs(num(r['value_difference'])),int(r['mlbam_id'])))[:c['top_per_metric_role_season']]:targets[key(r)].add('TOP_SUBSTANTIAL_'+r['metric'])
 return targets

def trace_events(db,year,targets,stage,append):
 selected=[(role,int(pid),'|'.join(sorted(reasons))) for (y,role,pid),reasons in sorted(targets.items()) if y==year]
 db.execute('CREATE OR REPLACE TEMP TABLE targets(player_type VARCHAR,mlbam_id BIGINT,trace_reasons VARCHAR)')
 if selected:db.executemany('INSERT INTO targets VALUES (?,?,?)',selected)
 q='''SELECT '''+str(year)+''' AS source_season,t.player_type,CAST(t.mlbam_id AS VARCHAR) AS mlbam_id,t.trace_reasons,b.*,
  launch_speed IS NOT NULL AS ev_observed,valid_la IS NOT NULL AS la_observed,
  launch_speed>=95 AS hardhit_event,launch_speed_angle=6 AS barrel_event,
  launch_speed_angle BETWEEN 1 AND 6 AS classic_barrel_denominator_member,
  valid_class IS NOT NULL AS integer_classification_valid,
  coalesce(description LIKE '%bunt%',false) AS bunt_description_hint,
  coalesce(launch_speed<50,false) AS low_ev_diagnostic_only
 FROM bbe b JOIN targets t ON (t.player_type='hitter' AND t.mlbam_id=b.batter) OR (t.player_type='pitcher' AND t.mlbam_id=b.pitcher)'''
 db.execute('CREATE OR REPLACE TEMP VIEW trace AS '+q)
 cur=db.execute('SELECT * FROM trace ORDER BY player_type,mlbam_id,game_pk,at_bat_number,pitch_number');fields=[x[0] for x in cur.description];count=0
 with (stage/'target_event_trace.csv').open('a' if append else 'w',encoding='utf-8',newline='') as f:
  w=csv.writer(f)
  if not append:w.writerow(fields)
  while True:
   batch=cur.fetchmany(5000)
   if not batch:break
   w.writerows(batch);count+=len(batch)
 subgroups={'ALL_BBE':'true','EV_MEASURED':'ev_observed','EV_MISSING':'NOT ev_observed','LA_MEASURED':'la_observed','LA_MISSING_OR_INVALID':'NOT la_observed','CLASSIFICATION_VALID':'integer_classification_valid','CLASSIFICATION_MISSING_OR_INVALID':'NOT integer_classification_valid','DIRECTION_UNAVAILABLE':'NOT direction_known','EV_BELOW_50_DIAGNOSTIC':'low_ev_diagnostic_only','EV_AT_LEAST_50_DIAGNOSTIC':'launch_speed>=50','BUNT_DESCRIPTION_HINT_ONLY':'bunt_description_hint'}
 subgroups.update({name:"bb_type="+lit(name) for name in ['ground_ball','line_drive','fly_ball','popup']})
 summaries=[]
 for name,condition in subgroups.items():
  cur=db.execute('''SELECT source_season,player_type,mlbam_id,count(*) AS bbe,count(launch_speed) AS ev_n,avg(launch_speed) AS ev_mean,count(valid_la) AS la_n,avg(valid_la) AS la_mean,count(*) FILTER(WHERE valid_la BETWEEN 8 AND 32) AS sweet_n,count(*) FILTER(WHERE hardhit_event) AS hardhit_n,count(*) FILTER(WHERE barrel_event) AS barrel_n,count(*) FILTER(WHERE direction_known) AS direction_n,count(*) FILTER(WHERE pulled) AS pull_n FROM trace WHERE '''+condition+' GROUP BY ALL ORDER BY ALL');fields=[x[0] for x in cur.description]
  summaries.extend(dict(zip(fields,row),subgroup=name,interpretation='DESCRIPTIVE_OVERLAPPING_SUBGROUP_NOT_OFFICIAL_SCOPE_PROOF') for row in cur.fetchall())
 # Date-level bridge locates events without broad network downloads.
 cur=db.execute('''SELECT source_season,player_type,mlbam_id,game_date,game_pk,count(*) AS bbe,count(launch_speed) AS ev_n,sum(launch_speed) AS ev_sum,count(valid_la) AS la_n,sum(valid_la) AS la_sum,count(*) FILTER(WHERE hardhit_event) AS hardhit_n,count(*) FILTER(WHERE barrel_event) AS barrel_n,count(*) FILTER(WHERE pulled) AS pull_n FROM trace GROUP BY ALL ORDER BY ALL''');fields=[x[0] for x in cur.description]
 games=[dict(zip(fields,row)) for row in cur.fetchall()]
 return count,summaries,games

def decisions(history,denoms,recon):
 di={(key(r),r['metric']):r for r in denoms};ri={(key(r),r['metric']):r for r in recon};rows=[]
 for k,metrics in sorted(history.items()):
  for (family,m),h in sorted(metrics.items()):
   family=h['family'];existing=h['eligible'] is True;d=di.get((k,m));r=ri.get((k,m))
   count_check=di.get((k,'ev95percent' if m=='ev95plus' else 'brl_percent')) if family=='exit_velocity' and m in ['ev95plus','barrels'] else None
   if not existing:status='HELD_EXISTING_SAMPLE_OR_DEFINITION_MASK'
   elif d and d['status'] not in ['RATE_MATCHES_BOTH_DENOMINATORS','RATE_MATCHES_TOTAL_BBE_ONLY','RATE_MATCHES_MEASURED_ONLY']:status='HELD_UNRESOLVED_COUNTS_OR_RATE_SCOPE'
   elif d:status='RESEARCH_ELIGIBLE_EXPLICIT_DENOMINATOR'
   elif count_check and count_check['export_count_matches_archive'] and count_check['total_bbe_counts_match']:status='RESEARCH_ELIGIBLE_RECONCILED_COUNT_SEPARATE_FROM_RATE'
   elif family=='bat_tracking':status='RESEARCH_ONLY_SHORT_PARTIAL_HISTORY'
   elif family=='baserunning':status='HELD_OPPORTUNITY_DEFINITION'
   elif family=='batted_ball' and any(s in m for s in ['pull','straight','oppo']):status='RESEARCH_ONLY_OFFICIAL_DIRECTION_SEPARATE_FROM_PROXY'
   elif m in ['avg_hit_speed','avg_hit_angle','anglesweetspotpercent']:status='HELD_MEASUREMENT_SCOPE_UNVERIFIED'
   elif r and r['status']=='MATCH_WITHIN_ROUNDING_TOLERANCE':status='RESEARCH_ELIGIBLE_RECONCILED_DEFINITION'
   else:status='RESEARCH_ONLY_UNRECONCILED_DEFINITION'
   rows.append(dict(source_season=k[0],player_type=k[1],mlbam_id=k[2],name=h.get('name'),family=family,metric=m,feature=h['feature'],source_id=h['source_id'],existing_eligible=existing,existing_reason=h['reason'],audit_decision=status,denominator_status=d['status'] if d else None,model_fit_approved=False,accepted_source_modified=False))
 return rows

def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 cfg=Path(a.config).resolve();c=load(cfg)
 if c!=DEFAULT:raise ValueError('Fixed v1.22 audit controls changed')
 lb=Path(a.leaderboards).resolve();matrix=Path(a.matrix).resolve();expanded=Path(a.expanded).resolve();watched={str(cfg):sha(cfg)}
 print('Verifying frozen historical leaderboard tables and archive bindings...',flush=True)
 report=load(checked(lb,'leaderboard_build_report.json',watched))
 if report['version']!='1.21.0' or report['models_fitted'] or report['accepted_projection_source_modified']:raise ValueError('Require unchanged v1.21 intake')
 old_bind=load(checked(lb,'input_hashes.json',watched));recon=readcsv(checked(lb,'reconciliation_details.csv',watched));flags=readcsv(checked(lb,'normalization_review.csv',watched))
 hp=checked(lb,'historical/leaderboard_features.parquet',watched)
 selected,manifest=selected_windows(matrix,watched,c)
 er=load(checked(expanded,'expanded_feature_report.json',watched));ep=checked(expanded,'expanded_features_season.parquet',watched);eb=load(checked(expanded,'input_hashes.json',watched))
 if er['version']!='1.20.0' or er['models_fitted'] or er['accepted_matrix_modified'] or eb.get(str(manifest))!=sha(manifest) or old_bind.get(str(manifest))!=sha(manifest) or old_bind.get(str(ep))!=sha(ep):raise ValueError('Archive/input binding differs from intake')
 if any(int(r['source_season']) not in c['source_seasons'] for r in recon):raise ValueError('Future/nonhistorical reconciliation row')
 historical_flags=[r for r in flags if r['split']=='historical']
 if any(int(r['source_season']) not in c['source_seasons'] for r in historical_flags):raise ValueError('Future historical flag')
 history=defaultdict(dict)
 with duckdb.connect() as db:
  columns={r[0] for r in db.execute('DESCRIBE SELECT * FROM read_parquet('+lit(hp)+')').fetchall()};namecol='name' if 'name' in columns else 'NULL::VARCHAR AS name'
  cur=db.execute('SELECT source_season,player_type,mlbam_id,'+namecol+',family,metric,feature,source_id,raw_text,raw_value,normalized_value,denominator,eligible,reason FROM read_parquet('+lit(hp)+')');fields=[x[0] for x in cur.description]
  for values in cur.fetchall():
   r=dict(zip(fields,values));k=key(r)
   if k[0] not in c['source_seasons'] or k[1] not in ['hitter','pitcher'] or not k[2].isdigit() or int(k[2])<=0 or (r['family'],r['metric']) in history[k]:raise ValueError('Invalid/duplicate historical leaderboard key')
   history[k][r['family'],r['metric']]=r
 # Family names prevent accidentally merging a metric from two leaderboards.
 recon_seen=set()
 for r in recon:
  k=key(r);mk=(r['family'],r['metric']);h=history.get(k,{}).get(mk)
  if (k,mk) in recon_seen or h is None or h['source_id']!=r['source_id'] or (h['raw_text'] or '')!=r['export_original'] or not close(h['normalized_value'],num(r['export_normalized'])) or not close(h['denominator'],num(r['export_denominator'])):raise ValueError('Reconciliation differs from frozen historical export')
  recon_seen.add((k,mk))
 sources=check_export_snapshots(lb,history,watched,c)
 out,backups,stage=start(a.output,a.backup_root,[lb,matrix,expanded,cfg]+[Path(r['parquet_path']) for r in selected]+[Path(r['raw_path']) for r in selected]+[Path(r['schedule_path']) for r in selected])
 try:
  bank={};denoms=[];replay=[]
  # First pass reconstructs all exported participants. Second pass emits only targeted events.
  with duckdb.connect() as db:
   for year in c['source_seasons']:
    print(f'{year}: reconstructing BBE, numerator and measured-denominator totals...',flush=True);bank.update(prepare(db,selected,year,c))
   for r in recon:
    k=key(r);ar=bank.get(k)
    if r['metric'] in REPLAY:
     vfield,dfield=REPLAY[r['metric']];v=ar[vfield] if ar else None;den=ar[dfield] if ar else None
     ok=close(v,num(r['archive_value'])) and close(den,num(r['archive_observations'])) and close(ar['bbe'] if ar else None,num(r['archive_bbe']))
     replay.append(dict(**{n:r[n] for n in ['source_season','player_type','mlbam_id','metric']},original_archive_value=num(r['archive_value']),reconstructed_value=v,reconstructed_denominator=den,replay_matches=ok))
     if not ok:raise ValueError('Physical reconstruction does not reproduce frozen reconciliation: '+str((k,r['metric'])))
    if r['metric'] in COUNT_METRICS:
     metrics={m:h for (family,m),h in history[k].items() if family=='exit_velocity'}
     denoms.append(denominator_row(r,metrics,ar,c))
   normalization=[];flag_keys=set()
   for r in historical_flags:
    k=key(r);mk='exit_velocity',r['metric'];h=history.get(k,{}).get(mk)
    if h is None or r['code']!='COUNT_RATE_DIFFERENCE_BEYOND_ROUNDING' or r['metric'] not in COUNT_METRICS:raise ValueError('Unsupported historical normalization flag; retain and investigate explicitly')
    fk=(k,r['metric'])
    if fk in flag_keys:raise ValueError('Duplicate normalization flag')
    flag_keys.add(fk);d=next((x for x in denoms if key(x)==k and x['metric']==r['metric']),None)
    if d is None or not d['original_normalization_flag'] or d['source_id']!=r['source_id']:raise ValueError('Normalization flag not reproduced')
    normalization.append(dict(d,original_code=r['code'],original_detail=r['detail'],interpretation='ROUNDING_COMPATIBLE_DENOMINATORS_ARE_LEADS_NOT_PROOF_OF_MEMBERSHIP'))
   if flag_keys!={(key(d),d['metric']) for d in denoms if d['original_normalization_flag']}:raise ValueError('Missing/unregistered historical normalization flag')
   targets=choose_targets(recon,denoms,c);events=0;subgroups=[];games=[]
   for index,year in enumerate(c['source_seasons']):
    print(f'{year}: writing targeted physical-event and game bridges...',flush=True);prepare(db,selected,year,c)
    n,ss,gg=trace_events(db,year,targets,stage,index>0);events+=n;subgroups.extend(ss);games.extend(gg)
  # Decision rows cover every imported metric, not only the reconciliation subset.
  decision_rows=decisions(history,denoms,recon)
  metrics=defaultdict(Counter)
  for r in decision_rows:metrics[r['family'],r['player_type'],r['metric']][r['audit_decision']]+=1
  summary=[dict(family=f,player_type=role,metric=m,audit_decision=d,player_seasons=n,model_fit_approved=False) for (f,role,m),cc in sorted(metrics.items()) for d,n in sorted(cc.items())]
  # Deterministic within-metric cohorts; fractions remain fractions in machine-readable reports.
  cohorts=defaultdict(list)
  for r in recon:
   delta=num(r['value_difference']);bbe=num(r['export_denominator'])
   if delta is None or bbe is None:continue
   cohorts[r['metric'],r['player_type'],int(r['source_season']),'BELOW_30' if bbe<30 else '30_TO_99' if bbe<100 else 'AT_LEAST_100'].append(r)
  cohort_rows=[]
  for (m,role,y,cohort),rr in sorted(cohorts.items()):
   ds=sorted(abs(num(r['value_difference'])) for r in rr);n=len(ds)
   cohort_rows.append(dict(metric=m,player_type=role,source_season=y,exposure_cohort=cohort,rows=n,median_absolute_difference=(ds[(n-1)//2]+ds[n//2])/2,p90_absolute_difference=ds[int(.9*(n-1))],flagged_rows=sum(abs(num(r['value_difference']))>num(r['review_tolerance']) for r in rr)))
  comparisons=[dict(r,name=history[key(r)][r['family'],r['metric']].get('name'),trace_reasons='|'.join(sorted(targets[key(r)])),substantial_sample=num(r['export_denominator']) is not None and num(r['export_denominator'])>=c['substantial_bbe'],interpretation='SOURCE_SCOPE_UNVERIFIED_NO_EVENT_MEMBERSHIP_INFERRED') for r in recon if key(r) in targets and r['metric'] in c['trace_metrics']]
  tables={'denominator_count_audit':denoms,'hardhit_prior_residuals':[r for r in denoms if r['metric']=='ev95percent' and r['prior_accounting_residual']], 'historical_normalization_flag_audit':normalization,'archive_replay':replay,'target_player_seasons':[dict(source_season=y,player_type=role,mlbam_id=pid,reasons='|'.join(sorted(why))) for (y,role,pid),why in sorted(targets.items())], 'target_scope_comparisons':comparisons,'target_subgroup_summary':subgroups,'target_game_bridge':games,'feature_eligibility_decisions':decision_rows,'metric_eligibility_summary':summary,'exposure_scope_summary':cohort_rows,'physical_value_exceptions':[dict(source_season=y,player_type=role,mlbam_id=pid,invalid_ev=r['invalid_ev'],invalid_la=r['invalid_la'],invalid_class=r['invalid_class']) for (y,role,pid),r in sorted(bank.items()) if r['invalid_ev'] or r['invalid_la'] or r['invalid_class']]}
  tables.update(verified_export_snapshots=sources,verified_source_windows=selected)
  for name,rows in tables.items():emit(stage/(name+'.csv'),rows)
  dump(stage/'audit_contract.json',dict(settings=c,denominator_policy='Total BBE, finite EV observations and valid classification observations are separate; never zero-impute unmeasured events',candidate_denominators='All integers compatible with fixed displayed-rate tolerance; not evidence of which events were included',trace_policy='Top 5 discrepancies per metric/role/year with >=100 exported BBE plus all unresolved count/rate and normalization cases; overlapping subgroups are diagnostics only',definitions='Classic finite EV and launch_speed_angle range reproduce frozen original. Expanded LA and geometry reproduce v1.20. No official event membership is inferred.',eligibility='Decision overlay only; original v1.20/v1.21 tables and accepted forecasts remain unchanged. Research eligibility is not model selection or complete feature comparability approval.'))
  report=dict(version=VERSION,status='TARGETED_SCOPE_AUDIT_BUILT_REVIEW_REQUIRED',source_seasons=c['source_seasons'],frozen_windows_checked=len(selected),denominator_rows=len(denoms),denominator_classifications=dict(Counter(r['status'] for r in denoms)),hardhit_prior_accounting_residuals=sum(r['metric']=='ev95percent' and r['prior_accounting_residual'] for r in denoms),historical_normalization_flags=len(normalization),archive_replay_verified=True,target_player_seasons=len(targets),target_event_rows=events,feature_decision_rows=len(decision_rows),models_fitted=False,forecasts_modified=False,original_references_modified=False,counts_replaced=False,training_labels_read=False,source_2026_pitches_read=False,evaluation_outcomes_read=False,inputs_unchanged=True,model_ready=False,limitations=['Accounting agreement is not proof of identical official event membership or historical scoring revisions.','Top substantial-sample targets are predefined; full count and normalization audits include small samples.','Low-EV and bunt-description subgroups are diagnostic only; no inferred leaderboard exclusion rule.','Combined historical normalization report contains quarantined-row metadata; no 2026 feature tables, source snapshots, outcomes or pitch files are opened.','Historical supplemental coverage is 2023-2025; bat tracking 2023 is partial. No independent vintage certification.','Research decisions are an overlay; no new model, projection source or corrected rate export is published.'])
  report['build_implementation_version']=IMPLEMENTATION_VERSION
  dump(stage/'scope_audit_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(leaderboards='outputs/statcast_leaderboards_v1_21',matrix='outputs/standalone_lagged_features_v1_0',expanded='outputs/expanded_statcast_v1_20',config='config/statcast_scope_v1_22.json',output='outputs/statcast_scope_audit_v1_22',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
