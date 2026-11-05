"""Separate prior-role-informed relative workload change and SB opportunity/rate models."""
import copy,json,math
from collections import defaultdict
import numpy as np
from standalone_models_v1_0 import Target,fit,predict,finite,feature_names,fit_transform,transform
from standalone_opportunity_v1_1 import enrich,DERIVED,role_of
from standalone_role_workload_v1_2 import ROLES,prior_role
from standalone_holds_v1_5 import prepared as pitcher_features

DISCLOSURE='2026 is previously reviewed disclosed evaluation data. v1.6 model fitting and selection use historical target seasons only. Target 2020 is stress-only.'
PROBS=['role_probability_'+r for r in ROLES]
CALENDAR='sb_calendar_era'
FULL_METHODS=['frozen_v1_5','selected_workload_experiment','selected_SB_experiment']
SCORE_METHODS=['frozen_v1_5','workload_candidate','SB_candidate','selected_workload_experiment','selected_SB_experiment']


def opportunity(v):
 if not all(finite(v.get(n)) for n in ['H','HR','BB','HBP']):return None
 if min(v[n] for n in ['H','HR','BB','HBP'])<0 or v['HR']>v['H']:raise ValueError('Invalid on-base proxy components')
 return v['H']-v['HR']+v['BB']+v['HBP']

def prepared(c,s):
 rr=pitcher_features(c)
 for r in enrich([r for r in c['rows'].values() if r['player_type']=='hitter'],'hitter'):
  r[CALENDAR]=int(r['target_season']>=s['SB_calendar_era_start'])
  for lag in [1,2,3]:
   prefix=f'x_actual_lag{lag}_';v=opportunity({n:r.get(prefix+n) for n in ['H','HR','BB','HBP']});sb=r.get(prefix+'SB');r[prefix+'SB_ONBASE']=v;r[prefix+'POS_SB']=sb if finite(sb) and sb>0 and finite(v) and v>0 else None
  rr.append(r)
 return rr

def anchor(r,s):
 v=r.get('x_actual_lag1_OUTS')
 if not finite(v) or v<0:return None
 return float(v)*(s['source_2020_multiplier'] if r.get('source_season_lag1')==2020 else 1.)

def checked(r,actual,metric):
 key=(r['target_season'],r['player_type'],r['mlbam_id'],metric);a=actual.get(key)
 if bool(r.get('y_eligible_'+metric,False))!=(a is not None) or (a is not None and (not finite(r.get('y_'+metric)) or abs(a-r['y_'+metric])>1e-9)):raise ValueError('Frozen target mask/value disagreement: '+str(key))
 return a

def configuration(base,s,role):
 c=copy.deepcopy(base);c['minimum_fit_rows']=s['minimum_fit_rows'];c['actual_features'][role]=sorted(set(c['actual_features'][role]+DERIVED+(['G','GS','HLD','SV'] if role=='pitcher' else ['PA','H','HR','BB','HBP','SB','SB_ONBASE','POS_SB'])));c['context_features']=sorted(set(c['context_features']+(PROBS if role=='pitcher' else [CALENDAR])));c['volume_metrics']=sorted(set(c['volume_metrics']+(['SB_ONBASE','POS_SB'] if role=='hitter' else [])));return c

def sigmoid(z):return np.exp(-np.logaddexp(0.,-z))
def binary(rows,label,names,c,s):
 rr=[r for r in rows if r.get('y_eligible_'+label)];ys=[r['y_'+label] for r in rr];cc=[ys.count(0),ys.count(1)];frequency=(sum(ys)+1)/(len(ys)+2);m=dict(label=label,n_fit=len(rr),class_counts=cc,fit_years=sorted({r['target_season'] for r in rr}),frequency=frequency,preprocessing=None,coefficients=None,status='UNSUPPORTED_CLASSES')
 if len(rr)<s['minimum_fit_rows'] or min(cc)<s['minimum_binary_class_rows']:return m
 state=fit_transform(rr,names,c);x=transform(rr,state,c);y=np.array(ys);w=np.zeros(x.shape[1]);w[0]=math.log(frequency/(1-frequency));penalty=np.ones(len(w))*s['binary_penalty'];penalty[0]=0
 def objective(v):
  z=x@v;return float(np.mean(np.logaddexp(0.,z)-y*z)+.5*np.sum(penalty*v*v))
 loss=objective(w)
 for _ in range(s['binary_iterations']):
  grad=x.T@(sigmoid(x@w)-y)/len(y)+penalty*w;norm=float(grad@grad)
  if norm<1e-12:break
  step=1.
  for _ in range(40):
   candidate=w-step*grad;value=objective(candidate)
   if np.isfinite(value) and value<=loss-1e-4*step*norm:break
   step*=.5
  else:raise ValueError('Binary solver failed finite descent')
  w=candidate;loss=value
 if not np.isfinite(w).all():raise ValueError('Nonfinite binary model')
 m.update(status='FITTED',preprocessing=state,coefficients=w.tolist());return m

