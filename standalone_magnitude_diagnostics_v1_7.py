"""Read-only magnitude and opportunity diagnostics. No fitting, selection or forecast edits."""
import hashlib,json,math
from collections import defaultdict
from standalone_models_v1_0 import finite
from standalone_combined_v1_4 import near
from standalone_attribution_v1_5 import decomposition,workload_band
from standalone_role_workload_v1_2 import prior_role
from standalone_growth_sb_v1_6 import anchor,opportunity

P_METHODS={'frozen_v1_5':'baseline','v1_6_candidate':'candidate','v1_6_selected':'selected'}

def phase(year):
 return 'DISCLOSED_2026_EVALUATION' if year==2026 else 'HISTORICAL_2020_STRESS' if year==2020 else 'HISTORICAL_DEVELOPMENT'

def mean(values):
 v=[x for x in values if finite(x)];return sum(v)/len(v) if v else None

def rmse(values):
 m=mean([x*x for x in values if finite(x)]);return math.sqrt(m) if m is not None else None

def hash_ids(rows):return hashlib.sha256(json.dumps(sorted(r['mlbam_id'] for r in rows)).encode()).hexdigest()

def pitcher_row(key,d,r,actual,settings):
 year,role,pid=key;a=actual.get(key+('OUTS',));g=actual.get(key+('G',));an=d.get('anchor');expected=anchor(r,settings)
 if not near(an,expected):raise ValueError('Frozen historical anchor disagrees with prior-season information')
 prior=r.get('x_actual_lag1_OUTS');p=d.get('growth_probability');grow=d.get('conditional_growth_OUTS');decline=d.get('conditional_decline_OUTS');part=d.get('participation_probability');raw=d.get('raw_candidate')
 out=dict(season=year,split=phase(year),mlbam_id=pid,prior_role=prior_role(r),prior_source_season=r.get('source_season_lag1'),prior_observed_OUTS=prior,prior_observed_workload=workload_band(prior,'pitcher'),anchor_OUTS=an,anchor_workload=workload_band(an,'pitcher'),actual_OUTS=a,actual_G=g,baseline_OUTS=d['baseline'],candidate_OUTS=d['candidate'],selected_OUTS=d['selected'],raw_candidate_OUTS=raw,growth_probability=p,conditional_growth_OUTS=grow,conditional_decline_OUTS=decline,participation_probability=part,full_vector_supported=d['supported'],source_support_status=d['support_status'],anchor_above_count_cap=finite(an) and an>settings['maximum_OUTS'],growth_branch_at_count_cap=finite(grow) and near(grow,settings['maximum_OUTS']))
 for n in ['observed_change_OUTS','observed_magnitude_OUTS','predicted_magnitude_OUTS','magnitude_error_OUTS','conditional_mixture_OUTS','observed_branch_prediction_OUTS','branch_count_error_OUTS','direction_mixing_effect_OUTS','participation_effect_OUTS','fallback_effect_OUTS','raw_reconstruction_residual','candidate_reconstruction_residual','growth_target','brier','baseline_error_OUTS','candidate_error_OUTS','selected_error_OUTS']:out[n]=None
 out['observed_branch']='UNKNOWN';out['magnitude_status']='MISSING_ACTUAL_OR_ANCHOR';out['component_status']='UNAVAILABLE'
 for m,name in P_METHODS.items():
  if finite(a) and finite(d[name]):out[name+'_error_OUTS']=d[name]-a
 if not finite(a) or not finite(an):return out
 out['observed_change_OUTS']=a-an
 if not finite(g) or g<=0:out['magnitude_status']='NOT_CONFIRMED_ACTIVE_FOR_CONDITIONAL_MODEL';return out
 target=int(a>an);out['growth_target']=target;out['observed_branch']='GROWTH' if target else 'DECLINE_OR_FLAT';out['observed_magnitude_OUTS']=abs(a-an)
 if finite(p):out['brier']=(p-target)**2
 branch=grow if target else decline
 if not finite(branch):out['magnitude_status']='MISSING_CONDITIONAL_BRANCH';return out
 predicted=branch-an if target else an-branch;out.update(predicted_magnitude_OUTS=predicted,magnitude_error_OUTS=predicted-abs(a-an),observed_branch_prediction_OUTS=branch,branch_count_error_OUTS=branch-a,magnitude_status='AVAILABLE')
 if not all(finite(x) for x in [p,grow,decline,part,raw]):return out
 q=p*grow+(1-p)*decline;mix=q-branch;participation=(part-1)*q;branch_error=branch-a;residual=raw-a-branch_error-mix-participation
 if abs(residual)>1e-8*max(1,abs(raw-a),abs(branch_error),abs(mix)):raise ValueError('Pitcher raw error decomposition failed')
 fallback=d['candidate']-raw if finite(d['candidate']) else None;cr=None if fallback is None else d['candidate']-a-branch_error-mix-participation-fallback
 if cr is not None and abs(cr)>1e-8*max(1,abs(d['candidate']-a)):raise ValueError('Pitcher effective error decomposition failed')
 out.update(conditional_mixture_OUTS=q,direction_mixing_effect_OUTS=mix,participation_effect_OUTS=participation,fallback_effect_OUTS=fallback,raw_reconstruction_residual=residual,candidate_reconstruction_residual=cr,component_status='AVAILABLE');return out

