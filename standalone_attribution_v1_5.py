"""Read-only count-error decomposition and role/workload diagnostics."""
import csv,hashlib,json,math
from collections import defaultdict
from standalone_models_v1_0 import finite
from standalone_combined_v1_4 import vectors
from standalone_opportunity_v1_1 import role_of
from standalone_role_workload_v1_2 import prior_role

ATTR_FIELDS=['season','player_type','mlbam_id','metric','method','exposure_metric','forecast_count','actual_count','forecast_exposure','actual_exposure','forecast_rate','actual_rate','error','workload_contribution','skill_contribution','reconstruction_residual','actual_exposure_forecast_rate','forecast_exposure_actual_rate','status','prior_role','actual_role','prior_workload_cohort','actual_workload_cohort']
SUMMARY_FIELDS=['season','player_type','metric','cohort','method','n','mae','rmse','bias','mean_workload_contribution','mean_skill_contribution','workload_mse','skill_mse','interaction_mse','total_mse','membership_sha256']
HOLD_FIELDS=['season','player_type','metric','cohort','method','n','mae','rmse','bias','membership_sha256']
COUNT_OUTLIER_FIELDS=ATTR_FIELDS+['rank','share_of_group_squared_error']
RATIO_FIELDS=['season','mlbam_id','metric','prediction','actual','error','squared_error','share_of_season_squared_error','actual_IP','prior_role','actual_role']


def decomposition(forecast_count,forecast_exposure,actual_count,actual_exposure):
 out=dict(forecast_count=forecast_count,actual_count=actual_count,forecast_exposure=forecast_exposure,actual_exposure=actual_exposure,forecast_rate=None,actual_rate=None,error=None,workload_contribution=None,skill_contribution=None,reconstruction_residual=None,actual_exposure_forecast_rate=None,forecast_exposure_actual_rate=None,status='AVAILABLE')
 if finite(forecast_count) and finite(actual_count):out['error']=forecast_count-actual_count
 if not all(finite(v) for v in [forecast_count,forecast_exposure,actual_count,actual_exposure]):out['status']='MISSING_ELIGIBLE_COUNT_OR_EXPOSURE';return out
 if min(forecast_count,forecast_exposure,actual_count,actual_exposure)<0:raise ValueError('Negative count/exposure in attribution')
 if forecast_exposure<=0 or actual_exposure<=0:out['status']='ZERO_DENOMINATOR_RATE_UNKNOWN';return out
 rf=forecast_count/forecast_exposure;ra=actual_count/actual_exposure;work=(forecast_exposure-actual_exposure)*(rf+ra)/2;skill=(rf-ra)*(forecast_exposure+actual_exposure)/2;residual=out['error']-work-skill
 if abs(residual)>1e-9*max(1,abs(out['error']),abs(work),abs(skill)):raise ValueError('Attribution identity failed')
 out.update(forecast_rate=rf,actual_rate=ra,workload_contribution=work,skill_contribution=skill,reconstruction_residual=residual,actual_exposure_forecast_rate=actual_exposure*rf,forecast_exposure_actual_rate=forecast_exposure*ra);return out

def workload_band(value,role):
 if not finite(value):return 'UNKNOWN'
 if role=='pitcher':value/=3;return 'LT40_IP' if value<40 else '40_TO_LT100_IP' if value<100 else 'GE100_IP'
 return 'LT100_PA' if value<100 else '100_TO_LT300_PA' if value<300 else 'GE300_PA'

def tags(key,r,actual):
 y,role,pid=key;den='PA' if role=='hitter' else 'OUTS';get=lambda m:actual.get(key+(m,));pr=prior_role(r) if role=='pitcher' else 'NOT_APPLICABLE';ar=role_of(get('G'),get('GS')) if role=='pitcher' else 'NOT_APPLICABLE'
 return dict(prior_role=pr,actual_role=ar,prior_workload_cohort=workload_band(r.get('x_actual_lag1_'+den),role),actual_workload_cohort=workload_band(get(den),role))

def cohorts(t):
 out=['all_eligible','prior_workload_'+t['prior_workload_cohort'],'actual_workload_'+t['actual_workload_cohort']]
 if t['prior_role']!='NOT_APPLICABLE':out+=['prior_role_'+t['prior_role'],'actual_role_'+t['actual_role']]
 return out

