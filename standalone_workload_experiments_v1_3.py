"""Separate probability-input and workload-change experiments; no classification-policy changes."""
import copy,hashlib,json
import numpy as np
from standalone_models_v1_0 import Target,fit,predict,finite,feature_names,fit_transform,transform
from standalone_opportunity_v1_1 import enrich,DERIVED
from standalone_role_workload_v1_2 import prior_role
DISCLOSURE='2026 has been reviewed during prior releases. It is disclosed evaluation data, not an untouched holdout. All v1.3 selection uses historical folds only.'
METHODS=['frozen_v1_2','prior_probability_control','categorical_probability_candidate','workload_change_candidate','selected_probability_experiment','selected_change_experiment']

def anchor(r,s):
 metric='PA' if r['player_type']=='hitter' else 'OUTS';v=r.get('x_actual_lag1_'+metric)
 if not finite(v) or v<0:return None
 return float(v)*(s['source_2020_multiplier'] if r.get('source_season_lag1')==2020 else 1.)

def change_config(base,role):
 c=copy.deepcopy(base);c['actual_features'][role]=sorted(set(c['actual_features'][role]+DERIVED));return c

def change_rows(rows,role,s):
 result=enrich([r for r in rows if r['player_type']==role],role);metric='PA' if role=='hitter' else 'OUTS'
 for r in result:
  a=anchor(r,s);v=r.get('y_'+metric) if r.get('y_eligible_'+metric) else None;g=r.get('y_G') if r.get('y_eligible_G') else None
  delta=v-a if a is not None and finite(v) and finite(g) and g>0 else None
  r['change_anchor']=a;r['change_delta']=delta
  for name,value in [('GAIN',delta if delta is not None and delta>0 else None),('LOSS',-delta if delta is not None and delta<=0 else None)]:r['y_'+name]=value;r['y_eligible_'+name]=int(value is not None)
 return result

def sigmoid(z):return np.exp(-np.logaddexp(0.,-z))
def fit_direction(rows,names,c,s):
 known=[r for r in rows if r['change_delta'] is not None];y=np.array([float(r['change_delta']>0) for r in known]);positive=int(y.sum());n=len(y);frequency=(positive+1)/(n+2)
 model=dict(status='TRAINING_FREQUENCY_FALLBACK',n_fit=n,positive_rows=positive,non_growth_rows=n-positive,frequency=frequency,fit_years=sorted({r['target_season'] for r in known}),preprocessing=None,coefficients=None,iterations=0)
 if n<s['minimum_change_rows'] or min(positive,n-positive)<s['minimum_direction_class_rows']:return model
 state=fit_transform(known,names,c);x=transform(known,state,c);w=np.zeros(x.shape[1]);w[0]=np.log(frequency/(1-frequency));penalty=s['direction_penalty']
 def objective(coef):
  z=x@coef;return float(np.mean(np.logaddexp(0.,z)-y*z)+.5*penalty*(coef[1:]**2).sum())
 loss=objective(w);iterations=0
 for i in range(s['direction_iterations']):
  grad=x.T@(sigmoid(x@w)-y)/n;grad[1:]+=penalty*w[1:];norm=float((grad**2).sum())
  if norm<1e-12:break
  step=1.
  for _ in range(30):
   candidate=w-step*grad;value=objective(candidate)
   if np.isfinite(value) and value<=loss-1e-4*step*norm:break
   step*=.5
  else:raise ValueError('Growth classifier failed finite descent')
  w=candidate;loss=value;iterations=i+1
 if not np.isfinite(w).all():raise ValueError('Nonfinite growth coefficients')
 model.update(status='FITTED',preprocessing=state,coefficients=w.tolist(),iterations=iterations,training_objective=loss);return model

def fit_change(rows,allow,base,s):
 bundle={};audit=[]
 for role in ['hitter','pitcher']:
  rr=change_rows([r for r in rows if r['target_season']!=2020],role,s);c=change_config(base,role);c['minimum_fit_rows']=s['minimum_change_rows'];aa=allow+['x_actual_lag1_'+m for m in DERIVED];t=Target(role,'GAIN','GAIN',None,0,s['volume_caps'][role],0);names=feature_names(aa,t,c);direction=fit_direction(rr,names,c,s);magnitudes={}
  for name in ['GAIN','LOSS']:
   target=Target(role,name,name,None,0,s['volume_caps'][role],0);m=fit(rr,target,aa,c);magnitudes[name]=dict(target=target.__dict__,model=m);audit.append(dict(player_type=role,component=name,n_fit=m['n_fit'],fit_years=m['fit_target_seasons'],status=m['ridge_status']))
  bundle[role]=dict(direction=direction,magnitudes=magnitudes,config=c);audit.append(dict(player_type=role,component='GROWTH_DIRECTION',n_fit=direction['n_fit'],fit_years=direction['fit_years'],status=direction['status']))
 return bundle,audit

