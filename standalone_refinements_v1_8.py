"""Chronological branch calibration and independent unconditional SB propensity."""
import copy,math
from collections import defaultdict
import numpy as np
from standalone_models_v1_0 import finite,Target,fit,predict
from standalone_role_workload_v1_2 import prior_role
from standalone_growth_sb_v1_6 import prepared,opportunity,configuration,checked,CALENDAR
from standalone_holds_v1_5 import gate_record

DISCLOSURE='2026 was previously reviewed. Fitting and choices use historical data only; 2020 is stress-only and 2021 is retained.'

def settings_checked(s):
 expected={'version','minimum_calibration_rows','minimum_role_calibration_rows','calibration_prior_rows','maximum_magnitude_multiplier','minimum_SB_fit_rows','minimum_SB_opportunities','SB_rate_prior_opportunities','maximum_SB_rate','maximum_SB','low_history_PA','minimum_validation_rows','minimum_guard_rows','minimum_selection_folds','minimum_candidate_fraction','minimum_mse_improvement','maximum_mae_degradation','prior_SB_floor'}
 if set(s)!=expected or s['version']!='1.8.0':raise ValueError('Unexpected settings/schema')
 for n,v in s.items():
  if n=='version':continue
  if not finite(v) or v<=0:raise ValueError('Nonpositive setting: '+n)
 if s['minimum_selection_folds']<2 or s['minimum_candidate_fraction']>1 or s['minimum_mse_improvement']>=1:raise ValueError('Invalid selection controls')
 return s

def slope(samples,s,minimum):
 # Penalized through-origin multiplier, shrunk toward unchanged branch size.
 n=len(samples);xx=sum(x*x for x,y in samples);xy=sum(x*y for x,y in samples);penalty=s['calibration_prior_rows']*xx/n if n else 0
 supported=n>=minimum and xx>0;raw=(xy+penalty)/(xx+penalty) if supported else 1.
 return dict(n=n,multiplier=min(s['maximum_magnitude_multiplier'],max(0.,raw)),supported=supported,raw_multiplier=raw,sum_predicted_squared=xx,sum_predicted_observed=xy)

def fit_calibration(items,rows,actual,origin,s):
 groups=defaultdict(list);members=[]
 for k,d in sorted(items.items()):
  if k[1]!='pitcher' or k[0]>=origin or k[0]==2020:continue
  a=actual.get(k+('OUTS',));g=actual.get(k+('G',));an=d.get('anchor')
  if not d['supported'] or not all(finite(v) for v in [a,g,an]) or g<=0:continue
  branch='growth' if a>an else 'decline';prediction=d.get('conditional_growth_OUTS' if branch=='growth' else 'conditional_decline_OUTS');x=prediction-an if branch=='growth' and finite(prediction) else an-prediction if finite(prediction) else None
  if not finite(x) or x<0:continue
  role=prior_role(rows[k]);y=abs(a-an);groups[branch,'pooled'].append((x,y));groups[branch,role].append((x,y));members.append(dict(origin=origin,season=k[0],mlbam_id=k[2],prior_role=role,branch=branch,predicted_magnitude_OUTS=x,observed_magnitude_OUTS=y))
 pooled={b:slope(groups[b,'pooled'],s,s['minimum_calibration_rows']) for b in ['growth','decline']};experts={}
 for b in ['growth','decline']:
  experts[b]={}
  for role in ['STARTER','RELIEVER','SWING','UNKNOWN']:
   state=slope(groups[b,role],s,s['minimum_role_calibration_rows']);state['use_pooled']=not state['supported'];experts[b][role]=state
 return dict(origin=origin,fit_years=sorted({m['season'] for m in members}),pooled=pooled,experts=experts,supported=all(v['supported'] for v in pooled.values())),members

def calibrated(d,r,model,s,old_settings):
 an=d.get('anchor');p=d.get('growth_probability');part=d.get('participation_probability');g=d.get('conditional_growth_OUTS');de=d.get('conditional_decline_OUTS');base=d['baseline'];out=dict(metric='OUTS',baseline=base,candidate=base,raw_candidate=None,supported=False,support_status='CALIBRATION_OR_SOURCE_UNSUPPORTED',anchor=an,growth_probability=p,participation_probability=part,uncalibrated_growth_OUTS=g,uncalibrated_decline_OUTS=de,conditional_growth_OUTS=None,conditional_decline_OUTS=None,growth_multiplier=None,decline_multiplier=None,uncalibrated_candidate=d['candidate'])
 if not model['supported'] or not d['supported'] or not all(finite(v) for v in [an,p,part,g,de]) or g<an or de>an:return out
 role=prior_role(r);factors={}
 for branch in ['growth','decline']:
  expert=model['experts'][branch][role];factors[branch]=(model['pooled'][branch] if expert['use_pooled'] else expert)['multiplier']
 cap=old_settings['maximum_OUTS'];cg=min(cap,max(0.,an+factors['growth']*(g-an)));cd=min(cap,max(0.,an-factors['decline']*(an-de)));value=part*(p*cg+(1-p)*cd)
 out.update(candidate=value,raw_candidate=value,supported=True,support_status='AVAILABLE',conditional_growth_OUTS=cg,conditional_decline_OUTS=cd,growth_multiplier=factors['growth'],decline_multiplier=factors['decline']);return out

