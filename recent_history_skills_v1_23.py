"""Recent-history weighting and expanded skill groups. 2026 labels are not read."""
import argparse,csv,json,shutil
from pathlib import Path
from collections import defaultdict,Counter
from standalone_io_v1_0 import load,dump,sha,start,finish
from recent_skill_core_v1_23 import *
from recent_skill_inputs_v1_23 import *

def bound(bindings,paths):
 for p in paths:
  if bindings.get(str(p))!=sha(p):raise ValueError('Frozen source binding differs: '+str(p))
def read_reference(root,n,watched):
 p=checked(root,n,watched);freeze=load(checked(root,'forecast_freeze.json',watched))
 if portable(freeze).get(n)!=sha(p):raise ValueError('Reference forecast freeze differs')
 return p
def merge(left,right):
 for k,v in right.items():
  if k in left and left[k]!=v:raise ValueError('Inconsistent historical/holdout source feature')
  left[k]=v
 return left
def evidence(year,role,accepted,vectors,support,actual,context):
 groups=defaultdict(list);methods=['accepted_frozen']+ARMS
 for k,a in accepted.items():
  if k[0]!=year or k[1]!=role:continue
  den='AB' if role=='hitter' else 'OUTS'
  if actual.get(k+(den,),0)<(30 if role=='hitter' else 90):continue
  if any(not finite(actual.get(k+(m,))) for m in GATE_METRICS[role]):continue
  # Gate comparisons use all six long-history fitted arms on the same bundle pool.
  if not all(support.get(k+(arm,),False) for arm in ARMS if not arm.startswith('bat_')):continue
  for cohort in ['ALL',history_class(context[k])]:groups[cohort].append(k)
 rows=[]
 for cohort,kk in groups.items():
  for m in GATE_METRICS[role]:
   errors={}
   for method in methods:
    ee=[vectors[k,method][m]-actual[k+(m,)] for k in kk];errors[method]=dict(mse=sum(e*e for e in ee)/len(ee),mae=sum(abs(e) for e in ee)/len(ee))
   rows.append(dict(season=year,player_type=role,cohort=cohort,metric=m,n=len(kk),membership_sha256=member(kk),supported={arm:True for arm in methods if not arm.startswith('bat_')},errors=errors))
 return rows
def score_vectors(vectors,actual,context,support=None,include_player=False):
 groups=defaultdict(list);coverage=[];player=[]
 keys=sorted({k for k,method in vectors});methods=sorted({method for k,method in vectors})
 for k in keys:
  role=k[1];den=actual.get(k+(('PA' if role=='hitter' else 'OUTS'),));exp='UNKNOWN' if den is None else 'ZERO' if den==0 else ('LT100_PA' if den<100 else '100_299_PA' if den<300 else 'GE300_PA') if role=='hitter' else ('LT20_IP' if den<60 else '20_99_IP' if den<300 else 'GE100_IP')
  for m in METRICS[role]:
   truth=actual.get(k+(m,));ratio_metric=m in ['AVG','OBP','SLG','OPS','ERA','WHIP'];d=actual.get(k+(('AB' if role=='hitter' else 'OUTS'),))
   for method in methods if include_player else []:
    v=vectors.get((k,method),{}).get(m);ok=finite(truth) and finite(v) and (not ratio_metric or finite(d) and d>0)
    player.append(dict(season=k[0],player_type=role,mlbam_id=k[2],metric=m,method=method,prediction=v,actual=truth,error=v-truth if ok else None,status='SCORED' if ok else 'MISSING_OR_INELIGIBLE_COMPONENT',exposure_cohort=exp,history_cohort=history_class(context.get(k,{}))))
   pairs=[('accepted_frozen',method) for method in methods if method!='accepted_frozen']+[(s.replace('expanded_','standard_'),s) for s in methods if s.startswith('expanded_')]+[('bat_control_recent','bat_recent_exploratory')]
   for reference,method in pairs:
    pair=[reference,method]
    if any(n not in methods for n in pair) or support is not None and any(n!='accepted_frozen' and not support.get(k+(n,),False) for n in pair):continue
    if not finite(truth) or ratio_metric and (not finite(d) or d<=0) or not all(finite(vectors.get((k,n),{}).get(m)) for n in pair):continue
    for dimension,cohort in [('ALL','ALL'),('HISTORY',history_class(context.get(k,{}))),('ACTUAL_EXPOSURE',exp)]:
     for arm in pair:groups[k[0],role,m,dimension,cohort,reference+'_vs_'+method,arm].append((k[2],vectors[k,arm][m]-truth))
 rows=[]
 for (year,role,m,dim,cohort,group,method),rr in sorted(groups.items()):
  ee=[e for pid,e in rr];n=len(ee);rows.append(dict(season=year,player_type=role,metric=m,cohort_dimension=dim,cohort=cohort,comparison_group=group,method=method,n=n,mae=sum(map(abs,ee))/n,rmse=(sum(e*e for e in ee)/n)**.5,bias=sum(ee)/n,membership_sha256=member([pid for pid,e in rr]),transition_2021_retained=year==2021))
 return rows,player
