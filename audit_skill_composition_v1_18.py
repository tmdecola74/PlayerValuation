"""Frozen skill-to-statistic replay and historical development diagnostics; no fitting."""
import argparse,json,math,shutil
from pathlib import Path
from collections import defaultdict,Counter
from standalone_io_v1_0 import load,dump,sha,verify,csvrows,start,finish
from standalone_diagnostics_v1_16 import checked,label_index,feature_index,cohorts,emit
from statcast_incremental_v1_17 import SPECS,METHODS,compose_fixed,rate_of,near,finite
VERSION='1.18.0'

def number(x):
 if x in ('',None):return None
 v=float(x)
 if not finite(v) or v<0:raise ValueError('Invalid forecast/rate')
 return v

def raw_vector(role,a,r):
 """Unnormalized diagnostic vector, not a publishable projection."""
 if not finite(a.get('PA' if role=='hitter' else 'OUTS')) or any(not finite(r.get(t.id)) for t in SPECS if t.role==role):return None
 if role=='hitter':
  v={'PA':a['PA']};v['AB']=v['PA']*r['hitter_AB_per_PA']
  for m in ['BB','HBP','SF','SH','R','RBI','SB']:v[m]=v['PA']*r['hitter_'+m+'_per_PA']
  for m in ['1B','2B','3B','HR']:v[m]=v['AB']*r['hitter_'+m+'_per_AB']
  v['H']=sum(v[m] for m in ['1B','2B','3B','HR'])
  v['AVG']=v['H']/v['AB'] if v['AB']>0 else None
  d=v['AB']+v['BB']+v['HBP']+v['SF'];v['OBP']=(v['H']+v['BB']+v['HBP'])/d if d>0 else None
  v['SLG']=sum(v[m]*w for m,w in [('1B',1),('2B',2),('3B',3),('HR',4)])/v['AB'] if v['AB']>0 else None
  v['OPS']=v['OBP']+v['SLG'] if v['OBP'] is not None and v['SLG'] is not None else None
 else:
  v={m:a['OUTS']*r['pitcher_'+m+'_per_OUTS'] for m in ['H','ER','BB','SO','HR','W','QS']};v.update({m:a[m] for m in ['OUTS','IP','SV','HLD','SV_plus_HLD']})
  v['ERA']=27*v['ER']/a['OUTS'] if a['OUTS']>0 else None;v['WHIP']=3*(v['H']+v['BB'])/a['OUTS'] if a['OUTS']>0 else None
 return v

def read_inputs(root,evaluation=False):
 prefix='frozen_2026' if evaluation else 'historical';rates={};vectors={}
 for r in csvrows(root/(prefix+'_skill_rates.csv')):
  k=int(r['season']),r['player_type'],r['mlbam_id'];t=r['target']
  if (k[0]!=2026 if evaluation else not 2019<=k[0]<=2025) or t not in {s.id for s in SPECS if s.role==k[1]}:raise ValueError('Wrong split/role/target')
  if k+(t,) in rates:raise ValueError('Duplicate skill row')
  rates[k+(t,)]=dict(r,**{m:number(r[m]) for m in METHODS})
 for r in csvrows(root/(prefix+'_forecasts.csv')):
  k=int(r['season']),r['player_type'],r['mlbam_id'];token=k+(r['method'],)
  if (k[0]!=2026 if evaluation else not 2019<=k[0]<=2025) or r['method'] not in METHODS or not k[2].isdigit():raise ValueError('Wrong forecast split/key')
  v=vectors.setdefault(token,{})
  if r['metric'] in v:raise ValueError('Duplicate forecast')
  v[r['metric']]=number(r['prediction'])
 if {k[:3] for k in rates}!={k[:3] for k in vectors}:raise ValueError('Unpaired rate/forecast populations')
 return rates,vectors

