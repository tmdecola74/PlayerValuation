"""Joint final-workload calibration with fixed source probabilities and caps."""
import math
from collections import defaultdict
import numpy as np
from standalone_models_v1_0 import finite
from standalone_role_workload_v1_2 import prior_role
from standalone_refinements_v1_8 import selection as selection18,add_history as add18

DISCLOSURE='2026 is previously reviewed disclosed evaluation data; historical fitting/selection only. 2020 is stress-only; 2021 is retained.'
METHODS=['frozen_v1_5','workload_candidate','selected_workload_experiment']

def settings_checked(s):
 integer=['minimum_calibration_rows','minimum_role_rows','solver_max_iterations','minimum_validation_rows','minimum_guard_rows','minimum_selection_folds','SB_minimum_bin_rows','SB_quantile_bins']
 if s.get('version')!='1.9.0':raise ValueError('Wrong settings version')
 for n,v in s.items():
  if n!='version' and (not finite(v) or v<=0):raise ValueError('Invalid setting: '+n)
 for n in integer:
  if int(s[n])!=s[n]:raise ValueError('Noninteger setting: '+n)
 if s['minimum_selection_folds']<2 or s['SB_quantile_bins']!=5 or s['minimum_candidate_fraction']>1 or s['minimum_mse_improvement']>=1:raise ValueError('Invalid fixed controls')
 return s

def branches(an,g,d,part,p,coef,cap):
 cg=np.minimum(cap,an+coef[0]*(g-an));cd=np.maximum(0.,an-coef[1]*(an-d));return part*(p*cg+(1-p)*cd)

def coordinate_minimum(const,slope,breaks,y,penalty,bound):
 """Exact minimum of a capped one-coordinate squared-error objective."""
 err=const-y;a=float(slope@slope)+penalty;b=float(slope@err)-penalty;c=float(err@err)+penalty
 events=sorted((float(t),i) for i,t in enumerate(breaks) if math.isfinite(t) and 0<=t<bound);lo=0.;best=(float('inf'),1.)
 def consider(hi,a,b,c,lo,best):
  v=min(hi,max(lo,-b/a)) if a>0 else lo;loss=a*v*v+2*b*v+c
  return (loss,v) if loss<best[0] else best
 for hi,i in events:
  best=consider(hi,a,b,c,lo,best);si=float(slope[i]);ei=float(err[i]);a-=si*si;b-=si*ei;c+=(ei+si*hi)**2-ei*ei;lo=hi
 best=consider(bound,max(a,penalty),b,c,lo,best);return best[1]

def solve_joint(samples,s,minimum,cap):
 model=dict(n=len(samples),growth_multiplier=1.,decline_multiplier=1.,supported=False,status='INSUFFICIENT_ROWS',iterations=0,fit_years=sorted({r['season'] for r in samples}),training_MSE_before=None,training_MSE_after=None,penalized_objective_before=None,penalized_objective_after=None)
 if len(samples)<minimum:return model
 an,g,d,part,p,y=[np.array([r[n] for r in samples],dtype=float) for n in ['anchor','growth','decline','participation','probability','actual']];dg=g-an;dd=an-d;sg=part*p*dg;sd=-part*(1-p)*dd
 if np.sum(sg*sg+sd*sd)==0:model['status']='NO_MAGNITUDE_INFORMATION';return model
 penalties=s['calibration_prior_rows']*np.maximum(np.array([np.mean(sg*sg),np.mean(sd*sd)]),1.);coef=np.ones(2)
 def objective(v):
  e=branches(an,g,d,part,p,v,cap)-y;return float(e@e+np.sum(penalties*(v-1.)**2))
 before=objective(coef);initial=branches(an,g,d,part,p,coef,cap)
 # A bounded quadratic warm start reduces collinearity-related solver stalls.
 # It is accepted only when it improves the exact deployed capped objective.
 x=np.column_stack([sg,sd]);h=x.T@x+np.diag(penalties);rhs=x.T@(y-part*an)+penalties;bound=s['maximum_multiplier'];warm=[];unconstrained=np.linalg.solve(h,rhs)
 if np.all((unconstrained>=0)&(unconstrained<=bound)):warm.append(unconstrained)
 for j in [0,1]:
  other=1-j
  for edge in [0.,bound]:
   v=np.zeros(2);v[j]=edge;v[other]=min(bound,max(0.,(rhs[other]-h[other,j]*edge)/h[other,other]));warm.append(v)
 for v in warm:
  if objective(v)<objective(coef):coef=v.copy()
 loss=objective(coef);converged=False
 for iteration in range(s['solver_max_iterations']):
  previous=coef.copy()
  cd=np.maximum(0.,an-coef[1]*dd);const=part*(p*an+(1-p)*cd);breaks=np.divide(cap-an,dg,out=np.full(len(an),np.inf),where=dg>0);coef[0]=coordinate_minimum(const,sg,breaks,y,float(penalties[0]),s['maximum_multiplier'])
  cg=np.minimum(cap,an+coef[0]*dg);const=part*(p*cg+(1-p)*an);breaks=np.divide(an,dd,out=np.full(len(an),np.inf),where=dd>0);coef[1]=coordinate_minimum(const,sd,breaks,y,float(penalties[1]),s['maximum_multiplier'])
  current=objective(coef)
  if not math.isfinite(current) or current>loss+1e-7*max(1.,loss):raise ValueError('Joint solver failed descent')
  loss=current
  if float(np.max(np.abs(coef-previous)))<=s['solver_tolerance']:converged=True;break
 model.update(growth_multiplier=float(coef[0]),decline_multiplier=float(coef[1]),supported=converged,status='CONVERGED' if converged else 'SOLVER_NOT_CONVERGED',iterations=iteration+1,training_MSE_before=float(np.mean((initial-y)**2)),training_MSE_after=float(np.mean((branches(an,g,d,part,p,coef,cap)-y)**2)),penalized_objective_before=before,penalized_objective_after=loss,penalty_growth=float(penalties[0]),penalty_decline=float(penalties[1]));return model