def pitcher_cohorts(d):
 out=['all','prior_role_'+d['prior_role'],'anchor_workload_'+d['anchor_workload'],'prior_observed_workload_'+d['prior_observed_workload'],'prior_role_'+d['prior_role']+'__anchor_workload_'+d['anchor_workload']]
 if d['full_vector_supported']:out.append('supported_full_vector_only')
 if d['observed_branch']!='UNKNOWN':out+=['observed_'+d['observed_branch'],'prior_role_'+d['prior_role']+'__observed_'+d['observed_branch']]
 if d['prior_source_season']==2020:out.append('prior_source_2020_normalized')
 return out

def pitcher_summary(rows):
 groups=defaultdict(list)
 for d in rows:
  for cohort in pitcher_cohorts(d):groups[d['season'],cohort,d['observed_branch']].append(d)
 out=[];components=[];calibration=[]
 for (year,cohort,branch),rr in sorted(groups.items()):
  pair=[d for d in rr if d['magnitude_status']=='AVAILABLE'];base=dict(season=year,split=phase(year),cohort=cohort,observed_branch=branch,rows=len(rr),magnitude_pairs=len(pair),supported_full_vectors=sum(d['full_vector_supported'] for d in rr),membership_sha256=hash_ids(pair))
  out.append(base|dict(mean_predicted_magnitude_OUTS=mean([d['predicted_magnitude_OUTS'] for d in pair]),mean_observed_magnitude_OUTS=mean([d['observed_magnitude_OUTS'] for d in pair]),magnitude_bias_OUTS=mean([d['magnitude_error_OUTS'] for d in pair]),magnitude_MAE_OUTS=mean([abs(d['magnitude_error_OUTS']) for d in pair]),magnitude_RMSE_OUTS=rmse([d['magnitude_error_OUTS'] for d in pair]),mean_prior_observed_OUTS=mean([d['prior_observed_OUTS'] for d in pair]),mean_normalized_anchor_OUTS=mean([d['anchor_OUTS'] for d in pair]),anchors_above_cap=sum(d['anchor_above_count_cap'] for d in rr)))
  complete=[d for d in rr if d['component_status']=='AVAILABLE' and finite(d['candidate_error_OUTS'])];terms=['branch_count_error_OUTS','direction_mixing_effect_OUTS','participation_effect_OUTS','fallback_effect_OUTS'];summary=dict(season=year,split=phase(year),cohort=cohort,observed_branch=branch,n=len(complete),membership_sha256=hash_ids(complete))
  for n in terms:summary['mean_'+n]=mean([d[n] for d in complete]);summary['MSE_'+n]=mean([d[n]**2 for d in complete])
  for i,a in enumerate(terms):
   for b in terms[i+1:]:summary['interaction_'+a+'__'+b]=mean([2*d[a]*d[b] for d in complete])
  total=mean([d['candidate_error_OUTS']**2 for d in complete]);parts=[v for n,v in summary.items() if n.startswith(('MSE_','interaction_'))];reconstructed=sum(parts) if parts and all(finite(v) for v in parts) else None
  if total is not None and abs(total-reconstructed)>1e-7*max(1,total):raise ValueError('Pitcher MSE reconstruction failed')
  summary.update(total_candidate_MSE_OUTS=total,reconstructed_MSE_OUTS=reconstructed);components.append(summary)
 # Calibration bins are fixed, not fitted or used to alter probabilities.
 gg=defaultdict(list)
 for d in rows:
  if d['growth_target'] is None or not finite(d['growth_probability']):continue
  for cohort in ['all','prior_role_'+d['prior_role'],'anchor_workload_'+d['anchor_workload']]:gg[d['season'],cohort,min(9,int(d['growth_probability']*10))].append(d)
 for (year,cohort,b),rr in sorted(gg.items()):calibration.append(dict(season=year,split=phase(year),cohort=cohort,probability_bin_lower=b/10,probability_bin_upper=(b+1)/10,n=len(rr),mean_probability=mean([d['growth_probability'] for d in rr]),observed_growth_fraction=mean([d['growth_target'] for d in rr]),brier=mean([d['brier'] for d in rr]),membership_sha256=hash_ids(rr)))
 return out,components,calibration

