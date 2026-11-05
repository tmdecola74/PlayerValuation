"""Independent holds opportunity, chronological features, and dual-baseline gates."""
import copy,hashlib,json
from collections import defaultdict
import numpy as np
from standalone_models_v1_0 import Target,finite,fit,predict,feature_names,fit_transform,transform
from standalone_opportunity_v1_1 import enrich,DERIVED
from standalone_role_workload_v1_2 import ROLES,prior_role
from workload_experiments_io_v1_3 import probability_bank,iter_csv
from standalone_io_v1_0 import load
from standalone_combined_v1_4 import near

DISCLOSURE='2026 is previously reviewed disclosed evaluation data. All v1.5 fitting and selection use historical target seasons only; 2020 target season is stress-only.'
METHODS=['frozen_v1_2','combined_v1_4','holds_opportunity_candidate','selected_v1_5']
PROBS=['role_probability_'+r for r in ROLES]

def prepared(c):
 rows=list(c['rows'].values());bank=probability_bank(c['baseline'],rows,load(c['baseline']/'freeze_manifest.json'));out=[];participant={}
 for d in iter_csv(c['source']/'change_predictions.csv'):
  k=(int(d['season']),d['player_type'],d['mlbam_id']);p=None if d['participation_probability']=='' else float(d['participation_probability'])
  if k in participant or (p is not None and (not finite(p) or not 0<=p<=1)):raise ValueError('Invalid frozen participation')
  participant[k]=p
 for r in enrich([r for r in rows if r['player_type']=='pitcher'],'pitcher'):
  # Aliases support the conditional positive-rate historical baseline without
  # turning observed zero holds into a zero positive-case rate.
  for lag in [1,2,3]:
   g,gs,h=(r.get(f'x_actual_lag{lag}_'+m) for m in ['G','GS','HLD'])
   rel=g-gs if finite(g) and finite(gs) and g>0 and 0<=gs<=g else None
   r[f'x_actual_lag{lag}_RELIEF_G']=rel
   r[f'x_actual_lag{lag}_POS_HLD']=h if finite(h) and h>0 and finite(rel) and rel>0 else None
  k=(r['target_season'],'pitcher',r['mlbam_id']);state=bank[k[0],k[2]]
  for i,name in enumerate(PROBS):r[name]=state['categorical']['probabilities'][i]
  if k[0]>=2019 and k not in participant:raise ValueError('Missing participation forecast')
  r['frozen_participation']=participant.get(k);out.append(r)
 return out

def model_config(base,s):
 c=copy.deepcopy(base);c['minimum_fit_rows']=s['minimum_fit_rows'];c['actual_features']['pitcher']=sorted(set(c['actual_features']['pitcher']+DERIVED+['G','GS','SV','HLD','RELIEF_G']));c['context_features']=sorted(set(c['context_features']+PROBS));c['volume_metrics']=sorted(set(c['volume_metrics']+['RELIEF_G']));return c

def training_rows(rows,truth):
 out=[]
 for source in rows:
  r=copy.deepcopy(source);k=(r['target_season'],'pitcher',r['mlbam_id'])
  for m in ['G','GS','HLD']:
   a=truth.get(k+(m,));flag=r.get('y_eligible_'+m,False);v=r.get('y_'+m)
   if bool(flag)!=(a is not None) or (flag and not near(v,a)):raise ValueError('Frozen matrix/actual '+m+' label disagreement')
   r['y_'+m]=a;r['y_eligible_'+m]=int(a is not None)
  g,gs,h=(r['y_'+m] for m in ['G','GS','HLD']);valid=finite(g) and finite(gs) and g>0 and 0<=gs<=g;rel=g-gs if valid else None
  if finite(g) and finite(gs) and not 0<=gs<=g:raise ValueError('Invalid official G/GS vector')
  r['y_RELIEF_G']=rel;r['y_eligible_RELIEF_G']=int(rel is not None)
  support=finite(rel) and rel>0 and finite(h)
  r['y_ANY_HOLD']=int(h>0) if support else None;r['y_eligible_ANY_HOLD']=int(support)
  r['y_POS_HLD']=h if support and h>0 else None;r['y_eligible_POS_HLD']=int(support and h>0);out.append(r)
 return out