def binary_predict(model,rows,c):
 return [None]*len(rows) if model['coefficients'] is None else sigmoid(transform(rows,model['preprocessing'],c)@np.array(model['coefficients'])).tolist()

def fit_models(rows,actual,allow,base,s,origin):
 # Target construction and all preprocessing occur after the chronological filter.
 before=[r for r in rows if r['target_season']<origin and r['target_season']!=2020];pitch=[];hit=[]
 for src in before:
  r=copy.deepcopy(src)
  if r['player_type']=='pitcher':
   v,g,gs=(checked(r,actual,m) for m in ['OUTS','G','GS']);a=anchor(r,s);known=a is not None and finite(v) and v>=0 and finite(g) and g>0;delta=math.log1p(v)-math.log1p(a) if known else None
   r['fit_role']=role_of(g,gs)
   for name,value in [('GROW',int(v>a) if known else None),('GROWTH_LOG',delta if known and delta>0 else None),('DECLINE_LOG',-delta if known and delta<=0 else None)]:r['y_'+name]=value;r['y_eligible_'+name]=int(value is not None)
   pitch.append(r)
  else:
   vals={m:checked(r,actual,m) for m in ['PA','H','HR','BB','HBP','SB']};opp=opportunity(vals);pa=vals['PA'];sb=vals['SB'];known=finite(pa) and pa>0 and finite(opp) and opp>0 and finite(sb)
   if finite(pa) and finite(opp) and opp>pa+1e-8:raise ValueError('On-base proxy exceeds actual PA')
   for name,value in [('SB_ONBASE',opp),('ANY_SB',int(sb>0) if known else None),('POS_SB',sb if known and sb>0 else None)]:r['y_'+name]=value;r['y_eligible_'+name]=int(value is not None)
   hit.append(r)
 result={};audit=[]
 for role,rr in [('pitcher',pitch),('hitter',hit)]:
  c=configuration(base,s,role);aa=allow+['x_actual_lag1_'+m for m in DERIVED]+(PROBS if role=='pitcher' else [CALENDAR]+[f'x_actual_lag{l}_'+m for l in [1,2,3] for m in ['SB_ONBASE','POS_SB']]);label='GROW' if role=='pitcher' else 'ANY_SB';dummy=Target(role,label,label,None,0,1,0);occ=binary(rr,label,feature_names(aa,dummy,c),c,s);audit.append(dict(origin=origin,experiment=role,component=label,n_fit=occ['n_fit'],fit_years=occ['fit_years'],status=occ['status']))
  if role=='pitcher':
   parts={}
   for name in ['GROWTH_LOG','DECLINE_LOG']:
    target=Target(role,name,name,None,0,math.log1p(s['maximum_OUTS']),0);pooled=fit(rr,target,aa,c);experts={}
    for group in ROLES:
     model=fit([r for r in rr if r['fit_role']==group],target,aa,c);use_pooled=model['n_fit']<s['minimum_expert_rows'];experts[group]=dict(model=model,use_pooled=use_pooled);audit.append(dict(origin=origin,experiment=role,component=name+'_'+group,n_fit=model['n_fit'],fit_years=model['fit_target_seasons'],status='POOLED_FALLBACK' if use_pooled else model['ridge_status']))
    parts[name]=dict(target=target.__dict__,pooled=pooled,experts=experts);audit.append(dict(origin=origin,experiment=role,component=name+'_POOLED',n_fit=pooled['n_fit'],fit_years=pooled['fit_target_seasons'],status=pooled['ridge_status']))
   supported=occ['status']=='FITTED' and all(p['pooled']['n_fit']>=s['minimum_fit_rows'] for p in parts.values());result[role]=dict(config=c,occurrence=occ,parts=parts,supported=supported)
  else:
   target=Target(role,'POS_SB_RATE','POS_SB','SB_ONBASE',s['minimum_positive_SB_opportunities'],s['maximum_SB_rate'],s['SB_rate_prior_opportunities']);model=fit(hit,target,aa,c);supported=occ['status']=='FITTED' and model['n_fit']>=s['minimum_fit_rows'];result[role]=dict(config=c,occurrence=occ,target=target.__dict__,model=model,supported=supported);audit.append(dict(origin=origin,experiment=role,component='POS_SB_RATE',n_fit=model['n_fit'],fit_years=model['fit_target_seasons'],status=model['ridge_status']))
 if any(y>=origin or y==2020 for a in audit for y in a['fit_years']):raise ValueError('Fit chronology violation')
 return result,audit