def rate_scores(rates,actual,context):
 groups=defaultdict(list)
 for r in rates:
  k=r['season'],r['player_type'],r['mlbam_id'];den=actual.get(k+(r['denominator'],));n=actual.get(k+(r['metric'],));pred=r['prediction'];base=r['accepted_rate']
  if not finite(den) or den<=0 or not finite(n) or not finite(pred) or not finite(base):continue
  exposure=('LT30_AB' if den<30 else '30_299_AB' if den<300 else 'GE300_AB') if k[1]=='hitter' else ('LT30_IP' if den<90 else '30_99_IP' if den<300 else 'GE100_IP')
  for dim,cohort in [('ALL','ALL'),('HISTORY',history_class(context[k])),('ACTUAL_EXPOSURE',exposure)]:
   for method,value in [('accepted_frozen',base),(r['method'],pred)]:groups[k[0],k[1],r['metric']+'_per_'+r['denominator'],dim,cohort,r['method'],method].append((k[2],value-n/den))
 return [dict(season=y,player_type=role,metric=m,cohort_dimension=dim,cohort=cohort,comparison_group='accepted_rate_vs_'+arm,method=method,n=len(rr),mae=sum(abs(e) for pid,e in rr)/len(rr),rmse=(sum(e*e for pid,e in rr)/len(rr))**.5,bias=sum(e for pid,e in rr)/len(rr),membership_sha256=member([pid for pid,e in rr])) for (y,role,m,dim,cohort,arm,method),rr in sorted(groups.items())]
def append_rows(path,rows):
 if not rows:return
 exists=path.exists()
 with path.open('a' if exists else 'w',encoding='utf-8',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));
  if not exists:w.writeheader()
  w.writerows(rows)
def summarize(scores):
 groups=defaultdict(list)
 for r in scores:groups[tuple(r[n] for n in ['player_type','metric','cohort_dimension','cohort','comparison_group','method'])].append(r)
 return [dict(player_type=role,metric=m,cohort_dimension=dim,cohort=cohort,comparison_group=g,method=method,seasons=json.dumps(sorted(r['season'] for r in rr)),folds=len(rr),n=sum(r['n'] for r in rr),equal_season_rmse=(sum(r['rmse']**2 for r in rr)/len(rr))**.5,equal_season_mae=sum(r['mae'] for r in rr)/len(rr),transition_2021_included=any(r['season']==2021 for r in rr)) for (role,m,dim,cohort,g,method),rr in sorted(groups.items())]
