"""Paired chronological skill-rate experiment. Accepted exposure/SV/HLD stay frozen."""
import argparse,csv,json,math,shutil,copy,hashlib
from pathlib import Path
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import load,dump,sha,write,table,start,finish
from standalone_models_v1_0 import Target,TARGETS,fit,predict,outcome,compose,finite
from standalone_combined_v1_4 import METRICS,coherent,near
from standalone_diagnostics_v1_16 import checked,label_index,feature_index,forecasts,cohorts,score,comparison_summary,emit

VERSION='1.17.0'
SPECS=[t for t in TARGETS if not t.playing_time and t.numerator not in ['SV','HLD']]
METHODS=['accepted_frozen','standard_skill','statcast_skill','historical_selected']
HITTER={'whiff_pct','chase_pct','zone_pct','ev','hardhit_pct','barrel_pct','xwobacon'}
PITCHER=HITTER|{'velocity','spin_rpm','extension_ft'}
DEFAULT_SETTINGS=dict(version=VERSION,first_origin=2019,last_historical_origin=2025,evaluation_origin=2026,minimum_fit_rows=50,minimum_gate_folds=3,minimum_gate_rows=30,minimum_guard_rows=20,minimum_mse_improvement=.01,maximum_mae_degradation=.01,maximum_guard_degradation=.02,ridge_alpha=1.0,clip_z=8,maximum_exposure_weight=600,statcast_policy='REGISTERED_ELIGIBILITY_AND_POSITIVE_OBSERVATIONS; unavailable values stay null',guard_cohorts=['LOW_HISTORY','ESTABLISHED_HISTORY'],accepted_release_policy='RESEARCH_ONLY_NO_AUTOMATIC_PROMOTION')

def key(r):return int(r['target_season']),r['player_type'],str(r['mlbam_id'])
def membership(keys):return hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()
def settings_checked(s):
 if s.get('version')!=VERSION or (s['first_origin'],s['last_historical_origin'],s['evaluation_origin'])!=(2019,2025,2026):raise ValueError('Unsupported chronology/version')
 if s['guard_cohorts']!=['LOW_HISTORY','ESTABLISHED_HISTORY']:raise ValueError('Guard cohort contract changed')
 for n in ['minimum_fit_rows','minimum_gate_folds','minimum_gate_rows','minimum_guard_rows']:
  if not isinstance(s[n],int) or s[n]<1:raise ValueError('Invalid support control')
 if s['ridge_alpha']<=0 or s['clip_z']<=0 or s['maximum_exposure_weight']<=0 or any(not 0<=s[n]<1 for n in ['minimum_mse_improvement','maximum_mae_degradation','maximum_guard_degradation']):raise ValueError('Invalid estimator/gate setting')
 return s

def masked_features(rows,allow):
 """Validate registered Statcast metadata; mask physical values before imputation."""
 out=[];audit=defaultdict(lambda:[0,0,0])
 for raw in rows:
  r=dict(raw);role=r['player_type'];allowed=HITTER if role=='hitter' else PITCHER
  for lag in [1,2,3]:
   for metric in allowed:
    stem=f'x_statcast_lag{lag}_{metric}';name=stem+'_value'
    if name not in allow:continue
    n=r.get(stem+'_observations');coverage=r.get(stem+'_coverage');eligible=r.get(stem+'_eligible');v=r.get(name)
    if eligible not in [None,0,1,False,True]:raise ValueError('Invalid registered measurement eligibility')
    if n is not None and (not finite(n) or n<0):raise ValueError('Invalid observation count')
    if coverage is not None and (not finite(coverage) or not 0<=coverage<=1):raise ValueError('Invalid measurement coverage')
    supported=bool(eligible) and finite(n) and n>0 and finite(coverage) and coverage>0
    if not supported:r[name]=None
    if r.get(name) is not None and not finite(r[name]):raise ValueError('Invalid physical feature')
    counts=audit[int(r['target_season']),role,name];counts[0]+=1;counts[1]+=int(finite(r.get(name)));counts[2]+=int(finite(v) and not supported)
  out.append(r)
 return out,[dict(target_season=y,player_type=role,feature=n,population_rows=v[0],supported_value_rows=v[1],finite_values_masked=v[2]) for (y,role,n),v in sorted(audit.items())]

