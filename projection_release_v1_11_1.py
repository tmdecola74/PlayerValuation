"""Consolidate accepted frozen projections. No fitting and no benchmark blending."""
import csv,json,math,shutil,hashlib
from collections import defaultdict,Counter
from pathlib import Path
import duckdb
from standalone_io_v1_0 import sha,load,dump,write,tree,verify,start,finish,table,csvrows
from standalone_combined_v1_4 import METRICS,coherent,vectors,read_all_labels,near
from holds_io_v1_5 import source_context,validate_run,overlay

HOME='HOMEGROWN_V1_5_ACCEPTED'
CONS='ESTABLISHED_CONSENSUS'
VERSION='1.11.1'
NEEDED={'hitter':['PA','AB','H','R','HR','RBI','SB','AVG'], 'pitcher':['OUTS','IP','H','BB','ER','SO','W','SV','ERA','WHIP']}
DERIVED={'hitter':{'H':['1B','2B','3B','HR'],'AVG':['H','AB'],'OBP':['H','BB','HBP','AB','SF'],'SLG':['1B','2B','3B','HR','AB'],'OPS':['OBP','SLG']},'pitcher':{'IP':['OUTS'],'ERA':['ER','OUTS'],'WHIP':['H','BB','OUTS'],'SV_plus_HLD':['SV','HLD']}}
META=['season','player_type','projection_source','projection_key','player_id','mlbam_id','name','identity_basis','teams','effective_date','valuation_ready','missing_category_components']

def finite(v):return isinstance(v,(float,int)) and not isinstance(v,bool) and math.isfinite(v)
def mid(v):
 s=str(v).strip()
 return str(int(s)) if s.isdigit() and int(s)>0 else None

def emit(stage,name,rows,fields=None):
 fields=fields or list(dict.fromkeys(n for r in rows for n in r)) or ['status']
 write(stage/name,rows,fields)

def parquet(path,rows,fields):
 # Explicit schema keeps missing numeric columns numeric, including empty tables.
 numeric=set(sum(METRICS.values(),[]))|{'K','season'}
 cols={n:('DOUBLE' if n in numeric and n!='season' else 'INTEGER' if n=='season' else 'BOOLEAN' if n=='valuation_ready' else 'VARCHAR') for n in fields}
 with duckdb.connect() as db:
  db.execute('CREATE TABLE export ('+','.join('"'+n+'" '+t for n,t in cols.items())+')')
  if rows:db.executemany('INSERT INTO export VALUES ('+','.join('?' for n in fields)+')',[[r.get(n) for n in fields] for r in rows])
  db.table('export').write_parquet(str(path))

def canonical_catalog(warehouse):
 warehouse=Path(warehouse).resolve();audit=warehouse.parent/'migration_audit.json';a=load(audit);w={str(warehouse):sha(warehouse),str(audit):sha(audit)}
 if not a.get('pass'):raise ValueError('Migration audit must pass')
 for obj in a['objects']:
  p=(warehouse.parent/obj['parquet_file']).resolve()
  if warehouse.parent not in p.parents or sha(p)!=obj['parquet_sha256']:raise ValueError('Migration Parquet path/hash mismatch')
  w[str(p)]=sha(p)
 bypid=defaultdict(set);owners=defaultdict(set)
 with duckdb.connect(str(warehouse),read_only=True) as db:
  names=dict(db.execute('SELECT player_id,preferred_name FROM players').fetchall())
  for pid,ns,external in db.execute('SELECT player_id,namespace,external_id FROM player_id_crosswalk').fetchall():
   if str(ns).lower()=='mlbam' and mid(external):bypid[str(pid)].add(mid(external));owners[mid(external)].add(str(pid))
 unique={pid:next(iter(ms)) for pid,ms in bypid.items() if len(ms)==1 and len(owners[next(iter(ms))])==1}
 return unique,names,w