def forecast_origin(origin,accepted,features,actual,cache,c):
 vectors={(k,'accepted_frozen'):v for k,v in accepted.items() if k[0]==origin};support={};models={};rate_rows=[];fit_rows=[];ledger=[]
 for role in METRICS:
  train=[k for k in accepted if k[1]==role and k[0]<origin];test=[k for k in accepted if k[1]==role and k[0]==origin]
  for arm in ARMS:
   component=defaultdict(dict);statuses=[]
   for m in TARGETS[role]:
    model,preds=fit_residual(train,test,cache[arm],accepted,actual,role,m,origin,c,bat_only=arm.startswith('bat_'));models[role,arm,m]=model;statuses.append(model['status'])
    fit_rows.append(dict(origin=origin,player_type=role,method=arm,metric=m,n_fit=model['n_fit'],fit_target_seasons=json.dumps(model['fit_target_seasons']),fit_membership_sha256=model['fit_membership_sha256'],status=model['status']))
    for k,v in preds.items():component[k][m]=v;rate_rows.append(dict(season=origin,player_type=role,mlbam_id=k[2],method=arm,metric=m,denominator='AB' if role=='hitter' else 'OUTS',prediction=v,accepted_rate=accepted[k][m]/accepted[k]['AB' if role=='hitter' else 'OUTS'] if finite(accepted[k][m]) and accepted[k]['AB' if role=='hitter' else 'OUTS'] else None,model_status=model['status']))
   for k in test:
    v,ok=compose(role,accepted[k],component[k]);vectors[k,arm]=v;support[k+(arm,)]=ok and all(s=='FITTED' for s in statuses)
    for m in TARGETS[role]:
     rate=component[k][m];den=accepted[k]['AB' if role=='hitter' else 'OUTS'];raw=rate*den if finite(rate) and finite(den) else None
     ledger.append(dict(season=origin,player_type=role,mlbam_id=k[2],method=arm,metric=m,accepted=accepted[k][m],raw_rate=rate,raw_count=raw,coherent_count=v[m],coherence_adjustment=v[m]-raw if finite(v[m]) and finite(raw) else None,accepted_group_fallback=not support[k+(arm,)]))
 return vectors,support,models,rate_rows,fit_rows,ledger