def predict_models(models,rows,base_vectors,s):
 result={}
 for role,m in models.items():
  rr=[r for r in rows if r['player_type']==role];prob=binary_predict(m['occurrence'],rr,m['config']);parts={}
  if role=='pitcher':
   for name,state in m['parts'].items():
    for group in ROLES:
     x=state['experts'][group];model=state['pooled'] if x['use_pooled'] else x['model'];_,parts[name,group]=predict(model,rr,Target(**state['target']),m['config'])
  else:_,rates=predict(m['model'],rr,Target(**m['target']),m['config'])
  for i,r in enumerate(rr):
   k=(r['target_season'],role,r['mlbam_id']);v=base_vectors[k];p=prob[i]
   if role=='pitcher':
    a=anchor(r,s);part=r.get('frozen_participation');supported=m['supported'] and a is not None and finite(part) and finite(p);grow=decline=None
    if supported:
     grows=[];declines=[]
     for group in ROLES:
      gl=parts['GROWTH_LOG',group][i];dl=parts['DECLINE_LOG',group][i];weight=r['role_probability_'+group]
      if not finite(gl) or not finite(dl):supported=False;break
      grows.append(weight*math.expm1(min(math.log1p(s['maximum_OUTS']),math.log1p(a)+gl)));declines.append(weight*min(s['maximum_OUTS'],max(0.,math.expm1(math.log1p(a)-dl))))
     if supported:grow=min(s['maximum_OUTS'],max(0.,sum(grows)));decline=min(s['maximum_OUTS'],max(0.,sum(declines)))
    conditional=min(s['maximum_OUTS'],max(0.,p*grow+(1-p)*decline)) if supported else None;raw=part*conditional if conditional is not None else None;volume=v.get('OUTS');usable=supported and finite(volume) and volume>0;value=raw if usable else volume
    result[k]=dict(metric='OUTS',raw_candidate=raw,candidate=value,supported=bool(usable),support_status='AVAILABLE' if usable else 'MISSING_ANCHOR_PARTICIPATION_OR_MODEL' if not supported else 'ZERO_OR_MISSING_BASELINE_OUTS',anchor=a,growth_probability=p,conditional_growth_OUTS=grow,conditional_decline_OUTS=decline,participation_probability=part)
   else:
    opp=opportunity(v);rate=rates[i];supported=m['supported'] and finite(opp) and finite(rate) and finite(p);raw=min(s['maximum_SB'],opp*p*rate) if supported else None
    result[k]=dict(metric='SB',raw_candidate=raw,candidate=raw if supported else v.get('SB'),supported=bool(supported),support_status='AVAILABLE' if supported else 'MISSING_OPPORTUNITY_OR_MODEL',projected_onbase_proxy=opp,any_SB_probability=p,positive_SB_rate=rate)
 return result


def selection(history,origin,role,s):
 guards=['all','prior_starter','prior_reliever'] if role=='pitcher' else ['all','prior_runner','prior_zero_SB'];result={}
 for cohort in guards:
  valid=[h for h in history if h['season']<origin and h['season']!=2020 and h['cohort']==cohort and h['n']>=(s['minimum_validation_rows'] if cohort=='all' else s['minimum_guard_rows']) and h['supported']/h['n']>=s['minimum_candidate_fraction']];stats={};adopt=False
  if len(valid)>=s['minimum_selection_folds']:
   stats={n:float(np.mean([h[n] for h in valid])) for n in ['baseline_mse','candidate_mse','baseline_mae','candidate_mae']};gain=s['minimum_mse_improvement'] if cohort=='all' else 0;adopt=stats['baseline_mse']>0 and stats['candidate_mse']<=stats['baseline_mse']*(1-gain) and stats['candidate_mae']<=stats['baseline_mae']*(1+s['maximum_mae_degradation'])
  result[cohort]=dict(adopt=bool(adopt),validation_seasons=[h['season'] for h in valid],reason='PASSED' if adopt else 'REJECTED_OR_INSUFFICIENT_PRIOR_FOLDS',**stats)
 return dict(adopt=all(x['adopt'] for x in result.values()),gates=result)


def add_history(year,items,rows,actual,history,s):
 groups=defaultdict(list)
 if year==2026:return
 for k,d in items.items():
  if k[0]!=year:continue
  a=actual.get(k+(d['metric'],));b=d['baseline'];candidate=d['candidate']
  if not all(finite(x) for x in [a,b,candidate]):continue
  role=k[1];r=rows[k];cohorts=['all']
  if role=='pitcher':
   pr=prior_role(r)
   if pr=='STARTER':cohorts.append('prior_starter')
   if pr=='RELIEVER':cohorts.append('prior_reliever')
  else:
   prior=r.get('x_actual_lag1_SB')
   if finite(prior) and prior>=s['prior_SB_floor']:cohorts.append('prior_runner')
   if finite(prior) and prior==0:cohorts.append('prior_zero_SB')
  for cohort in cohorts:groups[role,cohort].append((k[2],a,b,candidate,d['supported']))
 from standalone_holds_v1_5 import gate_record
 for (role,cohort),pp in groups.items():history[role].append(gate_record(year,cohort,pp))
