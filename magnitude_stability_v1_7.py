"""Fixed annual paired pools; no season removal or selection."""
from collections import defaultdict
from standalone_magnitude_diagnostics_v1_7 import *

def stability(pitchers,hitters,choices,maximum):
 groups=defaultdict(list)
 for d in pitchers:
  if not all(finite(d[n]) for n in ['baseline_error_OUTS','candidate_error_OUTS','selected_error_OUTS']):continue
  for c in pitcher_cohorts(d):
   for metric,scale in [('OUTS',1.),('IP',1/3)]:groups[d['season'],'pitcher',metric,c].append((d,scale))
 by=defaultdict(dict)
 for d in hitters:by[d['season'],d['mlbam_id']][d['method']]=d
 for mm in by.values():
  if len(mm)!=3 or not all(finite(d['error']) for d in mm.values()):continue
  d=mm['v1_6_candidate'];v=d|{name+'_error_OUTS':mm[method]['error'] for method,name in P_METHODS.items()}
  for c in sb_cohorts(d):groups[d['season'],'hitter','SB',c].append((v,1.))
 for y in range(2019,maximum+1):
  for role,metric in [('pitcher','OUTS'),('pitcher','IP'),('hitter','SB')]:groups[y,role,metric,'all']
 adoption={int(d['season']):d for d in choices};annual=[]
 for (y,role,metric,cohort),rr in sorted(groups.items()):
  common=dict(season=y,split=phase(y),player_type=role,metric=metric,cohort=cohort,n=len(rr),membership_sha256=hash_ids([d for d,s in rr]),candidate_supported=sum(d['full_vector_supported' if role=='pitcher' else 'full_candidate_supported'] for d,s in rr),frozen_adopted=adoption[y][role]['adopt'])
  for method,name in P_METHODS.items():
   e=[d[name+'_error_OUTS']*s for d,s in rr];mse=mean([x*x for x in e]);be=mean([(d['baseline_error_OUTS']*s)**2 for d,s in rr]);annual.append(common|dict(method=method,RMSE=rmse(e),MAE=mean([abs(x) for x in e]),bias=mean(e),MSE=mse,MSE_change_from_baseline=None if mse is None else mse-be))
 roll=[]
 for policy,years in [('development_policy',[2019,2021,2022,2023,2024,2025]),('all_historical_with_2020_stress',list(range(2019,2026)))]:
  gg=defaultdict(list)
  for d in annual:
   if d['season'] in years:gg[d['player_type'],d['metric'],d['cohort'],d['method']].append(d)
  for (role,metric,cohort,method),rr in sorted(gg.items()):
   valid=[d for d in rr if d['n']];roll.append(dict(policy=policy,player_type=role,metric=metric,cohort=cohort,method=method,requested_seasons=','.join(map(str,years)),eligible_seasons=','.join(str(d['season']) for d in valid),eligible_folds=len(valid),empty_folds=sum(not d['n'] for d in rr),equal_fold_mean_MSE=mean([d['MSE'] for d in valid]),equal_fold_mean_MAE=mean([d['MAE'] for d in valid]),improved_folds=sum(d['MSE_change_from_baseline']<0 for d in valid),worse_folds=sum(d['MSE_change_from_baseline']>0 for d in valid),selection_changed=False))
 return annual,roll
