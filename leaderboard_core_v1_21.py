"""Explicit source definitions and non-destructive leaderboard normalization."""
import csv,math
from decimal import Decimal,InvalidOperation
from collections import Counter
VERSION='1.21.0'
BB_RATES=['gb_rate','air_rate','fb_rate','ld_rate','pu_rate','pull_rate','straight_rate','oppo_rate','pull_gb_rate','straight_gb_rate','oppo_gb_rate','pull_air_rate','straight_air_rate','oppo_air_rate']
BAT_RATES=['percent_swings_competitive','hard_swing_rate','squared_up_per_bat_contact','squared_up_per_swing','blast_per_bat_contact','blast_per_swing','whiff_per_swing','batted_ball_event_per_swing']
EV_PERCENT=['anglesweetspotpercent','ev95percent','brl_percent','brl_pa']
EV_MEANS=['avg_hit_angle','max_hit_speed','avg_hit_speed','ev50','fbld','gb','max_distance','avg_distance','avg_hr_distance']
RUN_COUNTS=['N_runner_moved','N_runner_moved_XB','N_runner_moved_SBX']
RUN_VALUES=['runner_runs_tot','runner_runs_XB','runner_runs_SBX','runner_runs_XB_swipe','runner_runs_XB_snipe','runner_runs_XB_freeze','runner_runs_SB2','runner_runs_SB3','simple_stolen_on_running_act_SB2','simple_stolen_on_running_act_SB3']
COLUMNS={
 'batted_ball':['id','name','year','bbe']+BB_RATES,
 'bat_tracking':['id','name','year','swings_competitive','percent_swings_competitive','contact','avg_bat_speed','hard_swing_rate','squared_up_per_bat_contact','squared_up_per_swing','blast_per_bat_contact','blast_per_swing','swing_length','swords','batter_run_value','whiffs','whiff_per_swing','batted_ball_events','batted_ball_event_per_swing'],
 'exit_velocity':['last_name, first_name','player_id','attempts']+EV_MEANS+EV_PERCENT+['ev95plus','barrels'],
 'baserunning':['player_id','entity_name','team_name','start_year','end_year']+RUN_COUNTS+RUN_VALUES}
DEFAULT=dict(version=VERSION,historical_max_source_season=2025,quarantine_source_season=2026,minimum_bbe=30,minimum_competitive_swings=100,minimum_contacts=30,minimum_recorded_movements=20,maximum_count_rate_rounding_error=.0005001,proxy_fraction_review_threshold=.02,angle_rounding_tolerance=.0500001,definition_policy='NO_AUTOMATIC_PROMOTION_OR_SOURCE_SUBSTITUTION')

def numeric(v):
 if v is None or str(v).strip().lower() in ['','null','none','nan','n/a','na','--']:return None
 try:x=float(v)
 except (TypeError,ValueError):raise ValueError('Non-numeric source value: '+str(v)) from None
 if not math.isfinite(x):raise ValueError('Nonfinite source value')
 return x

def integer(v,name,positive=False):
 try:d=Decimal(str(v))
 except InvalidOperation:raise ValueError('Invalid '+name) from None
 if not d.is_finite() or d!=int(d) or d<(1 if positive else 0):raise ValueError('Invalid '+name)
 return int(d)

def row_key(raw,source):
 family=source['family'];role=source['player_type'];pid=str(integer(raw.get('id' if family in ['batted_ball','bat_tracking'] else 'player_id'),'MLBAM ID',True))
 if family=='exit_velocity':year=integer(source['season'],'registered season',True)
 elif family=='baserunning':
  year=integer(raw.get('start_year'),'start year',True)
  if year!=integer(raw.get('end_year'),'end year',True):raise ValueError('Multi-season baserunning rows cannot become single-year features')
 else:year=integer(raw.get('year'),'source year',True)
 if year not in source['expected_seasons'] or year not in [2023,2024,2025,2026] or role not in ['hitter','pitcher'] or family=='baserunning' and role!='hitter':raise ValueError('Unregistered source season/role')
 return family,role,year,pid

