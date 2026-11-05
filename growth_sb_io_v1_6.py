"""Frozen v1.5 source chain, separate experiment overlays, and integrity verification."""
from pathlib import Path
from collections import defaultdict
from standalone_io_v1_0 import load,sha,verify
from standalone_combined_v1_4 import vectors as vectors14,coherent,read_all_labels,near
from holds_io_v1_5 import source_context,validate_run as validate15,overlay as holds_overlay
from workload_experiments_io_v1_3 import iter_csv
from standalone_workload_experiments_v1_3 import volume_overlay
from standalone_growth_sb_v1_6 import *

FIELDS=['season','player_type','mlbam_id','method','metric','prediction']

def sources(run15,run14,source,matrix,baseline,labels):
 c=source_context(run14,source,matrix,baseline,labels);actual=read_all_labels(c['labels'],'training');old,holds,w=validate15(run15,c,actual);c['watched'].update(w);c['run15']=Path(run15).resolve();c['actual_training']=actual;c['base15']={}
 for k in c['predictions']:
  v=vectors14(c,k)['combined_v1_4'];c['base15'][k]=holds_overlay(v,holds[k]['selected_v1_5']) if k[1]=='pitcher' else v
 return c

def forecast(c,key,d,method):
 role=key[1];base=c['base15'][key];out=dict(base);candidate=method in ['workload_candidate','SB_candidate'];selected=method in ['selected_workload_experiment','selected_SB_experiment'];value=d['candidate'] if candidate else d['selected'] if selected else d['baseline']
 if role=='pitcher' and method in ['workload_candidate','selected_workload_experiment']:
  out=volume_overlay(base,value,role);out['SV']=base.get('SV');out['HLD']=base.get('HLD');out['SV_plus_HLD']=base.get('SV_plus_HLD')
 elif role=='hitter' and method in ['SB_candidate','selected_SB_experiment']:out['SB']=value
 out=coherent(role,out)
 for name in ['SV','HLD','SV_plus_HLD']:
  if out.get(name)!=base.get(name):raise ValueError('Frozen saves/holds changed')
 if role=='hitter' and out.get('PA')!=base.get('PA'):raise ValueError('SB experiment changed playing time')
 if role=='hitter' and any(not near(out.get(m),v) for m,v in base.items() if m!='SB'):raise ValueError('SB experiment changed another statistic')
 if method=='selected_workload_experiment' and role=='hitter' and out!=base:raise ValueError('Experiments were combined')
 if method=='selected_SB_experiment' and role=='pitcher' and out!=base:raise ValueError('Experiments were combined')
 return out

def replay(c,items,actual,s):
 history=defaultdict(list);choices=[]
 for year in range(2019,2027):
  choice={r:selection(history[r],year,r,s) for r in ['pitcher','hitter']};choices.append(dict(season=year,**choice))
  for k,d in items.items():
   if k[0]!=year:continue
   expected=d['candidate'] if choice[k[1]]['adopt'] else d['baseline']
   if not near(d['selected'],expected):raise ValueError('Selection used wrong historical choices')
  add_history(year,items,c['rows'],actual,history,s)
 return choices

def frozen_hashes(c):
 return dict(v1_5_freeze_sha256=sha(c['run15']/'freeze_manifest.json'),v1_4_freeze_sha256=sha(c['run14']/'freeze_manifest.json'),v1_3_models_sha256=sha(c['source']/'frozen_models.json'),training_matrix_sha256=sha(c['matrix']/'training_matrix.parquet'),holdout_features_sha256=sha(c['matrix']/'holdout_features.parquet'),training_labels_sha256=sha(c['labels']/'training_labels.parquet'),feature_schema_sha256=sha(c['matrix']/'feature_schema.json'),label_reference_sha256=load(c['labels']/'label_build_report.json')['reference_sha256'])