def sigmoid(z):return np.exp(-np.logaddexp(0.,-z))
def fit_occurrence(rows,names,c,s):
 rr=[r for r in rows if r.get('y_eligible_ANY_HOLD')];yy=[r['y_ANY_HOLD'] for r in rr];counts=[yy.count(0),yy.count(1)];frequency=(sum(yy)+1)/(len(yy)+2)
 m=dict(n_fit=len(rr),class_counts=counts,fit_years=sorted({r['target_season'] for r in rr}),frequency=frequency,preprocessing=None,coefficients=None,status='UNSUPPORTED_CLASS_COUNTS')
 if len(rr)<s['minimum_fit_rows'] or min(counts)<s['minimum_each_occurrence_class']:return m
 state=fit_transform(rr,names,c);x=transform(rr,state,c);y=np.array(yy);w=np.zeros(x.shape[1]);w[0]=np.log(frequency/(1-frequency));penalty=np.ones(len(w))*s['occurrence_penalty'];penalty[0]=0
 def objective(v):
  z=x@v;return float(np.mean(np.logaddexp(0.,z)-y*z)+.5*np.sum(penalty*v*v))
 loss=objective(w)
 for it in range(s['occurrence_iterations']):
  grad=x.T@(sigmoid(x@w)-y)/len(y)+penalty*w;norm=float(grad@grad)
  if norm<1e-12:break
  step=1.
  for _ in range(40):
   candidate=w-step*grad;value=objective(candidate)
   if np.isfinite(value) and value<=loss-1e-4*step*norm:break
   step*=.5
  else:raise ValueError('Holds occurrence solver failed finite descent')
  w=candidate;loss=value
 if not np.isfinite(w).all():raise ValueError('Invalid occurrence coefficients')
 m.update(preprocessing=state,coefficients=w.tolist(),status='FITTED');return m

def fit_holds(rows,truth,allow,base,s,origin):
 # Only actual labels for strictly earlier origins enter target construction or preprocessing.
 rr=training_rows([r for r in rows if r['target_season']<origin and r['target_season']!=2020],truth);c=model_config(base,s);aa=allow+['x_actual_lag1_'+m for m in DERIVED]+PROBS
 rel=Target('pitcher','RELIEF_G','RELIEF_G',None,0,s['maximum_relief_games'],0);pos=Target('pitcher','POS_HLD_RATE','POS_HLD','RELIEF_G',s['minimum_positive_relief_games'],1,s['positive_rate_prior_games']);relmodel=fit(rr,rel,aa,c);posmodel=fit(rr,pos,aa,c);occ=fit_occurrence(rr,feature_names(aa,rel,c),c,s)
 supported=occ['status']=='FITTED' and relmodel['n_fit']>=s['minimum_fit_rows'] and posmodel['n_fit']>=s['minimum_fit_rows']
 bundle=dict(config=c,relief_target=rel.__dict__,relief_model=relmodel,positive_target=pos.__dict__,positive_model=posmodel,occurrence=occ,supported=supported)
 audit=[dict(origin=origin,component=name,n_fit=m['n_fit'],fit_years=m.get('fit_target_seasons',m.get('fit_years')),status=m.get('ridge_status',m.get('status'))) for name,m in [('RELIEF_G',relmodel),('POS_HLD_RATE',posmodel),('ANY_HOLD',occ)]]
 if any(y>=origin or y==2020 for a in audit for y in a['fit_years']):raise ValueError('Holds fit chronology failure')
 return bundle,audit

