"""Read-only historical diagnostics and a frozen development contract; no fitting."""
import argparse,csv,json,math,hashlib,shutil
from pathlib import Path
from collections import defaultdict,Counter
from standalone_io_v1_0 import load,dump,sha,write,table,start,finish
from standalone_combined_v1_4 import METRICS,coherent,near

VERSION='1.16.0'
def finite(x):return isinstance(x,(float,int)) and not isinstance(x,bool) and math.isfinite(x)
def emit(p,rows):
 fields=list(dict.fromkeys(k for r in rows for k in r)) or ['status'];write(p,rows,fields)
def checked(root,name,watched):
 root=Path(root).resolve();manifest=load(root/'output_sha256.json');p=(root/name).resolve()
 if root not in p.parents or name not in manifest or sha(p)!=manifest[name]:raise ValueError('Frozen file hash/path failure: '+str(p))
 watched[str(root/'output_sha256.json')]=sha(root/'output_sha256.json');watched[str(p)]=sha(p);return p

def forecasts(path,methods):
 bank={};seen=set()
 with Path(path).open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   year=int(r['season']);role=r['player_type'];pid=str(r['mlbam_id']);m=r['metric'];method=r['method']
   if not 2016<=year<=2025:raise ValueError('Historical forecast contains target/future year')
   if role not in METRICS or not pid.isdigit() or int(pid)<=0 or m not in METRICS[role]:raise ValueError('Invalid historical forecast key')
   key=year,role,pid,m,method
   if key in seen:raise ValueError('Duplicate forecast key')
   seen.add(key)
   v=float(r['prediction']) if r['prediction']!='' else None
   if v is not None and (not finite(v) or v<0):raise ValueError('Invalid prediction')
   if method not in methods:continue
   bank[year,role,pid,m,methods[method]]=v
 return bank

def label_index(path):
 bank={};seen=set();excluded=Counter()
 for r in table(path):
  y=int(r['season']);role=r['player_type'];pid=str(r['mlbam_id']);m=r['metric'];key=y,role,pid,m
  if not 2015<=y<=2025 or role not in METRICS or not pid.isdigit() or int(pid)<=0 or key in seen:raise ValueError('Duplicate/invalid historical label')
  seen.add(key)
  if m not in METRICS[role] and m not in ['G','GS']:continue
  if r['eligible'] not in [True,False,0,1]:raise ValueError('Invalid eligibility flag')
  if not r['eligible']:excluded[role,m]+=1;continue
  v=r['label_value']
  if not finite(v) or v<0:raise ValueError('Invalid eligible scored label')
  bank[key]=float(v)
 return bank,excluded

def feature_index(path,allow):
 seen=set();rows=[]
 if len(allow)!=len(set(allow)) or any(n.startswith('y_') for n in allow):raise ValueError('Target leakage in feature allowlist')
 for r in table(path):
  y=int(r['target_season']);role=r['player_type'];pid=str(r['mlbam_id']);key=y,role,pid
  if not 2016<=y<=2025 or role not in METRICS or key in seen or not pid.isdigit() or int(pid)<=0:raise ValueError('Invalid/duplicate historical feature key')
  if int(r['max_source_season'])>=y or str(r['source_cutoff'])>=f'{y}-01-01':raise ValueError('Future feature chronology')
  for lag in [1,2,3]:
   if r.get('source_season_lag'+str(lag)) not in [None,y-lag]:raise ValueError('Incorrect lag year')
  if any(n not in r for n in allow):raise ValueError('Missing allowlisted feature')
  seen.add(key);rows.append(r)
 return rows,{(int(r['target_season']),r['player_type'],str(r['mlbam_id'])):r for r in rows}