def fit_SB(rows,actual,allow,base,old,s,origin):
 rr=[]
 for src in rows:
  if src['player_type']!='hitter' or src['target_season']>=origin or src['target_season']==2020:continue
  r=copy.deepcopy(src);values={m:checked(r,actual,m) for m in ['PA','H','HR','BB','HBP','SB']};opp=opportunity(values)
  if finite(opp) and finite(values['PA']) and opp>values['PA']+1e-8:raise ValueError('Actual proxy exceeds PA')
  known=finite(values['PA']) and values['PA']>0 and finite(opp) and opp>0
  r['y_SB_ONBASE']=opp if known else None;r['y_eligible_SB_ONBASE']=int(known);rr.append(r)
 c=configuration(base,old,'hitter');c['minimum_fit_rows']=s['minimum_SB_fit_rows'];allow=allow+[CALENDAR]+[f'x_actual_lag{l}_'+m for l in [1,2,3] for m in ['SB_ONBASE','POS_SB']]
 target=Target('hitter','UNCONDITIONAL_SB_RATE','SB','SB_ONBASE',s['minimum_SB_opportunities'],s['maximum_SB_rate'],s['SB_rate_prior_opportunities']);model=fit(rr,target,allow,c)
 if any(y>=origin or y==2020 for y in model['fit_target_seasons']):raise ValueError('SB fit chronology failure')
 return dict(origin=origin,config=c,target=target.__dict__,model=model,fit_years=model['fit_target_seasons'],supported=model['ridge_status']=='FITTED')

def sb_predict(model,rows,vectors,s,items16):
 rr=[r for r in rows if r['player_type']=='hitter'];_,rates=predict(model['model'],rr,Target(**model['target']),model['config']);out={}
 for r,rate in zip(rr,rates):
  k=(r['target_season'],'hitter',r['mlbam_id']);base=vectors[k];opp=opportunity(base);supported=model['supported'] and finite(opp) and finite(rate);value=min(s['maximum_SB'],opp*rate) if supported else None
  out[k]=dict(metric='SB',baseline=base.get('SB'),candidate=value if supported else base.get('SB'),raw_candidate=value,supported=bool(supported),support_status='AVAILABLE' if supported else 'MISSING_OPPORTUNITY_OR_RATE_MODEL',projected_onbase_proxy=opp,unconditional_SB_rate=rate,uncalibrated_candidate=items16[k]['candidate'])
 return out

def cohort_names(role,r,s):
 cc=['all']
 if role=='pitcher':
  p=prior_role(r)
  if p=='STARTER':cc.append('prior_starter')
  if p=='RELIEVER':cc.append('prior_reliever')
 else:
  sb=r.get('x_actual_lag1_SB');pa=r.get('x_actual_lag1_PA')
  if finite(sb) and sb>=s['prior_SB_floor']:cc.append('prior_runner')
  if finite(sb) and sb==0:cc.append('prior_zero_SB')
  if not finite(pa) or pa<s['low_history_PA']:cc.append('low_history')
 return cc

def add_history(year,items,rows,actual,history,s):
 if year==2026:return
 groups=defaultdict(list)
 for k,d in items.items():
  if k[0]!=year:continue
  a=actual.get(k+(d['metric'],));b=d['baseline'];p=d['candidate']
  if not all(finite(v) for v in [a,b,p]):continue
  for cc in cohort_names(k[1],rows[k],s):groups[k[1],cc].append((k[2],a,b,p,d['supported']))
 for (role,cohort),pp in groups.items():history[role].append(gate_record(year,cohort,pp))

def selection(history,origin,role,s):
 cc=['all','prior_starter','prior_reliever'] if role=='pitcher' else ['all','prior_runner','prior_zero_SB','low_history'];gates={}
 for cohort in cc:
  rr=[h for h in history if h['season']<origin and h['season']!=2020 and h['cohort']==cohort and h['n']>=(s['minimum_validation_rows'] if cohort=='all' else s['minimum_guard_rows']) and h['supported']/h['n']>=s['minimum_candidate_fraction']];stats={};adopt=False
  if len(rr)>=s['minimum_selection_folds']:
   stats={n:float(np.mean([h[n] for h in rr])) for n in ['baseline_mse','candidate_mse','baseline_mae','candidate_mae']};gain=s['minimum_mse_improvement'] if cohort=='all' else 0;adopt=stats['baseline_mse']>0 and stats['candidate_mse']<=stats['baseline_mse']*(1-gain) and stats['candidate_mae']<=stats['baseline_mae']*(1+s['maximum_mae_degradation'])
  gates[cohort]=dict(adopt=bool(adopt),validation_seasons=[h['season'] for h in rr],reason='PASSED' if adopt else 'REJECTED_OR_INSUFFICIENT_PRIOR_FOLDS',**stats)
 return dict(adopt=all(g['adopt'] for g in gates.values()),gates=gates)
