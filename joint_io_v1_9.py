"""Read-only source chain, replay and frozen forecast verification."""
from pathlib import Path
from collections import defaultdict
from standalone_io_v1_0 import load,sha,verify
from refinement_io_v1_8 import context as context18,validate as validate18,emit
from growth_sb_io_v1_6 import forecast,FIELDS
from standalone_combined_v1_4 import near
from workload_experiments_io_v1_3 import iter_csv
from standalone_joint_workload_v1_9 import *

def context(run18,run16,diagnostics,run15,run14,source,matrix,baseline,labels):
 c=context18(run16,diagnostics,run15,run14,source,matrix,baseline,labels);f,pp,w=validate18(run18,c);c['watched'].update(w);c.update(run18=Path(run18).resolve(),items18=pp);return c

def source_hashes(c):return {str(p):sha(p) for p in [c['run18']/'freeze_manifest.json',c['run16']/'freeze_manifest.json',c['diagnostics']/'output_sha256.json',c['matrix']/'training_matrix.parquet',c['matrix']/'holdout_features.parquet',c['labels']/'training_labels.parquet',c['matrix']/'feature_schema.json']}

def predictions(c,model,year):
 pp={}
 for k,d in c['items16'].items():
  if k[0]!=year:continue
  if k[1]=='pitcher':pp[k]=predict_joint(k,d,c['rows'][k],model,c['old16']['settings'])
  else:
   v=c['base15'][k].get('SB');pp[k]=dict(metric='SB',baseline=v,candidate=v,raw_candidate=None,supported=False,support_status='SB_AUDIT_ONLY_NO_REPLACEMENT',research_v1_6=d['candidate'])
 return pp

def replay(c,items,s):
 history=defaultdict(list);choices=[]
 for y in range(2019,2027):
  choice=dict(season=y,pitcher=selection(history['pitcher'],y,s));choices.append(choice)
  for k,d in items.items():
   if k[0]==y and not near(d['selected'],d['candidate'] if k[1]=='pitcher' and choice['pitcher']['adopt'] else d['baseline']):raise ValueError('Joint selection chronology failure')
  add_history(y,items,c['rows'],c['actual_training'],history,s)
 return choices

def validate(run,c):
 run=Path(run).resolve();watched=verify(run)
 for n,h in load(run/'freeze_manifest.json').items():
  if sha(run/n)!=h:raise ValueError('v1.9 freeze mismatch')
 f=load(run/'frozen_models.json');s=settings_checked(f['settings']);models=load(run/'origin_models.json')
 if f['source_hashes']!=source_hashes(c) or set(models)!=set(map(str,range(2019,2027))):raise ValueError('Source/model domain mismatch')
 items={}
 for row in iter_csv(run/'experiment_predictions.csv'):
  k=(int(row.pop('season')),row.pop('player_type'),row.pop('mlbam_id'))
  if k not in c['items16'] or k in items or row['supported'] not in ['True','False']:raise ValueError('Invalid scalar domain')
  d={n:(v if n in ['metric','support_status'] else v=='True' if n=='supported' else None if v=='' else float(v)) for n,v in row.items()}
  if any(v is not None and not finite(v) for n,v in d.items() if n not in ['metric','support_status','supported']):raise ValueError('Nonfinite prediction')
  items[k]=d
 if set(items)!=set(c['items16']):raise ValueError('Incomplete scalar forecasts')
 for y in range(2019,2027):
  model=models[str(y)]
  for m in [model,model['pooled']]+list(model['experts'].values()):
   if any(v>=y or v==2020 for v in m['fit_years']):raise ValueError('Joint fit chronology failure')
  if model['origin']!=y:raise ValueError('Wrong origin')
  for k,d in predictions(c,model,y).items():
   for n,v in d.items():
    if (items[k][n]!=v if isinstance(v,(str,bool)) else not near(items[k][n],v)):raise ValueError('Joint forecast reproduction failure')
 choices=replay(c,items,s)
 if choices!=load(run/'rolling_choices.json') or choices[-1]!=f['final_choice'] or models['2026']!=f['model']:raise ValueError('Choice/model replay mismatch')
 if sha(run/'classification_and_probability_inputs.csv')!=sha(c['run16']/'classification_and_probability_inputs.csv'):raise ValueError('Role inputs changed')
 seen=set()
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  last=None;vv=None
  for r in iter_csv(run/name):
   k=(int(r['season']),r['player_type'],r['mlbam_id']);method=r['method'];token=(k,method,r['metric'])
   if k not in items or method not in METHODS or token in seen or (k[0]==2026)!=(name.startswith('frozen')):raise ValueError('Full forecast domain mismatch')
   if last!=(k,method):vv=forecast(c,k,items[k],method);last=k,method
   if r['metric'] not in vv or not near(None if r['prediction']=='' else float(r['prediction']),vv[r['metric']]):raise ValueError('Full forecast reproduction failed')
   seen.add(token)
 if len(seen)!=sum(len(v)*len(METHODS) for v in c['base15'].values()):raise ValueError('Incomplete full forecasts')
 # Predictor-only bin boundaries are frozen before any evaluation labels are opened.
 from sb_propensity_audit_v1_9 import freeze_bins
 allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist']
 if freeze_bins(c['rows'],allow,s)!=load(run/'sb_frozen_feature_bins.json'):raise ValueError('SB feature-bin reproduction failure')
 return f,items,watched

def parameter_rows(models):
 return [dict(origin=int(y),prior_role=role,**m) for y,v in models.items() for role,m in [('POOLED',v['pooled'])]+list(v['experts'].items())]
