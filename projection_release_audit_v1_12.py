"""Read-only consensus provenance, rate exposure and missing-universe diagnostics."""
import argparse,csv,json,math,shutil,hashlib
from pathlib import Path
from collections import defaultdict,Counter
import duckdb
from standalone_io_v1_0 import load,sha,dump,verify,table,csvrows,start,finish
from projection_release_v1_11_1 import HOME,CONS,METRICS,finite,mid,emit,canonical_catalog

VERSION='1.12.0'
ROUNDING_SCALE=.001 # Descriptive bin, never an acceptance/reconciliation rule.
EPS=1e-8

def close(a,b):return finite(a) and finite(b) and abs(a-b)<=EPS*max(1,abs(a),abs(b))
def parse_json_cell(v,default):
 if v is None or v=='':return default
 return json.loads(v) if isinstance(v,str) else v

def primitive_provenance(row):
 if not row:return None,'MISSING_PROVENANCE'
 if row.get('method')!='weighted_available_source_mean':return None,'NOT_PRIMITIVE_WEIGHTED_MEAN'
 weights=parse_json_cell(row.get('normalized_weights'),{});values=parse_json_cell(row.get('source_values'),{})
 if not isinstance(weights,dict) or not isinstance(values,dict):return None,'INVALID_PROVENANCE_SHAPE'
 if any(not finite(v) or v<0 for v in weights.values()):return None,'INVALID_WEIGHT'
 w={str(s):v for s,v in weights.items() if v>0}
 if not w or not close(sum(w.values()),1) or any(not finite(values.get(s)) for s in w):return None,'INCOMPLETE_OR_UNNORMALIZED_PROVENANCE'
 return (w,values),'AVAILABLE'

def decompose(metrics,provenance,terms):
 """Exact algebra: differential = pool effect + weight effect + common residual.

 Common pool = positive-weight contributor intersection. Each metric's weights
 are first restricted/renormalized there; then all use the leading metric's
 restricted weights. This is descriptive, not a proposed projection replacement.
 """
 if any(not finite(metrics.get(m)) for m in terms):return dict(status='MISSING_COMPONENTS'),[]
 observed=math.fsum(a*metrics[m] for m,a in terms.items());base=dict(observed_difference=observed,magnitude_band='WITHIN_ROUNDING_SCALE_NOT_PROVEN' if abs(observed)<=ROUNDING_SCALE else 'ABOVE_ROUNDING_SCALE',rounding_scale=ROUNDING_SCALE,rounding_precision_verified=False)
 parsed={};replayed={};details=[]
 for m in terms:
  p,status=primitive_provenance(provenance.get(m))
  if p is None:return dict(base,status=status,problem_metric=m),[]
  w,v=p;parsed[m]=p;replayed[m]=math.fsum(w[s]*v[s] for s in w)
  if not close(replayed[m],metrics[m]):return dict(base,status='SNAPSHOT_PROVENANCE_REPLAY_MISMATCH',problem_metric=m,replayed_value=replayed[m],snapshot_value=metrics[m]),[]
 common=set.intersection(*(set(w) for w,v in parsed.values()));pools={tuple(sorted(w)) for w,v in parsed.values()};same_pool=len(pools)==1
 all_sources=sorted(set.union(*(set(w) for w,v in parsed.values())))
 for source in all_sources:
  complete=all(finite(v.get(source)) for w,v in parsed.values())
  details.append(dict(source=source,source_equation_complete=complete,source_difference=math.fsum(a*parsed[m][1][source] for m,a in terms.items()) if complete else None,source_values_json=json.dumps({m:parsed[m][1].get(source) for m in terms},sort_keys=True),source_weights_json=json.dumps({m:parsed[m][0].get(source,0) for m in terms},sort_keys=True)))
 if not common:return dict(base,status='NO_COMMON_CONTRIBUTOR_POOL',source_pools_differ=True,common_sources_json='[]'),details
 common=sorted(common);first=next(iter(terms));q=parsed[first][0];total=sum(q[s] for s in common);q={s:q[s]/total for s in common}
 restricted={};within={}
 for m,(w,v) in parsed.items():
  total=sum(w[s] for s in common);restricted[m]={s:w[s]/total for s in common};within[m]=math.fsum(restricted[m][s]*v[s] for s in common)
 pool=math.fsum(a*(replayed[m]-within[m]) for m,a in terms.items())
 weight=math.fsum(a*(within[m]-math.fsum(q[s]*parsed[m][1][s] for s in common)) for m,a in terms.items())
 residual=math.fsum(q[s]*math.fsum(a*parsed[m][1][s] for m,a in terms.items()) for s in common)
 reconstructed=pool+weight+residual
 if not close(observed,reconstructed):raise ValueError('Provenance decomposition failed conservation')
 weight_difference=any(any(abs(w[s]-q[s])>EPS for s in common) for w in restricted.values())
 return dict(base,status='DECOMPOSED',source_pools_differ=not same_pool,common_pool_weights_differ=weight_difference,common_sources_json=json.dumps(common),anchor_weights_json=json.dumps(q,sort_keys=True),source_pool_effect=pool,common_weight_effect=weight,common_source_residual=residual,reconstructed_difference=reconstructed,replay_error=observed-reconstructed),details