def sb_rows(key,d,r,base,actual,settings):
 year,_,pid=key;pr=r.get('x_actual_lag1_SB');actual_values={m:actual.get(key+(m,)) for m in ['H','HR','BB','HBP']};ao=opportunity(actual_values);fo=opportunity(base)
 if not near(fo,d.get('projected_onbase_proxy')):raise ValueError('Frozen projected opportunity proxy changed')
 a=actual.get(key+('SB',));pa=actual.get(key+('PA',));fp=base.get('PA');model_rate=d.get('positive_SB_rate');prob=d.get('any_SB_probability');raw=d['raw_candidate'];uncapped=fo*prob*model_rate if all(finite(x) for x in [fo,prob,model_rate]) else None;cap_effect=raw-uncapped if finite(raw) and finite(uncapped) else None;fallback=d['candidate']-raw if finite(raw) and finite(d['candidate']) else None;prior_runner=finite(pr) and pr>=settings['prior_SB_floor'];out=[]
 for method,name in P_METHODS.items():
  f=d[name];decomp=decomposition(f,fo,a,ao);x=dict(season=year,split=phase(year),mlbam_id=pid,method=method,prior_SB=pr,established_runner=prior_runner,prior_source_season=r.get('source_season_lag1'),prior_workload=workload_band(r.get('x_actual_lag1_PA'),'hitter'),full_candidate_supported=d['supported'],source_support_status=d['support_status'],forecast_SB=f,actual_SB=a,forecast_PA=fp,actual_PA=pa,projected_onbase_proxy=fo,actual_onbase_proxy=ao,any_SB_probability=prob,positive_SB_rate=model_rate,uncapped_candidate_SB=uncapped,raw_candidate_SB=raw,candidate_cap_effect=cap_effect,candidate_fallback_effect=fallback)
  for n,v in actual_values.items():x['actual_'+n]=v;x['forecast_'+n]=base.get(n)
  x.update(status=decomp['status'],error=decomp['error'],forecast_implied_propensity=decomp['forecast_rate'],actual_implied_propensity=decomp['actual_rate'],opportunity_contribution=decomp['workload_contribution'],propensity_contribution=decomp['skill_contribution'],reconstruction_residual=decomp['reconstruction_residual'],actual_opportunity_forecast_propensity=decomp['actual_exposure_forecast_rate'],forecast_opportunity_actual_propensity=decomp['forecast_exposure_actual_rate'])
  for n in ['forecast_onbase_yield','actual_onbase_yield','PA_contribution','onbase_yield_contribution','three_factor_residual']:x[n]=None
  x['three_factor_status']='MISSING_OR_ZERO_PA_OR_PROXY'
  if decomp['status']=='AVAILABLE' and all(finite(v) and v>0 for v in [fp,pa]):
   fy=fo/fp;ay=ao/pa;midrate=(decomp['forecast_rate']+decomp['actual_rate'])/2;playing=(fp-pa)*(fy+ay)/2*midrate;yield_effect=(fy-ay)*(fp+pa)/2*midrate;res=decomp['error']-playing-yield_effect-decomp['skill_contribution']
   if abs(res)>1e-8*max(1,abs(decomp['error'])):raise ValueError('SB hierarchical decomposition failed')
   x.update(forecast_onbase_yield=fy,actual_onbase_yield=ay,PA_contribution=playing,onbase_yield_contribution=yield_effect,three_factor_residual=res,three_factor_status='AVAILABLE')
  out.append(x)
 return out

def sb_cohorts(d):
 cc=['all','prior_workload_'+d['prior_workload']]
 if d['established_runner']:cc.append('established_runner')
 if finite(d['prior_SB']) and d['prior_SB']==0:cc.append('prior_zero_SB')
 if d['full_candidate_supported']:cc.append('supported_candidate_only')
 return cc

