"""Build audited player/arsenal/team features from registered complete daily windows."""
from pathlib import Path
from datetime import datetime,timezone
from contextlib import closing
import argparse,csv,json,shutil,tempfile,time
import duckdb
from statcast_pipeline_v1_0 import config,active,lit,ident,sha,finished_games

PA_EVENTS=['single','double','triple','home_run','walk','intent_walk','hit_by_pitch','strikeout','strikeout_double_play','field_out','force_out','grounded_into_double_play','fielders_choice','fielders_choice_out','field_error','double_play','triple_play','sac_fly','sac_bunt','sac_fly_double_play','sac_bunt_double_play','catcher_interf']
SWINGS=['swinging_strike','swinging_strike_blocked','foul','foul_tip','foul_bunt','missed_bunt','hit_into_play','hit_into_play_no_out','hit_into_play_score','swinging_pitchout','foul_pitchout','bunt_foul_tip']
MISSES=['swinging_strike','swinging_strike_blocked','missed_bunt','swinging_pitchout']

def csv_write(p,rows,fields):
 with p.open('w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def in_list(values):return '('+','.join(lit(x) for x in values)+')'

def build(c,output,start=None,end=None,projection_warehouse=None,target_season=None):
 if target_season:
  cutoff=f'{target_season-1}-12-31'
  if end and end>cutoff:raise ValueError('Feature end exceeds pre-target-season cutoff')
  end=end or cutoff
 t=time.perf_counter();selected=active(c,start,end);output=Path(output).resolve()
 if output.exists():raise ValueError('Feature output must not exist')
 if output==c['_root'] or output in c['_root'].parents:raise ValueError('Output cannot contain ingestion root')
 paths=[r['parquet_path'] for r in selected if r['parquet_path'] and r['rows']]
 if not paths:raise ValueError('No pitch rows in selected windows')
 output.parent.mkdir(parents=True,exist_ok=True)
 stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent));db=None;published=False
 try:
  db=duckdb.connect(str(stage/'statcast_features.duckdb'))
  query='SELECT * FROM read_parquet(['+','.join(lit(p) for p in paths)+'],union_by_name=true,hive_partitioning=false)'
  db.execute('CREATE VIEW statcast_pitch AS '+query)
  count=db.execute('SELECT count(*) FROM statcast_pitch').fetchone()[0]
  if count!=sum(r['rows'] for r in selected):raise ValueError('Catalog/source row reconciliation failed')
  if db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number,pitch_number FROM statcast_pitch GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Duplicate keys across registered daily windows')
  db.execute('''CREATE VIEW pitch_features AS SELECT *,
   CASE WHEN inning_topbot='Top' THEN away_team WHEN inning_topbot='Bot' THEN home_team END AS batting_team,
   CASE WHEN inning_topbot='Top' THEN home_team WHEN inning_topbot='Bot' THEN away_team END AS fielding_team,
   description IN '''+in_list(SWINGS)+''' AS swing,
   description IN '''+in_list(MISSES)+''' AS miss,
   description='called_strike' AS called_strike,
   description NOT IN ('automatic_ball','automatic_strike') AND type IN ('B','S','X') AS thrown_pitch,
   zone BETWEEN 1 AND 9 AS in_zone,
   zone BETWEEN 11 AND 14 AS out_zone,
   type='X' AS bbe,
   events IN '''+in_list(PA_EVENTS)+''' AS terminal_pa,
   events IN ('strikeout','strikeout_double_play') AS strikeout,
   events IN ('walk','intent_walk') AS walk
   FROM statcast_pitch''')
  games={}
  for window in selected:
   schedule=json.loads(Path(window['schedule_path']).read_text(encoding='utf-8'))
   for g in finished_games(schedule):
    h=g['teams']['home'];a=g['teams']['away']
    row={'game_pk':g['gamePk'],'season':int(window['day'][:4]),'home_team_id':h['team']['id'],'away_team_id':a['team']['id'],'home_runs':h.get('score'),'away_runs':a.get('score')}
    if g['gamePk'] in games and games[g['gamePk']]!=row:raise ValueError('Conflicting schedule game metadata')
    games[g['gamePk']]=row
  csv_write(stage/'games.csv',list(games.values()),['game_pk','season','home_team_id','away_team_id','home_runs','away_runs'])
  db.execute('CREATE TABLE mlb_game AS SELECT * FROM read_csv('+lit((stage/'games.csv').as_posix())+',header=true,columns={game_pk:BIGINT,season:INTEGER,home_team_id:BIGINT,away_team_id:BIGINT,home_runs:INTEGER,away_runs:INTEGER})')
  (stage/'games.csv').unlink()
  db.execute('CREATE VIEW pa AS SELECT * FROM pitch_features WHERE terminal_pa')
  dup_pa=db.execute('SELECT count(*) FROM (SELECT game_pk,at_bat_number FROM pa GROUP BY ALL HAVING count(*)>1)').fetchone()[0]
  if dup_pa:raise ValueError('Multiple terminal PA events in one plate appearance')
  exported=[]
  common='''count(*) AS pitch_rows,
   count(*) FILTER (WHERE thrown_pitch) AS thrown_pitches,
   count(*) FILTER (WHERE swing) AS swings,
   count(*) FILTER (WHERE miss) AS misses,
   count(*) FILTER (WHERE swing AND zone BETWEEN 1 AND 14) AS swings_known_zone,
   count(*) FILTER (WHERE swing AND out_zone) AS chase_swings,
   count(*) FILTER (WHERE out_zone) AS out_zone_pitches,
   count(*) FILTER (WHERE zone BETWEEN 1 AND 14) AS zone_known_pitches,
   count(*) FILTER (WHERE terminal_pa) AS pa_observed,
   count(*) FILTER (WHERE bbe) AS bbe,
   count(launch_speed) FILTER (WHERE bbe) AS ev_observations,
   count(launch_speed_angle) FILTER (WHERE bbe) AS barrel_observations,
   count(estimated_woba_using_speedangle) FILTER (WHERE bbe) AS expected_contact_observations,
   1.0*count(*) FILTER (WHERE miss)/nullif(count(*) FILTER (WHERE swing),0) AS whiff_pct,
   1.0*count(*) FILTER (WHERE miss AND thrown_pitch)/nullif(count(*) FILTER (WHERE thrown_pitch),0) AS swstr_pct,
   1.0*count(*) FILTER (WHERE (miss OR called_strike) AND thrown_pitch)/nullif(count(*) FILTER (WHERE thrown_pitch),0) AS csw_pct,
   1.0*count(*) FILTER (WHERE in_zone)/nullif(count(*) FILTER (WHERE zone BETWEEN 1 AND 14),0) AS zone_pct,
   1.0*count(*) FILTER (WHERE swing AND out_zone)/nullif(count(*) FILTER (WHERE out_zone),0) AS chase_pct,
   1.0*count(*) FILTER (WHERE strikeout)/nullif(count(*) FILTER (WHERE terminal_pa),0) AS k_pct_observed,
   1.0*count(*) FILTER (WHERE walk)/nullif(count(*) FILTER (WHERE terminal_pa),0) AS bb_pct_observed,
   avg(launch_speed) FILTER (WHERE bbe) AS ev,
   1.0*count(*) FILTER (WHERE bbe AND launch_speed>=95)/nullif(count(launch_speed) FILTER (WHERE bbe),0) AS hardhit_pct,
   1.0*count(*) FILTER (WHERE bbe AND launch_speed_angle=6)/nullif(count(launch_speed_angle) FILTER (WHERE bbe),0) AS barrel_pct,
   avg(estimated_woba_using_speedangle) FILTER (WHERE bbe) AS xwobacon,
   avg(estimated_ba_using_speedangle) FILTER (WHERE bbe) AS xba_contact,
   avg(release_speed) AS velocity,
   count(release_speed) AS velocity_observations,
   avg(release_spin_rate) AS spin_rpm,
   avg(release_extension) AS extension_ft,
   12*avg(pfx_x) AS hbreak_inches_catcher,
   12*avg(pfx_z) AS vbreak_inches_catcher,
   avg(release_pos_x) AS release_side_ft,
   avg(release_pos_z) AS release_height_ft'''
  def publish(name,query):
   print('Building '+name,flush=True);db.execute('CREATE TABLE '+ident(name)+' AS '+query)
   folder=stage/'parquet'/name;folder.mkdir(parents=True)
   db.execute('COPY '+ident(name)+' TO '+lit(folder.as_posix())+' (FORMAT PARQUET,COMPRESSION ZSTD,PARTITION_BY(season))')
   db.execute('COPY '+ident(name)+' TO '+lit((stage/(name+'.csv')).as_posix())+' (HEADER,FORMAT CSV)')
   exported.append({'table':name,'rows':db.execute('SELECT count(*) FROM '+ident(name)).fetchone()[0]})
  for entity,col in [('hitter','batter'),('pitcher','pitcher')]:
   entity_common=common if entity=='pitcher' else common.replace(' AS velocity,',' AS pitch_velocity_faced,').replace(' AS velocity_observations,',' AS pitch_velocity_faced_observations,').replace(' AS spin_rpm,',' AS opposing_spin_rpm,').replace(' AS extension_ft,',' AS opposing_extension_ft,').replace(' AS hbreak_inches_catcher,',' AS opposing_hbreak_inches_catcher,').replace(' AS vbreak_inches_catcher,',' AS opposing_vbreak_inches_catcher,').replace(' AS release_side_ft,',' AS opposing_release_side_ft,').replace(' AS release_height_ft',' AS opposing_release_height_ft')
   publish(entity+'_statcast_season','SELECT season,'+col+' AS mlbam_id,measurement_era,'+entity_common+' FROM pitch_features GROUP BY season,'+col+',measurement_era')
  publish('pitcher_arsenal_season','''SELECT season,pitcher AS mlbam_id,pitch_type,measurement_era,'''+common+''',
    1.0*count(*)/sum(count(*)) OVER (PARTITION BY season,pitcher) AS usage_pct,
    1.0*count(*) FILTER (WHERE strikes=2 AND strikeout)/nullif(count(*) FILTER (WHERE strikes=2),0) AS putaway_pct_observed,
    avg(delta_run_exp)*100 AS rv100_offense_observed
    FROM pitch_features WHERE pitch_type IS NOT NULL GROUP BY season,pitcher,pitch_type,measurement_era''')
  publish('pitcher_arsenal_changes','SELECT cur.*,cur.velocity-prev.velocity AS velocity_yoy,cur.usage_pct-prev.usage_pct AS usage_pct_yoy,cur.whiff_pct-prev.whiff_pct AS whiff_pct_yoy FROM pitcher_arsenal_season cur LEFT JOIN pitcher_arsenal_season prev ON cur.mlbam_id=prev.mlbam_id AND cur.pitch_type=prev.pitch_type AND cur.season=prev.season+1')
  publish('pitcher_platoon_season','SELECT season,pitcher AS mlbam_id,stand,'+common+' FROM pitch_features GROUP BY season,pitcher,stand')
  for entity in ('hitter','pitcher'):
   source=entity+'_statcast_season'
   metrics=['velocity','whiff_pct','chase_pct','barrel_pct','hardhit_pct','xwobacon'] if entity=='pitcher' else ['whiff_pct','chase_pct','barrel_pct','hardhit_pct','xwobacon']
   publish(entity+'_skill_changes','SELECT cur.*,'+','.join('cur.'+m+'-prev.'+m+' AS '+m+'_yoy' for m in metrics)+' FROM '+source+' cur LEFT JOIN '+source+' prev ON cur.mlbam_id=prev.mlbam_id AND cur.season=prev.season+1')
  # Team results come from schedule scores, not pitch-level earned-run guesses.
  db.execute('''CREATE TABLE team_game AS
    SELECT DISTINCT g.game_pk,g.season,p.home_team AS team,g.home_team_id AS mlb_team_id,g.home_runs AS runs_scored,g.away_runs AS runs_allowed
    FROM mlb_game g JOIN statcast_pitch p USING(game_pk)
    UNION ALL
    SELECT DISTINCT g.game_pk,g.season,p.away_team AS team,g.away_team_id AS mlb_team_id,g.away_runs AS runs_scored,g.home_runs AS runs_allowed
    FROM mlb_game g JOIN statcast_pitch p USING(game_pk)''')
  publish('team_context_season','''SELECT season,team,mlb_team_id,count(*) AS games,
   count(runs_scored) AS score_observations,
   sum(CASE WHEN runs_scored>runs_allowed THEN 1 WHEN runs_scored IS NULL OR runs_allowed IS NULL THEN NULL ELSE 0 END) AS wins,
   sum(runs_scored) AS runs_scored,sum(runs_allowed) AS runs_allowed,
   avg(runs_scored) AS runs_per_game,avg(runs_allowed) AS runs_allowed_per_game,
   pow(sum(runs_scored),1.83)/nullif(pow(sum(runs_scored),1.83)+pow(sum(runs_allowed),1.83),0) AS pythag_wpct,
   count(*) FILTER (WHERE abs(runs_scored-runs_allowed)<=3) AS games_final_margin_le3,
   CAST(NULL AS BIGINT) AS saves,CAST(NULL AS BIGINT) AS holds,CAST(NULL AS BIGINT) AS stolen_bases,CAST(NULL AS BIGINT) AS caught_stealing
   FROM team_game GROUP BY season,team,mlb_team_id''')
  db.execute('''CREATE TABLE pitcher_appearance AS SELECT season,game_pk,pitcher,fielding_team AS team,
    min(inning) AS entry_inning,count(*) AS pitch_rows,
    bool_or(inning=7) AS pitched_7th,bool_or(inning=8) AS pitched_8th,bool_or(inning=9) AS pitched_9th
    FROM pitch_features WHERE fielding_team IS NOT NULL GROUP BY season,game_pk,pitcher,fielding_team''')
  publish('team_pitcher_usage_season','''SELECT season,team,pitcher AS mlbam_id,count(*) AS appearances,
   count(*) FILTER (WHERE entry_inning>=2) AS later_entry_appearances_proxy,
   count(*) FILTER (WHERE entry_inning=1) AS first_inning_entry_appearances,
   avg(pitched_7th::INTEGER) AS seventh_inning_appearance_share,
   avg(pitched_8th::INTEGER) AS eighth_inning_appearance_share,
   avg(pitched_9th::INTEGER) AS ninth_inning_appearance_share,
   CAST(NULL AS DOUBLE) AS save_share,CAST(NULL AS DOUBLE) AS hold_share,
   CAST(NULL AS DOUBLE) AS gmLI FROM pitcher_appearance GROUP BY season,team,pitcher''')
  publish('team_running_opportunities_season','''WITH eligible AS (
   SELECT season,batting_team AS team,game_pk,at_bat_number,
    bool_or(on_1b IS NOT NULL AND on_2b IS NULL) AS runner_on_first_second_open,
    bool_or(on_1b IS NOT NULL AND on_2b IS NULL AND outs_when_up<2) AS runner_first_open_under2outs
   FROM pitch_features GROUP BY season,batting_team,game_pk,at_bat_number)
   SELECT season,team,count(*) AS observed_pa_sequences,
   count(*) FILTER (WHERE runner_on_first_second_open) AS eligible_pa_sequences_proxy,
   count(*) FILTER (WHERE runner_first_open_under2outs) AS eligible_pa_under2outs_proxy,
   CAST(NULL AS DOUBLE) AS sb_attempt_rate FROM eligible GROUP BY season,team''')
  publish('team_late_lead_states_season','''WITH states AS (
   SELECT season,fielding_team AS team,game_pk,
    bool_or(inning=9 AND CASE WHEN inning_topbot='Top' THEN home_score-away_score ELSE away_score-home_score END BETWEEN 1 AND 3) AS ninth_lead
   FROM pitch_features GROUP BY season,fielding_team,game_pk)
   SELECT season,team,count(*) AS observed_defensive_games,
    count(*) FILTER (WHERE ninth_lead) AS games_observed_ninth_lead_1to3_proxy
   FROM states GROUP BY season,team''')
  supplement_paths=[]
  for season_config in c['seasons']:
   year=season_config['season'];year_days=[r['day'] for r in selected if int(r['day'][:4])==year]
   # Whole-season team aggregates cannot enter a partial-season snapshot.
   if not year_days or min(year_days)>season_config['start'] or max(year_days)<season_config['end']:continue
   for group in ('hitting','pitching'):
    folder=c['_root']/'team_supplement'/f'season={year}'/group
    if (folder/'manifest.json').exists():
     manifest=json.loads((folder/'manifest.json').read_text())
     if sha(folder/'source.json')!=manifest['source_sha256'] or sha(folder/'team_stats.parquet')!=manifest['parquet_sha256']:raise ValueError('Supplement hash mismatch')
     supplement_paths.append(str(folder/'team_stats.parquet'))
  if supplement_paths:
   db.execute('CREATE TABLE team_stat_supplement AS SELECT * FROM read_parquet(['+','.join(lit(p) for p in supplement_paths)+'],union_by_name=true,hive_partitioning=false)')
   # Column lists vary if only one group was downloaded; build views without inventing fields.
   supplement_columns={r[0] for r in db.execute('DESCRIBE team_stat_supplement').fetchall()}
   fields=['ctx.*']
   for field,group in [('sb','hitting'),('cs','hitting'),('sb_attempts','hitting'),('sb_success_pct','hitting'),('sb_attempts_per_pa','hitting'),('saves','pitching'),('holds','pitching'),('blown_saves','pitching')]:
    fields.append((('hit.' if group=='hitting' else 'pit.')+ident(field) if field in supplement_columns else 'CAST(NULL AS DOUBLE)')+' AS official_'+field)
   publish('team_context_enriched','SELECT '+','.join(fields)+" FROM team_context_season ctx LEFT JOIN team_stat_supplement hit ON ctx.season=hit.season AND ctx.mlb_team_id=hit.mlb_team_id AND hit.stat_group='hitting' LEFT JOIN team_stat_supplement pit ON ctx.season=pit.season AND ctx.mlb_team_id=pit.mlb_team_id AND pit.stat_group='pitching'")
  identities=[];reference_hash=None
  if projection_warehouse:
   warehouse=Path(projection_warehouse).resolve();reference_hash=sha(warehouse)
   with duckdb.connect(str(warehouse),read_only=True) as reference:
    identities=reference.execute("SELECT try_cast(external_id AS BIGINT) AS mlbam_id,player_id FROM player_id_crosswalk WHERE lower(namespace)='mlbam'").fetchall()
   if sha(warehouse)!=reference_hash:raise ValueError('Projection reference changed')
  crosswalk={}
  for mid,pid in identities:
   if mid is None:continue
   if mid in crosswalk and crosswalk[mid]!=pid:raise ValueError('Conflicting MLBAM crosswalk')
   crosswalk[mid]=pid
  mappings=[]
  for entity in ('hitter','pitcher'):
   for season,mid in db.execute('SELECT season,mlbam_id FROM '+entity+'_statcast_season').fetchall():
    mappings.append({'season':season,'player_type':entity,'mlbam_id':mid,'canonical_player_id':crosswalk.get(mid),'match_status':'MAPPED' if mid in crosswalk else 'UNMAPPED'})
  csv_write(stage/'player_identity_coverage.csv',mappings,['season','player_type','mlbam_id','canonical_player_id','match_status'])
  # Persistent mapping table allows future joins without name matching.
  db.execute('CREATE TABLE player_identity_coverage AS SELECT * FROM read_csv('+lit((stage/'player_identity_coverage.csv').as_posix())+',header=true,all_varchar=true)')
  unknown=db.execute('SELECT events,count(*) FROM statcast_pitch WHERE events IS NOT NULL AND events NOT IN '+in_list(PA_EVENTS)+' GROUP BY events').fetchall()
  metadata={'target_season':target_season,'feature_cutoff':end,'version':'1.0.0','built_at':datetime.now(timezone.utc).isoformat(),'event_start':selected[0]['day'],'event_end':selected[-1]['day'],'latest_source_retrieved_at':max(r['available_at'] for r in selected),'selected_windows':len(selected),'pitch_rows':count,'complete_requested_windows':True,'tables':exported,'mapped_player_season_rows':sum(r['match_status']=='MAPPED' for r in mappings),'unmapped_player_season_rows':sum(r['match_status']=='UNMAPPED' for r in mappings),'projection_catalog_sha256':reference_hash,'non_pa_events':unknown,'included_team_supplement_paths':supplement_paths,'notes':['Coverage confirms registered daily windows and scheduled completed-game presence, not official full-season PA totals.','Team SB/SV/HLD and xERA require supplemental sources. No fabricated zeros.','Partial seasons and unmatched measurement eras must be controlled in modeling.']}
  (stage/'feature_audit.json').write_text(json.dumps(metadata,indent=2))
  (stage/'source_windows.json').write_text(json.dumps(selected,indent=2))
  db.close();db=None
  stage.rename(output);published=True
  return metadata
 except BaseException:
  if db is not None:db.close()
  shutil.rmtree(output if published else stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='config/statcast_ingestion_v1_0.json');p.add_argument('--start');p.add_argument('--end');p.add_argument('--output',required=True);p.add_argument('--target-season',type=int,default=2026);p.add_argument('--projection-warehouse',default='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb')
 a=p.parse_args();r=build(config(a.config),a.output,a.start,a.end,a.projection_warehouse,a.target_season)
 print(json.dumps(r,indent=2))
if __name__=='__main__':main()