EQUATIONS={'hitter':{'H_MINUS_HIT_TYPES':{'H':1,'1B':-1,'2B':-1,'3B':-1,'HR':-1},'PA_MINUS_COMPONENTS':{'PA':1,'AB':-1,'BB':-1,'HBP':-1,'SF':-1,'SH':-1}},'pitcher':{'H_MINUS_HR_BOUND':{'H':1,'HR':-1}}}

def audit_consensus(consensus,provenance,quarantine):
 equations=[];source_rows=[];replay=[];ratios=[];index={}
 for row in provenance:
  if int(row['season'])!=2026:continue
  k=row['player_type'],row['player_id'],row['metric']
  if k in index:raise ValueError('Duplicate metric provenance')
  index[k]=row
 seen=set()
 for r in consensus:
  k=r['player_type'],r['player_id'];role=k[0];metrics=r['metrics']
  if k in seen or r['season']!=2026 or role not in METRICS:raise ValueError('Invalid consensus snapshot domain')
  seen.add(k);identity=dict(season=2026,player_type=role,player_id=k[1],name=r['name'],quarantined=k in quarantine)
  # Replay all primitive metrics, not just the equation selected by old validation.
  for m,value in metrics.items():
   p,status=primitive_provenance(index.get(k+(m,)))
   result=None;difference=None
   if p:
    w,v=p;result=math.fsum(w[s]*v[s] for s in w)
    if finite(value):difference=value-result;status='REPLAY_MATCH' if close(value,result) else 'SNAPSHOT_PROVENANCE_REPLAY_MISMATCH'
    else:status='SNAPSHOT_COMPONENT_MISSING'
   replay.append(dict(**identity,metric=m,snapshot_value=value,replayed_value=result,difference=difference,status=status))
  for name,terms in EQUATIONS[role].items():
   d,details=decompose(metrics,{m:index.get(k+(m,)) for m in terms},terms)
   # PA need not equal its listed components (e.g. omitted CI); positive residual
   # is a budget remainder, not evidence that a count must be changed.
   relation='EQUALITY' if name=='H_MINUS_HIT_TYPES' else 'NONNEGATIVE_BOUND'
   observed=d.get('observed_difference');violation=abs(observed)>EPS if relation=='EQUALITY' and observed is not None else observed < -EPS if observed is not None else None
   equations.append(dict(**identity,equation=name,relation=relation,violates_arithmetic=violation,**d))
   for row in details:source_rows.append(dict(**identity,equation=name,source_record_id=r.get('source_record_ids',{}).get(row['source']),**row))
  def ratio(m,deps,fn):
   value=fn() if all(finite(metrics.get(d)) for d in deps) else None
   published=metrics.get(m);ratios.append(dict(**identity,metric=m,published_value=published,component_derived_value=value,difference=published-value if finite(published) and finite(value) else None,status='MATCH' if close(published,value) else 'REVIEW_DIFFERENCE' if finite(published) and finite(value) else 'MISSING_COMPONENT_OR_ZERO_DENOMINATOR'))
  if role=='hitter':
   ratio('AVG',['H','AB'],lambda:metrics['H']/metrics['AB'] if metrics['AB']>0 else None)
   ratio('OPS',['H','BB','HBP','AB','SF','1B','2B','3B','HR'],lambda:(metrics['H']+metrics['BB']+metrics['HBP'])/(metrics['AB']+metrics['BB']+metrics['HBP']+metrics['SF'])+(metrics['1B']+2*metrics['2B']+3*metrics['3B']+4*metrics['HR'])/metrics['AB'] if metrics['AB']>0 and metrics['AB']+metrics['BB']+metrics['HBP']+metrics['SF']>0 else None)
  else:
   ratio('ERA',['ER','IP'],lambda:9*metrics['ER']/metrics['IP'] if metrics['IP']>0 else None)
   ratio('WHIP',['H','BB','IP'],lambda:(metrics['H']+metrics['BB'])/metrics['IP'] if metrics['IP']>0 else None)
 return equations,source_rows,replay,ratios

