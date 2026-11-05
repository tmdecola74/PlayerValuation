"""Frozen source verification, reproducible overlays and audit output."""
from pathlib import Path
from collections import defaultdict
from standalone_io_v1_0 import load,sha,verify,write
from growth_sb_io_v1_6 import sources,validate as validate16,forecast,FIELDS
from standalone_growth_sb_v1_6 import prepared,FULL_METHODS
from standalone_combined_v1_4 import near
from standalone_refinements_v1_8 import *
from workload_experiments_io_v1_3 import iter_csv

def context(run16,diagnostics,run15,run14,source,matrix,baseline,labels):
 c=sources(run15,run14,source,matrix,baseline,labels);old,items,w=validate16(run16,c);c['watched'].update(w);diagnostics=Path(diagnostics).resolve();w=verify(diagnostics);c['watched'].update(w)
 report=load(diagnostics/'magnitude_diagnostic_report.json')
 if report['version']!='1.7.0' or report['include_2026'] or report['models_fitted'] or report['selection_changed'] or report['forecasts_modified']:raise ValueError('Require original historical-only v1.7 diagnostic evidence')
 if load(diagnostics/'source_rolling_choices_v1_6.json')!=load(Path(run16)/'rolling_choices.json'):raise ValueError('v1.7 source choice binding mismatch')
 recorded=load(diagnostics/'input_hashes.json')
 if sha(Path(run16)/'experiment_predictions.csv') not in recorded.values():raise ValueError('v1.7 not bound to this v1.6 forecast set')
 c.update(run16=Path(run16).resolve(),diagnostics=diagnostics,old16=old,items16=items);return c

def source_hashes(c):return {str(p):sha(p) for p in [c['run16']/'freeze_manifest.json',c['diagnostics']/'output_sha256.json',c['matrix']/'training_matrix.parquet',c['matrix']/'holdout_features.parquet',c['labels']/'training_labels.parquet']}

def predictions(c,models,rows,s):
 pp=sb_predict(models['hitter'],rows,c['base15'],s,c['items16'])
 for r in rows:
  if r['player_type']=='pitcher':
   k=(r['target_season'],'pitcher',r['mlbam_id']);pp[k]=calibrated(c['items16'][k],r,models['pitcher'],s,c['old16']['settings'])
 return pp

def replay(c,items,s):
 history=defaultdict(list);choices=[]
 for year in range(2019,2027):
  choice=dict(season=year,**{role:selection(history[role],year,role,s) for role in ['pitcher','hitter']});choices.append(choice)
  for k,d in items.items():
   if k[0]==year and not near(d['selected'],d['candidate'] if choice[k[1]]['adopt'] else d['baseline']):raise ValueError('Selection chronology replay failure')
  add_history(year,items,c['rows'],c['actual_training'],history,s)
 return choices

def validate(run,c):
 run=Path(run).resolve();w=verify(run)
 for n,h in load(run/'freeze_manifest.json').items():
  if sha(run/n)!=h:raise ValueError('v1.8 freeze mismatch')
 f=load(run/'frozen_models.json');s=settings_checked(f['settings'])
 if f['source_hashes']!=source_hashes(c):raise ValueError('v1.8 source bindings changed')
 items={};models=load(run/'origin_models.json');rr=prepared(c,c['old16']['settings'])
 for row in iter_csv(run/'experiment_predictions.csv'):
  k=(int(row.pop('season')),row.pop('player_type'),row.pop('mlbam_id'))
  if k in items or k not in c['items16']:raise ValueError('Duplicate/orphan v1.8 forecast')
  if row['supported'] not in ['True','False']:raise ValueError('Invalid support flag')
  d={n:(v if n in ['metric','support_status'] else v=='True' if n=='supported' else None if v=='' else float(v)) for n,v in row.items()}
  if any(v is not None and not finite(v) for n,v in d.items() if n not in ['metric','support_status','supported']):raise ValueError('Nonfinite forecast')
  items[k]=d
 if set(items)!=set(c['items16']) or set(models)!=set(map(str,range(2019,2027))):raise ValueError('Incomplete prediction/model domain')
 def chronology(x,year):
  if isinstance(x,dict):
   for n,v in x.items():
    if n in ['fit_years','fit_target_seasons'] and any(y>=year or y==2020 for y in v):raise ValueError('Model chronology failure')
    chronology(v,year)
  elif isinstance(x,list):
   for v in x:chronology(v,year)
 for year in range(2019,2027):
  model=models[str(year)];chronology(model,year);pp=predictions(c,model,[r for r in rr if r['target_season']==year],s)
  for k,d in pp.items():
   for n,v in d.items():
    if (items[k][n]!=v if isinstance(v,(str,bool)) else not near(v,items[k][n])):raise ValueError('Frozen forecast reproduction failed')
 choices=replay(c,items,s)
 if choices!=load(run/'rolling_choices.json') or choices[-1]!=f['final_choices'] or models['2026']!=f['models']:raise ValueError('Frozen choices/model mismatch')
 # Verify full vectors as well as the scalar experiments.
 seen=set()
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  last=None;vv=None
  for r in iter_csv(run/name):
   k=(int(r['season']),r['player_type'],r['mlbam_id']);method=r['method'];token=(k,method,r['metric'])
   if k not in items or method not in FULL_METHODS or token in seen or (k[0]==2026)!=(name.startswith('frozen')):raise ValueError('Invalid full forecast domain')
   if last!=(k,method):vv=forecast(c,k,items[k],method);last=k,method
   if r['metric'] not in vv or not near(None if r['prediction']=='' else float(r['prediction']),vv[r['metric']]):raise ValueError('Full projection mismatch')
   seen.add(token)
 if len(seen)!=sum(len(v)*len(FULL_METHODS) for v in c['base15'].values()):raise ValueError('Incomplete full projections')
 c['settings18']=s;return f,items,w

def emit(stage,name,rows):write(stage/name,rows,list(dict.fromkeys(n for r in rows for n in r)) or ['status'])

def parameter_rows(models):
 out=[]
 for y,m in models.items():
  for branch,pooled in m['pitcher']['pooled'].items():
   out.append(dict(origin=y,component=branch,prior_role='POOLED',use_pooled=False,fit_years=','.join(map(str,m['pitcher']['fit_years'])),**pooled))
   for role,d in m['pitcher']['experts'][branch].items():out.append(dict(origin=y,component=branch,prior_role=role,fit_years=','.join(map(str,m['pitcher']['fit_years'])),**d))
 return out