def snapshot_consensus(root,catalog):
 root=Path(root).resolve();rows=[];w={};seen=set()
 for role in METRICS:
  p=root/(role+'_consensus.json');w[str(p)]=sha(p)
  for r in load(p):
   if int(r['season'])!=2026:continue
   pid=str(r['player_id']);k=(role,pid)
   if k in seen or r['player_type']!=role:raise ValueError('Duplicate/wrong-role consensus identity')
   seen.add(k)
   supplied={mid(x) for x in r.get('mlbam_ids',[]) if mid(x)}
   if supplied and pid in catalog and supplied!={catalog[pid]}:raise ValueError('Consensus/crosswalk identity disagreement')
   rows.append(r)
 if not rows:raise ValueError('No 2026 consensus snapshot rows')
 pp=root/'metric_provenance.csv'
 if not pp.exists():raise FileNotFoundError('Consensus metric_provenance.csv required: '+str(pp))
 w[str(pp)]=sha(pp);provenance={}
 for r in csvrows(pp):
  if int(r['season'])!=2026:continue
  k=(r['player_type'],r['player_id'],r['metric'])
  if k in provenance:raise ValueError('Duplicate consensus component provenance')
  provenance[k]=r
 for r in rows:
  for m in r['metrics']:
   if (r['player_type'],r['player_id'],m) not in provenance:raise ValueError('Missing consensus provenance')
 return rows,provenance,w

def consensus_vector(role,metrics):
 # Counts stay untouched. Derived rates are rebuilt, never averaged as rates.
 v={n:metrics.get(n) for n in METRICS[role]}
 if v.get('SO') is None and finite(metrics.get('K')):v['SO']=metrics['K']
 if role=='pitcher':
  if v.get('OUTS') is None and finite(v.get('IP')):v['OUTS']=3*v['IP']
  if finite(metrics.get('OUTS')) and finite(metrics.get('IP')) and not near(metrics['OUTS'],3*metrics['IP']):raise ValueError('Consensus IP/OUTS conflict')
 def calc(m,deps,fn):v[m]=fn() if all(finite(v.get(n)) for n in deps) else None
 if role=='hitter':
  # A published H is retained when the complete hit-type vector is absent.
  if all(finite(v.get(n)) for n in ['1B','2B','3B','HR']):
   total=sum(v[n] for n in ['1B','2B','3B','HR'])
   if finite(v.get('H')) and not near(total,v['H']):raise ValueError('Incoherent consensus hit components')
   v['H']=total
  calc('AVG',['H','AB'],lambda:v['H']/v['AB'] if v['AB']>0 else None)
  calc('OBP',['H','BB','HBP','AB','SF'],lambda:(v['H']+v['BB']+v['HBP'])/(v['AB']+v['BB']+v['HBP']+v['SF']) if v['AB']+v['BB']+v['HBP']+v['SF']>0 else None)
  calc('SLG',['1B','2B','3B','HR','AB'],lambda:(v['1B']+2*v['2B']+3*v['3B']+4*v['HR'])/v['AB'] if v['AB']>0 else None)
  calc('OPS',['OBP','SLG'],lambda:v['OBP']+v['SLG'])
  if finite(v.get('H')) and finite(v.get('AB')) and v['H']>v['AB']+1e-8:raise ValueError('Consensus H exceeds AB')
  parts=['AB','BB','HBP','SF','SH']
  if finite(v.get('PA')) and all(finite(v.get(n)) for n in parts) and sum(v[n] for n in parts)>v['PA']+1e-8:raise ValueError('Consensus PA components exceed PA')
 else:
  calc('IP',['OUTS'],lambda:v['OUTS']/3)
  calc('ERA',['ER','OUTS'],lambda:27*v['ER']/v['OUTS'] if v['OUTS']>0 else None)
  calc('WHIP',['H','BB','OUTS'],lambda:3*(v['H']+v['BB'])/v['OUTS'] if v['OUTS']>0 else None)
  calc('SV_plus_HLD',['SV','HLD'],lambda:v['SV']+v['HLD'])
  if finite(v.get('HR')) and finite(v.get('H')) and v['HR']>v['H']+1e-8:raise ValueError('Consensus HR exceeds H')
 if any(x is not None and (not finite(x) or x<0) for x in v.values()):raise ValueError('Invalid consensus number')
 return v

