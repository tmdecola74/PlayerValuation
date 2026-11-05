"""Categorical role forecasts and chronological mixture-of-role workload experts."""
import copy,hashlib,json
import numpy as np
from standalone_models_v1_0 import Target,fit,predict,finite,feature_names,fit_transform,transform
from standalone_opportunity_v1_1 import role_of,enrich,DERIVED
ROLES=['STARTER','RELIEVER','SWING']
PROB_FEATURES=['role_probability_'+r for r in ROLES]
DISCLOSURE='2026 was reviewed during v1.0/v1.1 development. It is a disclosed evaluation set, not an untouched holdout; v1.2 choices use historical folds only.'

def prior_role(r):return role_of(r.get('x_actual_lag1_G'),r.get('x_actual_lag1_GS'))
def actual_role(r):return role_of(r.get('y_G') if r.get('y_eligible_G') else None,r.get('y_GS') if r.get('y_eligible_GS') else None)
def prepare(rows):return enrich([r for r in rows if r['player_type']=='pitcher'],'pitcher')
def role_config(base):
 c=copy.deepcopy(base);c['actual_features']['pitcher']=sorted(set(c['actual_features']['pitcher']+DERIVED+['G','GS','SV','HLD']));c['context_features']=sorted(set(c['context_features']+PROB_FEATURES));return c

def softmax(z):
 z=z-z.max(axis=1,keepdims=True);v=np.exp(z);return v/v.sum(axis=1,keepdims=True)
def role_baseline(rows,priors,mass):
 probabilities=[];predicted=[]
 for r in rows:
  prior=prior_role(r);p=np.array(priors,dtype=float)
  if prior in ROLES:p=(1-mass)*p;p[ROLES.index(prior)]+=mass
  probabilities.append(p);predicted.append(prior if prior in ROLES else ROLES[int(np.argmax(p))])
 return np.array(probabilities).reshape((-1,3)),predicted

def fit_roles(rows,allow,base,settings):
 rr=prepare([r for r in rows if r['target_season']!=2020 and actual_role(r) in ROLES]);c=role_config(base);classes=[actual_role(r) for r in rr];counts=[classes.count(role) for role in ROLES];priors=((np.array(counts)+1)/(len(rr)+3)).tolist()
 model=dict(status='INSUFFICIENT_CATEGORICAL_SUPPORT',n_fit=len(rr),class_order=ROLES,class_counts=counts,priors=priors,fit_target_seasons=sorted({r['target_season'] for r in rr}),preprocessing=None,coefficients=None,config=c,iterations=0)
 if len(rr)<settings['minimum_role_fit_rows'] or min(counts)<settings['minimum_role_class_rows']:return model
 names=feature_names(allow+['x_actual_lag1_'+m for m in DERIVED],Target('pitcher','role','OUTS',None,0,900,0),c);state=fit_transform(rr,names,c);x=transform(rr,state,c);y=np.eye(3)[[ROLES.index(v) for v in classes]];w=np.zeros((x.shape[1],3));w[0]=np.log(priors);w[0]-=w[0].mean();penalty=settings['softmax_penalty']
 def objective(w):
  z=x@w;mx=z.max(axis=1);logsum=mx+np.log(np.exp(z-mx[:,None]).sum(axis=1));return float(np.mean(logsum-(y*z).sum(axis=1))+.5*penalty*(w[1:]**2).sum())
 loss=objective(w);steps=0
 for iteration in range(settings['softmax_iterations']):
  grad=x.T@(softmax(x@w)-y)/len(rr);grad[1:]+=penalty*w[1:];norm=float((grad*grad).sum())
  if norm<1e-12:break
  step=1.
  for _ in range(30):
   candidate=w-step*grad;candidate-=candidate.mean(axis=1,keepdims=True);value=objective(candidate)
   if np.isfinite(value) and value<=loss-1e-4*step*norm:break
   step*=.5
  else:raise ValueError('Categorical optimizer could not make a finite descent step')
  w=candidate;loss=value;steps=iteration+1
 if not np.isfinite(w).all():raise ValueError('Nonfinite categorical coefficients')
 model.update(status='FITTED',preprocessing=state,coefficients=w.tolist(),iterations=steps,training_objective=loss);return model

def predict_roles(model,rows,settings):
 rr=prepare(rows);base,base_classes=role_baseline(rr,model['priors'],settings['prior_role_probability_mass'])
 if model['status']!='FITTED':return base,base_classes,base.copy(),list(base_classes)
 x=transform(rr,model['preprocessing'],model['config']);p=softmax(x@np.array(model['coefficients']));return base,base_classes,p,[ROLES[int(i)] for i in np.argmax(p,axis=1)]

def probability_metrics(rows,base,bclasses,cat,cclasses,cohort):
 ix=[i for i,r in enumerate(rows) if actual_role(r) in ROLES and (cohort=='all' or prior_role(r) in ROLES)]
 if not ix:return dict(n=0)
 truth=np.array([ROLES.index(actual_role(rows[i])) for i in ix]);one=np.eye(3)[truth];out=dict(n=len(ix),membership_sha256=hashlib.sha256(json.dumps([str(rows[i]['mlbam_id']) for i in ix]).encode()).hexdigest())
 for name,p,classes in [('baseline',base,bclasses),('categorical',cat,cclasses)]:
  pp=p[ix];correct=np.array([classes[i]==ROLES[t] for i,t in zip(ix,truth)]);recalls=[float(correct[truth==k].mean()) for k in range(3) if np.any(truth==k)]
  out.update({name+'_brier':float(((pp-one)**2).sum(axis=1).mean()),name+'_logloss':float(-np.log(np.clip(pp[np.arange(len(ix)),truth],1e-15,1)).mean()),name+'_accuracy':float(correct.mean()),name+'_balanced_accuracy':float(np.mean(recalls))})
 return out