def sb_summary(rows):
 bykey=defaultdict(dict)
 for d in rows:bykey[d['season'],d['mlbam_id']][d['method']]=d
 groups=defaultdict(list)
 for mm in bykey.values():
  if set(mm)!=set(P_METHODS):raise ValueError('Incomplete SB paired-method domain')
  # A decomposition comparison always uses identical eligible components for all methods.
  if not all(d['status']=='AVAILABLE' for d in mm.values()):continue
  for d in mm.values():
   for cohort in sb_cohorts(d):groups[d['season'],cohort,d['method']].append(d)
 out=[];three=[]
 for (year,cohort,method),rr in sorted(groups.items()):
  n=len(rr);m=lambda name:mean([d[name] for d in rr]);total=mean([d['error']**2 for d in rr]);opp=mean([d['opportunity_contribution']**2 for d in rr]);prop=mean([d['propensity_contribution']**2 for d in rr]);interaction=mean([2*d['opportunity_contribution']*d['propensity_contribution'] for d in rr])
  if abs(total-opp-prop-interaction)>1e-7*max(1,total):raise ValueError('SB MSE reconstruction failed')
  out.append(dict(season=year,split=phase(year),cohort=cohort,method=method,n=n,membership_sha256=hash_ids(rr),MAE=mean([abs(d['error']) for d in rr]),RMSE=math.sqrt(total),bias=m('error'),mean_opportunity_contribution=m('opportunity_contribution'),mean_propensity_contribution=m('propensity_contribution'),opportunity_MSE=opp,propensity_MSE=prop,interaction_MSE=interaction,total_MSE=total,mean_projected_onbase_proxy=m('projected_onbase_proxy'),mean_actual_onbase_proxy=m('actual_onbase_proxy')))
  tt=[d for d in rr if d['three_factor_status']=='AVAILABLE'];terms=['PA_contribution','onbase_yield_contribution','propensity_contribution'];v=dict(season=year,split=phase(year),cohort=cohort,method=method,n=len(tt),membership_sha256=hash_ids(tt))
  for name in terms:v['mean_'+name]=mean([d[name] for d in tt]);v['MSE_'+name]=mean([d[name]**2 for d in tt])
  for i,a in enumerate(terms):
   for b in terms[i+1:]:v['interaction_'+a+'__'+b]=mean([2*d[a]*d[b] for d in tt])
  total3=mean([d['error']**2 for d in tt]);parts=[z for n,z in v.items() if n.startswith(('MSE_','interaction_'))];reconstructed=sum(parts) if parts and all(finite(z) for z in parts) else None
  if total3 is not None and abs(total3-reconstructed)>1e-7*max(1,total3):raise ValueError('SB three-factor MSE reconstruction failed')
  v.update(total_MSE=total3,reconstructed_MSE=reconstructed);three.append(v)
 return out,three

def largest_pitcher_misses(rows):
 gg=defaultdict(list);out=[]
 for d in rows:
  if finite(d['candidate_error_OUTS']):gg[d['season'],'all','candidate_error_OUTS'].append(d)
  if finite(d['magnitude_error_OUTS']):gg[d['season'],d['observed_branch'],'magnitude_error_OUTS'].append(d)
 for (year,cohort,metric),rr in sorted(gg.items()):
  total=sum(d[metric]**2 for d in rr)
  for rank,d in enumerate(sorted(rr,key=lambda d:(-d[metric]**2,d['mlbam_id']))[:25],1):out.append(d|dict(outlier_cohort=cohort,rank_metric=metric,rank=rank,share_of_cohort_squared_error=d[metric]**2/total if total>0 else 0.))
 return out

def largest_sb_misses(rows):
 gg=defaultdict(list);out=[]
 for d in rows:
  if not finite(d['error']):continue
  gg[d['season'],d['method'],'all'].append(d)
  if d['established_runner']:gg[d['season'],d['method'],'established_runner'].append(d)
 for (year,method,cohort),rr in sorted(gg.items()):
  total=sum(d['error']**2 for d in rr)
  for rank,d in enumerate(sorted(rr,key=lambda d:(-d['error']**2,d['mlbam_id']))[:25],1):out.append(d|dict(outlier_cohort=cohort,rank=rank,share_of_cohort_squared_error=d['error']**2/total if total>0 else 0.))
 return out
