"""Descriptive prior-feature audit; no SB model fit, selection or forecast edits."""
import math,bisect,hashlib,json
from collections import defaultdict,Counter
import numpy as np
from standalone_models_v1_0 import finite
from standalone_growth_sb_v1_6 import opportunity

DERIVED=['audit_prior_SB_rate','audit_prior_onbase_yield','audit_prior_SB_rate_change','audit_prior_CS_rate','audit_calendar_era']

def features(r,allow):
 out={n:r.get(n) for n in allow}
 def lag(l):
  p=f'x_actual_lag{l}_';return opportunity({m:r.get(p+m) for m in ['H','HR','BB','HBP']})
 o=lag(1);o2=lag(2);sb=r.get('x_actual_lag1_SB');sb2=r.get('x_actual_lag2_SB');pa=r.get('x_actual_lag1_PA');cs=r.get('x_actual_lag1_CS');rate=sb/o if finite(sb) and finite(o) and o>0 else None;rate2=sb2/o2 if finite(sb2) and finite(o2) and o2>0 else None
 out.update(audit_prior_SB_rate=rate,audit_prior_onbase_yield=o/pa if finite(o) and finite(pa) and pa>0 else None,audit_prior_SB_rate_change=rate-rate2 if finite(rate) and finite(rate2) else None,audit_prior_CS_rate=cs/o if finite(cs) and finite(o) and o>0 else None,audit_calendar_era=int(r['target_season']>=2023));return out

def observation(k,r,actual,s):
 values={m:actual.get(k+(m,)) for m in ['H','HR','BB','HBP']};opp=opportunity(values);sb=actual.get(k+('SB',));prioropp=opportunity({m:r.get('x_actual_lag1_'+m) for m in ['H','HR','BB','HBP']});priorSB=r.get('x_actual_lag1_SB');priorPA=r.get('x_actual_lag1_PA');cc=['all']
 if finite(priorSB) and priorSB>=s['SB_prior_runner_floor']:cc.append('established_runner')
 if not finite(priorPA) or priorPA<s['SB_low_history_PA']:cc.append('low_history')
 if finite(priorSB) and priorSB==0:cc.append('prior_zero_SB')
 status='AVAILABLE'
 if not all(finite(v) for v in [opp,sb,prioropp,priorSB]):status='MISSING_ELIGIBLE_ACTUAL_OR_PRIOR_COMPONENT'
 elif opp<s['SB_minimum_proxy'] or prioropp<s['SB_minimum_proxy']:status='INSUFFICIENT_PROXY_EXPOSURE'
 current=sb/opp if finite(sb) and finite(opp) and opp>0 else None;prior=priorSB/prioropp if finite(priorSB) and finite(prioropp) and prioropp>0 else None
 return dict(season=k[0],mlbam_id=k[2],cohorts=cc,status=status,actual_SB=sb,actual_proxy=opp,prior_SB=priorSB,prior_proxy=prioropp,actual_propensity=current,prior_propensity=prior,propensity_change=current-prior if status=='AVAILABLE' else None)

def freeze_bins(rows,allow,s):
 if len(set(allow))!=len(allow) or any(n.startswith('y_') or n in DERIVED for n in allow):raise ValueError('Invalid SB feature allowlist')
 ff={k:features(r,allow) for k,r in rows.items() if k[1]=='hitter'};names=allow+DERIVED;out={}
 for y in range(2019,2027):
  before=[v for k,v in ff.items() if k[0]<y and k[0]!=2020];cuts={}
  for n in names:
   values=[v[n] for v in before if finite(v.get(n))];cuts[n]=dict(n_prior_features=len(values),cutpoints=np.quantile(values,[.2,.4,.6,.8]).tolist() if values else None)
  out[str(y)]=dict(fit_years=sorted({k[0] for k in ff if k[0]<y and k[0]!=2020}),features=cuts)
 return out

def correlation(x,y):
 if len(x)<2 or len(set(x))<2 or len(set(y))<2:return None
 a=np.array(x)-np.mean(x);b=np.array(y)-np.mean(y);return float((a@b)/math.sqrt(float(a@a)*float(b@b)))
def ranks(x):
 order=sorted(range(len(x)),key=x.__getitem__);out=[0.]*len(x);i=0
 while i<len(order):
  j=i+1
  while j<len(order) and x[order[j]]==x[order[i]]:j+=1
  for k in order[i:j]:out[k]=(i+j-1)/2
  i=j
 return out

