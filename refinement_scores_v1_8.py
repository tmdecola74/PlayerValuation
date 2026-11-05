"""Common-pool category and cohort scoring for separate frozen experiments."""
import csv,hashlib,json,math
from collections import defaultdict
from standalone_models_v1_0 import finite
from standalone_combined_v1_4 import METRICS
from standalone_attribution_v1_5 import tags,cohorts
from standalone_growth_sb_v1_6 import SCORE_METHODS
from standalone_refinements_v1_8 import cohort_names
from growth_sb_io_v1_6 import forecast

SCORE_FIELDS=['season','player_type','metric','cohort','comparison_group','method','n','mae','rmse','bias','membership_sha256','stress_season']
PAIR_FIELDS=['season','player_type','mlbam_id','metric','cohort','comparison_group','method','prediction','actual','source_record_id']
COVERAGE_FIELDS=['season','player_type','metric','cohort','comparison_group','method','eligible_actuals','available_forecasts','common_pool']
DIRECTION_FIELDS=['season','n','growth_cases','model_brier','frequency_brier','model_accuracy','membership_sha256']


def summaries(c,items,actual,sw,cw,pw,external=None,available=None,maximum=2026):
 external=external or {};available=available or {};score_rows=pair_rows=0
 for year in range(2019,maximum+1):
  for role,metrics in METRICS.items():
   pool={k:{m:forecast(c,k,d,m) for m in SCORE_METHODS} for k,d in items.items() if k[:2]==(year,role)};groups=[('internal',SCORE_METHODS)];ss=sorted(available.get(year,set()));groups += [(s+'_paired',SCORE_METHODS+[s]) for s in ss]
   if ss:groups.append(('all_available_sources',SCORE_METHODS+ss))
   for metric in metrics:
    eligible={k:actual[k+(metric,)] for k in pool if k+(metric,) in actual};cc=defaultdict(dict)
    for k,a in eligible.items():
     tt=tags(k,c['rows'][k],actual)
     labels=cohorts(tt)+[n for n in cohort_names(role,c['rows'][k],c['settings18']) if n not in ['all','prior_starter','prior_reliever']]
     if role=='pitcher' and metric in ['ERA','WHIP']:
      ip=actual.get(k+('IP',))
      for floor in [40,100]:
       if finite(ip) and ip>=floor:labels.append('actual_IP_ge'+str(floor))
     if role=='hitter' and metric in ['AVG','OBP','SLG','OPS','SB']:
      pa=actual.get(k+('PA',))
      for floor in [100,300]:
       if finite(pa) and pa>=floor:labels.append('actual_PA_ge'+str(floor))
     for cohort in labels:cc[cohort][k]=a
    # Empty all-player pools remain visible rather than silently disappearing.
    cc.setdefault('all_eligible',{})
    for cohort,subset in sorted(cc.items()):
     for group,methods in groups:
      def value(k,m):return pool[k][m].get(metric) if m in SCORE_METHODS else external.get(k+(metric,m),(None,None))[0]
      common=sorted(k for k in subset if all(finite(value(k,m)) for m in methods));membership=hashlib.sha256(json.dumps(common).encode()).hexdigest()
      for m in methods:
       errors=[value(k,m)-subset[k] for k in common];n=len(errors);sw.writerow(dict(season=year,player_type=role,metric=metric,cohort=cohort,comparison_group=group,method=m,n=n,mae=sum(abs(e) for e in errors)/n if n else None,rmse=math.sqrt(sum(e*e for e in errors)/n) if n else None,bias=sum(errors)/n if n else None,membership_sha256=membership,stress_season=year==2020));score_rows+=1;cw.writerow(dict(season=year,player_type=role,metric=metric,cohort=cohort,comparison_group=group,method=m,eligible_actuals=len(subset),available_forecasts=sum(finite(value(k,m)) for k in subset),common_pool=n))
       # Keep pair files focused on the experimental targets and downstream count effects.
       if cohort=='all_eligible' and metric in ['SB','OUTS','IP','W','SO']:
        for k in common:pw.writerow(dict(season=year,player_type=role,mlbam_id=k[2],metric=metric,cohort=cohort,comparison_group=group,method=m,prediction=value(k,m),actual=subset[k],source_record_id='FROZEN_STANDALONE' if m in SCORE_METHODS else external[k+(metric,m)][1]));pair_rows+=1
 return dict(score_rows=score_rows,pair_rows=pair_rows)


def workload_comparator(c,items,actual):
 out=[]
 for year in range(2019,2027):
  methods=['frozen_v1_5','workload_candidate','selected_workload_experiment','v1_3_change_candidate'];common=[k for k,d in items.items() if k[:2]==(year,'pitcher') and finite(actual.get(k+('OUTS',))) and all(finite(d[n]) for n in ['baseline','candidate','selected','v1_3_change_candidate'])];membership=hashlib.sha256(json.dumps(sorted(common)).encode()).hexdigest()
  for method,name in zip(methods,['baseline','candidate','selected','v1_3_change_candidate']):
   errors=[items[k][name]-actual[k+('OUTS',)] for k in common];n=len(errors);out.append(dict(season=year,method=method,n=n,rmse_OUTS=math.sqrt(sum(e*e for e in errors)/n) if n else None,mae_OUTS=sum(abs(e) for e in errors)/n if n else None,bias_OUTS=sum(errors)/n if n else None,membership_sha256=membership))
 return out


def direction_scores(items,actual,frequencies,maximum=2026):
 groups=defaultdict(list)
 for k,d in items.items():
  a=actual.get(k+('OUTS',));g=actual.get(k+('G',));anchor=d.get('anchor');p=d.get('growth_probability')
  if k[1]!='pitcher' or k[0]>maximum or not all(finite(x) for x in [a,g,anchor,p]) or g<=0:continue
  target=int(a>anchor);groups[k[0]].append((k[2],p,target))
 out=[]
 for year,rr in sorted(groups.items()):
  frequency=frequencies[str(year)];n=len(rr);out.append(dict(season=year,n=n,growth_cases=sum(r[2] for r in rr),model_brier=sum((p-a)**2 for _,p,a in rr)/n,frequency_brier=sum((frequency-a)**2 for _,p,a in rr)/n,model_accuracy=sum(int((p>=.5)==bool(a)) for _,p,a in rr)/n,membership_sha256=hashlib.sha256(json.dumps([r[0] for r in rr]).encode()).hexdigest()))
 return out