def market_assets(root,catalog):
 root=Path(root);w={};assets={};pids={}
 def ingest(filename,review=False):
  p=root/filename;w[str(p.resolve())]=sha(p)
  for r in csvrows(p):
   role=r['player_type'];nfbc=str(r['nfbc_player_id']).strip();pid=str(r.get('player_id','')).strip();k=(role,nfbc)
   if role not in METRICS or not nfbc.isdigit():raise ValueError('Invalid NFBC asset key')
   d=dict(player_type=role,nfbc_player_id=nfbc,player_id=pid or None,name=r.get('source_player_name') or r.get('name') or '',team=r.get('source_team') or r.get('team') or '',positions=r.get('positions',''),market_ADP=float(r['ADP']) if r.get('ADP') else None,review_reason=r.get('reason',''))
   if d['market_ADP'] is not None and (not finite(d['market_ADP']) or d['market_ADP']<=0):raise ValueError('Invalid ADP')
   if review:
    if k not in assets:assets[k]=d
   else:
    if k in pids:raise ValueError('Duplicate NFBC role/asset identity')
    pids[k]=pid
    # Reviewed eligibility is ingested last and overrides the older mapping.
    assets[k]=d
 ingest('nfbc15_dc_adp.csv')
 # Reviewed eligibility may intentionally fix blank/obsolete mappings in original ADP.
 pids.clear();old=dict(assets);assets={}
 ingest('nfbc15_dc_eligibility.csv')
 for k,r in assets.items():
  if r['market_ADP'] is None and k in old:r['market_ADP']=old[k]['market_ADP']
 for k,r in old.items():
  if k not in assets:assets[k]=r
 ingest('nfbc15_dc_eligibility_review.csv',True)
 for r in assets.values():r['mlbam_id']=catalog.get(r['player_id'])
 return sorted(assets.values(),key=lambda r:(r['player_type'],int(r['nfbc_player_id']))),w

def missing(v,role):return [n for n in NEEDED[role] if not finite(v.get(n))]

def flat(source,role,pid,mlbam,name,basis,teams,v):
 miss=missing(v,role);exposure=v.get('AB' if role=='hitter' else 'IP')
 return dict(season=2026,player_type=role,projection_source=source,projection_key=f'{source}:2026:{role}:{pid or "mlbam_"+mlbam}',player_id=pid,mlbam_id=mlbam,name=name,identity_basis=basis,teams=json.dumps(teams),effective_date='2026-03-24',valuation_ready=bool(pid and not miss and finite(exposure) and exposure>=1),missing_category_components=json.dumps(miss),**v,**({'K':v.get('SO')} if role=='pitcher' else {}))

def provenance_home(c,k,m,holds):
 role=k[1];choice=c['choices'][-1]
 if role=='hitter':
  method='selected_change_experiment';adopt=choice['change_experiment']['hitter']['adopt']
 else:
  method='selected_probability_experiment';adopt=choice['probability_experiment']['adopt']
 component='v1.3 selected workload overlay' if adopt else 'v1.2 frozen fallback workload'
 if m=='SV':component='v1.2 saves forecast preserved exactly';method='frozen_v1_2'
 if m=='HLD':component='v1.5 selected holds opportunity / v1.4 fallback';method='selected_v1_5'
 deps=DERIVED[role].get(m,[])
 if deps:component='derived from released components';method='coherent_component_formula'
 return dict(component_origin=component,selected_method=method,frozen_v1_2_value=c['base'][k].get(m),frozen_v1_2_forecast_reference=str(c['baseline']/'frozen_2026_forecasts.csv'),frozen_v1_2_forecast_sha256=c['provenance_hashes']['baseline_forecasts'],workload_models_reference=str(c['source']/'frozen_models.json'),workload_models_sha256=c['provenance_hashes']['workload_models'],holds_model_reference=str(c['run15']/'frozen_models.json') if role=='pitcher' else None,workload_choice_adopted=adopt,dependencies=json.dumps(deps),holds_supported=holds.get(k,{}).get('supported'),holds_choice_adopted=c.get('holds_final_choice',{}).get('adopt'),forecast_reference=str(c['run15']/'frozen_2026_forecasts.csv'),forecast_sha256=c['provenance_hashes']['accepted_forecasts'])

