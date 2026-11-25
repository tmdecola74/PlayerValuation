"""Fixed recent-history feature, estimator, coherence and historical selection contract."""
import math,json,hashlib
from pathlib import Path,PureWindowsPath
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import load,sha,write

VERSION='1.23.0'
METRICS={'hitter':['PA','AB','H','1B','2B','3B','HR','R','RBI','SB','BB','HBP','SF','SH','AVG','OBP','SLG','OPS'],'pitcher':['OUTS','IP','H','ER','BB','SO','HR','W','SV','HLD','QS','ERA','WHIP','SV_plus_HLD']}
TARGETS={'hitter':['1B','2B','3B','HR'],'pitcher':['H','BB','ER','SO','HR']}
CHANGED={'hitter':['1B','2B','3B','HR','H','AVG','OBP','SLG','OPS'],'pitcher':['H','BB','ER','SO','HR','ERA','WHIP']}
GATE_METRICS={'hitter':['AVG','OPS','HR'],'pitcher':['ERA','WHIP','SO','HR']}
WEIGHTS={'equal':[1.,1.,1.],'recent':[3.,2.,1.],'strong':[5.,2.,1.]}
ARMS=['standard_'+w for w in WEIGHTS]+['expanded_'+w for w in WEIGHTS]+['bat_control_recent','bat_recent_exploratory']
SELECTABLE=['standard_recent','standard_strong','expanded_recent','expanded_strong']
CLASSIC={'hitter':['whiff_pct','chase_pct','zone_pct','ev','hardhit_pct','barrel_pct','xwobacon'],'pitcher':['whiff_pct','chase_pct','zone_pct','ev','hardhit_pct','barrel_pct','xwobacon','velocity','spin_rpm','extension_ft']}
CONTACT=['gb_pct','ld_pct','fb_pct','popup_pct','air_pct','launch_angle_sd','launch_angle_p10','launch_angle_p50','launch_angle_p90','launch_angle_below_zero_pct','launch_angle_ge50_pct','zone_contact_pct','outside_zone_contact_pct','contact_pct','zone_swing_pct','swinging_strike_pct','called_strike_plus_whiff_pct']
EXPANDED={'hitter':CONTACT,'pitcher':CONTACT+['pfx_x_mean','pfx_z_mean']}
BAT=['avg_bat_speed','hard_swing_rate','squared_up_per_bat_contact','squared_up_per_swing','blast_per_bat_contact','blast_per_swing','swing_length']
PTYPES=['FF','SI','FC','SL','ST','CU','KC','CH','FS','OTHER','UNKNOWN']
PTMETRICS=['pitch_type_usage','release_speed_mean','whiff_pct']
DEFAULT=dict(version=VERSION,first_origin=2019,last_historical_origin=2025,evaluation_origin=2026,minimum_fit_rows=50,ridge_alpha=1.,clip_z=8.,maximum_exposure_weight=600.,minimum_folds=3,minimum_rows_per_fold=30,minimum_history_folds=2,minimum_history_rows=20,recent_folds=2,minimum_objective_improvement=.01,maximum_metric_degradation=.01,maximum_guard_degradation=.02,weights=WEIGHTS,accepted_policy='FROZEN_REFERENCE_NO_PROMOTION',bat_policy='EXPLORATORY_NOT_SELECTABLE',future_2027_primary_source_years=[2023,2024,2025,2026],future_2027_weights_status='NOT_SELECTED_OR_FITTED')

def finite(v):return isinstance(v,(int,float,np.number)) and not isinstance(v,(bool,np.bool_)) and math.isfinite(float(v))
def number(v):return None if v is None or v=='' else float(v)
def key(r):return int(r['target_season']),r['player_type'],str(r['mlbam_id'])
def member(keys):return hashlib.sha256(json.dumps(sorted(keys)).encode()).hexdigest()
def emit(path,rows):write(path,rows,list(dict.fromkeys(n for r in rows for n in r)) or ['status'])
def portable(manifest):
 out={}
 for name,h in manifest.items():
  n=name.replace('\\','/')
  if PureWindowsPath(name).drive or n.startswith('/') or any(p in ('','.', '..') for p in n.split('/')) or n in out:raise ValueError('Unsafe/ambiguous manifest path')
  out[n]=h
 return out
def checked(root,name,watched):
 root=Path(root).resolve();mp=root/'output_sha256.json';mm=portable(load(mp));n=name.replace('\\','/');p=(root/n).resolve()
 if root not in p.parents or n not in mm or sha(p)!=mm[n]:raise ValueError('Frozen hash/path mismatch: '+str(p))
 watched[str(mp)]=sha(mp);watched[str(p)]=sha(p);return p