def trace(rates,vectors,actual,features):
 components=[];statistics=[];coverage=[]
 for k in sorted({k[:3] for k in rates}):
  role=k[1];spec=[t for t in SPECS if t.role==role];a=vectors[k+('accepted_frozen',)];rr={t.id:rates[k+(t.id,)] for t in spec}
  for t in spec:
   if not near(rr[t.id]['accepted_frozen'],rate_of(a,t)):raise ValueError('Accepted implied rate differs from frozen vector')
  for method in METHODS[1:]:
   r={t.id:rr[t.id][method] for t in spec};raw=raw_vector(role,a,r);final=vectors[k+(method,)];composed,_=compose_fixed(role,a,r,method)
   allaccepted=method=='historical_selected' and all(rr[t.id]['selected_method']=='accepted_frozen' for t in spec)
   if allaccepted:composed=dict(a)
   if set(final)!=set(composed) or any(not near(final[m],composed[m]) for m in final):raise ValueError('Frozen final forecast does not replay')
   anchors=['PA'] if role=='hitter' else ['OUTS','IP','SV','HLD','SV_plus_HLD']
   if any(final[m]!=a[m] for m in anchors):raise ValueError('Frozen anchor changed')
   paf=sum(r[t] for t in ['hitter_AB_per_PA','hitter_BB_per_PA','hitter_HBP_per_PA','hitter_SF_per_PA','hitter_SH_per_PA']) if role=='hitter' and raw else None
   hitf=sum(r['hitter_'+m+'_per_AB'] for m in ['1B','2B','3B','HR']) if role=='hitter' and raw else None
   base=dict(season=k[0],player_type=role,mlbam_id=k[2],method=method,history_seasons=features.get(k,{}).get('history_seasons'),prior_role=dict(cohorts(k,features,actual))['PRIOR_ROLE'])
   coverage.append(dict(base,unsupported_vector=raw is None,all_components_selected_accepted=allaccepted,pa_fraction_sum=paf,hit_fraction_sum=hitf,pa_scale=max(1,paf) if paf is not None else None,hit_scale=max(1,hitf) if hitf is not None else None,pitcher_hr_clipped=bool(role=='pitcher' and raw and raw['HR']>raw['H'])))
   for t in spec:
    av=rate_of(a,t);rv=r[t.id];fv=rate_of(final,t);num=actual.get(k+(t.numerator,));den=actual.get(k+(t.denominator,));truth=num/den if num is not None and den is not None and den>0 else None
    status='UNSUPPORTED_RATE' if rv is None else 'ALREADY_REPRODUCES_ACCEPTED' if near(rv,av) else 'NEW_RATE_FINAL_REPRODUCES_ACCEPTED' if near(fv,av) else 'NEW_RATE_FINAL_CHANGED'
    components.append(dict(base,target=t.id,selected_method=rr[t.id]['selected_method'],fit_status=rr[t.id].get('standard_fit_status' if method=='standard_skill' else 'statcast_fit_status') if method!='historical_selected' else 'MIXED_COMPONENTS',accepted_rate=av,raw_rate=rv,final_implied_rate=fv,actual_rate=truth,raw_rate_delta=rv-av if rv is not None and av is not None else None,composition_rate_delta=fv-rv if fv is not None and rv is not None else None,status=status))
   for m,fv in final.items():
    av=a.get(m);rv=raw.get(m) if raw else None;truth=actual.get(k+(m,))
    if m in ['AVG','OBP','SLG','OPS'] and actual.get(k+('AB',),0)<=0:truth=None
    if m in ['ERA','WHIP'] and actual.get(k+('OUTS',),0)<=0:truth=None
    row=dict(base,metric=m,accepted=av,raw_unconstrained=rv,final=fv,actual=truth,raw_minus_accepted=rv-av if rv is not None and av is not None else None,coherence_adjustment=fv-rv if fv is not None and rv is not None else None,final_minus_accepted=fv-av if fv is not None and av is not None else None)
    if all(x is not None for x in [av,rv,fv,truth]):
     ae=(av-truth)**2;re=(rv-truth)**2;fe=(fv-truth)**2
     row.update(raw_squared_error_change=re-ae,composition_squared_error_change=fe-re,final_squared_error_change=fe-ae)
     if not math.isclose((re-ae)+(fe-re),fe-ae,rel_tol=1e-9,abs_tol=1e-8):raise ValueError('Error decomposition does not telescope')
    statistics.append(row)
 return components,statistics,coverage

def summaries(rows,features,actual):
 groups=defaultdict(list)
 for r in rows:
  if 'final_squared_error_change' not in r:continue
  k=r['season'],r['player_type'],r['mlbam_id']
  for dim,c in cohorts(k,features,actual):groups[r['season'],r['player_type'],r['metric'],r['method'],dim,c].append(r)
 out=[]
 for (y,role,m,method,dim,c),rr in sorted(groups.items()):
  n=len(rr);row=dict(season=y,player_type=role,metric=m,method=method,cohort_dimension=dim,cohort=c,n=n,membership_sha256=__import__('hashlib').sha256(json.dumps(sorted(r['mlbam_id'] for r in rr)).encode()).hexdigest())
  for stage,col in [('accepted','accepted'),('raw','raw_unconstrained'),('final','final')]:
   e=[r[col]-r['actual'] for r in rr];row[stage+'_rmse']=math.sqrt(sum(x*x for x in e)/n);row[stage+'_mae']=sum(abs(x) for x in e)/n
  for col in ['raw_squared_error_change','composition_squared_error_change','final_squared_error_change']:row['mean_'+col]=sum(r[col] for r in rr)/n
  row['changed_from_accepted']=sum(not near(r['final'],r['accepted']) for r in rr);row['coherence_changed']=sum(not near(r['raw_unconstrained'],r['final']) for r in rr);out.append(row)
 return out