def consensus_summary(equations):
 grouped=defaultdict(list)
 for r in equations:
  if r['quarantined']:grouped[r['equation'],r['relation'],r['status'],r.get('magnitude_band','UNAVAILABLE'),r.get('source_pools_differ'),r.get('common_pool_weights_differ'),r['violates_arithmetic']].append(r)
 out=[]
 for key,rows in grouped.items():
  equation,relation,status,band,pool,weights,violates=key;row=dict(equation=equation,relation=relation,status=status,magnitude_band=band,source_pools_differ=pool,common_pool_weights_differ=weights,violates_arithmetic=violates,player_rows=len(rows))
  for n in ['observed_difference','source_pool_effect','common_weight_effect','common_source_residual']:
   values=[abs(r[n]) for r in rows if finite(r.get(n))];row['mean_absolute_'+n]=sum(values)/len(values) if values else None;row['maximum_absolute_'+n]=max(values) if values else None
  out.append(row)
 return out

COHORTS={'hitter':[('ALL_POSITIVE_PA',0,None),('PA_LT100',0,100),('PA_100_299',100,300),('PA_300_499',300,500),('PA_GE500',500,None),('PA_GE100',100,None),('PA_GE300',300,None)],'pitcher':[('ALL_POSITIVE_IP',0,None),('IP_LT20',0,20),('IP_20_39',20,40),('IP_40_99',40,100),('IP_GE100',100,None),('IP_GE20',20,None),('IP_GE40',40,None)]}
GROUPS=[('homegrown_all_eligible',[HOME]),('consensus_all_eligible',[CONS]),('homegrown_consensus_matched',[HOME,CONS]),('Steamer_matched',[HOME,'Steamer']),('OOPSY_matched',[HOME,'OOPSY']),('all_sources_matched',[HOME,CONS,'Steamer','OOPSY'])]

def labels_index(rows,minimum,maximum):
 out={}
 for r in rows:
  k=int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric']
  if not minimum<=k[0]<=maximum or k[1] not in METRICS or mid(k[2])!=k[2] or k in out:raise ValueError('Invalid/duplicate actual label domain')
  if r['eligible'] and (not finite(r['label_value']) or k[3] in METRICS[k[1]] and r['label_value']<0):raise ValueError('Invalid eligible actual label: '+str(k))
  out[k]=r
 return out