def near(a,b):return a is None and b is None or finite(a) and finite(b) and abs(a-b)<=1e-8*max(1.,abs(a),abs(b))
def coherent(role,v):
 if set(v)!=set(METRICS[role]) or any(x is not None and (not finite(x) or x<0) for x in v.values()):raise ValueError('Incomplete/invalid forecast')
 def eq(m,deps,fn):
  e=fn() if all(finite(v[d]) for d in deps) else None
  if not near(v[m],e):raise ValueError('Incoherent '+m)
 if role=='hitter':
  eq('H',['1B','2B','3B','HR'],lambda:sum(v[m] for m in ['1B','2B','3B','HR']))
  if all(finite(v[m]) for m in ['PA','AB','BB','HBP','SF','SH']) and sum(v[m] for m in ['AB','BB','HBP','SF','SH'])>v['PA']+1e-6:raise ValueError('PA bound')
  if finite(v['H']) and finite(v['AB']) and v['H']>v['AB']+1e-6:raise ValueError('Hit bound')
  eq('AVG',['H','AB'],lambda:v['H']/v['AB'] if v['AB'] else None)
  eq('OBP',['H','BB','HBP','AB','SF'],lambda:(v['H']+v['BB']+v['HBP'])/(v['AB']+v['BB']+v['HBP']+v['SF']) if v['AB']+v['BB']+v['HBP']+v['SF'] else None)
  eq('SLG',['1B','2B','3B','HR','AB'],lambda:sum(v[m]*w for m,w in [('1B',1),('2B',2),('3B',3),('HR',4)])/v['AB'] if v['AB'] else None)
  eq('OPS',['OBP','SLG'],lambda:v['OBP']+v['SLG'])
 else:
  eq('IP',['OUTS'],lambda:v['OUTS']/3);eq('ERA',['ER','OUTS'],lambda:27*v['ER']/v['OUTS'] if v['OUTS'] else None);eq('WHIP',['H','BB','OUTS'],lambda:3*(v['H']+v['BB'])/v['OUTS'] if v['OUTS'] else None);eq('SV_plus_HLD',['SV','HLD'],lambda:v['SV']+v['HLD'])
  if finite(v['H']) and finite(v['HR']) and v['HR']>v['H']+1e-6:raise ValueError('Pitcher HR bound')
 return v
def compose(role,accepted,rates):
 a=dict(accepted);den=a['AB' if role=='hitter' else 'OUTS']
 if not finite(den) or den<=0 or any(not finite(rates.get(m)) for m in TARGETS[role]) or role=='hitter' and any(not finite(a.get(m)) for m in ['BB','HBP','SF']):return a,False
 v=dict(a)
 if role=='hitter':
  scale=max(1.,sum(rates.values()))
  for m in TARGETS[role]:v[m]=den*rates[m]/scale
  v['H']=sum(v[m] for m in TARGETS[role]);v['AVG']=v['H']/den;d=den+a['BB']+a['HBP']+a['SF'];v['OBP']=(v['H']+a['BB']+a['HBP'])/d if d else None;v['SLG']=sum(v[m]*w for m,w in [('1B',1),('2B',2),('3B',3),('HR',4)])/den;v['OPS']=v['OBP']+v['SLG'] if v['OBP'] is not None else None
 else:
  for m in TARGETS[role]:v[m]=den*rates[m]
  v['H']=max(v['H'],v['HR']);v['ERA']=27*v['ER']/den;v['WHIP']=3*(v['H']+v['BB'])/den
 coherent(role,v)
 if any(v[m]!=a[m] for m in a if m not in CHANGED[role]):raise ValueError('Frozen anchor changed')
 return v,True

def weighted(samples,weights):
 good=[(v,n,w) for (v,n),w in zip(samples,weights) if finite(v) and finite(n) and n>0]
 return (sum(v*n*w for v,n,w in good)/sum(n*w for v,n,w in good) if good else None,sum(n for v,n,w in good),len(good))