def audit(rows,actual,allow,s,bins,maximum=2025):
 names=allow+DERIVED;groups=defaultdict(list);coverage=[];detail=[]
 for k,r in sorted(rows.items()):
  if k[1]!='hitter' or not 2019<=k[0]<=maximum:continue
  o=observation(k,r,actual,s);detail.append({n:v for n,v in o.items() if n!='cohorts'}|dict(cohorts=';'.join(o['cohorts'])));ff=features(r,allow)
  for cohort in o['cohorts']:groups[k[0],cohort].append((o,ff))
 associations=[];binned=[]
 for y in range(2019,maximum+1):
  for cohort in ['all','established_runner','low_history','prior_zero_SB']:groups[y,cohort]
 for (y,cohort),rr in sorted(groups.items()):
  counts=Counter(o['status'] for o,f in rr)
  for st in ['AVAILABLE','MISSING_ELIGIBLE_ACTUAL_OR_PRIOR_COMPONENT','INSUFFICIENT_PROXY_EXPOSURE']:coverage.append(dict(season=y,cohort=cohort,status=st,n=counts[st],total_rows=len(rr),stress_season=y==2020,disclosed_evaluation=y==2026))
  for n in names:
   pairs=[(o,f[n]) for o,f in rr if o['status']=='AVAILABLE' and finite(f.get(n))];x=[v for o,v in pairs];delta=[o['propensity_change'] for o,v in pairs];level=[o['actual_propensity'] for o,v in pairs];member=hashlib.sha256(json.dumps([o['mlbam_id'] for o,v in pairs]).encode()).hexdigest();usable=len(pairs)>=s['SB_minimum_bin_rows'];associations.append(dict(season=y,cohort=cohort,feature=n,total_rows=len(rr),eligible_changes=sum(o['status']=='AVAILABLE' for o,f in rr),feature_present=sum(finite(f.get(n)) for o,f in rr),paired_rows=len(pairs),unique_feature_values=len(set(x)),pearson_change=correlation(x,delta) if usable else None,spearman_change=correlation(ranks(x),ranks(delta)) if usable else None,spearman_current_level=correlation(ranks(x),ranks(level)) if usable else None,status='DESCRIPTIVE' if usable and len(set(x))>=2 else 'INSUFFICIENT_ROWS_OR_VARIATION',membership_sha256=member,stress_season=y==2020,disclosed_evaluation=y==2026))
   state=bins[str(y)]['features'][n];cut=state['cutpoints'];bb=defaultdict(list)
   for o,f in rr:
    if o['status']!='AVAILABLE':continue
    v=f.get(n);band='MISSING' if not finite(v) else 'NO_PRIOR_DISTRIBUTION' if cut is None else str(bisect.bisect_right(cut,v));bb[band].append(o)
   for band in [str(i) for i in range(5)]+['MISSING','NO_PRIOR_DISTRIBUTION']:
    pp=bb[band];z=[o['propensity_change'] for o in pp];av=lambda key:float(np.mean([o[key] for o in pp])) if pp else None
    binned.append(dict(season=y,cohort=cohort,feature=n,band=band,n=len(pp),prior_feature_rows=state['n_prior_features'],cutpoints=json.dumps(cut),mean_prior_propensity=av('prior_propensity'),mean_actual_propensity=av('actual_propensity'),mean_propensity_change=float(np.mean(z)) if z else None,median_propensity_change=float(np.median(z)) if z else None,growth_fraction=sum(v>0 for v in z)/len(z) if z else None,sufficient_rows=len(pp)>=s['SB_minimum_bin_rows'],stress_season=y==2020,disclosed_evaluation=y==2026))
 stability=[];gg=defaultdict(list)
 for d in associations:
  if d['season']<=2025 and d['season']!=2020:gg[d['cohort'],d['feature']].append(d)
 for (cohort,n),rr in sorted(gg.items()):
  vv=[d for d in rr if finite(d['spearman_change'])];pos=sum(d['spearman_change']>0 for d in vv);neg=sum(d['spearman_change']<0 for d in vv);stability.append(dict(cohort=cohort,feature=n,requested_seasons='2019,2021,2022,2023,2024,2025',eligible_seasons=','.join(str(d['season']) for d in vv),eligible_folds=len(vv),positive_folds=pos,negative_folds=neg,equal_fold_mean_spearman=float(np.mean([d['spearman_change'] for d in vv])) if vv else None,feature_selected=False,causal_or_predictive_approval=False))
 return dict(sb_propensity_players=detail,sb_propensity_coverage=coverage,sb_feature_associations=associations,sb_feature_bins=binned,sb_feature_stability=stability)