def feature_sets(allow,role):
 common=[n for n in allow if n.startswith(('x_actual_lag','tracking_era_lag','short_season_lag')) or n in ['age_at_target_estimate','history_seasons','has_any_actual_history']]
 permitted=HITTER if role=='hitter' else PITCHER;advanced=[]
 for n in allow:
  if not n.startswith('x_statcast_lag'):continue
  tail=n.split('_',3)[-1]
  if any(tail==metric+'_'+suffix for metric in permitted for suffix in ['value','observations','coverage','eligible']):advanced.append(n)
 return sorted(common),sorted(common+advanced)

def joined_rows(rows,actual):
 out=[]
 for raw in rows:
  r=dict(raw);k=key(r)
  for metric in {n for t in SPECS if t.role==k[1] for n in [t.numerator,t.denominator]}:
   v=actual.get(k+(metric,));old=r.get('y_'+metric)
   if r.get('y_eligible_'+metric) and (v is None or not near(old,v)):raise ValueError('Matrix target differs from frozen eligible labels')
   r['y_'+metric]=v;r['y_eligible_'+metric]=int(v is not None)
  out.append(r)
 return out

def read_vectors(path,year=None):
 result=defaultdict(dict);seen=set()
 with Path(path).open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   y=int(r['season']);role=r['player_type'];pid=str(r['mlbam_id']);metric=r['metric'];k=y,role,pid
   if role not in METRICS or not pid.isdigit() or int(pid)<=0 or metric not in METRICS[role] or (k,metric) in seen or r['method']!='selected_v1_5':raise ValueError('Invalid/duplicate accepted vector')
   if (year is None and not 2016<=y<=2025) or (year is not None and y!=year):raise ValueError('Wrong accepted forecast split')
   seen.add((k,metric));v=float(r['prediction']) if r['prediction']!='' else None
   if v is not None and (not finite(v) or v<0):raise ValueError('Invalid accepted component')
   result[k][metric]=v
 for (y,role,pid),v in result.items():
  if set(v)!=set(METRICS[role]):raise ValueError('Incomplete accepted vector')
  coherent(role,v)
 return dict(result)

def rate_of(v,t):
 n=v.get(t.numerator);d=v.get(t.denominator)
 return n/d if finite(n) and finite(d) and d>0 else None

def history_guard(r):
 h=r.get('history_seasons');return 'LOW_HISTORY' if finite(h) and h<=1 else 'ESTABLISHED_HISTORY' if finite(h) and h>=2 else 'UNKNOWN_HISTORY'

def decide(history,t,origin,s):
 rows=[r for r in history if r['target']==t.id and r['season']<origin]
 def gate(candidate,reference,incremental=False):
  answer={};passed=True
  for cohort in ['ALL']+s['guard_cohorts']:
   minimum=s['minimum_gate_rows'] if cohort=='ALL' else s['minimum_guard_rows'];rr=[r for r in rows if r['cohort']==cohort and r['n']>=minimum and r['models_fitted']]
   support=len(rr)>=s['minimum_gate_folds'];bm=float(np.mean([r[reference+'_mse'] for r in rr])) if rr else None;cm=float(np.mean([r[candidate+'_mse'] for r in rr])) if rr else None;ba=float(np.mean([r[reference+'_mae'] for r in rr])) if rr else None;ca=float(np.mean([r[candidate+'_mae'] for r in rr])) if rr else None
   ok=bool(support and bm is not None and bm>0 and cm<=bm*((1-s['minimum_mse_improvement']) if cohort=='ALL' else 1+s['maximum_guard_degradation']) and ca<=ba*(1+(s['maximum_mae_degradation'] if cohort=='ALL' else s['maximum_guard_degradation'])))
   answer[cohort]=dict(pass_gate=ok,seasons=[r['season'] for r in rr],n=sum(r['n'] for r in rr),reference_mse=bm,candidate_mse=cm,reference_mae=ba,candidate_mae=ca,sufficient_support=support);passed=passed and ok
  return dict(adopt=bool(passed),cohorts=answer)
 incremental=gate('statcast_skill','standard_skill',True);candidate='statcast_skill' if incremental['adopt'] else 'standard_skill';accepted_gate=gate(candidate,'accepted_frozen')
 return dict(target=t.id,origin=origin,incremental_statcast=incremental,candidate_vs_accepted=accepted_gate,selected=candidate if accepted_gate['adopt'] else 'accepted_frozen',evaluation_used=False)

