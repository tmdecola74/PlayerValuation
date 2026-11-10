"""Descriptive workload histories, not injury labels or new pitcher forecasts."""
import math,hashlib,json
from collections import defaultdict,Counter
from standalone_models_v1_0 import finite
from standalone_opportunity_v1_1 import role_of
from standalone_attribution_v1_5 import workload_band

P_METHODS=['frozen_v1_5','research_v1_6','research_v1_8','research_v1_9','selected_v1_9']

def prior_tags(r,s):
 raw=[r.get(f'x_actual_lag{i}_OUTS') for i in [1,2,3]];norm=[v*(s['source_2020_multiplier'] if r.get('source_season_lag'+str(i))==2020 else 1.) if finite(v) else None for i,v in enumerate(raw,1)];roles=[role_of(r.get(f'x_actual_lag{i}_G'),r.get(f'x_actual_lag{i}_GS')) for i in [1,2,3]];a,b,c=norm;floor=s['diagnostic_older_OUTS_floor'];frac=s['diagnostic_reduction_fraction'];reduced=finite(a) and finite(b) and b>=floor and a<=frac*b;rebound=all(finite(v) for v in [a,b,c]) and c>=floor and b<=frac*c and a>b;gap=not finite(a) and any(finite(v) for v in [b,c]) or finite(a) and not finite(b) and finite(c);older=max([v for v in [b,c] if finite(v)],default=None)
 pattern='NO_RECORDED_LAG1' if not finite(a) else 'KNOWN_ZERO_LAG1_OUTS' if a==0 else 'PRIOR_REDUCTION' if reduced else 'REBOUND_ALREADY_UNDERWAY' if rebound else 'NO_LAG2_REFERENCE' if not finite(b) else 'OTHER_RECORDED_HISTORY'
 out=dict(prior_workload_pattern=pattern,prior_reduction=bool(reduced),prior_rebound=bool(rebound),gap_in_recorded_history=bool(gap),older_reference_OUTS=older,prior_role=roles[0],prior_role_transition=roles[1]+'_TO_'+roles[0] if 'UNKNOWN' not in roles[:2] else 'UNKNOWN',prior_workload_band=workload_band(a,'pitcher'),has_2020_prior=any(r.get('source_season_lag'+str(i))==2020 for i in [1,2,3]),history_presence=''.join('1' if finite(v) else '0' for v in raw))
 for i in [1,2,3]:out[f'prior_raw_OUTS_lag{i}']=raw[i-1];out[f'prior_normalized_OUTS_lag{i}']=norm[i-1];out[f'prior_role_lag{i}']=roles[i-1]
 return out

def player(k,c,actual,s):
 r=c['rows'][k];tags=prior_tags(r,s);a=actual.get(k+('OUTS',));g=actual.get(k+('G',));gs=actual.get(k+('GS',));ar=role_of(g,gs);pr=tags['prior_role'];older=tags['older_reference_OUTS'];ret='NOT_A_PRIOR_REDUCTION_OR_GAP'
 if tags['prior_reduction'] or tags['gap_in_recorded_history']:
  ret='UNKNOWN_ACTUAL_OR_OLDER_REFERENCE' if not finite(a) or not finite(older) or older<s['diagnostic_older_OUTS_floor'] else 'RETURNED_TOWARD_OLDER_WORKLOAD' if a>=s['diagnostic_return_fraction']*older else 'REMAINED_BELOW_OLDER_WORKLOAD'
 out=dict(season=k[0],mlbam_id=k[2],actual_OUTS=a,actual_G=g,actual_GS=gs,actual_role=ar,actual_role_transition=pr+'_TO_'+ar if 'UNKNOWN' not in [pr,ar] else 'UNKNOWN',retrospective_return_pattern=ret,**tags,growth_probability=c['items16'][k].get('growth_probability'),conditional_growth_OUTS=c['items16'][k].get('conditional_growth_OUTS'),conditional_decline_OUTS=c['items16'][k].get('conditional_decline_OUTS'))
 source=c['items16'][k];an=source.get('anchor');grow=source.get('conditional_growth_OUTS');decline=source.get('conditional_decline_OUTS');known=all(finite(v) for v in [a,an,grow,decline]);branch='GROWTH' if known and a>an else 'DECLINE_OR_FLAT' if known else 'UNKNOWN';value=grow if branch=='GROWTH' else decline if branch=='DECLINE_OR_FLAT' else None
 out.update(source_anchor_OUTS=an,observed_branch=branch,actual_above_growth=bool(a>grow) if known else None,actual_below_decline=bool(a<decline) if known else None,observed_branch_error_IP=(value-a)/3 if known else None)
 vals={'frozen_v1_5':c['base15'][k].get('OUTS'),'research_v1_6':c['items16'][k]['candidate'],'research_v1_8':c['items18'][k]['candidate'],'research_v1_9':c['items19'][k]['candidate'],'selected_v1_9':c['items19'][k]['selected']}
 out['paired_status']='AVAILABLE' if finite(a) and all(finite(v) for v in vals.values()) else 'MISSING_ELIGIBLE_ACTUAL_OR_FORECAST'
 for method,v in vals.items():out[method+'_OUTS']=v;out[method+'_error_IP']=(v-a)/3 if finite(v) and finite(a) else None
 return out