def choose_role(history,origin,s):
 decisions={}
 for cohort,minrows in [('all',s['minimum_validation_rows']),('known_prior',s['minimum_known_prior_rows'])]:
  valid=[h for h in history if h['season']<origin and h['season']!=2020 and h['cohort']==cohort and h['model_fitted'] and h['n']>=minrows];reason='INSUFFICIENT_EARLIER_FOLDS';adopt=False;details={}
  if len(valid)>=s['minimum_selection_folds']:
   for name in ['baseline','categorical']:
    for metric in ['brier','logloss','accuracy','balanced_accuracy']:details[name+'_'+metric]=float(np.mean([h[name+'_'+metric] for h in valid]))
   adopt=details['categorical_brier']<=details['baseline_brier']*(1-s['minimum_probability_improvement']) and details['categorical_logloss']<=details['baseline_logloss']*(1+s['maximum_logloss_degradation']) and details['categorical_accuracy']+1e-12>=details['baseline_accuracy'] and details['categorical_balanced_accuracy']+1e-12>=details['baseline_balanced_accuracy'];reason='EARLIER_FOLDS_GATE_PASSED' if adopt else 'EARLIER_FOLDS_GATE_REJECTED'
  decisions[cohort]=dict(adopt=bool(adopt),reason=reason,validation_seasons=[h['season'] for h in valid],**details)
 return dict(candidate='categorical' if all(d['adopt'] for d in decisions.values()) else 'prior_role',gates=decisions)

def with_probabilities(rows,probabilities):
 if len(rows)!=len(probabilities):raise ValueError('Probability row mismatch')
 out=prepare(rows)
 for r,p in zip(out,probabilities):
  if len(p)!=3 or not np.isfinite(p).all() or min(p)<0 or abs(sum(p)-1)>1e-8:raise ValueError('Invalid role probability vector')
  for name,value in zip(PROB_FEATURES,p):r[name]=float(value)
 return out

def fit_workload(rows,allow,base,settings):
 c=role_config(base);eligible=[r for r in rows if r['player_type']=='pitcher' and r['target_season']!=2020 and r.get('y_eligible_OUTS') and finite(r.get('y_OUTS')) and r.get('y_eligible_G') and finite(r.get('y_G')) and r['y_G']>0];target=Target('pitcher','OUTS','OUTS',None,0,900,0);aa=allow+['x_actual_lag1_'+m for m in DERIVED]+PROB_FEATURES;c['minimum_fit_rows']=settings['minimum_expert_rows'];pool=fit(eligible,target,aa,c);experts={}
 for role in ROLES:
  rr=[r for r in eligible if actual_role(r)==role];m=fit(rr,target,aa,c);experts[role]=dict(model=m,use_pooled=m['n_fit']<settings['minimum_expert_rows'],status='POOLED_FALLBACK' if m['n_fit']<settings['minimum_expert_rows'] else m['ridge_status'])
 return dict(pooled=pool,experts=experts,config=c,target=target.__dict__)

def predict_workload(bundle,rows):
 t=Target(**bundle['target']);values={}
 for role,s in bundle['experts'].items():_,values[role]=predict(bundle['pooled'] if s['use_pooled'] else s['model'],rows,t,bundle['config'])
 mixture=[]
 for i,r in enumerate(rows):
  v=[values[role][i] for role in ROLES];mixture.append(None if any(x is None for x in v) else sum(r[name]*x for name,x in zip(PROB_FEATURES,v)))
 return mixture,values

def choose_workload(history,origin,s):
 gates={}
 for cohort,minrows in [('all',s['minimum_validation_rows']),('prior_starter',s['minimum_prior_starter_rows'])]:
  valid=[h for h in history if h['season']<origin and h['season']!=2020 and h['cohort']==cohort and h['n']>=minrows];adopt=False;reason='INSUFFICIENT_EARLIER_FOLDS';stats={}
  if len(valid)>=s['minimum_selection_folds']:
   stats={name:float(np.mean([h[name] for h in valid])) for name in ['baseline_mse','candidate_mse','baseline_mae','candidate_mae']};improve=s['minimum_workload_improvement'] if cohort=='all' else 0.;adopt=stats['baseline_mse']>0 and stats['candidate_mse']<=stats['baseline_mse']*(1-improve) and stats['candidate_mae']<=stats['baseline_mae']*(1+s['maximum_workload_mae_degradation']);reason='EARLIER_FOLDS_GATE_PASSED' if adopt else 'EARLIER_FOLDS_GATE_REJECTED'
  gates[cohort]=dict(adopt=bool(adopt),reason=reason,validation_seasons=[h['season'] for h in valid],**stats)
 return dict(adopt=all(g['adopt'] for g in gates.values()),gates=gates)

def overlay(old,value,adopt):
 v=dict(old)
 if adopt and finite(value) and finite(old.get('OUTS')) and old['OUTS']>0:
  for name in ['OUTS','IP','H','ER','BB','SO','HR','W','HLD','QS']:
   if finite(v.get(name)):v[name]*=value/old['OUTS']
  if value==0:v['ERA']=None;v['WHIP']=None
 # SV is always the exact frozen v1.1 value, even with accepted innings changes.
 return v