def rate_cohorts(comparisons,actual):
 forecasts={};identities={};seen=set()
 for r in comparisons:
  if int(r['season'])!=2026:raise ValueError('Wrong paired forecast season')
  role=r['player_type'];m=r['metric'];pid=r['mlbam_id'];source=r['projection_source'];k=role,pid,m,source
  if k in seen:raise ValueError('Duplicate player comparison key')
  seen.add(k)
  if m not in (['AVG','OPS'] if role=='hitter' else ['ERA','WHIP']):continue
  prediction=None if r['prediction']=='' else float(r['prediction'])
  if prediction is not None and not finite(prediction):raise ValueError('Nonfinite frozen prediction')
  forecasts[k]=prediction;identities[role,pid]=dict(player_id=r.get('player_id'),name=r.get('name'))
 def eligible(pid,role,m):
  r=actual.get((2026,role,pid,m));return r['label_value'] if r and r['eligible'] else None
 scores=[];pairs=[];coverage=[];outliers=[]
 for role,metrics in [('hitter',['AVG','OPS']),('pitcher',['ERA','WHIP'])]:
  exposure='PA' if role=='hitter' else 'IP'
  population=sorted({k[2] for k in actual if k[1]==role})
  for metric in metrics:
   label_pool=[pid for pid in population if finite(eligible(pid,role,metric))]
   for cohort,lo,hi in COHORTS[role]:
    subset=[pid for pid in label_pool if finite(eligible(pid,role,exposure)) and eligible(pid,role,exposure)>0 and eligible(pid,role,exposure)>=lo and (hi is None or eligible(pid,role,exposure)<hi)]
    for group,sources in GROUPS:
     common=[pid for pid in subset if all(finite(forecasts.get((role,pid,metric,s))) for s in sources)]
     member=hashlib.sha256(json.dumps(common).encode('utf-8')).hexdigest()
     for source in sources:
      errors=[forecasts[role,pid,metric,source]-eligible(pid,role,metric) for pid in common];n=len(errors);sse=sum(e*e for e in errors)
      scores.append(dict(season=2026,player_type=role,metric=metric,cohort=cohort,comparison_group=group,projection_source=source,n=n,mae=sum(map(abs,errors))/n if n else None,rmse=math.sqrt(sse/n) if n else None,bias=sum(errors)/n if n else None,squared_error_sum=sse,membership_sha256=member,cohort_basis='ELIGIBLE_ACTUAL_EXPOSURE_RETROSPECTIVE_DIAGNOSTIC_ONLY'))
      coverage.append(dict(player_type=role,metric=metric,cohort=cohort,comparison_group=group,projection_source=source,eligible_rate_labels=len(label_pool),eligible_exposure_cohort=len(subset),missing_or_ineligible_exposure=sum(eligible(pid,role,exposure) is None for pid in label_pool),nonpositive_exposure=sum(finite(eligible(pid,role,exposure)) and eligible(pid,role,exposure)<=0 for pid in label_pool),source_forecasts_in_cohort=sum(finite(forecasts.get((role,pid,metric,source))) for pid in subset),common_pool=n,membership_sha256=member))
      rows=[]
      for pid,error in zip(common,errors):
       row=dict(season=2026,player_type=role,mlbam_id=pid,**identities.get((role,pid),{}),metric=metric,cohort=cohort,comparison_group=group,projection_source=source,prediction=forecasts[role,pid,metric,source],actual=eligible(pid,role,metric),actual_exposure=eligible(pid,role,exposure),exposure_metric=exposure,error=error,absolute_error=abs(error),squared_error=error*error);pairs.append(row);rows.append(row)
      outliers.extend(sorted(rows,key=lambda r:(-r['absolute_error'],r['mlbam_id']))[:10])
 return scores,pairs,coverage,outliers

