"""Frozen-input validation and common-pool workload comparisons for v1.3."""
import csv,hashlib,json
from pathlib import Path
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import load,sha,csvrows,write
from standalone_models_v1_0 import finite
from standalone_role_workload_v1_2 import ROLES,prior_role,actual_role
from standalone_workload_experiments_v1_3 import METHODS

FULL_FIELDS=['season','player_type','mlbam_id','method','metric','prediction']
def iter_csv(path):
 with Path(path).open(encoding='utf-8-sig',newline='') as f:yield from csv.DictReader(f)
def read_baseline(root):
 result={}
 for filename in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in iter_csv(Path(root)/filename):
   if r['method']!='v1_2':continue
   key=(int(r['season']),r['player_type'],r['mlbam_id']);v=result.setdefault(key,{})
   if r['metric'] in v:raise ValueError('Duplicate frozen baseline forecast')
   v[r['metric']]=float(r['prediction']) if r['prediction']!='' else None
 return result

def probability_bank(root,rows,freeze):
 path=Path(root)/'role_predictions.csv'
 if sha(path)!=freeze['role_predictions_sha256']:raise ValueError('Frozen role probability hash mismatch')
 expected={(int(r['target_season']),r['mlbam_id']) for r in rows if r['player_type']=='pitcher'};bank={}
 for r in iter_csv(path):
  if r['method'] not in ['prior_role','categorical']:continue
  key=(int(r['season']),r['mlbam_id']);latest=int(r['latest_fit_year']) if r['latest_fit_year']!='' else None;p=[float(r['p_'+role]) for role in ROLES]
  if key not in expected or (latest is not None and latest>=key[0]) or (key[0]==2026 and r['actual_role']!='NOT_READ') or r['predicted_role'] not in ROLES or r['prior_role'] not in ROLES+['UNKNOWN'] or not np.isfinite(p).all() or min(p)<0 or abs(sum(p)-1)>1e-8:raise ValueError('Invalid/nonchronological role probability source')
  item=bank.setdefault(key,{})
  if r['method'] in item:raise ValueError('Duplicate role probability source')
  item[r['method']]=dict(probabilities=p,predicted_role=r['predicted_role'],prior_role=r['prior_role'],latest_fit_year=latest)
 if set(bank)!=expected or any(set(v)!= {'prior_role','categorical'} for v in bank.values()):raise ValueError('Incomplete role probability source')
 for item in bank.values():
  if item['prior_role']['prior_role']!=item['categorical']['prior_role'] or item['prior_role']['latest_fit_year']!=item['categorical']['latest_fit_year']:raise ValueError('Probability arms have different source chronology or prior roles')
 return bank

def scores(predictions,rows,truth):
 rowmap={(r['target_season'],r['player_type'],str(r['mlbam_id'])):r for r in rows};groups=defaultdict(list);pairs=[];coverage=[]
 for r in predictions:
  key=(int(r['season']),r['player_type'],r['mlbam_id']);metric='PA' if key[1]=='hitter' else 'OUTS';a=truth.get(key+(metric,));paired=a is not None and all(finite(r.get(method)) for method in METHODS)
  coverage.append(dict(season=key[0],player_type=key[1],mlbam_id=key[2],eligible_actual=a is not None,paired=paired,change_supported=r.get('change_supported'),probability_supported=r.get('probability_supported')))
  d=dict(r);d['actual']=a;d['paired']=paired;pairs.append(d)
  if not paired:continue
  source=rowmap[key];cohorts=['all_eligible'];pv=source.get('x_actual_lag1_'+metric)
  if key[1]=='pitcher':cohorts += ['prior_role_'+prior_role(source),'actual_role_'+actual_role(source)]
  for floor in ([100,300] if key[1]=='hitter' else [40,100]):
   if a/(3 if key[1]=='pitcher' else 1)>=floor:cohorts.append('actual_exposure_ge'+str(floor))
  if finite(pv):cohorts.append('actual_increase_from_prior' if a>pv else 'actual_no_increase_from_prior')
  for cohort in cohorts:
   for method in METHODS:groups[key[0],key[1],metric,cohort,method].append((key[2],r[method]-a))
 summary=[]
 for (year,role,metric,cohort,method),items in sorted(groups.items()):
  e=np.array([e for _,e in items]);summary.append(dict(season=year,player_type=role,metric=metric,cohort=cohort,method=method,n=len(items),mae=float(abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias=float(e.mean()),membership_sha256=hashlib.sha256(json.dumps([pid for pid,e in items]).encode()).hexdigest()))
 return summary,pairs,coverage

def write_scores(stage,predictions,rows,truth,prefix):
 summary,pairs,coverage=scores(predictions,rows,truth);fields=sorted(set().union(*(r.keys() for r in pairs))) if pairs else ['season','player_type','mlbam_id','actual'];write(stage/(prefix+'_scores.csv'),summary,['season','player_type','metric','cohort','method','n','mae','rmse','bias','membership_sha256']);write(stage/(prefix+'_pairs.csv'),pairs,fields);write(stage/(prefix+'_coverage.csv'),coverage,['season','player_type','mlbam_id','eligible_actual','paired','change_supported','probability_supported']);return summary
