"""Read-only frozen-label joins, matching comparison pools and workload attribution."""
import hashlib,json
from collections import defaultdict
from pathlib import Path
import numpy as np
import duckdb
from standalone_io_v1_0 import load,sha,table,csvrows,write
from standalone_models_v1_0 import finite
from standalone_role_workload_v1_2 import prior_role,actual_role
METRICS=['PA','OUTS','G','GS']
FIELDS=['season','player_type','mlbam_id','method','metric','prediction']

def read_labels(root,split):
 root=Path(root);name='training_labels.parquet' if split=='training' else 'holdout_labels.parquet';values={}
 with duckdb.connect() as db:
  rel=db.read_parquet(str(root/name));required={'season','player_type','mlbam_id','metric','label_value','eligible'}
  if not required<=set(rel.columns):raise ValueError('Frozen label schema mismatch')
  seasons={int(r[0]) for r in rel.project('season').distinct().fetchall()}
  if (split=='training' and any(y<2015 or y>2025 for y in seasons)) or (split!='training' and seasons!={2026}):raise ValueError('Frozen label split/season contamination')
  rows=rel.filter("metric IN ('PA','OUTS','G','GS')").project('season,player_type,mlbam_id,metric,label_value,eligible').fetchall()
  for y,role,pid,metric,value,eligible in rows:
   k=(int(y),role,str(pid),metric)
   if k in values or role not in ('hitter','pitcher') or not str(pid).isdigit() or int(str(pid))<=0 or not eligible or not finite(value) or value<0:raise ValueError('Invalid/duplicate frozen eligible actual')
   values[k]=float(value)
 return values

def verify_join(rows,values):
 for r in rows:
  for metric in METRICS:
   k=(int(r['target_season']),r['player_type'],str(r['mlbam_id']),metric);a=values.get(k);flag=r.get('y_eligible_'+metric,0);v=r.get('y_'+metric)
   if bool(flag)!=(a is not None) or (flag and (not finite(v) or abs(v-a)>1e-9)):raise ValueError('Frozen matrix/actual label disagreement: '+str(k))
 return values

def read_forecasts(root):
 out={}
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in csvrows(Path(root)/name):
   if r['method']!='v1_1':continue
   k=(int(r['season']),r['player_type'],r['mlbam_id']);v=out.setdefault(k,{})
   if r['metric'] in v:raise ValueError('Duplicate frozen v1.1 forecast')
   v[r['metric']]=float(r['prediction']) if r['prediction']!='' else None
 return out

def attribution(predictions,rows,actual):
 mapping={(r['target_season'],r['player_type'],str(r['mlbam_id'])):r for r in rows};groups=defaultdict(dict)
 for p in predictions:
  if p['metric'] in ['PA','OUTS']:groups[p['season'],p['player_type'],p['mlbam_id'],p['metric']][p['method']]=p['prediction']
 detail=[];errors=defaultdict(list);coverage=defaultdict(lambda:dict(candidates=0,eligible_actuals=0,paired=0))
 for k,v in sorted(groups.items()):
  y,role,pid,m=k;r=mapping[k[:3]];a=actual.get(k);c=coverage[y,role,m];c['candidates']+=1;c['eligible_actuals']+=int(a is not None)
  pair=a is not None and all(finite(v.get(method)) for method in ['v1_1','v1_2']);c['paired']+=int(pair);prior=prior_role(r) if role=='pitcher' else 'NOT_APPLICABLE';ar=actual_role(r) if role=='pitcher' else 'NOT_APPLICABLE';pv=r.get('x_actual_lag1_'+m);scale=1/3 if m=='OUTS' else 1
  d=dict(season=y,player_type=role,mlbam_id=pid,metric=m,actual=a,v1_1=v.get('v1_1'),v1_2=v.get('v1_2'),paired=pair,prior_role=prior,actual_role=ar,prior_volume=pv,actual_change_from_prior=None if a is None or not finite(pv) else a-pv,v1_1_error=None if not pair else v['v1_1']-a,v1_2_error=None if not pair else v['v1_2']-a,actual_IP=None if m!='OUTS' or a is None else a/3,v1_1_IP=None if m!='OUTS' or not finite(v.get('v1_1')) else v['v1_1']/3,v1_2_IP=None if m!='OUTS' or not finite(v.get('v1_2')) else v['v1_2']/3);detail.append(d)
  if not pair:continue
  cohorts=['all_eligible']
  if role=='pitcher':cohorts+=['prior_role_'+prior,'actual_role_'+ar]
  for floor in ([100,300] if role=='hitter' else [40,100]):
   if a*scale>=floor:cohorts.append('actual_'+('PA' if role=='hitter' else 'IP')+'_ge'+str(floor))
  if finite(pv):cohorts.append('actual_increase_from_prior' if a>pv else 'actual_no_increase_from_prior')
  for cohort in cohorts:
   for method,p in v.items():errors[y,role,m,cohort,method].append((pid,p-a))
 summary=[]
 for (y,role,m,cohort,method),items in sorted(errors.items()):
  e=np.array([e for _,e in items]);summary.append(dict(season=y,player_type=role,metric=m,cohort=cohort,method=method,n=len(items),mae=float(abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias=float(e.mean()),membership_sha256=hashlib.sha256(json.dumps([pid for pid,_ in items]).encode()).hexdigest()))
 return detail,summary,[dict(season=y,player_type=role,metric=m,**v) for (y,role,m),v in sorted(coverage.items())]

def write_attribution(stage,predictions,rows,actual):
 detail,summary,coverage=attribution(predictions,rows,actual)
 write(stage/'workload_attribution.csv',detail,['season','player_type','mlbam_id','metric','actual','v1_1','v1_2','paired','prior_role','actual_role','prior_volume','actual_change_from_prior','v1_1_error','v1_2_error','actual_IP','v1_1_IP','v1_2_IP']);write(stage/'workload_scores.csv',summary,['season','player_type','metric','cohort','method','n','mae','rmse','bias','membership_sha256']);write(stage/'workload_coverage.csv',coverage,['season','player_type','metric','candidates','eligible_actuals','paired']);return summary