def assemble(c,accepted,holds,consensus,cp,catalog,names,assets,settings):
 c['provenance_hashes']={'baseline_forecasts':sha(c['baseline']/'frozen_2026_forecasts.csv'),'workload_models':sha(c['source']/'frozen_models.json'),'accepted_forecasts':sha(c['run15']/'frozen_2026_forecasts.csv')}
 reverse={m:pid for pid,m in catalog.items()};cons_by={(r['player_type'],r['player_id']):r for r in consensus};out=[];prov=[];exceptions=[];quarantined={}
 for k,v in sorted(accepted.items()):
  if k[0]!=2026:continue
  role,mlbam=k[1:];pid=reverse.get(mlbam);meta=cons_by.get((role,pid),{});name=meta.get('name') or names.get(pid) or 'MLBAM '+mlbam
  r=flat(HOME,role,pid,mlbam,name,'UNIQUE_WAREHOUSE_MLBAM' if pid else 'MLBAM_ONLY_UNMAPPED',meta.get('teams',[]),coherent(role,v));out.append(r)
  for m in METRICS[role]:prov.append(dict(projection_key=r['projection_key'],projection_source=HOME,player_type=role,player_id=pid,mlbam_id=mlbam,metric=m,value=r.get(m),**provenance_home(c,k,m,holds)))
 for r in consensus:
  role=r['player_type'];pid=r['player_id']
  try:v=consensus_vector(role,r['metrics'])
  except ValueError as error:
   metrics=r['metrics'];hit_types=['1B','2B','3B','HR']
   total=sum(metrics[m] for m in hit_types) if all(finite(metrics.get(m)) for m in hit_types) else None
   h=metrics.get('H');ab=metrics.get('AB');pa=metrics.get('PA');parts=['AB','BB','HBP','SF','SH']
   pa_sum=sum(metrics[m] for m in parts) if all(finite(metrics.get(m)) for m in parts) else None
   detail=dict(season=2026,projection_source=CONS,player_type=role,player_id=pid,mlbam_id=catalog.get(pid),name=r['name'],reason='QUARANTINED_INCOHERENT_SOURCE_COMPONENTS',validation_error=str(error),H=h,hit_type_sum=total,H_minus_hit_type_sum=h-total if finite(h) and total is not None else None,AB=ab,PA=pa,PA_component_sum=pa_sum,PA_minus_component_sum=pa-pa_sum if finite(pa) and pa_sum is not None else None,IP=metrics.get('IP'),OUTS=metrics.get('OUTS'),original_metrics_json=json.dumps(metrics,sort_keys=True,allow_nan=False),disposition='EXCLUDED_FROM_COHERENT_CONSENSUS_EXPORT_AND_VALUATION; ORIGINAL_SNAPSHOT_PRESERVED; HOMEGROWN_UNCHANGED')
   quarantined[role,pid]=detail;exceptions.append(detail);continue
  row=flat(CONS,role,pid,catalog.get(pid),r['name'],'FROZEN_CONSENSUS_CANONICAL',r.get('teams',[]),v);out.append(row)
  for m in METRICS[role]:
   origin='DERIVED_FROM_RELEASE_COMPONENTS' if m in DERIVED[role] else 'FROZEN_CONSENSUS'
   source_metric='IP' if m=='OUTS' and m not in r['metrics'] else m
   original=cp.get((role,pid,source_metric))
   prov.append(dict(projection_key=row['projection_key'],projection_source=CONS,player_type=role,player_id=pid,mlbam_id=catalog.get(pid),metric=m,value=row.get(m),component_origin=origin,dependencies=json.dumps(DERIVED[role].get(m,[])),original_component_provenance=json.dumps(original,sort_keys=True)))
 lookup={(r['projection_source'],r['player_type'],r['player_id'] or '@'+r['mlbam_id']):r for r in out}
 if len(lookup)!=len(out):raise ValueError('Duplicate release projection key')
 coverage=[]
 for a in assets:
  for source in [HOME,CONS]:
   role=a['player_type'];pid=a['player_id'];r=lookup.get((source,role,pid));mlbam=a['mlbam_id']
   if r is None and mlbam and source==HOME:r=lookup.get((source,role,'@'+mlbam))
   if source==CONS and (role,pid) in quarantined:status='QUARANTINED_INCOHERENT_SOURCE_COMPONENTS'
   elif r is None:status='NO_CONFIRMED_PROJECTION_IDENTITY' if not pid else 'NO_SOURCE_PROJECTION'
   elif missing(r,role):status='UNSUPPORTED_CATEGORY_COMPONENTS'
   elif not r['valuation_ready']:status='BELOW_EXPOSURE_FLOOR_OR_UNMAPPED'
   else:status='AVAILABLE'
   key=(2026,role,mlbam)
   no_history=bool(r is None and source==HOME and mlbam and key not in c['rows'])
   d=dict(**a,projection_source=source,coverage_status=status,projection_key=r['projection_key'] if r else None,PA=r.get('PA') if r else None,IP=r.get('IP') if r else None,missing_components=json.dumps(missing(r,role)) if r else None,prior_MLB_history_status='NOT_IN_MODEL_PRIOR_HISTORY_UNIVERSE' if no_history else 'IN_MODEL_HISTORY_UNIVERSE' if key in c['rows'] else 'UNKNOWN',prospect_status='NOT_CLASSIFIED_NO_MINOR_LEAGUE_INPUT')
   coverage.append(d)
   if status!='AVAILABLE':exceptions.append(dict(**d,reason=status))
   if no_history:exceptions.append(dict(**d,reason='POSSIBLE_COLD_START_OR_PROSPECT_REQUIRES_REVIEW'))
 for r in out:
  role=r['player_type'];reasons=[]
  if missing(r,role):reasons.append('UNSUPPORTED_CATEGORY_COMPONENTS')
  if not r['player_id']:reasons.append('NO_CANONICAL_MAPPING_FOR_VALUATION')
  if not r['mlbam_id']:reasons.append('NO_UNIQUE_MLBAM_MAPPING_FOR_EVALUATION')
  exp=r.get('PA' if role=='hitter' else 'IP');floor=settings['low_PA_review'] if role=='hitter' else settings['low_IP_review'];ceiling=settings['high_PA_review'] if role=='hitter' else settings['high_IP_review']
  if finite(exp) and exp>ceiling:reasons.append('EXTREME_HIGH_PLAYING_TIME_REVIEW_ONLY')
  if finite(exp) and exp<floor:reasons.append('LOW_PLAYING_TIME_REVIEW_ONLY')
  if r['projection_source']==HOME:
   hist=c['rows'].get((2026,role,r['mlbam_id']),{});prior=hist.get('x_actual_lag1_PA' if role=='hitter' else 'x_actual_lag1_OUTS');projected=r.get('PA' if role=='hitter' else 'OUTS')
   if finite(prior) and finite(projected) and abs(projected-prior)>settings['large_PA_change_review' if role=='hitter' else 'large_OUTS_change_review']:reasons.append('LARGE_PRIOR_WORKLOAD_CHANGE_REVIEW_ONLY')
  for reason in reasons:exceptions.append(dict(projection_source=r['projection_source'],player_type=role,player_id=r['player_id'],mlbam_id=r['mlbam_id'],name=r['name'],projection_key=r['projection_key'],reason=reason,PA=r.get('PA'),IP=r.get('IP')))
 return out,prov,coverage,exceptions