def missing_universe(actual,training,features,records,catalog,names,raw_owners):
 home={(r['player_type'],r['mlbam_id']) for r in records if r['projection_source']==HOME};population={(k[1],k[2]) for k,r in actual.items() if r['eligible'] and k[3] in METRICS[k[1]]}
 prior=defaultdict(set);evidence=defaultdict(set)
 for k,r in training.items():
  y,role,pid,m=k;prior[role,pid].add(y)
  if r['eligible'] and m in ['G','PA','OUTS'] and finite(r['label_value']) and r['label_value']>0:evidence[role,pid].add(y)
 feature_index={}
 for r in features:
  key=r['player_type'],str(r['mlbam_id'])
  if key in feature_index or int(r['target_season'])!=2026 or int(r['max_source_season'])>=2026 or str(r['source_cutoff'])>='2026-01-01' or any(n.startswith('y_') for n in r):raise ValueError('Feature population chronology/domain failure')
  feature_index[key]=r
 reverse={m:pid for pid,m in catalog.items()};rows=[];reference_start=min((k[0] for k in training),default=None)
 for role,pid in sorted(population-home):
  years=sorted(prior[role,pid]);other='pitcher' if role=='hitter' else 'hitter';other_years=sorted(prior[other,pid]);last=max(years,default=None);recent=[y for y in years if y>=2023];in_features=(role,pid) in feature_index
  if in_features:classification='FEATURE_ROW_PRESENT_FORECAST_MISSING_COVERAGE_REVIEW'
  elif recent:classification='RECENT_PRIOR_ROLE_HISTORY_MISSING_FEATURE_ROW_REVIEW'
  elif years:classification='RETURNER_OUTSIDE_THREE_YEAR_LAG_WINDOW'
  elif other_years or (other,pid) in home:classification='OTHER_ROLE_HISTORY_ONLY_ROLE_TRANSITION_REVIEW'
  else:classification='NO_PRIOR_REFERENCE_HISTORY_COLD_START_CANDIDATE'
  canonical=reverse.get(pid);owners=sorted(raw_owners.get(pid,[]));identity='UNIQUE_CANONICAL_MLBAM' if canonical else 'AMBIGUOUS_OR_NONUNIQUE_WAREHOUSE_MLBAM' if owners else 'MISSING_WAREHOUSE_MLBAM_MAPPING'
  def target(m):
   r=actual.get((2026,role,pid,m));return r['label_value'] if r and r['eligible'] else None
  rows.append(dict(season=2026,player_type=role,mlbam_id=pid,player_id=canonical,name=names.get(canonical) or 'MLBAM '+pid,classification=classification,identity_status=identity,canonical_candidates_json=json.dumps(owners),feature_row_present=in_features,opposite_role_homegrown_present=(other,pid) in home,prior_role_seasons_json=json.dumps(years),other_role_seasons_json=json.dumps(other_years),last_prior_role_season=last,prior_positive_participation_seasons_json=json.dumps(sorted(evidence[role,pid])),prior_reference_window_start=reference_start,actual_PA=target('PA'),actual_IP=target('IP'),actual_G=target('G'),actual_GS=target('GS'),debut_status='NOT_CERTIFIED_NO_COMPLETE_CAREER_OR_DEBUT_REFERENCE',prospect_status='NOT_CLASSIFIED_NO_MINOR_LEAGUE_REFERENCE',disposition='AUDIT_ONLY_NO_PLAYER_OR_FORECAST_ADDED'))
 return rows

def exposure_partition(scores):
 lookup={(r['player_type'],r['metric'],r['comparison_group'],r['projection_source'],r['cohort']):r for r in scores};out=[]
 for key,r in lookup.items():
  role,metric,group,source,cohort=key
  if not cohort.startswith('ALL_'):continue
  bins=[n for n,lo,hi in COHORTS[role] if n in (['PA_LT100','PA_100_299','PA_300_499','PA_GE500'] if role=='hitter' else ['IP_LT20','IP_20_39','IP_40_99','IP_GE100'])]
  subset=[lookup[role,metric,group,source,n] for n in bins]
  if sum(x['n'] for x in subset)!=r['n'] or not close(sum(x['squared_error_sum'] for x in subset),r['squared_error_sum']):raise ValueError('Exposure bins do not partition paired population/errors')
  for x in subset:out.append(dict(player_type=role,metric=metric,comparison_group=group,projection_source=source,cohort=x['cohort'],n=x['n'],all_positive_n=r['n'],player_share=x['n']/r['n'] if r['n'] else None,squared_error_sum=x['squared_error_sum'],all_positive_squared_error_sum=r['squared_error_sum'],squared_error_share=x['squared_error_sum']/r['squared_error_sum'] if r['squared_error_sum']>0 else None))
 return out