def compose_fixed(role,accepted,rates,method):
 if method=='accepted_frozen':return dict(accepted),[]
 if any(not finite(rates.get(t.id)) for t in SPECS if t.role==role):return dict(accepted),[dict(reason='UNSUPPORTED_SKILL_VECTOR_ACCEPTED_FALLBACK')]
 components=dict(rates)
 if role=='hitter':components['hitter_PA']=accepted['PA']
 else:
  components['pitcher_OUTS']=accepted['OUTS'];components['pitcher_SV_per_OUTS']=0.;components['pitcher_HLD_per_OUTS']=0.
 v=compose(role,components)
 if role=='pitcher':v['SV']=accepted['SV'];v['HLD']=accepted['HLD'];v['SV_plus_HLD']=accepted['SV_plus_HLD'];v['IP']=accepted['IP']
 coherent(role,v)
 anchors=['PA'] if role=='hitter' else ['OUTS','IP','SV','HLD','SV_plus_HLD']
 if any(v.get(m)!=accepted.get(m) for m in anchors):raise ValueError('Frozen workload/saves/holds changed')
 return v,[dict(metric=m,accepted=accepted.get(m),candidate=v.get(m),delta=v[m]-accepted[m] if finite(v.get(m)) and finite(accepted.get(m)) else None,reason='COHERENT_SKILL_VECTOR_RECOMPOSITION') for m in v if not near(v.get(m),accepted.get(m))]

def rate_scores(rows,actual,feature_map):
 groups=defaultdict(list)
 for row in rows:
  k=(row['season'],row['player_type'],row['mlbam_id']);t=next(t for t in SPECS if t.id==row['target']);n=actual.get(k+(t.numerator,));den=actual.get(k+(t.denominator,))
  if n is None or den is None or den<=0:continue
  truth=n/den;values={m:row[m] for m in METHODS};comparisons=[('standard_vs_statcast',['standard_skill','statcast_skill']),('accepted_vs_selected',['accepted_frozen','historical_selected']),('all_three',['accepted_frozen','standard_skill','statcast_skill'])]
  for group,methods in comparisons:
   if not all(finite(values[m]) for m in methods):continue
   for method in methods:
    for dim,cohort in cohorts(k,feature_map,actual):groups[k[0],k[1],t.id,dim,cohort,group,method].append((k[2],values[method]-truth))
 out=[]
 for (year,role,target,dim,cohort,group,method),rr in sorted(groups.items()):
  n=len(rr);err=[e for _,e in rr];out.append(dict(season=year,player_type=role,metric=target,cohort_dimension=dim,cohort=cohort,comparison_group=group,method=method,n=n,mae=sum(abs(e) for e in err)/n,rmse=math.sqrt(sum(e*e for e in err)/n),bias=sum(err)/n,membership_sha256=membership([pid for pid,e in rr]),transition_2021_retained=year==2021,short_season_2020=year==2020))
 return out

def paired_statistic_scores(bank,actual,features):
 paired={}
 for k in {key[:4] for key in bank}:
  a=bank.get(k+('standard_skill',));b=bank.get(k+('statcast_skill',))
  if finite(a) and finite(b):paired[k+('accepted_v1_5',)]=a;paired[k+('statcast_skill',)]=b
 scores,_,_=score(paired,actual,features);out=[]
 for r in scores:
  if r['comparison_group']=='INDIVIDUAL_ELIGIBLE':continue
  r=dict(r,comparison_group='standard_vs_statcast',method='standard_skill' if r['method']=='accepted_v1_5' else r['method']);out.append(r)
 return out


def gate_history(test,t,predictions,accepted,models,origin):
 groups=defaultdict(list)
 for r in test:
  o=outcome(r,t)
  if o is None:continue
  k=key(r);v=predictions[k];a=rate_of(accepted[k],t);values=dict(accepted_frozen=a,standard_skill=v['standard_skill'],statcast_skill=v['statcast_skill'])
  if not all(finite(x) for x in values.values()):continue
  for cohort in ['ALL',history_guard(r)]:groups[cohort].append((k[2],o[0],values))
 out=[]
 for cohort,rr in groups.items():
  row=dict(season=origin,target=t.id,cohort=cohort,n=len(rr),models_fitted=all(m['ridge_status']=='FITTED' for m in models.values()),membership_sha256=membership([pid for pid,truth,v in rr]))
  for method in ['accepted_frozen','standard_skill','statcast_skill']:
   errors=[v[method]-truth for pid,truth,v in rr];row[method+'_mse']=float(np.mean(np.square(errors)));row[method+'_mae']=float(np.mean(np.abs(errors)))
  out.append(row)
 return out