def validate(run,c):
 run=Path(run).resolve();watched=verify(run)
 for n,h in load(run/'freeze_manifest.json').items():
  if sha(run/n)!=h:raise ValueError('v1.6 freeze mismatch')
 f=load(run/'frozen_models.json');s=f['settings']
 if f['source_hashes']!=frozen_hashes(c):raise ValueError('Frozen source binding mismatch')
 numeric=['baseline','candidate','selected','raw_candidate','anchor','growth_probability','conditional_growth_OUTS','conditional_decline_OUTS','participation_probability','projected_onbase_proxy','any_SB_probability','positive_SB_rate','v1_3_change_candidate'];items={}
 for r in iter_csv(run/'experiment_predictions.csv'):
  k=(int(r['season']),r['player_type'],r['mlbam_id'])
  if k not in c['predictions'] or k in items:raise ValueError('Invalid/duplicate experiment key')
  if r['supported'] not in ['True','False']:raise ValueError('Invalid candidate support')
  d={n:float(r[n]) if r[n]!='' else None for n in numeric};d.update(metric=r['metric'],supported=r['supported']=='True',support_status=r['support_status'])
  metric='OUTS' if k[1]=='pitcher' else 'SB'
  if d['metric']!=metric or not near(d['baseline'],c['base15'][k].get(metric)):raise ValueError('Changed baseline or target metric')
  if any(v is not None and (not finite(v) or v<0) for n,v in d.items() if n in numeric):raise ValueError('Invalid numeric forecast')
  if any(d[n] is not None and not 0<=d[n]<=1 for n in ['growth_probability','participation_probability','any_SB_probability']):raise ValueError('Invalid probability')
  expected=d['raw_candidate'] if d['supported'] else d['baseline']
  if not near(expected,d['candidate']):raise ValueError('Unsupported forecast did not retain baseline')
  if not near(d['v1_3_change_candidate'],c['predictions'][k]['workload_change_candidate'] if k[1]=='pitcher' else None):raise ValueError('Earlier rejected comparator changed')
  items[k]=d
 if set(items)!=set(c['predictions']):raise ValueError('Incomplete experiment domain')
 choices=replay(c,items,c['actual_training'],s)
 if choices!=load(run/'rolling_choices.json') or choices[-1]!=f['final_choices']:raise ValueError('Historical gate replay disagreement')
 for a in load(run/'fit_audit.json'):
  if not 2019<=a['origin']<=2026 or any(y>=a['origin'] or y==2020 for y in a['fit_years']):raise ValueError('Fit audit chronology failure')
 def inspect_models(x):
  if isinstance(x,dict):
   for n,v in x.items():
    if n in ['fit_years','fit_target_seasons'] and any(y>=2026 or y==2020 for y in v):raise ValueError('Final model chronology failure')
    inspect_models(v)
  elif isinstance(x,list):
   for v in x:inspect_models(v)
 inspect_models(f['models']);rr=prepared(c,s);pp=predict_models(f['models'],[r for r in rr if r['target_season']==2026],c['base15'],s)
 for k,d in pp.items():
  for n,v in d.items():
   if n in ['metric','support_status','supported']:
    if v!=items[k][n]:raise ValueError('Final support/metric reproduction failure')
   elif not near(v,items[k][n]):raise ValueError('Frozen forecast reproduction failure')
 seen=set()
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  last=None;vv=None
  for r in iter_csv(run/name):
   k=(int(r['season']),r['player_type'],r['mlbam_id']);method=r['method'];token=(k,method,r['metric'])
   if k not in items or method not in FULL_METHODS or token in seen or (k[0]==2026)!=(name.startswith('frozen')):raise ValueError('Duplicate/orphan full projection')
   if (k,method)!=last:vv=forecast(c,k,items[k],method);last=k,method
   if r['metric'] not in vv or not near(None if r['prediction']=='' else float(r['prediction']),vv[r['metric']]):raise ValueError('Full projection differs from frozen experiment overlay')
   seen.add(token)
 if len(seen)!=sum(len(v)*len(FULL_METHODS) for v in c['base15'].values()):raise ValueError('Incomplete full vector')
 if sha(run/'classification_and_probability_inputs.csv')!=sha(c['run15']/'classification_and_probability_inputs.csv'):raise ValueError('Hard role labels changed')
 return f,items,watched