def predict_holds(bundle,rows,s):
 _,games=predict(bundle['relief_model'],rows,Target(**bundle['relief_target']),bundle['config']);_,rates=predict(bundle['positive_model'],rows,Target(**bundle['positive_target']),bundle['config']);m=bundle['occurrence'];probs=[None]*len(rows) if m['coefficients'] is None else sigmoid(transform(rows,m['preprocessing'],bundle['config'])@np.array(m['coefficients'])).tolist();out={}
 for r,g,rate,p in zip(rows,games,rates,probs):
  part=r.get('frozen_participation');supported=bundle['supported'] and all(finite(x) for x in [g,rate,p,part]);v=min(s['maximum_holds'],max(0.,part*g*p*rate)) if supported else None
  out[r['target_season'],'pitcher',r['mlbam_id']]=dict(predicted_relief_G=g,hold_probability_given_relief=p,positive_hold_rate=rate,participation_probability=part,raw_candidate_HLD=v,supported=supported)
 return out

def gate_record(year,cohort,items):
 # Items use a common full pool, retaining explicit support counts.
 x=np.array([(b-a,v-a) for pid,a,b,v,supported in items]);return dict(season=year,cohort=cohort,n=len(items),supported=sum(bool(i[4]) for i in items),membership_sha256=__import__('hashlib').sha256(json.dumps([i[0] for i in items]).encode()).hexdigest(),baseline_mse=float(np.mean(x[:,0]**2)),candidate_mse=float(np.mean(x[:,1]**2)),baseline_mae=float(np.mean(abs(x[:,0]))),candidate_mae=float(np.mean(abs(x[:,1]))))

def choose(history,origin,s):
 comparisons={}
 for baseline in ['frozen_v1_2','combined_v1_4']:
  result={}
  for cohort,minimum in [('all',s['minimum_validation_rows']),('prior_relief',s['minimum_guard_rows']),('prior_holds',s['minimum_prior_holds_rows'])]:
   valid=[h for h in history.get(baseline,[]) if h['season']<origin and h['season']!=2020 and h['cohort']==cohort and h['n']>=minimum and h['supported']/h['n']>=s['minimum_candidate_fraction']];adopt=False;stats={}
   if len(valid)>=s['minimum_selection_folds']:
    stats={n:float(np.mean([h[n] for h in valid])) for n in ['baseline_mse','candidate_mse','baseline_mae','candidate_mae']};gain=s['minimum_mse_improvement'] if cohort=='all' else 0.;adopt=stats['baseline_mse']>0 and stats['candidate_mse']<=stats['baseline_mse']*(1-gain) and stats['candidate_mae']<=stats['baseline_mae']*(1+s['maximum_mae_degradation'])
   result[cohort]=dict(adopt=bool(adopt),validation_seasons=[h['season'] for h in valid],reason='EARLIER_FOLDS_GATE_PASSED' if adopt else 'REJECTED_OR_INSUFFICIENT_EARLIER_FOLDS',**stats)
  comparisons[baseline]=dict(adopt=all(r['adopt'] for r in result.values()),gates=result)
 return dict(adopt=all(r['adopt'] for r in comparisons.values()),comparisons=comparisons)

def fold_history(year,items,rows,truth,history,s):
 grouped=defaultdict(list)
 for k,d in items.items():
  if k[0]!=year or year==2026:continue
  a=truth.get(k+('HLD',))
  if a is None or not all(finite(d[m]) for m in METHODS[:3]):continue
  r=rows[k];cohorts=['all'];prior=r.get('x_actual_lag1_HLD')
  if prior_role(r)=='RELIEVER':cohorts.append('prior_relief')
  if finite(prior) and prior>=s['prior_holds_floor']:cohorts.append('prior_holds')
  for baseline in METHODS[:2]:
   for cohort in cohorts:grouped[baseline,cohort].append((k[2],a,d[baseline],d['holds_opportunity_candidate'],d['supported']))
 for (baseline,cohort),pp in grouped.items():history[baseline].append(gate_record(year,cohort,pp))