def registry(family):
 if family=='batted_ball':return ['bbe']+BB_RATES
 if family=='bat_tracking':return ['swings_competitive','contact','avg_bat_speed','swing_length','swords','batter_run_value','whiffs','batted_ball_events']+BAT_RATES
 if family=='exit_velocity':return ['attempts','ev95plus','barrels']+EV_MEANS+EV_PERCENT
 return RUN_COUNTS+RUN_VALUES

def normalize(raw,source,line,c):
 family,role,year,pid=row_key(raw,source);rows=[];issues=[]
 def issue(code,metric,detail):issues.append(dict(source_id=source['source_id'],source_row=line,source_season=year,player_type=role,mlbam_id=pid,code=code,metric=metric,detail=detail,split='quarantine_2026' if year==2026 else 'historical'))
 counts={'batted_ball':['bbe'],'bat_tracking':['swings_competitive','contact','swords','whiffs','batted_ball_events'],'exit_velocity':['attempts','ev95plus','barrels'],'baserunning':RUN_COUNTS}[family]
 cc={m:integer(raw[m],m) if numeric(raw[m]) is not None else None for m in counts}
 if family=='bat_tracking' and cc['swings_competitive'] is not None:
  sw=cc['swings_competitive']
  for m in ['contact','whiffs','batted_ball_events']:
   if cc[m] is not None and cc[m]>sw:raise ValueError('Bat-tracking component exceeds competitive swings')
  if cc['contact'] is not None and cc['batted_ball_events'] is not None and cc['batted_ball_events']>cc['contact']:raise ValueError('BBE exceeds competitive contacts')
 if family=='exit_velocity' and cc['attempts'] is not None:
  if any(cc[m] is not None and cc[m]>cc['attempts'] for m in ['ev95plus','barrels']):raise ValueError('EV event counts exceed BBE')
 for m in registry(family):
  value=numeric(raw[m]);normal=value;den=None;unit='count' if m in counts else 'source_units';allowed=True;definition='USER_SUPPLIED_LEADERBOARD';minimum=c['minimum_bbe'];sample_basis=None;den_basis=None
  if family=='batted_ball':
   den=cc['bbe'];den_basis='EXPORTED_BBE';unit='count' if m=='bbe' else 'fraction';definition='EXPORTED_FRACTION_OF_ALL_BBE' if m!='bbe' else 'EXPORTED_BBE_COUNT'
  elif family=='bat_tracking':
   den=cc['contact'] if m.endswith('_per_bat_contact') else cc['swings_competitive'];den_basis='EXPORTED_COMPETITIVE_CONTACTS' if m.endswith('_per_bat_contact') else 'EXPORTED_COMPETITIVE_SWINGS';minimum=c['minimum_contacts'] if m.endswith('_per_bat_contact') else c['minimum_competitive_swings'];unit='fraction' if m in BAT_RATES else 'count' if m in counts else 'mph' if m=='avg_bat_speed' else 'feet' if m=='swing_length' else 'runs'
   definition='COMPETITIVE_SWING_CONTACT_EXPORT_HITTER_VALUE' if role=='hitter' else 'COMPETITIVE_SWING_CONTACT_EXPORT_ALLOWED_TO_BATTERS'
   if m=='percent_swings_competitive':den=None;den_basis='ALL_SWINGS_NOT_EXPORTED';allowed=False
   if m in ['batter_run_value','swords']:allowed=False;definition='CONTEXT_RESEARCH_DEFINITION_REVIEW_REQUIRED'
  elif family=='exit_velocity':
   den=cc['attempts'];den_basis='EXPORTED_BBE_PROXY_NOT_MEASURED_SAMPLE';unit='fraction' if m in EV_PERCENT else 'count' if m in counts else 'degrees' if m=='avg_hit_angle' else 'feet' if 'distance' in m else 'mph'
   if m in EV_PERCENT:normal=value/100 if value is not None else None
   definition='EV50_HARDEST_HALF' if m=='ev50' and role=='hitter' else 'EV50_SOFTEST_HALF_ALLOWED' if m=='ev50' else 'EXPORTED_EV_BBE_SAMPLE_PROXY'
   if m in ['brl_pa','fbld','gb','avg_hr_distance']:
    den=None;den_basis='REQUIRED_PA_OR_CONTACT_SUBSET_DENOMINATOR_NOT_EXPORTED';allowed=False
  else:
   den=cc['N_runner_moved'];den_basis='RECORDED_MOVEMENTS_NOT_ALL_OPPORTUNITIES';unit='count' if m in RUN_COUNTS else 'runs_or_UNVERIFIED_SOURCE_UNITS';minimum=c['minimum_recorded_movements'];allowed=False;definition='BASERUNNING_CONTEXT_REVIEW_NO_ATTEMPT_RATE_INFERENCE'
  sample_basis=den_basis
  range_ok=True
  if unit=='fraction' and normal is not None and not 0<=normal<=1:range_ok=False;issue('OUT_OF_RANGE_RATE',m,str(normal))
  if normal is not None and family=='exit_velocity' and m=='avg_hit_angle' and not -90<=normal<=90:range_ok=False;issue('OUT_OF_RANGE_ANGLE',m,str(normal))
  if normal is not None and m not in RUN_VALUES+['batter_run_value','avg_hit_angle'] and unit in ['mph','feet','count'] and normal<0:range_ok=False;issue('NEGATIVE_PHYSICAL_VALUE',m,str(normal))
  sample_eligible=den is not None and den>=minimum;eligible=normal is not None and sample_eligible and range_ok and allowed
  reason='AVAILABLE_FIXED_SAMPLE_CONTROL' if eligible else 'MISSING_VALUE' if normal is None else 'INVALID_RANGE' if not range_ok else 'DEFINITION_OR_DENOMINATOR_REVIEW_REQUIRED' if not allowed else 'MISSING_OR_BELOW_FIXED_SAMPLE'
  rows.append(dict(source_id=source['source_id'],source_row=line,family=family,player_type=role,source_season=year,mlbam_id=pid,name=raw.get('name',raw.get('last_name, first_name',raw.get('entity_name',''))),metric=m,feature='savant_'+family+'_'+m,raw_text=raw[m],raw_value=value,normalized_value=normal,value=normal if eligible else None,unit=unit,denominator=den,sample_basis=sample_basis,minimum_observations=minimum,sample_eligible=sample_eligible,definition_supported=allowed,eligible=eligible,reason=reason,definition=definition,period_scope='PARTIAL_2023_BAT_TRACKING_EXACT_START_NOT_EXPORTED' if family=='bat_tracking' and year==2023 else 'USER_SUPPLIED_SEASON_SCOPE_FILTERS_UNVERIFIED',coverage=None))
 # Export rounding is audited; the official values are never replaced by reconstructed ratios.
 if family=='exit_velocity' and cc['attempts']:
  for m,count in [('ev95percent','ev95plus'),('brl_percent','barrels')]:
   v=numeric(raw[m]);n=cc[count]
   if v is not None and n is not None and abs(v/100-n/cc['attempts'])>c['maximum_count_rate_rounding_error']:issue('COUNT_RATE_DIFFERENCE_BEYOND_ROUNDING',m,'Export fraction differs from count / BBE; preserved without replacement')
 if family=='batted_ball':
  for target,parts in [('air_rate',['fb_rate','ld_rate','pu_rate']),('gb_rate',['pull_gb_rate','straight_gb_rate','oppo_gb_rate']),('air_rate',['pull_air_rate','straight_air_rate','oppo_air_rate'])]:
   v=numeric(raw[target]);pp=[numeric(raw[n]) for n in parts]
   if v is not None and all(x is not None for x in pp) and abs(v-sum(pp))>1e-8:issue('BATTED_BALL_PARTITION_DIFFERENCE',target,'Exported rate components do not sum within tolerance')
 if family=='bat_tracking':
  for prefix in ['squared_up','blast']:
   contact=numeric(raw[prefix+'_per_bat_contact']);sw=numeric(raw[prefix+'_per_swing'])
   if contact is not None and sw is not None and cc['contact'] is not None and cc['swings_competitive'] is not None and abs(contact*cc['contact']-sw*cc['swings_competitive'])>1e-5:issue('BAT_RATE_DENOMINATOR_DIFFERENCE',prefix,'Per-contact and per-swing implied counts differ; no counts fabricated')
 for review in issues:
  for row in rows:
   affected=row['metric']==review['metric'] or review['code']=='BAT_RATE_DENOMINATOR_DIFFERENCE' and row['metric'].startswith(review['metric']+'_') or review['code']=='BATTED_BALL_PARTITION_DIFFERENCE' and row['metric'] in BB_RATES
   if affected:row.update(value=None,eligible=False,definition_supported=False,reason='SOURCE_RELATIONSHIP_REVIEW_REQUIRED')
 return rows,issues