def eligible_source(d,cap):
 return d['supported'] and all(finite(d.get(n)) for n in ['anchor','growth_probability','participation_probability','conditional_growth_OUTS','conditional_decline_OUTS']) and 0<=d['conditional_decline_OUTS']<=d['anchor']<=d['conditional_growth_OUTS']<=cap

def fit_joint(items,rows,actual,origin,s,old):
 samples=[];cap=old['maximum_OUTS']
 for k,d in sorted(items.items()):
  if k[1]!='pitcher' or k[0]>=origin or k[0]==2020 or not eligible_source(d,cap):continue
  a=actual.get(k+('OUTS',));games=actual.get(k+('G',))
  if not finite(a) or not finite(games) or games<=0:continue
  samples.append(dict(season=k[0],mlbam_id=k[2],prior_role=prior_role(rows[k]),anchor=d['anchor'],growth=d['conditional_growth_OUTS'],decline=d['conditional_decline_OUTS'],participation=d['participation_probability'],probability=d['growth_probability'],actual=a))
 pooled=solve_joint(samples,s,s['minimum_calibration_rows'],cap);experts={}
 for role in ['STARTER','RELIEVER','SWING','UNKNOWN']:
  m=solve_joint([r for r in samples if r['prior_role']==role],s,s['minimum_role_rows'],cap);m['use_pooled']=not m['supported'];experts[role]=m
 return dict(origin=origin,fit_years=pooled['fit_years'],pooled=pooled,experts=experts,supported=pooled['supported']),[dict(origin=origin,**r) for r in samples]

def predict_joint(k,d,r,model,old):
 base=d['baseline'];out=dict(metric='OUTS',baseline=base,candidate=base,raw_candidate=None,supported=False,support_status='UNSUPPORTED_SOURCE_OR_CALIBRATION',anchor=d.get('anchor'),growth_probability=d.get('growth_probability'),participation_probability=d.get('participation_probability'),growth_multiplier=None,decline_multiplier=None,conditional_growth_OUTS=None,conditional_decline_OUTS=None,research_v1_6=d['candidate'])
 if not model['supported'] or not eligible_source(d,old['maximum_OUTS']):return out
 expert=model['experts'][prior_role(r)];m=model['pooled'] if expert['use_pooled'] else expert;an=d['anchor'];cg=min(old['maximum_OUTS'],an+m['growth_multiplier']*(d['conditional_growth_OUTS']-an));cd=max(0.,an-m['decline_multiplier']*(an-d['conditional_decline_OUTS']));v=d['participation_probability']*(d['growth_probability']*cg+(1-d['growth_probability'])*cd)
 out.update(candidate=v,raw_candidate=v,supported=True,support_status='AVAILABLE',growth_multiplier=m['growth_multiplier'],decline_multiplier=m['decline_multiplier'],conditional_growth_OUTS=cg,conditional_decline_OUTS=cd);return out

def selection(history,origin,s):return selection18(history,origin,'pitcher',s)
def add_history(year,items,rows,actual,history,s):add18(year,{k:d for k,d in items.items() if k[1]=='pitcher'},rows,actual,history,s)