def export_tables(stage,rows):
 adapters={}
 for source,label in [(HOME,'homegrown'),(CONS,'consensus')]:
  adapters[label]={}
  for role in METRICS:
   rr=[r for r in rows if r['projection_source']==source and r['player_type']==role];fields=META+METRICS[role]+(['K'] if role=='pitcher' else [])
   emit(stage,f'{label}_{role}s_2026.csv',rr,fields);parquet(stage/f'{label}_{role}s_2026.parquet',rr,fields)
   # Exact input shape of value_players/candidate_records, kept source-separated.
   adapter=[dict(season=2026,player_type=role,player_id=r['player_id'],name=r['name'],mlbam_ids=[r['mlbam_id']] if r['mlbam_id'] else [],teams=json.loads(r['teams']),projection_source=source,metrics={m:r.get(m) for m in METRICS[role]}) for r in rr if r['valuation_ready']]
   dump(stage/f'{label}_{role}_valuation_input.json',adapter);adapters[label][role]=len(adapter)
 return adapters

DEFAULTS=dict(run15='outputs/standalone_holds_attribution_v1_5',run14='outputs/standalone_combined_v1_4',source='outputs/standalone_workload_experiments_v1_3',matrix='outputs/standalone_lagged_features_v1_0',baseline='outputs/standalone_role_workload_v1_2',labels='outputs/training_labels_v1_0',consensus='outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix/consensus',warehouse='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb',draft_inputs='data/valuation_inputs_dc_v1_1',settings='config/projection_release_v1_11.json',output='outputs/projection_release_2026_v1_11_1',backup_root='backups')