def predict_change(bundle,rows,s):
 out={}
 for role,b in bundle.items():
  rr=enrich([r for r in rows if r['player_type']==role],role);m=b['direction'];p=np.full(len(rr),m['frequency']) if m['coefficients'] is None else sigmoid(transform(rr,m['preprocessing'],b['config'])@np.array(m['coefficients']));mag={}
  for name,state in b['magnitudes'].items():_,mag[name]=predict(state['model'],rr,Target(**state['target']),b['config'])
  for i,r in enumerate(rr):
   a=anchor(r,s);raw_gain=mag['GAIN'][i];raw_loss=mag['LOSS'][i];gain=None if a is None or raw_gain is None else min(max(0.,s['volume_caps'][role]-a),raw_gain);loss=None if a is None or raw_loss is None else min(a,raw_loss);v=None if a is None or gain is None or loss is None else min(s['volume_caps'][role],max(0.,a+p[i]*gain-(1-p[i])*loss))
   out[r['target_season'],role,r['mlbam_id']]=dict(anchor=a,growth_probability=float(p[i]),training_growth_frequency=m['frequency'],raw_GAIN=raw_gain,raw_LOSS=raw_loss,conditional_GAIN=gain,conditional_LOSS=loss,conditional_volume=v,support='AVAILABLE' if v is not None else 'FROZEN_FORECAST_FALLBACK')
 return out

def gates(history,origin,s):
 result={}
 for cohort,minrows in [('all',s['minimum_validation_rows']),('guard',s['minimum_guard_rows'])]:
  valid=[h for h in history if h['season']<origin and h['season']!=2020 and h['cohort']==cohort and h['n']>=minrows];stats={};adopt=False;reason='INSUFFICIENT_EARLIER_FOLDS'
  if len(valid)>=s['minimum_selection_folds']:
   stats={name:float(np.mean([h[name] for h in valid])) for name in ['baseline_mse','candidate_mse','baseline_mae','candidate_mae']};gain=s['minimum_workload_improvement'] if cohort=='all' else 0.;adopt=stats['baseline_mse']>0 and stats['candidate_mse']<=stats['baseline_mse']*(1-gain) and stats['candidate_mae']<=stats['baseline_mae']*(1+s['maximum_workload_mae_degradation']);reason='EARLIER_FOLDS_GATE_PASSED' if adopt else 'EARLIER_FOLDS_GATE_REJECTED'
  result[cohort]=dict(adopt=bool(adopt),validation_seasons=[h['season'] for h in valid],reason=reason,**stats)
 return dict(adopt=all(g['adopt'] for g in result.values()),gates=result)

def volume_overlay(old,value,role):
 volume='PA' if role=='hitter' else 'OUTS';out=dict(old)
 if finite(value) and finite(old.get(volume)) and old[volume]>0:
  counts=['PA','AB','H','1B','2B','3B','HR','BB','HBP','SF','SH','R','RBI','SB'] if role=='hitter' else ['OUTS','IP','H','ER','BB','SO','HR','W','HLD','QS']
  for name in counts:
   if finite(out.get(name)):out[name]*=value/old[volume]
  if value==0:
   for name in (['AVG','OBP','SLG','OPS'] if role=='hitter' else ['ERA','WHIP']):out[name]=None
 return out

def effective(value,old):return float(value) if finite(value) and finite(old) and old>0 else old

def gate_statistics(season,cohort,items):
 e=np.array([(b-a,v-a) for pid,a,b,v in items]);return dict(season=season,cohort=cohort,n=len(items),membership_sha256=hashlib.sha256(json.dumps([pid for pid,a,b,v in items]).encode()).hexdigest(),baseline_mse=float((e[:,0]**2).mean()),candidate_mse=float((e[:,1]**2).mean()),baseline_mae=float(abs(e[:,0]).mean()),candidate_mae=float(abs(e[:,1]).mean()))