def make_features(r,expanded,bat,ptype,weight):
 y,role,pid=key(r);w=WEIGHTS[weight];f={'age':r.get('age_at_target_estimate')};used=set()
 for era in [1,2,3,4]:f['tracking_era_share_'+str(era)]=sum(ww for lag,ww in enumerate(w,1) if (1 if y-lag<=2016 else 2 if y-lag<=2019 else 3 if y-lag<=2023 else 4)==era)/sum(w)
 pairs=[('H','AB'),('1B','AB'),('2B','AB'),('3B','AB'),('HR','AB'),('BB','PA'),('HBP','PA'),('SO','PA')] if role=='hitter' else [(n,'OUTS') for n in ['H','BB','ER','SO','HR']]+[('GS','G')]
 for n,d in pairs:
  samples=[]
  for lag in [1,2,3]:
   a=r.get(f'x_actual_lag{lag}_{n}');b=r.get(f'x_actual_lag{lag}_{d}')
   samples.append((a/b,b) if finite(a) and a>=0 and finite(b) and b>0 else (None,None))
   if samples[-1][0] is not None:used.add(y-lag)
  v,obs,nlags=weighted(samples,w);f['actual_'+n+'_per_'+d]=v;f['actual_'+n+'_exposure']=obs;f['actual_'+n+'_lags']=nlags
 for m in (['PA','AB','G'] if role=='hitter' else ['OUTS','G','GS']):
  f['actual_mean_'+m]=weighted([(r.get(f'x_actual_lag{lag}_{m}'),1.) for lag in [1,2,3]],w)[0]
 for m in CLASSIC[role]:
  ss=[]
  for lag in [1,2,3]:
   stem=f'x_statcast_lag{lag}_{m}';v=r.get(stem+'_value');n=r.get(stem+'_observations');cv=r.get(stem+'_coverage');ok=r.get(stem+'_eligible') in [True,1] and finite(cv) and .5<=cv<=1
   ss.append((v,n) if ok else (None,None))
   if ok and finite(v) and finite(n) and n>0:used.add(y-lag)
  v,n,lags=weighted(ss,w);f['classic_'+m]=v;f['classic_'+m+'_observations']=n;f['classic_'+m+'_lags']=lags
 f['recent_history_seasons']=len(used);f['source_2020_in_window']=int(y-3<=2020<y)
 standard=dict(f);new=[]
 for family,metrics,index in [('expanded',EXPANDED[role],expanded),('bat',BAT,bat)]:
  for m in metrics:
   ss=[]
   for lag in [1,2,3]:
    a=index.get((y-lag,role,pid,m));ss.append(a if a else (None,None))
   v,n,lags=weighted(ss,w);f[family+'_'+m]=v;f[family+'_'+m+'_observations']=n;f[family+'_'+m+'_lags']=lags
   if family=='expanded':new.extend([family+'_'+m,family+'_'+m+'_observations',family+'_'+m+'_lags'])
 if role=='pitcher':
  for pt in PTYPES:
   for m in PTMETRICS:
    ss=[]
    for lag in [1,2,3]:
     ss.append(ptype.get((y-lag,role,pid,pt,m),(None,None)))
    v,n,lags=weighted(ss,w);name='arsenal_'+pt+'_'+m;f[name]=v;f[name+'_observations']=n;f[name+'_lags']=lags;new.extend([name,name+'_observations',name+'_lags'])
 extended={n:f[n] for n in sorted(set(standard)|set(new))};full={n:f[n] for n in sorted(f)};full['__bat_available']=any(finite(v) for name,v in full.items() if name.startswith('bat_') and not name.endswith(('_observations','_lags')));full['partial_bat_2023_in_window']=float(y-3<=2023<y)
 return standard,extended,full

def preprocess(rows,names,c):
 state={};dropped=[]
 for name in names:
  vals=[r.get(name) for r in rows];ok=[v for v in vals if finite(v)]
  if not ok:dropped.append(name);continue
  med=float(np.median(ok));a=np.array([v if finite(v) else med for v in vals]);sd=float(a.std());state[name]=dict(median=med,mean=float(a.mean()),scale=sd if sd>1e-12 else 1.)
 return dict(numeric=state,dropped=dropped,clip_z=c['clip_z'])
def transform(rows,state):
 cols=[np.ones(len(rows))]
 for name,s in state['numeric'].items():
  vals=[r.get(name) for r in rows];cols.extend([np.clip(np.array([(v if finite(v) else s['median'])-s['mean'] for v in vals])/s['scale'],-state['clip_z'],state['clip_z']),np.array([not finite(v) for v in vals],dtype=float)])
 return np.column_stack(cols)