def build(a):
 print('Verifying accepted historical choices and frozen v1.5 forecasts...',flush=True)
 c=source_context(a.run14,a.source,a.matrix,a.baseline,a.labels);truth=read_all_labels(c['labels'],'training');f,holds,w=validate_run(a.run15,c,truth);c['watched'].update(w);c['run15']=Path(a.run15).resolve();c['holds_final_choice']=f['final_choice']
 accepted={k:overlay(vectors(c,k)['combined_v1_4'],holds[k]['selected_v1_5']) if k[1]=='pitcher' else vectors(c,k)['combined_v1_4'] for k in c['predictions']}
 catalog,names,w=canonical_catalog(a.warehouse);c['watched'].update(w);cons,cp,w=snapshot_consensus(a.consensus,catalog);c['watched'].update(w);assets,w=market_assets(a.draft_inputs,catalog);c['watched'].update(w);settings=load(a.settings);c['watched'][str(Path(a.settings).resolve())]=sha(a.settings)
 if settings!=dict(low_PA_review=50,low_IP_review=10,high_PA_review=750,high_IP_review=220,large_PA_change_review=300,large_OUTS_change_review=240):raise ValueError('Review thresholds must match the versioned v1.11 policy; create another version to revise')
 # Output cannot overlap any source directory, including rejected research releases.
 inputs=[a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.consensus,a.warehouse,a.draft_inputs,a.settings]
 out,backups,stage=start(a.output,a.backup_root,inputs)
 try:
  rr,pp,coverage,exceptions=assemble(c,accepted,holds,cons,cp,catalog,names,assets,settings);counts=export_tables(stage,rr)
  emit(stage,'component_provenance.csv',pp);emit(stage,'draft_pool_coverage.csv',coverage);emit(stage,'exceptions.csv',exceptions)
  quarantined=[r for r in exceptions if r.get('original_metrics_json') is not None and r['reason']=='QUARANTINED_INCOHERENT_SOURCE_COMPONENTS']
  emit(stage,'consensus_component_exceptions.csv',quarantined, list(dict.fromkeys(n for r in quarantined for n in r)) or ['season','player_type','player_id','mlbam_id','name','reason','validation_error','H','hit_type_sum','H_minus_hit_type_sum','original_metrics_json','disposition'])
  dump(stage/'quarantined_consensus_records.json',[r for r in cons if (r['player_type'],r['player_id']) in {(x['player_type'],x['player_id']) for x in quarantined}])
  dump(stage/'coherent_projection_records.json',rr)
  for file in ['hitter_consensus.json','pitcher_consensus.json','metric_provenance.csv']:shutil.copyfile(Path(a.consensus)/file,stage/('source_'+file))
  dump(stage/'accepted_component_choices.json',dict(workload=c['choices'][-1],holds=f['final_choice']))
  dump(stage/'forecast_freeze.json',{n:sha(stage/n) for n in tree(stage)})
  dump(stage/'export_schema.json',dict(version=VERSION,season=2026,keys=['projection_source','season','player_type','player_id_or_mlbam_id'],pitcher_K_alias='SO',IP='decimal innings = expected OUTS / 3; never baseball .1/.2 notation',OUTS='continuous expected outs; actual OUTS remain integer',null='Unsupported or unavailable, never zero-filled',rates='AVG=H/AB; ERA=27*ER/OUTS; WHIP=3*(H+BB)/OUTS',valuation_adapter='Pass one source\'s hitter+pitcher *_valuation_input.json arrays to existing value_players with reviewed eligibility/calibration. No automatic consensus fallback.',platform_assets='NFBC IDs live in draft_pool_coverage.csv. Same-name and two-way platform assets are not merged by name; one canonical player cannot be counted twice.',source_separation=[HOME,CONS]))
  report=dict(version=VERSION,status='EXPORTED_WITH_CONSENSUS_QUARANTINE_REVIEW_REQUIRED' if quarantined else 'FROZEN_PROJECTIONS_EXPORTED_NOT_NEW_MODEL_SELECTION',season=2026,source_policy=HOME,effective_date='2026-03-24',date_basis='User-confirmed effective date; retrospective retrieval, not independently archived preseason vintages',evaluation_status='2026 previously reviewed; evaluation-only, not untouched holdout',models_fitted=False,choices_changed=False,evaluation_outcomes_read=False,external_projections_used_as_homegrown_predictors=False,saves_preserved=True,holds_preserved=True,projection_rows=dict(Counter(r['projection_source']+'_'+r['player_type'] for r in rr)),valuation_adapter_rows=counts,draft_assets=len(assets),coverage_statuses=dict(Counter(r['projection_source']+':'+r['coverage_status'] for r in coverage)),exceptions=len(exceptions),quarantined_consensus_rows=len(quarantined),consensus_source_rows=len(cons),consensus_quarantine_policy='Preserve original values; exclude internally inconsistent rows from coherent consensus exports and adapters; never alter homegrown forecasts',label_reference_sha256=load(c['labels']/'label_build_report.json')['reference_sha256'],warehouse_sha256=sha(a.warehouse),inputs_unchanged=True,limitations=['No prospect/minor-league or full preseason roster universe: missing cold starts are explicitly audited.','Projected R/RBI/W/SV/HLD are not derivable identities; coherence covers component arithmetic and ratios, not a game simulation.','Review thresholds flag estimates and never cap, rerank or replace them.','Research v1.6-v1.10 remains separate, including the multiyear SB candidate; no multiplier or SB research overlay is released.','No new Yahoo eligibility feed supplied; export is source-neutral and NFBC coverage only.','Full weekly draft-and-hold production and injury/availability information remain separate research needs.'])
  dump(stage/'projection_release_report.json',report);backup=finish(out,backups,stage,c['watched']);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def load_valuation_source(run,source):
 """Stable adapter: select exactly 'homegrown' or 'consensus'; no cross-source fallback.

 Returns the player dictionaries accepted by existing value_players/candidate_records.
 Eligibility and SGP calibration must still be supplied to that engine separately.
 """
 if source not in ['homegrown','consensus']:raise ValueError('Choose homegrown or consensus explicitly')
 run=Path(run).resolve();verify(run);f=load(run/'forecast_freeze.json')
 names=[source+'_'+role+'_valuation_input.json' for role in METRICS]
 for n in names:
  if n not in f or sha(run/n)!=f[n]:raise ValueError('Valuation adapter freeze mismatch')
 result=[];seen=set();expected=HOME if source=='homegrown' else CONS
 for n in names:
  for r in load(run/n):
   k=(r['player_type'],r['player_id'])
   if k in seen or r['season']!=2026 or r['projection_source']!=expected or not r['player_id']:raise ValueError('Invalid valuation source identity')
   seen.add(k);result.append(r)
 return result