def cohorts(d):
 cc=['all','prior_role_'+d['prior_role'],'prior_workload_'+d['prior_workload_band'],'prior_pattern_'+d['prior_workload_pattern'],'prior_role_transition_'+d['prior_role_transition'],'observed_role_transition_'+d['actual_role_transition'],'observed_return_'+d['retrospective_return_pattern']]
 for flag in ['prior_reduction','prior_rebound','gap_in_recorded_history','has_2020_prior']:
  if d[flag]:cc.append(flag)
 return cc

def audit(c,actual,s,maximum=2025):
 detail=[player(k,c,actual,s) for k in sorted(c['items19']) if k[1]=='pitcher' and k[0]<=maximum];groups=defaultdict(list);summary=[];coverage=[];outliers=[];branches=[]
 for d in detail:
  for cc in cohorts(d):groups[d['season'],cc].append(d)
 for y in range(2019,maximum+1):groups[y,'all']
 for (y,cc),rr in sorted(groups.items()):
  pp=[d for d in rr if d['paired_status']=='AVAILABLE'];n=len(pp);member=hashlib.sha256(json.dumps([d['mlbam_id'] for d in pp]).encode()).hexdigest();coverage.append(dict(season=y,cohort=cc,total_rows=len(rr),paired_rows=n,missing_rows=len(rr)-n,stress_season=y==2020,disclosed_evaluation=y==2026))
  bb=[d for d in pp if d['observed_branch']!='UNKNOWN'];bn=len(bb);branches.append(dict(season=y,cohort=cc,n=bn,actual_above_growth_fraction=sum(d['actual_above_growth'] for d in bb)/bn if bn else None,actual_below_decline_fraction=sum(d['actual_below_decline'] for d in bb)/bn if bn else None,observed_branch_MAE_IP=sum(abs(d['observed_branch_error_IP']) for d in bb)/bn if bn else None,membership_sha256=hashlib.sha256(json.dumps([d['mlbam_id'] for d in bb]).encode()).hexdigest(),stress_season=y==2020,disclosed_evaluation=y==2026))
  for method in P_METHODS:
   ee=[d[method+'_error_IP'] for d in pp];summary.append(dict(season=y,cohort=cc,method=method,n=n,RMSE_IP=math.sqrt(sum(e*e for e in ee)/n) if n else None,MAE_IP=sum(abs(e) for e in ee)/n if n else None,bias_IP=sum(ee)/n if n else None,underprediction_fraction=sum(e<0 for e in ee)/n if n else None,membership_sha256=member,stress_season=y==2020,disclosed_evaluation=y==2026))
 for y in range(2019,maximum+1):
  rr=[d for d in detail if d['season']==y and d['paired_status']=='AVAILABLE']
  for method in ['frozen_v1_5','research_v1_9']:
   total=sum(d[method+'_error_IP']**2 for d in rr)
   for rank,d in enumerate(sorted(rr,key=lambda d:(-d[method+'_error_IP']**2,d['mlbam_id']))[:25],1):outliers.append(d|dict(ranking_method=method,rank=rank,share_of_squared_error=d[method+'_error_IP']**2/total if total else 0.))
 return dict(pitcher_history_players=detail,pitcher_history_summary=summary,pitcher_history_coverage=coverage,pitcher_history_largest_misses=outliers,pitcher_branch_coverage=branches)