def cohorts(key,features,actual):
 y,role,pid=key;r=features.get(key,{})
 age=r.get('age_at_target_estimate');hist=r.get('history_seasons');g=r.get('x_actual_lag1_G');gs=r.get('x_actual_lag1_GS');prior='UNKNOWN'
 if role=='pitcher' and finite(g) and finite(gs) and g>0 and 0<=gs<=g:prior='STARTER' if gs/g>=.5 else 'RELIEVER' if gs/g<=.1 else 'SWING'
 agebin='UNKNOWN' if not finite(age) else 'LT25' if age<25 else '25_29' if age<30 else '30_34' if age<35 else 'GE35'
 history='UNKNOWN' if not finite(hist) else 'LE1' if hist<=1 else '2' if hist<3 else 'GE3'
 exposure=actual.get(key+('PA' if role=='hitter' else 'OUTS',));exposure=exposure/3 if exposure is not None and role=='pitcher' else exposure
 if exposure is None:eb='UNKNOWN'
 elif exposure==0:eb='ZERO'
 elif role=='hitter':eb='LT100_PA' if exposure<100 else '100_299_PA' if exposure<300 else 'GE300_PA'
 else:eb='LT20_IP' if exposure<20 else '20_39_IP' if exposure<40 else '40_99_IP' if exposure<100 else 'GE100_IP'
 return [('ALL','ALL'),('AGE',agebin),('HISTORY',history),('PRIOR_ROLE',prior if role=='pitcher' else 'NOT_APPLICABLE'),('ACTUAL_EXPOSURE',eb)]

def score(bank,actual,features):
 groups=defaultdict(list);outliers=[];coverage=[];methods=sorted({k[4] for k in bank});keys=sorted({k[:4] for k in bank});pairs=defaultdict(list)
 for key in keys:
  y,role,pid,m=key;a=actual.get(key)
  available={method:bank.get(key+(method,)) for method in methods};status='MISSING_OR_EXCLUDED_LABEL' if a is None else 'ELIGIBLE_LABEL'
  coverage.append(dict(season=y,player_type=role,mlbam_id=pid,metric=m,status=status,available_methods=json.dumps([n for n,v in available.items() if finite(v)])))
  if a is None:continue
  if m in ['AVG','OBP','SLG','OPS'] and actual.get((y,role,pid,'AB'),0)<=0:continue
  if m in ['ERA','WHIP'] and actual.get((y,role,pid,'OUTS'),0)<=0:continue
  for method,v in available.items():
   if not finite(v):continue
   e=v-a
   for dim,cohort in cohorts((y,role,pid),features,actual):groups[y,role,m,dim,cohort,method,'INDIVIDUAL_ELIGIBLE'].append((pid,e))
   outliers.append(dict(season=y,player_type=role,mlbam_id=pid,metric=m,method=method,prediction=v,actual=a,error=e,absolute_error=abs(e)))
  # Each comparator gets its own identical eligible pool, never compares disjoint scores.
  if finite(available.get('accepted_v1_5')):
   for comparator in methods:
    if comparator=='accepted_v1_5' or not finite(available[comparator]):continue
    group='accepted_vs_'+comparator
    for method in ['accepted_v1_5',comparator]:
     for dim,cohort in cohorts((y,role,pid),features,actual):groups[y,role,m,dim,cohort,method,group].append((pid,available[method]-a))
 scores=[]
 for (y,role,m,dim,cohort,method,group),rr in sorted(groups.items()):
  n=len(rr);err=[e for pid,e in rr];member=hashlib.sha256(json.dumps(sorted(pid for pid,e in rr)).encode()).hexdigest();scores.append(dict(season=y,player_type=role,metric=m,cohort_dimension=dim,cohort=cohort,method=method,comparison_group=group,n=n,mae=sum(abs(e) for e in err)/n,rmse=math.sqrt(sum(e*e for e in err)/n),bias=sum(err)/n,membership_sha256=member,transition_2021_retained=y==2021,short_season_2020=y==2020))
 # Largest misses are retained separately for every season/role/metric/method, no mixed-unit ranking.
 selected=[];buckets=defaultdict(list)
 for r in outliers:buckets[r['season'],r['player_type'],r['metric'],r['method']].append(r)
 for rr in buckets.values():selected.extend(sorted(rr,key=lambda r:(-r['absolute_error'],r['mlbam_id']))[:20])
 return scores,coverage,selected

def comparison_summary(scores):
 groups=defaultdict(list)
 for r in scores:
  if r['comparison_group']=='INDIVIDUAL_ELIGIBLE':continue
  groups[r['player_type'],r['metric'],r['cohort_dimension'],r['cohort'],r['method'],r['comparison_group']].append(r)
 out=[]
 for (role,m,dim,cohort,method,group),rr in sorted(groups.items()):
  n=sum(r['n'] for r in rr);out.append(dict(player_type=role,metric=m,cohort_dimension=dim,cohort=cohort,method=method,comparison_group=group,folds=len(rr),seasons=json.dumps(sorted(r['season'] for r in rr)),n=n,pooled_rmse=math.sqrt(sum(r['rmse']**2*r['n'] for r in rr)/n),pooled_mae=sum(r['mae']*r['n'] for r in rr)/n,equal_season_rmse=math.sqrt(sum(r['rmse']**2 for r in rr)/len(rr)),equal_season_mae=sum(r['mae'] for r in rr)/len(rr),selection_performed=False,transition_2021_included=any(r['season']==2021 for r in rr)))
 return out