def attribution(c,actual,detail_writer,summary_writer,ratio_writer,maximum=2026,count_outlier_writer=None):
 groups=defaultdict(list);coverage=defaultdict(int);ratios=defaultdict(list)
 for key in sorted(c['predictions']):
  y,role,pid=key
  if y>maximum:continue
  vv=vectors(c,key);r=c['rows'][key];t=tags(key,r,actual);exposure='PA' if role=='hitter' else 'OUTS'
  for metric in (['HR','SB'] if role=='hitter' else ['W','SO']):
   ds={m:decomposition(vv[m].get(metric),vv[m].get(exposure),actual.get(key+(metric,)),actual.get(key+(exposure,))) for m in ['frozen_v1_2','combined_v1_4']};paired=all(d['status']=='AVAILABLE' for d in ds.values())
   for m,d in ds.items():
    detail_writer.writerow(dict(season=y,player_type=role,mlbam_id=pid,metric=metric,method=m,exposure_metric=exposure,**d,**t));coverage[role,metric,d['status']]+=1
    if paired:
     for cohort in cohorts(t):groups[y,role,metric,cohort,m].append((pid,d))
  if role=='pitcher':
   for metric in ['ERA','WHIP']:
    pred=vv['combined_v1_4'].get(metric);a=actual.get(key+(metric,))
    if finite(pred) and finite(a):ratios[y,metric].append(dict(season=y,mlbam_id=pid,metric=metric,prediction=pred,actual=a,error=pred-a,squared_error=(pred-a)**2,actual_IP=None if not finite(actual.get(key+('OUTS',))) else actual[key+('OUTS',)]/3,prior_role=t['prior_role'],actual_role=t['actual_role']))
 for (y,role,metric,cohort,m),items in sorted(groups.items()):
  n=len(items);mean=lambda fn:sum(fn(d) for _,d in items)/n;total=mean(lambda d:d['error']**2);wm=mean(lambda d:d['workload_contribution']**2);sm=mean(lambda d:d['skill_contribution']**2);interaction=mean(lambda d:2*d['workload_contribution']*d['skill_contribution'])
  if abs(total-wm-sm-interaction)>1e-8*max(1,total):raise ValueError('MSE decomposition failed')
  summary_writer.writerow(dict(season=y,player_type=role,metric=metric,cohort=cohort,method=m,n=n,mae=mean(lambda d:abs(d['error'])),rmse=math.sqrt(total),bias=mean(lambda d:d['error']),mean_workload_contribution=mean(lambda d:d['workload_contribution']),mean_skill_contribution=mean(lambda d:d['skill_contribution']),workload_mse=wm,skill_mse=sm,interaction_mse=interaction,total_mse=total,membership_sha256=hashlib.sha256(json.dumps([pid for pid,_ in items]).encode()).hexdigest()))
 if count_outlier_writer is not None:
  for (year,role,metric,cohort,method),items in sorted(groups.items()):
   if cohort!='all_eligible':continue
   total=sum(d['error']**2 for _,d in items)
   for rank,(pid,d) in enumerate(sorted(items,key=lambda x:(-x[1]['error']**2,x[0]))[:25],1):
    key=(year,role,pid);count_outlier_writer.writerow(dict(season=year,player_type=role,mlbam_id=pid,metric=metric,method=method,exposure_metric='PA' if role=='hitter' else 'OUTS',**d,**tags(key,c['rows'][key],actual),rank=rank,share_of_group_squared_error=d['error']**2/total if total>0 else 0.))
 for (year,metric),items in sorted(ratios.items()):
  total=sum(x['squared_error'] for x in items)
  for d in sorted(items,key=lambda d:(-d['squared_error'],d['mlbam_id']))[:25]:ratio_writer.writerow(d|{'share_of_season_squared_error':d['squared_error']/total if total>0 else 0.})
 return [dict(player_type=k[0],metric=k[1],status=k[2],method_rows=n) for k,n in sorted(coverage.items())]

def holds_scores(items,rows,actual,methods):
 groups=defaultdict(list);coverage=[]
 for key,d in items.items():
  a=actual.get(key+('HLD',));paired=finite(a) and all(finite(d.get(m)) for m in methods);coverage.append(dict(season=key[0],mlbam_id=key[2],actual_HLD=a,paired=paired,candidate_supported=d['supported']))
  if not paired:continue
  t=tags(key,rows[key],actual);cc=cohorts(t);prior=rows[key].get('x_actual_lag1_HLD')
  if finite(prior) and prior>=5:cc.append('prior_HLD_ge5')
  if a>0:cc.append('actual_HLD_positive')
  for cohort in cc:
   for m in methods:groups[key[0],cohort,m].append((key[2],d[m]-a))
 out=[]
 for (y,cohort,m),pp in sorted(groups.items()):
  n=len(pp);errors=[x[1] for x in pp];out.append(dict(season=y,player_type='pitcher',metric='HLD',cohort=cohort,method=m,n=n,mae=sum(abs(e) for e in errors)/n,rmse=math.sqrt(sum(e*e for e in errors)/n),bias=sum(errors)/n,membership_sha256=hashlib.sha256(json.dumps([x[0] for x in pp]).encode()).hexdigest()))
 return out,coverage