def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 s=settings_checked(load(a.config));watched={str(Path(a.config).resolve()):sha(a.config)};release=Path(a.release).resolve();accepted_root=Path(a.accepted).resolve();matrix=Path(a.matrix).resolve();labels=Path(a.labels).resolve();baseline=Path(a.baseline).resolve()
 print('Verifying frozen accepted forecasts, matrices, labels and estimator controls...',flush=True)
 bindings=load(checked(release,'input_hashes.json',watched));rep=load(checked(release,'projection_release_report.json',watched));lp=checked(labels,'training_labels.parquet',watched);lr=load(checked(labels,'label_build_report.json',watched));mp=checked(matrix,'training_matrix.parquet',watched);hp=checked(matrix,'holdout_features.parquet',watched);schema=checked(matrix,'feature_schema.json',watched)
 if lr['reference_sha256']!=rep['label_reference_sha256'] or bindings.get(str(mp))!=sha(mp) or bindings.get(str(hp))!=sha(hp) or bindings.get(str(schema))!=sha(schema):raise ValueError('Accepted matrix/reference binding mismatch')
 paths=[checked(accepted_root,n,watched) for n in ['historical_forecasts.csv','frozen_2026_forecasts.csv','frozen_models.json']]
 if any(bindings.get(str(p))!=sha(p) for p in paths):raise ValueError('Accepted forecast/model differs from release')
 if load(paths[2])['training_labels_sha256']!=sha(lp):raise ValueError('Training labels differ from accepted model')
 accepted=read_vectors(paths[0]);accepted.update(read_vectors(paths[1],2026));actual,_=label_index(lp);allow=load(schema)['predictor_allowlist'];rows,fmap=feature_index(mp,allow)
 hold=table(hp)
 for r in hold:
  if int(r['target_season'])!=2026 or int(r['max_source_season'])>=2026 or str(r['source_cutoff'])>='2026-01-01' or any(n.startswith('y_') for n in r) or any(n not in r for n in allow):raise ValueError('Invalid evaluation features or target leakage')
 if any(r['player_type'] not in METRICS or not str(r['mlbam_id']).isdigit() or any(r.get('source_season_lag'+str(lag)) not in [None,2026-lag] for lag in [1,2,3]) for r in hold):raise ValueError('Invalid evaluation identity or lag year')
 if len({key(r) for r in hold})!=len(hold):raise ValueError('Duplicate evaluation features')
 rows=joined_rows(rows,actual);masked,availability=masked_features(rows+hold,allow);rows=[r for r in masked if r['target_season']<2026];hold=[r for r in masked if r['target_season']==2026];fmap={key(r):r for r in rows}
 if not set(accepted).issubset({key(r) for r in rows+hold}):raise ValueError('Accepted forecast has no matching prior-feature row')
 base_model=load(checked(baseline,'frozen_models.json',watched));config=copy.deepcopy(base_model['config']);config.update({n:s[n] for n in ['minimum_fit_rows','ridge_alpha','clip_z','maximum_exposure_weight']});config['context_features']=[n for n in config['context_features'] if n!='has_any_statcast_history']
 output,backups,stage=start(a.output,a.backup_root,[release,accepted_root,matrix,labels,baseline,a.config]);history=[];choices=[];rates=[];vectors=[];adjustments=[];composition_support=[];chronology=[];predictors=[];frozen_models={}
 try:
  for origin in range(s['first_origin'],2027):
   print(f'{origin}: paired skill models fit target seasons < {origin}; accepted workload/SV/HLD fixed',flush=True)
   training=[r for r in rows if r['target_season']<origin];testing=[r for r in (hold if origin==2026 else rows) if r['target_season']==origin and key(r) in accepted];rate_bank={key(r):{m:{} for m in METHODS} for r in testing};origin_models={}
   # Decisions see only completed earlier-origin OOF errors, never this origin's labels.
   decisions={t.id:decide(history,t,origin,s) for t in SPECS}
   for t in SPECS:
    common,augmented=feature_sets(allow,t.role);modelpair={};predpair={};test=[r for r in testing if r['player_type']==t.role];fit_keys=[key(r) for r in training if r['player_type']==t.role and outcome(r,t) is not None]
    for method,features in [('standard_skill',common),('statcast_skill',augmented)]:
     model=fit(training,t,features,config);_,values=predict(model,test,t,config);modelpair[method]=model;predpair[method]=values
     if any(y>=origin for y in model['fit_target_seasons']) or model['n_fit']!=len(fit_keys):raise ValueError('Fold fitting chronology/domain failure')
     chronology.append(dict(origin=origin,target=t.id,method=method,n_fit=model['n_fit'],fit_target_seasons=json.dumps(model['fit_target_seasons']),fit_membership_sha256=membership(fit_keys),ridge_status=model['ridge_status']))
     state=model.get('preprocessing') or {}
     for status in ['numeric','categorical','dropped']:
      for name in state.get(status,[]):predictors.append(dict(origin=origin,target=t.id,method=method,feature=name,status=status))
    if modelpair['standard_skill']['population_value']!=modelpair['statcast_skill']['population_value']:raise ValueError('Unpaired population prior')
    left=modelpair['standard_skill'].get('preprocessing');right=modelpair['statcast_skill'].get('preprocessing')
    if left is not None:
     if right is None or any(right[k].get(name)!=value for k in ['numeric','categorical'] for name,value in left[k].items()) or any(name not in right['dropped'] for name in left['dropped']):raise ValueError('Common-feature preprocessing differs between arms')
    choice=decisions[t.id];choices.append(choice);paired={}
    for i,r in enumerate(test):
     k=key(r);values=dict(accepted_frozen=rate_of(accepted[k],t),standard_skill=predpair['standard_skill'][i],statcast_skill=predpair['statcast_skill'][i]);values['historical_selected']=values[choice['selected']]
     for method,value in values.items():rate_bank[k][method][t.id]=value
     paired[k]=values;rates.append(dict(season=origin,player_type=t.role,mlbam_id=k[2],target=t.id,selected_method=choice['selected'],standard_fit_status=modelpair['standard_skill']['ridge_status'],statcast_fit_status=modelpair['statcast_skill']['ridge_status'],**values))
    if origin<2026:history.extend(gate_history(test,t,paired,accepted,modelpair,origin))
    origin_models[t.id]=dict(target=t.__dict__,models=modelpair,choice=choice)
   for r in testing:
    k=key(r);role=k[1]
    for method in METHODS:
     chosen=rate_bank[k][method]
     if method=='historical_selected' and all(decisions[t.id]['selected']=='accepted_frozen' for t in SPECS if t.role==role):v,ledger=dict(accepted[k]),[]
     else:v,ledger=compose_fixed(role,accepted[k],chosen,method)
     composition_support.append(dict(season=origin,player_type=role,mlbam_id=k[2],method=method,accepted_vector_fallback=any(x['reason']=='UNSUPPORTED_SKILL_VECTOR_ACCEPTED_FALLBACK' for x in ledger),all_role_skill_models_fitted=all(origin_models[t.id]['models'][arm]['ridge_status']=='FITTED' for t in SPECS if t.role==role for arm in ['standard_skill','statcast_skill'])))
     for m,value in v.items():vectors.append(dict(season=origin,player_type=role,mlbam_id=k[2],method=method,metric=m,prediction=value))
     for entry in ledger:adjustments.append(dict(season=origin,player_type=role,mlbam_id=k[2],method=method,**entry))
   dump(stage/f'fold_models_{origin}.json',dict(origin=origin,config=config,models=origin_models))
   if origin==2026:frozen_models=origin_models
  historical_rates=[r for r in rates if r['season']<2026];historical_vectors=[r for r in vectors if r['season']<2026];rs=rate_scores(historical_rates,actual,fmap)
  supported_rate_scores=rate_scores([r for r in historical_rates if r['standard_fit_status']=='FITTED' and r['statcast_fit_status']=='FITTED'],actual,fmap)
  # Reuse diagnostic scorer with its explicit accepted-method key and paired pools.
  bank={(r['season'],r['player_type'],r['mlbam_id'],r['metric'],'accepted_v1_5' if r['method']=='accepted_frozen' else r['method']):r['prediction'] for r in historical_vectors};cs,coverage,outliers=score(bank,actual,fmap);paired_counts=paired_statistic_scores(bank,actual,fmap)
  support_lookup={(r['season'],r['player_type'],r['mlbam_id'],r['method']):r for r in composition_support};supported_keys={k[:3] for k in bank if all((lambda r:not r['accepted_vector_fallback'] and r['all_role_skill_models_fitted'])(support_lookup[k[:3]+(method,)]) for method in ['standard_skill','statcast_skill'])};supported_cs,_,_=score({k:v for k,v in bank.items() if k[:3] in supported_keys},actual,fmap)
  for n,rr in [('historical_skill_rates',historical_rates),('frozen_2026_skill_rates',[r for r in rates if r['season']==2026]),('historical_forecasts',historical_vectors),('frozen_2026_forecasts',[r for r in vectors if r['season']==2026]),('historical_rate_scores',rs),('historical_rate_comparison_summary',comparison_summary(rs)),('historical_fitted_rate_scores',supported_rate_scores),('historical_fitted_statistic_scores',supported_cs),('historical_count_and_ratio_scores',cs),('historical_paired_statistic_scores',paired_counts),('historical_paired_statistic_summary',comparison_summary(paired_counts)),('historical_count_comparison_summary',comparison_summary(cs)),('historical_count_outliers',outliers),('historical_label_coverage',coverage),('statcast_availability',availability),('fold_fit_chronology',chronology),('fold_predictor_inventory',predictors),('composition_adjustments',adjustments),('composition_support',composition_support),('transition_2021_rates',[r for r in rs if r['season']==2021]),('transition_2021_counts',[r for r in cs if r['season']==2021])]:emit(stage/(n+'.csv'),rr)
  dump(stage/'rolling_choices.json',choices);dump(stage/'historical_gate_evidence.json',history);dump(stage/'frozen_models.json',dict(version=VERSION,config=config,settings=s,models=frozen_models,selection_max_season=2025,evaluation_outcomes_read=False));dump(stage/'experiment_contract.json',dict(settings=s,role_statcast_features=dict(hitter=sorted(HITTER),pitcher=sorted(PITCHER)),fixed_fields=dict(hitter=['PA'],pitcher=['OUTS','IP','SV','HLD','SV_plus_HLD']),AB_policy='Modeled opportunity fraction under fixed PA; coherent normalization can change multiple non-anchored components',comparison='Same estimator/target fitting rows/weights, fold-only preprocessing; Statcast block includes measurement metadata and missingness',release_status='RESEARCH_ONLY_NO_AUTOMATIC_ACCEPTED_SOURCE_REPLACEMENT'))
  report=dict(version=VERSION,status='PAIRED_SKILL_EXPERIMENT_FROZEN_RESEARCH_ONLY',historical_seasons=sorted({r['season'] for r in historical_rates}),skill_targets=len(SPECS),final_choices={n:v['choice']['selected'] for n,v in frozen_models.items()},final_incremental_statcast_pass=[n for n,v in frozen_models.items() if v['choice']['incremental_statcast']['adopt']],historical_rate_score_rows=len(rs),historical_statistic_score_rows=len(cs),models_fitted=True,accepted_forecasts_modified=False,workload_saves_holds_fixed=True,evaluation_outcomes_read=False,external_projections_used=False,new_source_promoted=False,inputs_unchanged=True,limitations=['Skill targets include opportunity-sensitive rates such as wins/outs; not all are pure talent measures.','Registered Statcast eligibility/sample masking is inherited; this experiment does not certify measurement-era comparability.','Incremental block includes physical values and observation/coverage/missingness metadata, not physical measurements in isolation.','Skill gate uses eligible target exposure floors; reporting includes lower positive exposures separately.','Historical guards require low-history and established-history support; insufficient support retains accepted components.','Coherent mixed-rate normalization can change nonselected counting components; inspect composition ledger. PA/OUTS/IP/SV/HLD anchors are exact.','Full statistical forecasts are research outputs; skill-rate gate passage does not automatically establish improved final count/rate forecasts.','Retrospective source vintages; 2026 previously reviewed disclosed evaluation only. No model selection uses 2026 outcomes.'])
  dump(stage/'incremental_build_report.json',report);dump(stage/'forecast_freeze.json',{p.name:sha(p) for p in stage.iterdir() if p.is_file()});backup=finish(output,backups,stage,watched);return dict(report,output=str(output),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(release='outputs/projection_release_2026_v1_11_1',accepted='outputs/standalone_holds_attribution_v1_5',matrix='outputs/standalone_lagged_features_v1_0',labels='outputs/training_labels_v1_0',baseline='outputs/standalone_baselines_v1_0',config='config/statcast_incremental_v1_17.json',output='outputs/statcast_incremental_v1_17',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
