"""Frozen-source loading, projection overlay and chronological selection replay."""
from collections import defaultdict
from pathlib import Path
from standalone_io_v1_0 import verify,load,sha
from standalone_combined_v1_4 import context,vectors,coherent,read_all_labels,near
from evaluate_standalone_combined_v1_4 import validate_combined
from standalone_holds_v1_5 import METHODS,prepared,predict_holds,choose,fold_history
from workload_experiments_io_v1_3 import iter_csv

HOLD_PRED_FIELDS=['season','player_type','mlbam_id','predicted_relief_G','hold_probability_given_relief','positive_hold_rate','participation_probability','raw_candidate_HLD','supported']+METHODS

def source_context(run,source,matrix,baseline,labels):
 c=context(source,matrix,baseline,labels);c['run14']=Path(run).resolve();c['watched'].update(validate_combined(c['run14'],c));return c

def overlay(v,holds):
 out=dict(v);out['HLD']=holds;out['SV_plus_HLD']=out['SV']+holds if out.get('SV') is not None and holds is not None else None
 result=coherent('pitcher',out)
 if result.get('SV')!=v.get('SV') or any(not near(result.get(m),x) for m,x in v.items() if m not in ['HLD','SV_plus_HLD']):raise ValueError('Non-holds component changed')
 return result

def replay(c,items,truth,s):
 history=defaultdict(list);choices=[]
 for year in range(2019,2027):
  d=choose(history,year,s);choices.append(dict(season=year,**d))
  for k,r in items.items():
   if k[0]!=year:continue
   expected=r['holds_opportunity_candidate'] if d['adopt'] else r['combined_v1_4']
   if not near(expected,r['selected_v1_5']):raise ValueError('Holds selection violates earlier-fold policy')
  fold_history(year,items,c['rows'],truth,history,s)
 return choices

def validate_run(run,c,truth):
 run=Path(run).resolve();watched=verify(run)
 for n,h in load(run/'freeze_manifest.json').items():
  if sha(run/n)!=h:raise ValueError('v1.5 freeze mismatch')
 frozen=load(run/'frozen_models.json')
 if sha(c['run14']/'freeze_manifest.json')!=frozen['v1_4_freeze_sha256'] or sha(c['source']/'frozen_models.json')!=frozen['v1_3_models_sha256'] or sha(c['labels']/'training_labels.parquet')!=frozen['training_labels_sha256'] or frozen['label_reference_sha256']!=load(c['labels']/'label_build_report.json')['reference_sha256']:raise ValueError('v1.5 source binding mismatch')
 s=frozen['settings'];items={}
 numeric=['predicted_relief_G','hold_probability_given_relief','positive_hold_rate','participation_probability','raw_candidate_HLD']+METHODS
 for r in iter_csv(run/'holds_predictions.csv'):
  key=(int(r['season']),r['player_type'],r['mlbam_id'])
  if key in items or key not in c['predictions'] or key[1]!='pitcher':raise ValueError('Duplicate/orphan holds forecast')
  if r['supported'] not in ['True','False']:raise ValueError('Invalid support flag')
  d={n:float(r[n]) if r[n]!='' else None for n in numeric};d['supported']=r['supported']=='True';vv=vectors(c,key)
  for m in METHODS[:2]:
   if not near(d[m],vv[m].get('HLD')):raise ValueError('Changed holds baseline')
  raw=d['raw_candidate_HLD'];expected=raw if raw is not None else d['combined_v1_4']
  if not near(expected,d['holds_opportunity_candidate']) or (raw is not None)!=(d['supported']):raise ValueError('Invalid unsupported candidate fallback')
  if any(v is not None and (not __import__('math').isfinite(v) or v<0) for n,v in d.items() if n!='supported'):raise ValueError('Invalid holds magnitude')
  if any(d[n] is not None and not 0<=d[n]<=1 for n in ['hold_probability_given_relief','positive_hold_rate','participation_probability']):raise ValueError('Invalid holds probability/rate')
  items[key]=d
 if set(items)!={k for k in c['predictions'] if k[1]=='pitcher'}:raise ValueError('Incomplete holds forecast domain')
 choices=replay(c,items,truth,s)
 if choices!=load(run/'historical_holds_choices.json') or choices[-1]!=frozen['final_choice']:raise ValueError('Replayed historical holds gates disagree')
 for a in load(run/'fit_audit.json'):
  if any(y>=a['origin'] or y==2020 for y in a['fit_years']):raise ValueError('Future fit year')
 for model in [frozen['model']['relief_model'],frozen['model']['positive_model']]:
  if any(y>=2026 or y==2020 for y in model['fit_target_seasons']):raise ValueError('Future final fit year')
 if any(y>=2026 or y==2020 for y in frozen['model']['occurrence']['fit_years']):raise ValueError('Future occurrence fit year')
 rows=prepared(c);reproduced=predict_holds(frozen['model'],[r for r in rows if r['target_season']==2026],s)
 for key,d in reproduced.items():
  for name,v in d.items():
   if name=='supported':
    if v!=items[key][name]:raise ValueError('Final support reproduction failed')
   elif not near(v,items[key][name]):raise ValueError('Frozen 2026 holds forecast reproduction failed')
 expected_keys=set();seen=set()
 for filename in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  last=None;v=None
  for r in iter_csv(run/filename):
   k=(int(r['season']),r['player_type'],r['mlbam_id']);token=(k,r['metric'])
   if k not in c['predictions'] or token in seen or r['method']!='selected_v1_5' or (k[0]==2026)!=(filename.startswith('frozen')):raise ValueError('Duplicate/orphan v1.5 full forecast')
   if last!=k:
    v=vectors(c,k)['combined_v1_4'];v=overlay(v,items[k]['selected_v1_5']) if k[1]=='pitcher' else v;last=k
   if r['metric'] not in v or not near(None if r['prediction']=='' else float(r['prediction']),v[r['metric']]):raise ValueError('Unexpected non-holds vector change')
   seen.add(token)
 if len(seen)!=sum(len(vectors(c,k)['combined_v1_4']) for k in c['predictions']):raise ValueError('Incomplete v1.5 full vector')
 if sha(run/'classification_and_probability_inputs.csv')!=sha(c['run14']/'classification_and_probability_inputs.csv'):raise ValueError('Classification changed')
 return frozen,items,watched