def measurement_audit(rows,allow):
 out=[]
 for (y,role),rr in __import__('itertools').groupby(sorted(rows,key=lambda r:(r['target_season'],r['player_type'])),key=lambda r:(r['target_season'],r['player_type'])):
  rr=list(rr)
  for n in allow:
   if not n.startswith(('x_statcast_lag','tracking_era_lag')):continue
   vals=[r.get(n) for r in rr];valid=[v for v in vals if finite(v)];categories=[v for v in vals if n.startswith('tracking_era') and isinstance(v,str) and v.strip()];available=len(valid)+len(categories);out.append(dict(target_season=y,player_type=role,feature=n,rows=len(rr),finite_rows=len(valid),categorical_rows=len(categories),available_rows=available,missing_or_unusable_rows=len(rr)-available,finite_fraction=len(valid)/len(rr),available_fraction=available/len(rr),categories_json=json.dumps(sorted(set(categories))),minimum=min(valid) if valid else None,maximum=max(valid) if valid else None,scope='MATRIX_AVAILABILITY_NOT_FOLD_FIT_USAGE_OR_PHYSICAL_COMPARABILITY'))
 return out

def model_inventory(obj,artifact,path='$'):
 out=[]
 if isinstance(obj,dict):
  if any(int(y)>=2026 for y in obj.get('fit_target_seasons',[])):raise ValueError('Model trained on 2026/future outcomes')
  state=obj.get('preprocessing')
  if isinstance(state,dict):
   years=obj.get('fit_target_seasons',[])
   if any(int(y)>=2026 for y in years):raise ValueError('Model trained on 2026/future outcomes')
   for kind in ['numeric','categorical','dropped']:
    for n in state.get(kind,[]):
     if n.startswith('y_'):raise ValueError('Outcome predictor in model preprocessing')
     out.append(dict(artifact=artifact,model_path=path,target=obj.get('target'),feature=n,feature_family='STATCAST' if n.startswith('x_statcast') else 'ACTUAL_HISTORY' if n.startswith('x_actual') else 'ERA' if n.startswith('tracking_era') else 'CONTEXT_OR_DERIVED',preprocessing_status=kind,n_fit=obj.get('n_fit'),fit_target_seasons=json.dumps(years),scope='FROZEN_MODEL_INVENTORY_NOT_PROOF_COMPONENT_WAS_ADOPTED'))
  for k,v in obj.items():out.extend(model_inventory(v,artifact,path+'.'+k))
 elif isinstance(obj,list):
  for i,v in enumerate(obj):out.extend(model_inventory(v,artifact,path+f'[{i}]'))
 return out

def workload_context(vectors,features,actual):
 out=[]
 for key,v in sorted(vectors.items()):
  y,role,pid=key;r=features.get(key,{})
  metric='PA' if role=='hitter' else 'OUTS';prior=[r.get(f'x_actual_lag{lag}_'+metric) for lag in [1,2,3]];older=[x for x in prior[1:] if finite(x) and x>0];recent=prior[0]
  pattern='RECENT_UNKNOWN_WITH_OLDER_HISTORY' if recent is None and older else 'RECENT_ZERO_WITH_OLDER_POSITIVE' if recent==0 and older else 'LOWER_RECENT_OBSERVED_WORKLOAD' if finite(recent) and older and recent<.5*max(older) else 'OTHER_OR_INSUFFICIENT_HISTORY'
  forecast=v.get(metric);truth=actual.get(key+(metric,));actual_g=actual.get(key+('G',));actual_gs=actual.get(key+('GS',));target_role='UNKNOWN'
  if role=='pitcher' and finite(actual_g) and finite(actual_gs) and actual_g>0 and 0<=actual_gs<=actual_g:target_role='STARTER' if actual_gs/actual_g>=.5 else 'RELIEVER' if actual_gs/actual_g<=.1 else 'SWING'
  out.append(dict(season=y,player_type=role,mlbam_id=pid,metric=metric,prediction=forecast,eligible_actual=truth,error=forecast-truth if finite(forecast) and truth is not None else None,prior_lag1=recent,prior_lag2=prior[1],prior_lag3=prior[2],observed_change=truth-recent if truth is not None and finite(recent) else None,predicted_change=forecast-recent if finite(forecast) and finite(recent) else None,history_pattern=pattern,prior_role=dict(cohorts(key,features,actual))['PRIOR_ROLE'],actual_role_diagnostic_only=target_role,prior_2020_observed_workload=any(r.get('source_season_lag'+str(lag))==2020 for lag in [1,2,3]),scope='RETROSPECTIVE_DIAGNOSTIC_ONLY; raw observed history, not normalized or causal injury evidence'))
 return out


