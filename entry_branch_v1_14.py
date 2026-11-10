"""Dated intake and chronological fold plan; no translation or forecasting fitted."""
import csv,json,datetime,hashlib
from collections import Counter,defaultdict
from pathlib import Path
from standalone_io_v1_0 import csvrows,sha
from projection_release_v1_11_1 import finite,mid

VERSION='1.14.0'
POPULATION=['origin_season','player_type','mlbam_id','branch_class','as_of_date','date_of_birth','source','source_record_id','evidence_reference','retrieved_at','vintage_basis']
HISTORY=['origin_season','player_type','mlbam_id','event_season','event_end_date','as_of_date','source_type','competition','metric','value','source','source_record_id','evidence_reference','retrieved_at','vintage_basis']
CONTEXT=['origin_season','player_type','mlbam_id','event_date','as_of_date','source_type','signal','value','source','source_record_id','evidence_reference','retrieved_at','vintage_basis']
CUTOFFS=['origin_season','cutoff_date','source','evidence_reference']
METRICS={'hitter':{'G','PA','AB','H','1B','2B','3B','HR','R','RBI','SB','CS','BB','HBP','SF','SH','SO'},'pitcher':{'G','GS','OUTS','H','ER','BB','SO','HR','W','SV','HLD','QS','TBF'}}
BASIS={'ARCHIVED_AS_OF_CLAIM','USER_CONFIRMED_PRESEASON_EFFECTIVE','RETROSPECTIVE_EVENT_TIME_ONLY'}
CLASSES={'prospect','international_arrival','returner'}
CONFIG=dict(version=VERSION,status='CONTRACT_AND_INTAKE_ONLY_NO_MODEL_FIT',first_origin=2019,first_population_origin=2016,historical_override_latest='FEBRUARY_28_CONSERVATIVE_CONTRACT_LIMIT',last_development_origin=2025,disclosed_evaluation_origin=2026,minimum_prior_population_origins=3,historical_default_cutoff='JANUARY_1_OF_ORIGIN_YEAR_CONSERVATIVE_RESEARCH_SNAPSHOT',evaluation_cutoff='2026-03-24',branches=['prospect','international_arrival','returner'],forecast_components=['participation_and_MLB_playing_time','skill_rates_and_coherent_count_components','pitcher_role_and_workload','separate_saves_and_holds_opportunity'],participation_target_policy='Missing actual-export row is unknown; negative participation requires a verified complete MLB appearance reference',workload_composition='MLB participation probability times conditional workload; rates use eligible positive denominators',skill_target_policy='Frozen component exclusions apply to labels and MLB-prior features; no cross-source backfill',target_denominators_are_predictors=False,baseline_controls=['no_automatic_forecast_when_inputs_unsupported','accepted_homegrown_for_existing_covered_players_unchanged','external_projections_benchmark_only'],candidate_selection='earlier_origin_out_of_fold_results_only; never 2026',special_seasons='2020 retained as observed; 2021 transition explicitly retained; no automatic rescaling',required_future_work=['frozen eligible MLB training labels joined only after origin populations/features freeze','complete MLB appearance coverage to distinguish nonparticipants from missing actual records','level/league/park/era translation with historical validation','role and availability features with historical vintages','sample-size controls, cold-start fallback and uncertainty checks','coherent final component constraints and separate benchmark pools'],fit_ready=False)

def iso(v):
 try:return datetime.date.fromisoformat(v)
 except (TypeError,ValueError):raise ValueError('Invalid ISO date: '+str(v))
def read_exact(path,fields,watched):
 if not path:return []
 path=Path(path).resolve()
 with path.open(encoding='utf-8-sig',newline='') as f:
  reader=csv.DictReader(f)
  if reader.fieldnames!=fields:raise ValueError('Wrong dated-input schema/order: '+str(path))
  rows=list(reader)
 watched[str(path)]=sha(path);return rows