def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 c=load(a.config)
 if c!=DEFAULT:raise ValueError('Fixed v1.23 experiment controls changed')
 roots={n:Path(getattr(a,n)).resolve() for n in ['reference','matrix','labels','expanded','supplement','audit']};w={str(Path(a.config).resolve()):sha(a.config)};ref=roots['reference'];matrix=roots['matrix'];labs=roots['labels'];expanded=roots['expanded'];supp=roots['supplement'];audit=roots['audit']
 print('Verifying frozen accepted reference, historical labels and feature-family bindings...',flush=True)
 rr=load(checked(ref,'incremental_build_report.json',w));bindings=load(checked(ref,'input_hashes.json',w))
 if rr['version']!='1.17.0' or rr['accepted_forecasts_modified'] or rr['evaluation_outcomes_read']:raise ValueError('Require unchanged v1.17 reference freeze')
 hp=checked(matrix,'holdout_features.parquet',w);mp=checked(matrix,'training_matrix.parquet',w);schema=checked(matrix,'feature_schema.json',w);lp=checked(labs,'training_labels.parquet',w);lr=checked(labs,'label_build_report.json',w);bound(bindings,[hp,mp,schema,lp,lr])
 source_manifest=checked(matrix,'source_windows.json',w);er=load(checked(expanded,'expanded_feature_report.json',w));eb=load(checked(expanded,'input_hashes.json',w));bound(eb,[source_manifest,hp])
 if er['version']!='1.20.0' or er['models_fitted'] or er['accepted_matrix_modified']:raise ValueError('Invalid expanded feature release')
 sr=load(checked(supp,'leaderboard_build_report.json',w));sb=load(checked(supp,'input_hashes.json',w));ep=checked(expanded,'expanded_features_season.parquet',w);bound(sb,[source_manifest,ep,hp])
 ar=load(checked(audit,'scope_audit_report.json',w));ab=load(checked(audit,'input_hashes.json',w));hist_supp=checked(supp,'historical/leaderboard_features.parquet',w);bound(ab,[source_manifest,ep,hist_supp])
 if sr['version']!='1.21.0' or sr['accepted_projection_source_modified'] or ar['version']!='1.22.0' or not ar['archive_replay_verified'] or ar['forecasts_modified']:raise ValueError('Scope/leaderboard audit not frozen')
 label_scope=[];actual=labels(lp,scope_audit=label_scope);allow=load(schema)['predictor_allowlist'];rows=feature_rows(mp,allow);features={key(r):r for r in rows};accepted=accepted_vectors(read_reference(ref,'historical_forecasts.csv',w));
 if not set(accepted)<=set(features):raise ValueError('Accepted reference outside frozen feature population')
 ex={};bat={};availability=[]
 for split in ['training','holdout']:
  xx,av=addon(checked(expanded,split+'_expanded_features.parquet',w),'expanded');merge(ex,xx);availability.extend(av);xx,av=addon(checked(supp,split+'_leaderboard_features.parquet',w),'bat');merge(bat,xx);availability.extend(av)
 pt=arsenal(checked(expanded,'pitch_type_features_season.parquet',w))
 print('Inventorying registered benchmarks; external forecasts never enter model features...',flush=True)
 benchmarks,inventory,identity_issues,raw_inventory=benchmark_snapshot(a.warehouse,a.benchmark_dir,w)
 output,backups,stage=start(a.output,a.backup_root,list(roots.values())+[a.config,a.warehouse,a.benchmark_dir]);history=[];choices=[];scores=[];fitted_scores=[];rate_summary=[];fitlog=[];support_rows=[];cache={arm:{} for arm in ARMS};context={}
 def cache_rows(keys):
  for k in sorted(keys):
   for weight in WEIGHTS:
    standard,long,full=make_features(features[k],ex,bat,pt,weight);cache['standard_'+weight][k]=standard;cache['expanded_'+weight][k]=long
    if weight=='recent':cache['bat_recent_exploratory'][k]=full;cache['bat_control_recent'][k]=dict(long,__bat_available=full['__bat_available'],partial_bat_2023_in_window=full['partial_bat_2023_in_window']);context[k]=standard
 try:
  emit(stage/'training_label_scope_audit.csv',label_scope)
  cache_rows(accepted)
  for origin in range(c['first_origin'],2026):
   print(f'{origin}: fitting residual skill groups on earlier forecasts only; anchors frozen...',flush=True)
   decisions={role:gate(history,role,origin,c) for role in METRICS};choices.extend(decisions.values());vectors,support,models,rates,fl,ledger=forecast_origin(origin,accepted,features,actual,cache,c);fitlog.extend(fl);append_rows(stage/'composition_ledger.csv',ledger)
   for k in [k for k in accepted if k[0]==origin]:
    arm=decisions[k[1]]['selected'];vectors[k,'historical_selected']=vectors[k,arm];support[k+('historical_selected',)]=True if arm=='accepted_frozen' else support[k+(arm,)]
    for method in ARMS:support_rows.append(dict(season=origin,player_type=k[1],mlbam_id=k[2],method=method,fitted_group=bool(support[k+(method,)]),fallback='NONE' if support[k+(method,)] else 'ACCEPTED_GROUP_FALLBACK'))
   for role in METRICS:history.extend(evidence(origin,role,accepted,vectors,support,actual,context))
   ss,_=score_vectors(vectors,actual,context);scores.extend(ss);fs,_=score_vectors(vectors,actual,context,support);fitted_scores.extend(fs);rate_summary.extend(rate_scores(rates,actual,context))
   append_rows(stage/'historical_forecasts.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,metric=m,prediction=v) for (k,method),vv in sorted(vectors.items()) for m,v in vv.items()]);append_rows(stage/'historical_skill_rates.csv',rates)
   dump(stage/f'fold_models_{origin}.json',[dict(method=arm,**model) for (role,arm,m),model in models.items()])
  frozen={role:gate(history,role,2026,c) for role in METRICS};choices.extend(frozen.values());dump(stage/'frozen_choices_2026.json',frozen);frozen_sha=sha(stage/'frozen_choices_2026.json')
  print('Historical choices frozen. Generating 2026 forecasts from 2023-2025 features; no 2026 labels...',flush=True)
  future=accepted_vectors(read_reference(ref,'frozen_2026_forecasts.csv',w),True);hold=feature_rows(hp,allow,True);features.update({key(r):r for r in hold})
  if not set(future)<=set(features):raise ValueError('Future accepted reference outside prior-feature universe')
  accepted.update(future);cache_rows(future);vectors,support,models,rates,fl,ledger=forecast_origin(2026,accepted,features,actual,cache,c);fitlog.extend(fl);append_rows(stage/'composition_ledger.csv',ledger)
  for k in future:
   vectors[k,'historical_selected']=vectors[k,frozen[k[1]]['selected']]
   for method in ARMS:support_rows.append(dict(season=2026,player_type=k[1],mlbam_id=k[2],method=method,fitted_group=bool(support[k+(method,)]),fallback='NONE' if support[k+(method,)] else 'ACCEPTED_GROUP_FALLBACK'))
  future_rows=[dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,metric=m,prediction=v) for (k,method),vv in sorted(vectors.items()) for m,v in vv.items()];emit(stage/'frozen_2026_forecasts.csv',future_rows);emit(stage/'frozen_2026_skill_rates.csv',rates);dump(stage/'frozen_models_2026.json',[dict(method=arm,**model) for (role,arm,m),model in models.items()]);dump(stage/'rolling_choices.json',choices);dump(stage/'historical_gate_evidence.json',history)
  emit(stage/'historical_scores.csv',scores);emit(stage/'historical_comparison_summary.csv',summarize(scores));emit(stage/'historical_fitted_scores.csv',fitted_scores);emit(stage/'historical_rate_scores.csv',rate_summary);emit(stage/'historical_rate_comparison_summary.csv',summarize(rate_summary));emit(stage/'recent_2023_2025_scores.csv',[r for r in scores if 2023<=r['season']<=2025]);emit(stage/'bat_short_history_scores.csv',[r for r in fitted_scores if r['comparison_group']=='bat_control_recent_vs_bat_recent_exploratory']);emit(stage/'transition_2021_scores.csv',[r for r in scores if r['season']==2021]);emit(stage/'fold_fit_chronology.csv',fitlog);emit(stage/'composition_support.csv',support_rows);emit(stage/'feature_family_availability.csv',availability);emit(stage/'benchmark_inventory.csv',inventory);emit(stage/'benchmark_identity_exceptions.csv',identity_issues);emit(stage/'benchmark_raw_file_inventory.csv',raw_inventory);emit(stage/'frozen_benchmark_predictions.csv',benchmarks)
  provenance=[]
  for k in future:
   for role in [k[1]]:
    for m in METRICS[role]:provenance.append(dict(season=2026,player_type=role,mlbam_id=k[2],metric=m,selected_method=frozen[role]['selected'],component_source='FROZEN_ACCEPTED' if m not in CHANGED[role] or frozen[role]['selected']=='accepted_frozen' else 'RECENT_SKILL_GROUP' if support[k+(frozen[role]['selected'],)] else 'FROZEN_ACCEPTED_GROUP_FALLBACK',source_years='2023|2024|2025',older_player_history_fallback=False))
  names={(r['player_type'],r['mlbam_id']):r['name'] for r in benchmarks if r['season']==2026 and r.get('name')}
  for role in METRICS:emit(stage/('projection_table_2026_'+('hitters' if role=='hitter' else 'pitchers')+'.csv'),[dict(season=2026,player_type=role,mlbam_id=k[2],name=names.get((role,k[2])) or 'MLBAM '+k[2],projection_source=method,selected_arm=frozen[role]['selected'] if method=='historical_selected' else 'accepted_frozen',**vectors[k,method]) for k in sorted(future) if k[1]==role for method in ['accepted_frozen','historical_selected']])
  emit(stage/'component_provenance_2026.csv',provenance);emit(stage/'frozen_evaluation_context.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],history_cohort=history_class(context[k]),age=features[k].get('age_at_target_estimate')) for k in future])
  dump(stage/'experiment_contract.json',dict(settings=c,arms=ARMS,selectable=SELECTABLE,groups=TARGETS,changed_statistics=CHANGED,gate_metrics=GATE_METRICS,classic_features=CLASSIC,expanded_features=EXPANDED,pitch_types=PTYPES,pitch_type_metrics=PTMETRICS,bat_features=BAT,fit='Exposure-weighted ridge residuals against earlier-fold accepted implied rates; numeric median/missing indicators/scaling fit within each fold',recent_history='Three prior event seasons only; rates pooled with exposure times fixed recency weights; no older player-history fallback',selection='Direct accepted coherence gates plus equal-weight or same-weight incremental controls; historical seasons only',bat='Short/partial-history experiment; never selectable and missing bat inputs retain accepted group',scope='Hit distribution and pitcher H/BB/ER/SO/HR only. All other primitive components including hitter R/RBI/SB and pitcher W/QS remain accepted.',vintage='Retrospectively retrieved data; not independently archived preseason vintages'))
  dump(stage/'plan_2027.json',dict(primary_source_years=[2023,2024,2025,2026],emphasize=[2026,2025],weights_selected=False,models_fitted=False,forecasts_generated=False,older_player_history_fallback='NONE_WITHOUT_EXPLICIT_POLICY',next_requirement='Four-lag matrix and historical four-year weighting comparison before 2027 fitting'))
  report=dict(version=VERSION,status='RECENT_HISTORY_RESEARCH_FORECASTS_FROZEN',historical_seasons=list(range(2019,2026)),final_choices={role:r['selected'] for role,r in frozen.items()},choices_sha256=frozen_sha,forecast_2026_player_seasons=len(future),source_years_for_2026=[2023,2024,2025],workload_saves_holds_fixed=True,accepted_forecasts_modified=False,new_source_promoted=False,evaluation_outcomes_read=False,external_projections_used_as_predictors=False,models_fitted=True,bat_selectable=False,inputs_unchanged=True,benchmark_sources_available_2026=sorted({r['source'] for r in benchmarks if r['season']==2026}),limitations=['Post-diagnostic historical research; not independent confirmation.','2026 is previously reviewed and is evaluated only by the separate evaluator.','Older target years teach forecasting relationships; every player feature uses only the three preceding seasons.','Bat tracking has only 2024-2025 historical target support and partial 2023 measurements; no acceptance claim.','Metadata and missingness accompany measurements; this does not isolate physical values alone.','Scope-held supplemental mean EV/LA/sweet spot, baserunning and direction proxies are excluded.','No 2027 forecast, prospect population expansion or draft-tool change.'])
  report['build_implementation_version']=IMPLEMENTATION_VERSION
  report['ignored_non_scoring_label_rows']=sum(r['rows'] for r in label_scope if r['status']=='IGNORED_NONSCORING_METRIC')
  dump(stage/'recent_history_build_report.json',report);dump(stage/'forecast_freeze.json',{p.name:sha(p) for p in stage.iterdir() if p.is_file()});backup=finish(output,backups,stage,w);return dict(report,output=str(output),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(reference='outputs/statcast_incremental_v1_17',matrix='outputs/standalone_lagged_features_v1_0',labels='outputs/training_labels_v1_0',expanded='outputs/expanded_statcast_v1_20',supplement='outputs/statcast_leaderboards_v1_21',audit='outputs/statcast_scope_audit_v1_22',warehouse='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb',benchmark_dir='../last3yrsproj',config='config/recent_history_skills_v1_23.json',output='outputs/recent_history_skills_v1_23',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
