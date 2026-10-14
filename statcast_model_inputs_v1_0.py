"""Read-only PA attribution audit and chronology-safe projection model inputs.
No projection values are adjusted and no valuation model is fitted.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,shutil,sqlite3,tempfile
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path
import duckdb

PA_EVENTS={'single','double','triple','home_run','walk','intent_walk','hit_by_pitch','strikeout','strikeout_double_play','field_out','force_out','grounded_into_double_play','fielders_choice','fielders_choice_out','field_error','double_play','triple_play','sac_fly','sac_bunt','sac_fly_double_play','sac_bunt_double_play','catcher_interf'}
KS={'strikeout','strikeout_double_play'};BBS={'walk','intent_walk'}
ADVANTAGE={(2,0),(2,1),(3,0),(3,1),(3,2)}
DEFAULTS={
 'whiff_pct':('swings',100,400), 'chase_pct':('out_zone_pitches',100,400),
 'swstr_pct':('thrown_pitches',200,500),'csw_pct':('thrown_pitches',200,500),
 'zone_pct':('zone_known_pitches',200,500),
 'ev':('ev_observations',30,100),'hardhit_pct':('ev_observations',30,100),
 'barrel_pct':('barrel_observations',30,100),'xwobacon':('expected_contact_observations',30,100),
 'velocity':('velocity_observations',100,300),
 'k_pct_scored':('scored_exposure',50,300),'bb_pct_scored':('scored_exposure',50,300)}

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def lit(x):return "'"+str(x).replace("'","''")+"'"
def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')
def csv_out(path,rows,fields):
 with Path(path).open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def jsonl(path,rows):
 with Path(path).open('w',encoding='utf-8') as f:
  for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def attribute_pa(rows):
 """Rows ordered by pitch_number; counts are PRE-pitch, not post-pitch.
 Returns cautious candidate scored owners, preserving physical pitch ownership.
 Multi-change walks are chained: an outgoing pitcher's current credited owner
 persists only when each incoming count satisfies 9.16(h).
 """
 rows=sorted(rows,key=lambda r:r['pitch_number'])
 terminal=[r for r in rows if r.get('events') in PA_EVENTS]
 if len(terminal)!=1:raise ValueError('Expected exactly one terminal PA event')
 last=terminal[0]
 if last is not rows[-1]:raise ValueError('Pitch rows after terminal PA event')
 batter_owner=rows[0]['batter'];pitcher_owner=rows[0]['pitcher'];transitions=[];unresolved=[]
 for prev,cur in zip(rows,rows[1:]):
  for entity,col in [('hitter','batter'),('pitcher','pitcher')]:
   if prev[col]==cur[col]:continue
   balls=cur.get('balls');strikes=cur.get('strikes');rule='terminal_owner'
   known=balls in range(4) and strikes in range(3)
   if not known:unresolved.append(entity)
   if entity=='hitter':
    if last['events'] in KS and known and strikes==2:rule='9.15(b): inherited two-strike strikeout'
    else:batter_owner=cur[col]
   else:
    if last['events'] in BBS and known and (balls,strikes) in ADVANTAGE:rule='9.16(h): inherited advantageous-count walk'
    else:pitcher_owner=cur[col]
   transitions.append(dict(player_type=entity,from_mlbam_id=prev[col],to_mlbam_id=cur[col],incoming_balls=balls,incoming_strikes=strikes,rule=rule))
 if not transitions:return dict(batter=last['batter'],pitcher=last['pitcher'],transitions=[],unresolved=[])
 return dict(batter=batter_owner,pitcher=pitcher_owner,transitions=transitions,unresolved=sorted(set(unresolved)))

def load_reference(path,years):
 players={};actuals={};projections=[];identities={}
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as con:
  con.row_factory=sqlite3.Row
  for r in con.execute('SELECT player_id,preferred_name FROM players'):players[r['player_id']]=r['preferred_name']
  for r in con.execute("SELECT external_id,player_id FROM player_id_crosswalk WHERE lower(namespace)='mlbam'"):
   mid=int(r['external_id'])
   if mid in identities and identities[mid]!=r['player_id']:raise ValueError('Conflicting MLBAM crosswalk')
   identities[mid]=r['player_id']
  for typ in ['hitter','pitcher']:
   # Actuals loaded only BEFORE the final target. Target holdout is never queried.
   for r in con.execute('SELECT a.* FROM '+typ+'_actuals a JOIN record_selection rs USING(record_id) WHERE rs.selected=1 AND a.season<?',[max(years)]):
    key=(typ,r['season'],r['player_id'])
    if key in actuals:raise ValueError('Duplicate selected actual player-season')
    actuals[key]=dict(name=r['name'],record_id=r['record_id'],metrics=json.loads(r['metrics_json']))
   seen=set()
   for year in years:
    for r in con.execute('SELECT * FROM analytical_'+typ+'_projections WHERE season=? ORDER BY source,player_id',[year]):
     key=(typ,year,r['source'],r['player_id'])
     if key in seen:raise ValueError('Duplicate analytical projection key')
     seen.add(key)
     projections.append(dict(player_type=typ,season=year,source=r['source'],player_id=r['player_id'],name=players.get(r['player_id'],r['name']),team=r['team'],record_id=r['record_id'],metrics=json.loads(r['metrics_json']),excluded_metrics=json.loads(r['excluded_metrics_json'] or '[]')))
 return players,actuals,projections,identities

def load_features(path,target):
 result={};teams=[]
 with duckdb.connect(str(path),read_only=True) as db:
  mapping={}
  for season,typ,mid,pid in db.execute('SELECT season,player_type,mlbam_id,canonical_player_id FROM player_identity_coverage').fetchall():
   key=(typ,int(season),int(mid))
   if key in mapping:raise ValueError('Duplicate feature mapping')
   mapping[key]=pid
  for typ in ['hitter','pitcher']:
   cur=db.execute('SELECT * FROM '+typ+'_statcast_season WHERE season<?',[target]);fields=[d[0] for d in cur.description]
   for vals in cur.fetchall():
    row=dict(zip(fields,vals));pid=mapping.get((typ,row['season'],row['mlbam_id']))
    if not pid:raise ValueError('Unmapped feature identity')
    key=(typ,row['season'],pid)
    if key in result:raise ValueError('Multiple feature measurement eras or IDs per canonical player-season')
    result[key]=row
  cur=db.execute('SELECT * FROM team_context_enriched WHERE season<?',[target]);fields=[d[0] for d in cur.description]
  teams=[dict(zip(fields,vals)) for vals in cur.fetchall()]
 return result,teams

def trace_pitches(config_path,start,end,identities,folder,source_windows=None):
 # Existing journal verifies raw/Parquet/schedule hashes and resumption dependencies.
 from statcast_pipeline_v1_0 import config,active
 selected=active(config(config_path),start,end)
 if source_windows:
  original=json.loads(Path(source_windows).read_text(encoding='utf-8'))
  expected={r['day']:(r['run_id'],r['raw_hash'],r['parquet_hash'],r['schedule_hash']) for r in original}
  current={r['day']:(r['run_id'],r['raw_hash'],r['parquet_hash'],r['schedule_hash']) for r in selected}
  if current!=expected:raise ValueError('Ingestion versions changed since feature build; rebuild features first')
 paths=[r['parquet_path'] for r in selected if r['parquet_path'] and r['rows']]
 counts=collections.defaultdict(lambda:[0,0,0]);issues=collections.defaultdict(set);changes=[];unsupported=[]
 with duckdb.connect() as db:
  db.execute('CREATE VIEW pitches AS SELECT * FROM read_parquet(['+','.join(lit(p) for p in paths)+'],union_by_name=true,hive_partitioning=false)')
  if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM pitches GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Duplicate raw pitch keys')
  events='('+','.join(lit(x) for x in sorted(PA_EVENTS))+')'
  db.execute('CREATE TEMP TABLE terminals AS SELECT * FROM pitches WHERE events IN '+events)
  if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number FROM terminals GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Multiple terminal events')
  for typ,col in [('hitter','batter'),('pitcher','pitcher')]:
   for year,mid,n,k,bb in db.execute('SELECT season,'+col+",count(*),count(*) FILTER(WHERE events IN ('strikeout','strikeout_double_play')),count(*) FILTER(WHERE events IN ('walk','intent_walk')) FROM terminals GROUP BY 1,2").fetchall():counts[(typ,year,mid)]=[n,k,bb]
  db.execute('''CREATE TEMP TABLE changed AS SELECT game_pk,at_bat_number FROM pitches GROUP BY 1,2 HAVING count(DISTINCT batter)>1 OR count(DISTINCT pitcher)>1''')
  cur=db.execute('''SELECT p.season,p.game_pk,p.at_bat_number,p.pitch_number,p.game_date,p.batter,p.pitcher,p.balls,p.strikes,p.events FROM pitches p JOIN changed USING(game_pk,at_bat_number) ORDER BY p.game_pk,p.at_bat_number,p.pitch_number''')
  fields=[d[0] for d in cur.description];groups=collections.defaultdict(list)
  for vals in cur.fetchall():
   row=dict(zip(fields,vals));groups[(row['game_pk'],row['at_bat_number'])].append(row)
  for key,rows in groups.items():
   if not any(r['events'] in PA_EVENTS for r in rows):
    unsupported.append(dict(game_pk=key[0],at_bat_number=key[1],reason='No completed PA; no counts moved',sequence=rows));continue
   attributed=attribute_pa(rows);terminal=next(r for r in rows if r['events'] in PA_EVENTS);event=terminal['events'];year=terminal['season']
   for typ,col in [('hitter','batter'),('pitcher','pitcher')]:
    participants={r[col] for r in rows}
    if typ in attributed['unresolved']:
     for mid in participants:issues[(typ,year,mid)].add('Missing or invalid count at substitution')
     continue
    old=terminal[col];new=attributed[col]
    if old!=new:
     delta=[1,int(event in KS),int(event in BBS)]
     for i,v in enumerate(delta):counts[(typ,year,old)][i]-=v;counts[(typ,year,new)][i]+=v
   changes.append(dict(game_pk=key[0],at_bat_number=key[1],season=year,event=event,terminal_batter=terminal['batter'],terminal_pitcher=terminal['pitcher'],attributed_batter=attributed['batter'],attributed_pitcher=attributed['pitcher'],**{k:v for k,v in attributed.items() if k in ('transitions','unresolved')},sequence=rows))
  print('Audited '+str(len(groups))+' player-change PAs',flush=True)
 out=[]
 for (typ,year,mid),vals in sorted(counts.items()):
  if min(vals)<0:raise ValueError('Negative attributed counts')
  out.append(dict(player_type=typ,season=year,mlbam_id=mid,player_id=identities.get(mid),exposure=vals[0],SO=vals[1],BB=vals[2],status='UNRESOLVED' if issues[(typ,year,mid)] else 'RULE_ATTRIBUTED',issues=sorted(issues[(typ,year,mid)])))
 jsonl(folder/'pa_player_changes.jsonl',changes);jsonl(folder/'nonterminal_player_changes.jsonl',unsupported)
 csv_out(folder/'attributed_player_season.csv',out,['player_type','season','mlbam_id','player_id','exposure','SO','BB','status','issues'])
 return {(r['player_type'],r['season'],r['player_id']):r for r in out},dict(status='COMPLETE',changed_completed_pas=len(changes),changed_nonterminal_pas=len(unsupported),unresolved_player_seasons=sum(r['status']=='UNRESOLVED' for r in out),pitch_rows=sum(r['rows'] for r in selected),windows=len(selected))

def scored_history(features,actuals,attributed):
 history={};reconcile=[]
 for key,f in features.items():
  typ,year,pid=key;a=actuals.get(key);m=a['metrics'] if a else {};corrected=attributed.get(key)
  observed=dict(exposure=f['pa_observed'],SO=round(f['pa_observed']*f['k_pct_observed']) if finite(f['k_pct_observed']) else None,BB=round(f['pa_observed']*f['bb_pct_observed']) if finite(f['bb_pct_observed']) else None)
  official=dict(exposure=m.get('PA' if typ=='hitter' else 'TBF'),SO=m.get('SO'),BB=m.get('BB'))
  complete_official=all(finite(v) and v>=0 for v in official.values())
  corrected_ok=corrected and corrected['status']=='RULE_ATTRIBUTED'
  baseline_match=complete_official and all(observed[k]==official[k] for k in official)
  corrected_match=complete_official and corrected_ok and all(corrected[k]==official[k] for k in official)
  status='EXACT_TERMINAL_MATCH' if baseline_match else 'EXPLAINED_BY_SUBSTITUTION_RULES' if corrected_match else 'UNRESOLVED_DIFFERENCE' if complete_official else 'NO_OFFICIAL_REFERENCE'
  if complete_official:chosen=official;provenance='WAREHOUSE_OFFICIAL_COUNTS'
  elif corrected_ok:chosen={k:corrected[k] for k in official};provenance='RULE_ATTRIBUTED_COUNTS_UNVERIFIED_OFFICIAL'
  else:chosen=dict(exposure=None,SO=None,BB=None);provenance='NO_VERIFIED_SCORED_COUNTS'
  row=dict(f);row['scored_exposure']=chosen['exposure'];den=chosen['exposure']
  row['k_pct_scored']=chosen['SO']/den if finite(den) and den>0 else None
  row['bb_pct_scored']=chosen['BB']/den if finite(den) and den>0 else None
  row['scored_provenance']=provenance;history[key]=row
  reconcile.append(dict(player_type=typ,season=year,player_id=pid,mlbam_id=f['mlbam_id'],name=a['name'] if a else '',status=status,observed_exposure=observed['exposure'],official_exposure=official['exposure'],attributed_exposure=corrected['exposure'] if corrected else None,observed_SO=observed['SO'],official_SO=official['SO'],attributed_SO=corrected['SO'] if corrected else None,observed_BB=observed['BB'],official_BB=official['BB'],attributed_BB=corrected['BB'] if corrected else None,scored_rate_provenance=provenance))
 return history,reconcile

def select_feature(history,typ,pid,year,metric,settings,lookback):
 denom,min_n,prior=settings
 candidates=[(y,history[(typ,y,pid)]) for y in range(year-1,year-lookback-1,-1) if (typ,y,pid) in history]
 for y,row in candidates:
  v=row.get(metric);n=row.get(denom)
  if finite(v) and finite(n) and n>=min_n and row.get('measurement_era')=='PRE_ABS_FRONT_PLATE':
   return dict(metric=metric,value=v,feature_season=y,sample_size=n,minimum_sample=min_n,reliability=n/(n+prior),status='ELIGIBLE' if y==year-1 else 'OLDER_ELIGIBLE_HISTORY',provenance=row.get('scored_provenance') if metric.endswith('_scored') else 'STATCAST_PHYSICAL_OBSERVATIONS')
 reason='NO_MLB_HISTORY' if not candidates else 'INSUFFICIENT_SAMPLE_OR_MISSING_VALUE'
 return dict(metric=metric,value=None,feature_season=None,sample_size=None,minimum_sample=min_n,reliability=0,status=reason,provenance=None)

# Explicit source-code aliases, not player-name matching. Oakland/ATH share team ID 133.
TEAM_ALIASES={'ARI':'AZ','CHW':'CWS','KCR':'KC','SDP':'SD','SFG':'SF','TBR':'TB','WSN':'WSH','OAK':'ATH'}
def assemble_team_context(projections,teams,lookback):
 lookup={}
 for row in teams:
  key=(row['season'],TEAM_ALIASES.get(row['team'],row['team']))
  if key in lookup:raise ValueError('Ambiguous historical team code')
  lookup[key]=row
 metrics=['runs_per_game','runs_allowed_per_game','pythag_wpct','official_sb_attempts_per_pa','official_sb_success_pct','official_saves','official_holds']
 result=[]
 for p in projections:
  code=TEAM_ALIASES.get(p['team'],p['team']);candidate=None;season=None
  for y in range(p['season']-1,p['season']-lookback-1,-1):
   if (y,code) in lookup:candidate=lookup[(y,code)];season=y;break
  row=dict(player_type=p['player_type'],projection_season=p['season'],player_id=p['player_id'],source=p['source'],projection_team=p['team'],context_team=code if candidate else None,context_season=season,status='PRIOR_TEAM_CONTEXT' if candidate else 'NO_UNAMBIGUOUS_TEAM_CONTEXT')
  row.update({k:candidate.get(k) if candidate else None for k in metrics});result.append(row)
 return result

def build(args):
 cfg=json.loads(Path(args.config).read_text(encoding='utf-8'));target=cfg['target_season'];years=cfg['training_seasons']+[target]
 if not isinstance(target,int) or isinstance(target,bool) or not cfg['training_seasons'] or not isinstance(cfg['history_lookback_seasons'],int) or cfg['history_lookback_seasons']<1 or not cfg['feature_rules']:raise ValueError('Invalid target/training/history/sample configuration')
 if any(not isinstance(y,int) or isinstance(y,bool) or y>=target for y in cfg['training_seasons']) or len(set(years))!=len(years):raise ValueError('Training seasons must be unique and before target')
 audit=json.loads(Path(args.feature_audit).read_text(encoding='utf-8'))
 if not audit.get('complete_requested_windows') or audit['event_end']>=f'{target}-01-01' or audit.get('target_season')!=target:raise ValueError('Feature audit violates target cutoff/completeness')
 warehouse=Path(args.sqlite).resolve();featuredb=Path(args.features).resolve();out=Path(args.output).resolve()
 if out.exists():raise ValueError('Output must not already exist')
 if any(out==p or out in p.parents for p in [warehouse,featuredb,Path(args.feature_audit).resolve()]):raise ValueError('Output must not contain inputs')
 fingerprints={str(p):sha(p) for p in [warehouse,featuredb,Path(args.feature_audit).resolve(),Path(args.config).resolve()]}
 # Feature build used migrated DuckDB, so its byte hash cannot equal reference SQLite.
 # Verify canonical MLBAM identities directly instead of comparing backend file hashes.
 print('Loading read-only warehouse and physical feature tables...',flush=True)
 names,actuals,projections,identities=load_reference(warehouse,years);features,teams=load_features(featuredb,target)
 for (typ,year,pid),row in features.items():
  if identities.get(row['mlbam_id'])!=pid:raise ValueError('Feature/SQLite MLBAM identity disagreement')
 if sum(row['pitch_rows'] for (typ,year,pid),row in features.items() if typ=='hitter')!=audit['pitch_rows']:raise ValueError('Feature rows differ from feature audit')
 if not projections:raise ValueError('No analytical projections')
 out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=out.name+'.staging-',dir=out.parent))
 try:
  attributed={};trace=dict(status='NOT_RUN',reason='--skip-pitch-trace; no substitutions confirmed')
  if not args.skip_pitch_trace:
   print('Tracing player changes from registered pitch Parquet...',flush=True)
   windows=Path(args.feature_audit).parent/'source_windows.json'
   if not windows.is_file():raise FileNotFoundError('Full trace requires source_windows.json beside feature_audit.json')
   attributed,trace=trace_pitches(args.ingestion_config,audit['event_start'],audit['event_end'],identities,stage,windows)
   if trace['pitch_rows']!=audit['pitch_rows'] or trace['windows']!=audit['selected_windows']:raise ValueError('Pitch trace differs from original feature build input window totals')
  history,reconciliation=scored_history(features,actuals,attributed)
  settings={k:tuple(v) for k,v in cfg['feature_rules'].items()}
  for k,(den,n,prior) in settings.items():
   if k not in DEFAULTS or den!=DEFAULTS[k][0] or not finite(n) or n<=0 or not finite(prior) or prior<=0:raise ValueError('Invalid feature sample control: '+k)
  grouped=collections.defaultdict(list)
  for p in projections:grouped[(p['player_type'],p['season'],p['player_id'])].append(p)
  feature_rows=[];players=[];labels=[];fallbacks=collections.Counter()
  for (typ,year,pid),records in sorted(grouped.items()):
   eligible=[]
   for metric,rule in settings.items():
    if typ=='hitter' and metric=='velocity':continue
    f=select_feature(history,typ,pid,year,metric,rule,cfg['history_lookback_seasons']);f.update(player_type=typ,projection_season=year,player_id=pid)
    feature_rows.append(f)
    if f['value'] is not None:eligible.append(metric)
   fallback='FEATURES_AVAILABLE' if eligible else 'PROJECTION_ONLY';fallbacks[(typ,year,fallback)]+=1
   players.append(dict(player_type=typ,season=year,player_id=pid,name=records[0]['name'],role='HOLDOUT_PREDICTION' if year==target else 'TRAINING',sources=sorted(r['source'] for r in records),source_record_ids={r['source']:r['record_id'] for r in records},eligible_features=eligible,fallback=fallback,projection_values_adjusted=False))
   if year<target and (typ,year,pid) in actuals:
    a=actuals[(typ,year,pid)];labels.append(dict(player_type=typ,season=year,player_id=pid,actual_record_id=a['record_id'],metrics=a['metrics']))
  team_rows=assemble_team_context(projections,teams,cfg['history_lookback_seasons'])
  csv_out(stage/'model_team_context.csv',team_rows,list(team_rows[0]))
  jsonl(stage/'projection_baselines.jsonl',projections);jsonl(stage/'model_players.jsonl',players);jsonl(stage/'training_labels.jsonl',labels)
  csv_out(stage/'model_features.csv',feature_rows,list(feature_rows[0]))
  csv_out(stage/'player_count_reconciliation.csv',reconciliation,list(reconciliation[0]))
  # Historical team rows retained separately. No arbitrary team assignment or target-year context.
  csv_out(stage/'historical_team_context.csv',teams,list(teams[0]))
  for p,h in fingerprints.items():
   if sha(p)!=h:raise ValueError('Input changed during build: '+p)
  summary=dict(version='1.0.0',built_at=datetime.now(timezone.utc).isoformat(),target_season=target,training_seasons=cfg['training_seasons'],feature_event_end=audit['event_end'],inputs_unchanged=True,input_sha256=fingerprints,trace=trace,projection_rows=len(projections),model_player_rows=len(players),training_label_rows=len(labels),holdout_labels_loaded=False,reconciliation_counts=[dict(player_type=t,season=y,status=status,rows=n) for (t,y,status),n in sorted(collections.Counter((r['player_type'],r['season'],r['status']) for r in reconciliation).items())],fallback_counts=[dict(player_type=t,season=y,status=status,rows=n) for (t,y,status),n in sorted(fallbacks.items())],sample_rules=cfg['feature_rules'],limitations=['Reliability scores and sample cutoffs are configurable initial controls, not fitted weights.','No consensus or projection adjustments are made. Source analytical metrics and exclusions are preserved exactly.','Historical K/BB rates prefer warehouse official counts; physical swing/contact ownership is unchanged.','Target outcome labels are excluded. Training labels are stored separately.','Raw pitch views in the uploaded feature database require original PC paths; the trace uses verified ingestion journal paths.','Team rows are historical only. Future joins must filter season strictly below each projection season.','2026 measurement-era features are outside this build.'],next_step='Review unresolved attribution rows before fitting an adjustment model')
  backup_root=Path(args.backup_root).resolve();backup_root.mkdir(parents=True,exist_ok=True)
  if backup_root==out or out in backup_root.parents:raise ValueError('Backup must be outside output folder')
  backup=backup_root/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
  summary['backup']=str(backup)
  summary['feature_catalog_reference_hash']=audit['projection_catalog_sha256']
  summary['reference_identity_check']='All physical feature MLBAM IDs agree with SQLite canonical identities'
  summary['team_context_rows']=len(team_rows)
  dump(stage/'model_input_audit.json',summary)
  print('Backing up complete model input folder...',flush=True)
  shutil.copytree(stage,backup)
  for path in stage.rglob('*'):
   if path.is_file() and sha(path)!=sha(backup/path.relative_to(stage)):raise ValueError('Backup verification failed')
  stage.rename(out);return summary
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--config',default='config/statcast_model_inputs_v1_0.json')
 p.add_argument('--sqlite',default='data/warehouse_resolved/historical_projection_warehouse.sqlite')
 p.add_argument('--features',default='outputs/statcast_features_for_2026_v1_0/statcast_features.duckdb')
 p.add_argument('--feature-audit',default='outputs/statcast_features_for_2026_v1_0/feature_audit.json')
 p.add_argument('--ingestion-config',default='config/statcast_ingestion_v1_0.json')
 p.add_argument('--output',default='outputs/statcast_model_inputs_2026_v1_0')
 p.add_argument('--backup-root',default='backups')
 p.add_argument('--skip-pitch-trace',action='store_true',help='Feature-table-only audit: substitutions stay unconfirmed.')
 a=p.parse_args();r=build(a);print(json.dumps(r,indent=2))
if __name__=='__main__':main()