def intake(population=None,history=None,context=None,cutoffs=None):
 watched={};cutoff_map={y:(datetime.date(y,1,1) if y<2026 else iso(CONFIG['evaluation_cutoff'])) for y in range(CONFIG['first_population_origin'],2027)};cutoff_basis={y:'CONSERVATIVE_JANUARY_1_RESEARCH_DEFAULT' if y<2026 else 'USER_CONFIRMED_2026_EFFECTIVE_DATE' for y in cutoff_map}
 for r in read_exact(cutoffs,CUTOFFS,watched):
  y=int(r['origin_season']);date=iso(r['cutoff_date'])
  if y not in cutoff_map or date.year!=y or not r['source'].strip() or not r['evidence_reference'].strip():raise ValueError('Invalid documented origin cutoff')
  if cutoff_basis[y]=='DOCUMENTED_OVERRIDE':raise ValueError('Duplicate origin cutoff')
  # Overrides must be documented preseason dates; no automatic opening-day guess.
  if y<2026 and date>datetime.date(y,2,28):raise ValueError('Historical overrides are capped at February 28 in this conservative contract; later snapshots require a revised contract')
  if y==2026 and date!=iso(CONFIG['evaluation_cutoff']):raise ValueError('2026 effective date remains fixed')
  cutoff_map[y]=date;cutoff_basis[y]='DOCUMENTED_OVERRIDE'
 rows={};seen={};population_keys=set()
 for kind,path,fields in [('population',population,POPULATION),('history',history,HISTORY),('context',context,CONTEXT)]:
  rows[kind]=[];seen[kind]=set()
  for r in read_exact(path,fields,watched):
   y=int(r['origin_season']);role=r['player_type'];pid=mid(r['mlbam_id']);key=(y,role,pid)
   if y not in cutoff_map or role not in METRICS or pid!=r['mlbam_id']:raise ValueError('Invalid origin/role/MLBAM identity')
   asof=iso(r['as_of_date'])
   if asof>cutoff_map[y]:raise ValueError('Input is later than its origin cutoff')
   if r['vintage_basis'] not in BASIS or not all(r[n].strip() for n in ['source','source_record_id','evidence_reference','retrieved_at']):raise ValueError('Dated source provenance required')
   try:retrieved=datetime.datetime.fromisoformat(r['retrieved_at'].replace('Z','+00:00'))
   except ValueError:raise ValueError('Invalid retrieval timestamp')
   if retrieved.tzinfo is None:raise ValueError('Retrieval timestamp requires a UTC offset or Z')
   if retrieved.date()<asof:raise ValueError('Retrieval cannot predate the claimed source as-of date')
   if kind=='population':
    if key in population_keys or r['branch_class'] not in CLASSES:raise ValueError('Duplicate population identity or unsupported branch class')
    if r['date_of_birth'] and iso(r['date_of_birth'])>asof:raise ValueError('Birth date after source date')
    population_keys.add(key);token=key
   elif key not in population_keys:raise ValueError('History/context cannot add a player absent from the frozen dated population')
   elif kind=='history':
    event_year=int(r['event_season']);event_end=iso(r['event_end_date'])
    if event_year>=y or event_end.year!=event_year or event_end>asof:raise ValueError('History contains target/future events or inconsistent event season')
    if r['source_type'] not in ['minor_league','overseas','mlb_prior'] or not r['competition'].strip() or r['metric'] not in METRICS[role]:raise ValueError('Invalid history source/competition/primitive metric; use integer OUTS, not baseball IP')
    if r['value']!='':
     value=float(r['value'])
     if not finite(value) or value<0 or not value.is_integer():raise ValueError('Historical primitive counts must be nonnegative integers; blanks stay unknown')
    token=key+(r['source_type'],r['competition'],event_year,r['metric'],r['source'],r['source_record_id'])
   else:
    if iso(r['event_date'])>asof or r['source_type'] not in ['roster','availability'] or r['signal'] not in ['mlb_roster','expected_assignment','injury_status','rotation_role','bullpen_role','return_from_injury','mlb_arrival']:raise ValueError('Invalid dated roster/availability context')
    token=key+(r['source_type'],r['signal'],r['event_date'],r['source'],r['source_record_id'])
   if token in seen[kind]:raise ValueError('Duplicate dated input record')
   seen[kind].add(token);rows[kind].append(dict(r,origin_season=y,mlbam_id=pid,origin_cutoff=cutoff_map[y].isoformat(),age_at_cutoff=((cutoff_map[y]-iso(r['date_of_birth'])).days/365.2425 if kind=='population' and r['date_of_birth'] else None)))
 folds=[];pop_years={r['origin_season'] for r in rows['population']};hist_keys={(r['origin_season'],r['player_type'],r['mlbam_id']) for r in rows['history'] if r['value']!=''};context_keys={(r['origin_season'],r['player_type'],r['mlbam_id']) for r in rows['context'] if r['value'].strip()}
 for y in range(2019,2027):
  train=sorted(x for x in pop_years if x<y and x<=2025);current=[r for r in rows['population'] if r['origin_season']==y]
  folds.append(dict(origin=y,cutoff=cutoff_map[y].isoformat(),cutoff_basis=cutoff_basis[y],split='DISCLOSED_EVALUATION_ONLY' if y==2026 else 'HISTORICAL_DEVELOPMENT',training_population_origins_json=json.dumps(train),population_rows=len(current),rows_with_numeric_history=sum((y,r['player_type'],r['mlbam_id']) in hist_keys for r in current),rows_with_roster_or_availability=sum((y,r['player_type'],r['mlbam_id']) in context_keys for r in current),enough_prior_population_origins=len(train)>=CONFIG['minimum_prior_population_origins'],transition_2021_retained=y==2021,training_labels_joined=False,fit_ready=False))
 report=dict(version=VERSION,status='DATED_INPUTS_VALIDATED_NOT_FIT_READY' if population_keys else 'BRANCH_DEFINED_INPUTS_REQUIRED',models_fitted=False,labels_read=False,forecasts_generated=False,fit_ready=False,population_rows=len(population_keys),history_rows=len(rows['history']),context_rows=len(rows['context']),vintage_bases=dict(Counter(r['vintage_basis'] for rr in rows.values() for r in rr)),limitations=['Date checks validate claims, not independent archive authenticity. Retrospective event-time records remain explicitly disclosed.','Historical defaults are conservative January 1 snapshots, not claimed historical draft dates. Later cutoffs require documented overrides before intake.','Minor/overseas rate translations, park/league strength, sample-size controls, MLB playing time and availability relationships are not guessed.','No actual-season participant list expands origin populations; history/context are restricted to registered identities.','No training labels joined or models fitted. Any later fit must use only earlier-origin features and eligible labels, including the 2021 transition; 2026 cannot select candidates.'])
 return rows,folds,report,watched
