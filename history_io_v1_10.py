"""Preserved v1.9 evidence and immutable simple-SB forecasts."""
from pathlib import Path
from collections import defaultdict
from standalone_io_v1_0 import load,sha,verify
from joint_io_v1_9 import context as context19,validate as validate19,emit,FIELDS
from standalone_combined_v1_4 import coherent,near
from workload_experiments_io_v1_3 import iter_csv
from standalone_SB_history_v1_10 import *

def context(run19,run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels):
 c=context19(run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels);f,pp,w=validate19(run19,c);c['watched'].update(w);c.update(run19=Path(run19).resolve(),items19=pp);return c

def source_hashes(c):return {str(p):sha(p) for p in [c['run19']/'freeze_manifest.json',c['run18']/'freeze_manifest.json',c['run16']/'freeze_manifest.json',c['matrix']/'training_matrix.parquet',c['matrix']/'holdout_features.parquet',c['labels']/'training_labels.parquet']}

def predictions(c,model,year,s):
 out={}
 for k in c['items19']:
  if k[0]!=year:continue
  if k[1]=='hitter':out[k]=prediction(k,c['rows'][k],c['base15'][k],model,s)
  else:
   b=c['base15'][k].get('OUTS');out[k]=dict(metric='OUTS',baseline=b,candidate=b,last_season=b,supported=False,last_supported=False,support_status='PITCHER_DIAGNOSTIC_ONLY',population_only=False)
 return out

def forecast(c,k,d,method):
 base=c['base15'][k];v=dict(base)
 if k[1]=='hitter':v['SB']=d['last_season'] if method=='last_season_rate' else d['candidate'] if method=='multiyear_candidate' else d['selected'] if method=='selected_SB_experiment' else d['baseline']
 v=coherent(k[1],v)
 if k[1]=='pitcher' and v!=base:raise ValueError('Pitcher diagnostic changed accepted forecasts')
 if k[1]=='hitter' and any(not near(v.get(n),value) for n,value in base.items() if n!='SB'):raise ValueError('SB baseline changed other hitter statistics')
 for n in ['SV','HLD','SV_plus_HLD']:
  if v.get(n)!=base.get(n):raise ValueError('Saves/holds changed')
 return v

def replay(c,items,s):
 history=defaultdict(list);choices=[]
 for y in range(2019,2027):
  choice=dict(season=y,hitter=selection(history,y,s));choices.append(choice)
  for k,d in items.items():
   if k[0]==y and not near(d['selected'],d['candidate'] if k[1]=='hitter' and choice['hitter']['adopt'] else d['baseline']):raise ValueError('SB choice chronology failure')
  add_history(y,items,c['rows'],c['actual_training'],history,s)
 return choices

def validate(run,c):
 run=Path(run).resolve();w=verify(run)
 for n,h in load(run/'freeze_manifest.json').items():
  if sha(run/n)!=h:raise ValueError('v1.10 freeze mismatch')
 f=load(run/'frozen_models.json');s=settings_checked(f['settings']);models=load(run/'origin_population_priors.json')
 if f['source_hashes']!=source_hashes(c) or set(models)!=set(map(str,range(2019,2027))):raise ValueError('Source/model bindings changed')
 items={}
 for row in iter_csv(run/'experiment_predictions.csv'):
  k=(int(row.pop('season')),row.pop('player_type'),row.pop('mlbam_id'))
  if k not in c['items19'] or k in items:raise ValueError('Scalar domain failure')
  for n in ['supported','last_supported','population_only']:
   if row[n] not in ['True','False']:raise ValueError('Invalid support flag')
  d={n:(v if n in ['metric','support_status'] else v=='True' if n in ['supported','last_supported','population_only'] else None if v=='' else float(v)) for n,v in row.items()}
  if any(v is not None and not finite(v) for n,v in d.items() if n not in ['metric','support_status','supported','last_supported','population_only']):raise ValueError('Nonfinite forecast')
  items[k]=d
 if set(items)!=set(c['items19']):raise ValueError('Incomplete scalar forecasts')
 for y in range(2019,2027):
  model=models[str(y)]
  if model['origin']!=y or any(v>=y or v==2020 for v in model['fit_years']):raise ValueError('Population prior chronology failure')
  if model['supported'] and not near(model['population_rate'],model['SB_sum']/model['proxy_sum']):raise ValueError('Population prior inconsistent')
  for k,d in predictions(c,model,y,s).items():
   for n,v in d.items():
    if (items[k][n]!=v if isinstance(v,(str,bool)) else not near(items[k][n],v)):raise ValueError('Frozen SB baseline reproduction failed')
 choices=replay(c,items,s)
 if choices!=load(run/'rolling_choices.json') or choices[-1]!=f['final_choice'] or models['2026']!=f['population_prior']:raise ValueError('Choice/prior mismatch')
 seen=set()
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  last=None;vv=None
  for r in iter_csv(run/name):
   k=(int(r['season']),r['player_type'],r['mlbam_id']);method=r['method'];token=(k,method,r['metric'])
   if k not in items or method not in METHODS or token in seen or (k[0]==2026)!=(name.startswith('frozen')):raise ValueError('Full forecast domain mismatch')
   if last!=(k,method):vv=forecast(c,k,items[k],method);last=k,method
   if r['metric'] not in vv or not near(None if r['prediction']=='' else float(r['prediction']),vv[r['metric']]):raise ValueError('Full forecast changed')
   seen.add(token)
 if len(seen)!=sum(len(v)*len(METHODS) for v in c['base15'].values()):raise ValueError('Incomplete full vector domain')
 return f,items,w