def fit_residual(training,test,features,accepted,actual,role,metric,origin,c,bat_only=False):
 den='AB' if role=='hitter' else 'OUTS';floor=30 if role=='hitter' else 90;train=[];res=[];weights=[];keys=[]
 for k in training:
  if k[0]>=origin or k[0]>2025:raise ValueError('Training chronology violation')
  a=accepted[k];d=actual.get(k+(den,));n=actual.get(k+(metric,));base=a.get(metric);ad=a.get(den)
  if not finite(d) or d<floor or not finite(n) or not finite(base) or not finite(ad) or ad<=0:continue
  if bat_only and (k[0]<2024 or not features[k].get('__bat_available',False)):continue
  train.append(features[k]);res.append(n/d-base/ad);weights.append(min(d,c['maximum_exposure_weight']));keys.append(k)
 model=dict(origin=origin,role=role,metric=metric,n_fit=len(train),fit_target_seasons=sorted({k[0] for k in keys}),fit_membership_sha256=member(keys),status='INSUFFICIENT_ROWS',preprocessing=None,coefficients=None)
 if len(train)>=c['minimum_fit_rows']:
  names=sorted(set(n for r in train for n in r if not n.startswith('__')));state=preprocess(train,names,c);x=transform(train,state);ww=np.array(weights);ww/=ww.sum();penalty=np.eye(x.shape[1])*c['ridge_alpha'];penalty[0,0]=1e-10;coef=np.linalg.solve(x.T@(x*ww[:,None])+penalty,x.T@(ww*np.array(res)))
  if not np.isfinite(coef).all():raise ValueError('Nonfinite coefficients')
  model.update(status='FITTED',preprocessing=state,coefficients=coef.tolist())
 predictions={}
 adjust=transform([features[k] for k in test],model['preprocessing'])@np.array(model['coefficients']) if model['status']=='FITTED' else [0.]*len(test)
 cap=1. if role=='hitter' else 2. if metric in ['SO','HR'] else 5.
 for k,delta in zip(test,adjust):
  a=accepted[k];d=a.get(den);n=a.get(metric);base=n/d if finite(n) and finite(d) and d>0 else None
  available=not bat_only or features[k].get('__bat_available',False)
  predictions[k]=min(cap,max(0.,base+float(delta))) if base is not None and model['status']=='FITTED' and available else None
 return model,predictions

def history_class(r):return 'LOW_HISTORY' if r.get('recent_history_seasons',0)<=1 else 'ESTABLISHED_HISTORY'
def gate(history,role,origin,c):
 candidates={};metrics=GATE_METRICS[role]
 def check(arm,reference):
  checks={};passed=True
  for cohort in ['ALL','RECENT','LOW_HISTORY','ESTABLISHED_HISTORY']:
   source='ALL' if cohort=='RECENT' else cohort;rows=[r for r in history if r['season']<origin and r['player_type']==role and r['cohort']==source];years=list(range(c['first_origin'],origin))
   if cohort=='RECENT':years=years[-c['recent_folds']:]
   minimum=c['minimum_rows_per_fold'] if cohort in ['ALL','RECENT'] else c['minimum_history_rows'];valid=[y for y in years if all(any(r['season']==y and r['metric']==m and r['n']>=minimum and r['supported'].get(arm,False) and r['supported'].get(reference,True) for r in rows) for m in metrics)]
   need=c['minimum_folds'] if cohort=='ALL' else c['recent_folds'] if cohort=='RECENT' else c['minimum_history_folds'];support=len(valid)>=need and (cohort!='RECENT' or valid==years and len(years)==need);rat=[];passed_metrics=True
   for m in metrics:
    rr=[r for r in rows if r['metric']==m and r['season'] in valid];mr=[r['errors'][arm]['mse']/r['errors'][reference]['mse'] for r in rr if r['errors'][reference]['mse']>0];ma=[r['errors'][arm]['mae']/r['errors'][reference]['mae'] for r in rr if r['errors'][reference]['mae']>0];limit=c['maximum_metric_degradation'] if cohort=='ALL' else c['maximum_guard_degradation'];passed_metrics=passed_metrics and len(mr)==len(rr) and len(ma)==len(rr) and bool(rr) and np.mean(mr)<=1+limit and np.mean(ma)<=1+limit;rat.extend(mr)
   objective=float(np.mean(rat)) if rat else None;limit=1-c['minimum_objective_improvement'] if cohort=='ALL' else 1+c['maximum_metric_degradation'];ok=bool(support and objective is not None and objective<=limit and passed_metrics);checks[cohort]=dict(pass_gate=ok,seasons=valid,sufficient_support=support,objective=objective);passed=passed and ok
  return dict(pass_gate=bool(passed),checks=checks)
 for arm in SELECTABLE:
  comparisons={'accepted':check(arm,'accepted_frozen')}
  if arm.startswith('expanded_'):comparisons['incremental_same_weight']=check(arm,arm.replace('expanded_','standard_'));comparisons['weighting_vs_equal']=check(arm,'expanded_equal')
  else:comparisons['weighting_vs_equal']=check(arm,'standard_equal')
  candidates[arm]=dict(pass_gate=all(v['pass_gate'] for v in comparisons.values()),comparisons=comparisons)
 eligible=[arm for arm,v in candidates.items() if v['pass_gate']];selected=min(eligible,key=lambda arm:(candidates[arm]['comparisons']['accepted']['checks']['ALL']['objective'],SELECTABLE.index(arm))) if eligible else 'accepted_frozen'
 return dict(origin=origin,player_type=role,selected=selected,candidates=candidates,selection_max_season=origin-1,evaluation_used=False)