CONTRACT=dict(version=VERSION,status='FROZEN_DEVELOPMENT_PLAN_NOT_FITTED',accepted_source='HOMEGROWN_V1_5_ACCEPTED',fit_new_models=False,selection_years='historical origins through 2025 only; earlier-origin preprocessing and validation',evaluation_2026='Previously reviewed disclosed evaluation only; separate later command, never candidate selection',comparison_design=['fixed accepted workload + standard-stat skill baseline','same workload and estimator + hitter Statcast features','same workload and estimator + pitcher Statcast features'],controls=['same eligible metric-specific paired pools','same fold-specific preprocessing and sample-size controls','compare skill rates before coherent count forecasts','2020 and 2021 reported without removing unfavorable seasons','missing measurements stay missing; era/coverage flags do not certify comparability','external projections benchmark only, never homegrown predictors','no adoption inferred from inventory or correlation'],coverage_branch='Separate dated minor/overseas/availability populations; no actual-participant-driven inclusion',draft_tool='No positional replacement, SGP, auction values, roster or ADP inputs')

def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 print('Verifying accepted release and historical source bindings...',flush=True)
 watched={};release=Path(a.release).resolve();run=Path(a.accepted).resolve();matrix=Path(a.matrix).resolve();labels=Path(a.labels).resolve();baseline=Path(a.baseline).resolve()
 reportpath=checked(release,'projection_release_report.json',watched);release_report=load(reportpath)
 if release_report.get('models_fitted') or release_report.get('choices_changed'):raise ValueError('Require accepted frozen release')
 bindings=load(checked(release,'input_hashes.json',watched));historical=checked(run,'historical_forecasts.csv',watched)
 if bindings.get(str(historical))!=sha(historical):raise ValueError('Accepted historical forecast is not bound to release')
 provenance=checked(release,'component_provenance.csv',watched)
 names={}
 for role in ['hitter','pitcher']:
  namefile=checked(release,f'homegrown_{role}s_2026.csv',watched)
  with namefile.open(encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    if r.get('mlbam_id') and r.get('name'):names[role,str(r['mlbam_id'])]=r['name']
 train=checked(matrix,'training_matrix.parquet',watched);schema=checked(matrix,'feature_schema.json',watched);lp=checked(labels,'training_labels.parquet',watched);lr=load(checked(labels,'label_build_report.json',watched))
 if lr['reference_sha256']!=release_report['label_reference_sha256'] or bindings.get(str(train))!=sha(train):raise ValueError('Historical matrix/reference differs from accepted release')
 frozen=load(checked(run,'frozen_models.json',watched))
 if frozen.get('training_labels_sha256')!=sha(lp):raise ValueError('Historical label file differs from accepted model')
 print('Reading historical matrix and eligible training labels only...',flush=True)
 allow=load(schema)['predictor_allowlist'];rows,features=feature_index(train,allow);actual,excluded=label_index(lp)
 bank=forecasts(historical,{'selected_v1_5':'accepted_v1_5'});bp=checked(baseline,'historical_forecasts.csv',watched);base=forecasts(bp,{'historical_baseline':'standard_history_baseline_v1_0','selected_standalone':'selected_baseline_v1_0'})
 if not bank:raise ValueError('No accepted historical forecasts')
 if set(bank)&set(base):raise ValueError('Forecast method collision')
 bank.update(base)
 # Verify complete accepted vectors with existing coherence rules; never repair them here.
 vectors=defaultdict(dict)
 for (y,role,pid,m,method),v in bank.items():
  if method=='accepted_v1_5':vectors[y,role,pid][m]=v
 for (y,role,pid),v in vectors.items():
  if set(v)!=set(METRICS[role]):raise ValueError('Incomplete accepted forecast vector')
  coherent(role,v)
 inventory=[];policies=[]
 for directory in [baseline,run]+[Path(p).resolve() for p in a.additional_models]:
  mp=checked(directory,'frozen_models.json',watched);obj=load(mp);inventory.extend(model_inventory(obj,str(mp)));policies.append(dict(artifact=str(mp),artifact_sha256=sha(mp),declared_controls={n:obj[n] for n in ['config','settings','target_specs','choices','final_choice','final_role_choice','final_workload_choice'] if n in obj}))
 print(f'Diagnosing {len(vectors):,} accepted player-seasons; scoring identical eligible comparison pools...',flush=True)
 scores,coverage,outliers=score(bank,actual,features)
 for r in outliers:r['name_display_only_from_frozen_release']=names.get((r['player_type'],r['mlbam_id']))
 component_rows=[]
 with provenance.open(encoding='utf-8-sig',newline='') as f:
  counts=Counter((r['player_type'],r['metric'],r['component_origin'],r['selected_method']) for r in csv.DictReader(f) if r['projection_source']=='HOMEGROWN_V1_5_ACCEPTED')
 for (role,m,origin,method),n in sorted(counts.items()):component_rows.append(dict(player_type=role,metric=m,component_origin=origin,selected_method=method,player_rows=n,scope='ACCEPTED_2026_RELEASE_COMPONENT_PROVENANCE'))
 print('Writing predictor, measurement, error and development-baseline reports...',flush=True)
 out,backups,stage=start(a.output,a.backup_root,[release,run,matrix,labels,baseline]+[Path(p).resolve() for p in a.additional_models])
 try:
  for name,rr in [('historical_scores',scores),('historical_comparison_summary',comparison_summary(scores)),('forecast_label_coverage',coverage),('historical_outliers',outliers),('workload_history_context',workload_context(vectors,features,actual)),('statcast_measurement_availability',measurement_audit(rows,allow)),('model_predictor_inventory',inventory),('accepted_component_inventory',component_rows),('transition_2021',[r for r in scores if r['season']==2021]),('label_exclusions',[dict(player_type=k[0],metric=k[1],excluded_rows=n) for k,n in sorted(excluded.items())])]:emit(stage/(name+'.csv'),rr)
  dump(stage/'development_contract.json',CONTRACT);dump(stage/'frozen_controls_and_choices.json',policies)
  report=dict(version=VERSION,status='HISTORICAL_DIAGNOSTIC_BASELINE_BUILT_NO_MODEL_SELECTION',historical_seasons=sorted({k[0] for k in bank}),accepted_player_seasons=len(vectors),score_rows=len(scores),predictor_inventory_rows=len(inventory),component_inventory_rows=len(component_rows),models_fitted=False,accepted_forecasts_modified=False,evaluation_outcomes_read=False,external_projections_used=False,inputs_unchanged=True,development_contract_sha256=sha(stage/'development_contract.json'),limitations=['Historical forecast scores inherit original fold choices; this build does not refit or independently replay every historical selection gate.','Comparison with v1.0 historical baseline is a development reference, not an isolated test of Statcast value: workloads and other components also differ.','Final-model retained preprocessing names are not proof of adopted-component usage or causal/incremental predictive value. Inspect accepted component provenance alongside inventory.','Measurement availability is in historical target matrices and reflects inherited source-lag/sample masking; it does not certify era comparability.','Age, prior role and history cohorts use prior-feature context. Actual exposure cohorts use target outcomes only for retrospective diagnostics.','Labels absent or excluded remain unknown, never zero or reconstructed. Rate diagnostics additionally require eligible positive AB/OUTS.','2026 outcome files are not opened. Prior sources were retrieved retrospectively, not independently archived preseason vintages.'])
  dump(stage/'standalone_diagnostic_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 defaults=dict(release='outputs/projection_release_2026_v1_11_1',accepted='outputs/standalone_holds_attribution_v1_5',matrix='outputs/standalone_lagged_features_v1_0',labels='outputs/training_labels_v1_0',baseline='outputs/standalone_baselines_v1_0',output='outputs/standalone_diagnostics_v1_16',backup_root='backups')
 for n,v in defaults.items():p.add_argument('--'+n.replace('_','-'),default=v)
 p.add_argument('--additional-models',nargs='*',default=['outputs/standalone_opportunity_v1_1','outputs/standalone_role_workload_v1_2','outputs/standalone_workload_experiments_v1_3']);return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