def build(a):
 root=Path(a.run).resolve();labels=Path(a.labels).resolve();matrix=Path(a.matrix).resolve();watched={}
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 names=['input_hashes.json','forecast_freeze.json','incremental_build_report.json','historical_skill_rates.csv','historical_forecasts.csv']
 for n in names:checked(root,n,watched)
 bindings=load(root/'input_hashes.json');freeze=load(root/'forecast_freeze.json')
 for n in ['incremental_build_report.json','historical_skill_rates.csv','historical_forecasts.csv']:
  if freeze.get(n)!=sha(root/n):raise ValueError('Invalid historical forecast freeze')
 if load(root/'incremental_build_report.json')['version']!='1.17.0':raise ValueError('Require v1.17 frozen experiment')
 print('Verifying historical labels, feature context and frozen v1.17 replay...',flush=True)
 paths=[checked(labels,'training_labels.parquet',watched),checked(matrix,'training_matrix.parquet',watched),checked(matrix,'feature_schema.json',watched)]
 if any(bindings.get(str(p))!=sha(p) for p in paths):raise ValueError('Historical reference/matrix binding mismatch')
 actual,_=label_index(paths[0]);_,features=feature_index(paths[1],load(paths[2])['predictor_allowlist']);rates,vectors=read_inputs(root)
 comp,stats,coverage=trace(rates,vectors,actual,features);summary=summaries(stats,features,actual)
 equal=defaultdict(list)
 for row in summary:equal[row['player_type'],row['metric'],row['method'],row['cohort_dimension'],row['cohort']].append(row)
 equal_rows=[]
 for (role,m,method,dim,c),rr in sorted(equal.items()):
  row=dict(player_type=role,metric=m,method=method,cohort_dimension=dim,cohort=c,seasons=json.dumps([x['season'] for x in rr]),folds=len(rr),n=sum(x['n'] for x in rr))
  for stage_name in ['accepted','raw','final']:
   row[stage_name+'_equal_season_rmse']=math.sqrt(sum(x[stage_name+'_rmse']**2 for x in rr)/len(rr));row[stage_name+'_equal_season_mae']=sum(x[stage_name+'_mae'] for x in rr)/len(rr)
  equal_rows.append(row)
 out,backups,stage=start(a.output,a.backup_root,[root,labels,matrix])
 try:
  for n,rows in [('equal_season_composition_summary',equal_rows),('component_trace',comp),('statistic_trace',stats),('composition_support',coverage),('historical_composition_scores',summary),('recent_2023_2025',[r for r in summary if r['season']>=2023]),('transition_2021',[r for r in summary if r['season']==2021]),('established_history',[r for r in summary if r['cohort_dimension']=='HISTORY' and r['cohort'] in ['2','GE3']]),('largest_composition_changes',[r for metric in sorted({x['metric'] for x in stats}) for r in sorted([x for x in stats if x['metric']==metric and x['coherence_adjustment'] is not None and not near(x['coherence_adjustment'],0)],key=lambda x:abs(x['coherence_adjustment']),reverse=True)[:25]])]:emit(stage/(n+'.csv'),rows)
  counts=Counter((r['method'],r['status']) for r in comp)
  emit(stage/'component_reproduction_counts.csv',[dict(method=m,status=s,rows=n) for (m,s),n in sorted(counts.items())])
  contract=dict(version=VERSION,status='DESIGN_ONLY_NOT_FITTED_OR_SELECTED',candidate='Chronological coherent-vector acceptance gate',hypothesis='Component-rate gains may fail to improve final coherent statistics; require end-to-end evidence.',design=['Retain the v1.17 paired estimator and frozen workload/saves/holds.', 'Compare full coherent candidate vectors with accepted forecasts on identical eligible earlier-fold pools.', 'Require historical final-statistic improvement and explicit recent-season, established-history and low-history guards before adoption.', 'Evaluate normalization-active and inactive rows separately; no residual-based corrections to individual players.', 'Keep 2021 and 2020; freeze metrics, support and gate thresholds before a new fit.'],thresholds='NOT_SELECTED_THIS_DIAGNOSTIC_BUILD',selection_max_season=2025,evaluation_2026_used=False)
  dump(stage/'next_candidate_design.json',contract)
  report=dict(version=VERSION,status='HISTORICAL_COMPOSITION_AUDIT_NO_MODEL_SELECTION',player_seasons=len({k[:3] for k in rates}),component_trace_rows=len(comp),statistic_trace_rows=len(stats),historical_seasons=sorted({r['season'] for r in comp}),replay_verified=True,anchors_verified=True,models_fitted=False,choices_changed=False,accepted_forecasts_modified=False,evaluation_outcomes_read=False,inputs_unchanged=True,limitations=['Unconstrained vectors are diagnostics, never valid projection exports.', 'Squared-error decomposition is an exact accounting identity, not causal attribution or proof of significance.', 'Raw rate equality uses the existing relative/absolute near tolerance.', 'Established-history cohorts use prior history; actual-exposure cohorts are retrospective only.', 'Large changes across different statistic units must not be compared as effect sizes; inspect within metric.', 'No new candidate is fitted or promoted. 2026 files are not opened; use existing v1.17 evaluation for disclosed reporting.'])
  dump(stage/'composition_audit_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(run='outputs/statcast_incremental_v1_17',labels='outputs/training_labels_v1_0',matrix='outputs/standalone_lagged_features_v1_0',output='outputs/skill_composition_audit_v1_18',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