FIELDS=['source_id','source_row','family','player_type','source_season','mlbam_id','name','metric','feature','raw_text','raw_value','normalized_value','value','unit','denominator','sample_basis','minimum_observations','sample_eligible','definition_supported','eligible','reason','definition','period_scope','coverage']

def read_sources(entries,input_dir,c,hashfn):
 seen=set();historical=[];quarantine=[];issues=[];inventory=[];paths=[];unexpected=[]
 for source in entries:
  family=source['family']
  if family not in COLUMNS:raise ValueError('Unsupported family')
  path=(input_dir/source['file']).resolve()
  if input_dir not in path.parents:raise ValueError('Source path escapes input folder')
  if hashfn(path)!=source['expected_sha256']:raise ValueError('Registered source hash differs: '+path.name)
  paths.append(path);counts=Counter()
  with path.open(encoding='utf-8-sig',newline='') as f:
   reader=csv.DictReader(f);header=reader.fieldnames or []
   if len(header)!=len(set(header)) or not set(COLUMNS[family])<=set(header):raise ValueError('Missing/duplicate source columns: '+path.name)
   unexpected.extend(dict(source_id=source['source_id'],column=n,status='PRESERVED_IN_SOURCE_SNAPSHOT_NOT_AUTO_FEATURE') for n in header if n not in COLUMNS[family])
   for line,raw in enumerate(reader,2):
    if None in raw or any(v is None for v in raw.values()):raise ValueError('Malformed CSV row')
    key=row_key(raw,source)
    if key in seen:raise ValueError('Duplicate source family/role/player-season; no automatic team-split merge')
    seen.add(key);rows,review=normalize(raw,source,line,c);(quarantine if key[2]==2026 else historical).extend(rows);issues.extend(review);counts[key[2]]+=1
  inventory.append(dict(source_id=source['source_id'],file=source['file'],family=family,player_type=source['player_type'],sha256=source['expected_sha256'],registered_season=source.get('season'),row_counts_by_season=dict(sorted(counts.items())),retrieved_at=source.get('retrieved_at'),filter_settings=source.get('filter_settings','UNKNOWN_NOT_IN_EXPORT'),season_basis='EXPLICIT_REGISTRY_FOR_YEARLESS_EV' if family=='exit_velocity' else 'CSV_YEAR_FIELDS',vintage_basis='RETROSPECTIVE_EXPORT_NOT_CERTIFIED_PRESEASON_ARCHIVE'))
 return historical,quarantine,issues,inventory,paths,unexpected