DEFAULTS=dict(run='outputs/projection_release_2026_v1_11_1',evaluation='outputs/projection_evaluation_2026_v1_11_2',labels='outputs/training_labels_v1_0',matrix='outputs/standalone_lagged_features_v1_0',warehouse='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb',output='outputs/projection_release_audit_v1_12',backup_root='backups')

def checked_file(root,name,watched):
 root=Path(root).resolve();p=root/name;manifest=load(root/'output_sha256.json')
 if sha(p)!=manifest.get(name):raise ValueError('Manifest mismatch: '+str(p))
 watched[str(p)]=sha(p);watched[str(root/'output_sha256.json')]=sha(root/'output_sha256.json');return p

def build(a):
 run,ev,labels,matrix=map(lambda p:Path(p).resolve(),[a.run,a.evaluation,a.labels,a.matrix]);watched=verify(run);watched.update(verify(ev));release=load(run/'projection_release_report.json');evaluation=load(ev/'projection_evaluation_report.json')
 if release['version']!='1.11.1' or evaluation['projection_release_version']!='1.11.1' or evaluation['version']!='1.11.2' or not evaluation['previously_reviewed']:raise ValueError('Require frozen v1.11.1 projections and disclosed v1.11.2 evaluation')
 if release['models_fitted'] or release['choices_changed'] or evaluation['models_fitted'] or evaluation['selection_changed'] or evaluation['forecasts_modified']:raise ValueError('Require unchanged frozen source projections and choices')
 bindings=load(ev/'input_hashes.json');run_bindings=load(run/'input_hashes.json')
 for name in ['coherent_projection_records.json','projection_release_report.json']:
  if bindings.get(str(run/name))!=sha(run/name):raise ValueError('Evaluation/release binding mismatch')
 for name,h in load(run/'forecast_freeze.json').items():
  path=(run/name).resolve()
  if run not in path.parents or sha(path)!=h:raise ValueError('Forecast freeze mismatch')
 label_report=checked_file(labels,'label_build_report.json',watched)
 if load(label_report)['reference_sha256']!=release['label_reference_sha256']:raise ValueError('Different actuals reference')
 training_path=checked_file(labels,'training_labels.parquet',watched);actual_path=checked_file(labels,'holdout_labels.parquet',watched);feature_path=checked_file(matrix,'holdout_features.parquet',watched)
 if run_bindings.get(str(training_path))!=sha(training_path) or run_bindings.get(str(feature_path))!=sha(feature_path) or bindings.get(str(actual_path))!=sha(actual_path):raise ValueError('Historical, feature or evaluation source binding mismatch')
 catalog,names,w=canonical_catalog(a.warehouse);watched.update(w)
 if sha(a.warehouse)!=release['warehouse_sha256']:raise ValueError('Warehouse differs from projection release')
 with duckdb.connect(str(Path(a.warehouse).resolve()),read_only=True) as db:
  raw_owners=defaultdict(set)
  for pid,ns,external in db.execute('SELECT player_id,namespace,external_id FROM player_id_crosswalk').fetchall():
   if str(ns).lower()=='mlbam' and mid(external):raw_owners[mid(external)].add(str(pid))
 out,backups,stage=start(a.output,a.backup_root,[run,ev,labels,matrix,a.warehouse])
 try:
  print('Auditing original consensus components and replaying contributor weights...',flush=True)
  consensus=[]
  for role in METRICS:consensus += [r for r in load(run/f'source_{role}_consensus.json') if int(r['season'])==2026]
  quarantine={(r['player_type'],r['player_id']) for r in csvrows(run/'consensus_component_exceptions.csv')}
  if len(quarantine)!=release['quarantined_consensus_rows'] or len(quarantine)!=evaluation['consensus_quarantined_rows'] or len(consensus)!=release['consensus_source_rows']:raise ValueError('Consensus population/quarantine count mismatch')
  eq,src,replay,ratios=audit_consensus(consensus,csvrows(run/'source_metric_provenance.csv'),quarantine)
  print('Scoring frozen rate forecasts in fixed actual-exposure cohorts...',flush=True)
  actual=labels_index(table(actual_path),2026,2026);training=labels_index(table(training_path),2015,2025)
  records=load(run/'coherent_projection_records.json');frozen={(r['player_type'],r['mlbam_id'],m,r['projection_source']):r.get(m) for r in records if r['mlbam_id'] for m in METRICS[r['player_type']]}
  comparisons=[]
  stream=(ev/'player_comparisons.csv').open(encoding='utf-8-sig',newline='')
  with stream:
   for r in csv.DictReader(stream):
    if r['projection_source'] in [HOME,CONS]:
     k=r['player_type'],r['mlbam_id'],r['metric'],r['projection_source'];value=None if r['prediction']=='' else float(r['prediction'])
     if k not in frozen or (value is None)!=(frozen[k] is None) or value is not None and not close(value,frozen[k]):raise ValueError('Paired forecast differs from frozen released projection')
    if r['metric'] in ['AVG','OPS','ERA','WHIP']:comparisons.append(r)
  scores,pairs,coverage,outliers=rate_cohorts(comparisons,actual);partition=exposure_partition(scores)
  print('Reviewing absent actual participants against historical reference and feature population...',flush=True)
  missing=missing_universe(actual,training,table(feature_path),records,catalog,names,raw_owners);expected={(r['player_type'],r['mlbam_id']) for r in csvrows(ev/'actual_participants_without_homegrown.csv')}
  if {(r['player_type'],r['mlbam_id']) for r in missing}!=expected or len(missing)!=evaluation['actual_participants_without_homegrown']:raise ValueError('Missing-universe population does not reproduce evaluation')
  for name,rows in [('consensus_driver_summary.csv',consensus_summary(eq)),('consensus_equation_audit.csv',eq),('consensus_source_residuals.csv',src),('consensus_primitive_replay.csv',replay),('consensus_ratio_audit.csv',ratios),('exposure_error_partition.csv',partition),('exposure_cohort_scores.csv',scores),('exposure_cohort_pairs.csv',pairs),('exposure_cohort_coverage.csv',coverage),('exposure_cohort_outliers.csv',outliers),('missing_universe_review.csv',missing)]:emit(stage,name,rows)
  report=dict(version=VERSION,status='READ_ONLY_DIAGNOSTICS_REVIEW_REQUIRED',evaluation_season=2026,previously_reviewed=True,models_fitted=False,selection_changed=False,forecasts_modified=False,consensus_reconciled=False,inputs_unchanged=True,consensus_rows=len(consensus),consensus_quarantined_rows=len(quarantine),provenance_replay_statuses=dict(Counter(r['status'] for r in replay)),quarantined_equation_statuses=dict(Counter(r['equation']+':'+r['status']+':'+r.get('magnitude_band','UNAVAILABLE') for r in eq if r['quarantined'])),exposure_score_rows=len(scores),missing_actual_participants=len(missing),missing_classifications=dict(Counter(r['classification'] for r in missing)),missing_identity_statuses=dict(Counter(r['identity_status'] for r in missing)),limitations=['The 0.001-stat magnitude band describes scale only; raw export precision is not certified and no tolerance or projection is changed.','Contributor decomposition uses the common positive-weight pool and leading-component weights; it is algebraic, not a repair or causal attribution.','Positive PA residuals can reflect omitted PA events; they are not automatically errors.','Cohorts use eligible actual PA/IP only as retrospective diagnostics, never predictors or selection gates. Cohort scores cannot be averaged without their membership counts.','Missing-history labels describe the frozen reference window, not certified MLB debuts; identity status and other-role history are reported separately.','No minors, injuries, preseason rosters or birth-date/debut service is inferred. No missing participant receives a projection.','2026 is previously reviewed evaluation data and cannot select new components.'])
  dump(stage/'projection_audit_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in DEFAULTS.items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(build(p.parse_args()),indent=2))
if __name__=='__main__':main()
