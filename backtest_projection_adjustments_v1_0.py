"""Single fixed ridge residual model, 2024 fit/2025 selection/2026 frozen test.
Retains per-source analytical projection baselines and equal paired player sets.
"""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,shutil,sqlite3,statistics,tempfile
from contextlib import closing
from datetime import datetime,timezone
from pathlib import Path

VERSION='1.0.0'
REQUIRED_FILES=['projection_baselines.jsonl','model_features.csv','model_team_context.csv','training_labels.jsonl','model_input_audit.json']
def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')
def jsonl(path,rows):
 with Path(path).open('w',encoding='utf-8') as f:
  for r in rows:f.write(json.dumps(r,allow_nan=False)+'\n')
def csv_out(path,rows,fields=None):
 fields=fields or list(dict.fromkeys(k for r in rows for k in r)) or ['status']
 with Path(path).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def read_jsonl(path):
 with Path(path).open(encoding='utf-8-sig') as f:return [json.loads(line) for line in f if line.strip()]
def scores(pairs):
 if not pairs:return dict(n=0,mae=None,rmse=None,bias=None)
 errors=[pred-actual for pred,actual in pairs]
 return dict(n=len(pairs),mae=statistics.fmean(abs(v) for v in errors),rmse=math.sqrt(statistics.fmean(v*v for v in errors)),bias=statistics.fmean(errors))
def gain(base,adjusted):
 if not finite(base) or base<=0:return None
 return 100*(base-adjusted)/base

def solve(a,b):
 """Pivoted linear solve; ridge makes slope system positive definite."""
 n=len(b);m=[list(row)+[y] for row,y in zip(a,b)]
 for i in range(n):
  pivot=max(range(i,n),key=lambda j:abs(m[j][i]));m[i],m[pivot]=m[pivot],m[i]
  if abs(m[i][i])<1e-12:raise ValueError('Singular fit')
  scale=m[i][i];m[i]=[v/scale for v in m[i]]
  for j in range(n):
   if j==i:continue
   scale=m[j][i]
   for k in range(i,n+1):m[j][k]-=scale*m[i][k]
 return [r[-1] for r in m]

def eligible(row,metric,settings,minimum_features):
 m=row['metrics'];base=m.get(metric);expo=m.get(settings['exposure'])
 if metric in row.get('excluded_metrics',[]) or not finite(base) or base<0:return False,'MISSING_OR_EXCLUDED_BASELINE'
 if not finite(expo) or expo<=0:return False,'NONPOSITIVE_PROJECTED_EXPOSURE'
 if sum(finite(row['features'].get(k,(None,0))[0]) for k in settings['features'])<minimum_features:return False,'INSUFFICIENT_PRIOR_PLAYER_FEATURES'
 rule=settings['metrics'][metric]
 if base<rule.get('minimum_projected_value_for_adjustment',0):return False,'OUTSIDE_PROJECTED_ROLE_COHORT'
 if rule['kind']=='count' and base==0:return False,'ZERO_BASELINE_RETAINED'
 return True,'ELIGIBLE'

def input_values(row,metric,settings):
 values={}
 for k in settings['features']:
  value,reliability=row['features'].get(k,(None,0));values[k]=(value,reliability)
 for k in settings['team_features']:values['team_'+k]=row['team_features'].get(k,(None,0))
 rule=settings['metrics'][metric];baseline=row['metrics'][metric]
 values['baseline_rate']=(baseline/row['metrics'][settings['exposure']] if rule['kind']=='count' else baseline,1.0)
 return values

def encode(row,model,metric,settings):
 values=input_values(row,metric,settings);x=[1.0]
 for col in model['columns']:
  value,rel=values.get(col['name'],(None,0))
  x.append((value-col['mean'])/col['scale']*rel if finite(value) else 0.0)
  x.append(1.0 if finite(value) else 0.0)
 return x

def fit(rows,labels,typ,source,metric,cfg):
 settings=cfg['player_types'][typ];rule=settings['metrics'][metric];examples=[]
 for row in rows:
  ok,_=eligible(row,metric,settings,cfg['minimum_usable_player_features'])
  a=labels.get((typ,row['season'],row['player_id']),{})
  av=a.get(metric);ae=a.get(settings['exposure'])
  if not ok or not finite(av) or av<0 or not finite(ae) or ae<settings['headline_actual_exposure'] or ae<=0:continue
  base=row['metrics'][metric];pe=row['metrics'][settings['exposure']]
  residual=av/ae-base/pe if rule['kind']=='count' else av-base
  examples.append((row,residual))
 model=dict(player_type=typ,source=source,metric=metric,fit_season=cfg['fit_season'],fit_players=len(examples),columns=[],coefficients=None,status='INSUFFICIENT_FIT_SAMPLE')
 if len(examples)<cfg['minimum_fit_players']:return model
 names=settings['features']+['team_'+k for k in settings['team_features']]+['baseline_rate']
 for name in names:
  vals=[input_values(row,metric,settings)[name][0] for row,_ in examples]
  known=[v for v in vals if finite(v)]
  if len(known)<max(20,len(examples)//10):continue
  mean=statistics.fmean(known);scale=math.sqrt(statistics.fmean((v-mean)**2 for v in known))
  if scale<1e-10:continue
  model['columns'].append(dict(name=name,mean=mean,scale=scale,observed_fit_players=len(known)))
 if not any(col['name'] in settings['features'] for col in model['columns']):model['status']='NO_VARIABLE_PLAYER_FEATURES';return model
 x=[encode(row,model,metric,settings) for row,_ in examples];y=[value for _,value in examples];n=len(x[0])
 a=[[math.fsum(r[i]*r[j] for r in x) for j in range(n)] for i in range(n)]
 b=[math.fsum(r[i]*value for r,value in zip(x,y)) for i in range(n)]
 for i in range(1,n):a[i][i]+=cfg['ridge_strength']
 try:model['coefficients']=solve(a,b)
 except ValueError:model['status']='SINGULAR_FIT';return model
 if not all(finite(v) for v in model['coefficients']):model['status']='NONFINITE_FIT';model['coefficients']=None;return model
 model['status']='FITTED';return model

def candidate(row,model,metric,cfg):
 settings=cfg['player_types'][row['player_type']];base=row['metrics'].get(metric)
 if metric in row.get('excluded_metrics',[]) or not finite(base):return None,'MISSING_OR_EXCLUDED_BASELINE'
 ok,reason=eligible(row,metric,settings,cfg['minimum_usable_player_features'])
 if not ok:return base,reason
 if model.get('coefficients') is None:return base,'NO_FITTED_MODEL'
 residual=math.fsum(v*c for v,c in zip(encode(row,model,metric,settings),model['coefficients']))
 rule=settings['metrics'][metric]
 if rule['kind']=='count':delta=residual*row['metrics'][settings['exposure']];cap=abs(base)*rule['maximum_relative_change']
 else:delta=residual;cap=rule['maximum_absolute_change']
 delta=max(-cap,min(cap,delta));pred=max(rule.get('lower_bound',0.0),base+delta)
 if 'upper_bound' in rule:pred=min(rule['upper_bound'],pred)
 return pred,'CANDIDATE_ADJUSTMENT'

def paired_scores(rows,labels,model,metric,cfg,selected=False):
 typ=model['player_type'];settings=cfg['player_types'][typ];pair_rows=[];omitted=collections.Counter()
 for row in rows:
  a=labels.get((typ,row['season'],row['player_id']))
  if a is None:omitted['NO_ACTUAL_RECORD']+=1;continue
  av=a.get(metric);ae=a.get(settings['exposure']);base=row['metrics'].get(metric)
  if metric in row.get('excluded_metrics',[]) or not finite(base) or not finite(av):omitted['MISSING_OR_EXCLUDED_METRIC']+=1;continue
  if not finite(ae) or ae<=0:omitted['NONPOSITIVE_OR_MISSING_ACTUAL_EXPOSURE']+=1;continue
  adjusted,reason=candidate(row,model,metric,cfg)
  if selected and not model.get('selected'):adjusted=base;reason='VALIDATION_REJECTED'
  pair_rows.append(dict(player_type=typ,season=row['season'],source=row['source'],player_id=row['player_id'],name=row['name'],metric=metric,baseline=base,adjusted=adjusted,actual=av,actual_exposure=ae,headline=ae>=settings['headline_actual_exposure'],adjustment_status=reason,record_id=row['record_id']))
 result={}
 for cohort in ['all_matched','headline']:
  cohort_rows=[r for r in pair_rows if cohort=='all_matched' or r['headline']]
  b=scores([(r['baseline'],r['actual']) for r in cohort_rows]);a=scores([(r['adjusted'],r['actual']) for r in cohort_rows])
  result[cohort]=dict(baseline=b,adjusted=a,mae_gain_pct=gain(b['mae'],a['mae']),rmse_gain_pct=gain(b['rmse'],a['rmse']),changed_players=sum(r['baseline']!=r['adjusted'] for r in cohort_rows))
 return result,pair_rows,dict(omitted)

def select(model,validation,cfg):
 if model['status']!='FITTED':return False,model['status']
 for cohort in ['all_matched','headline']:
  r=validation[cohort]
  if r['baseline']['n']<cfg['minimum_validation_players']:return False,'INSUFFICIENT_VALIDATION_SAMPLE_'+cohort
  if r['mae_gain_pct'] is None or r['mae_gain_pct']<cfg['minimum_mae_gain_pct']:return False,'MAE_GATE_FAILED_'+cohort
  if r['rmse_gain_pct'] is None or r['rmse_gain_pct']<-cfg['maximum_rmse_decline_pct']:return False,'RMSE_GATE_FAILED_'+cohort
 return True,'VALIDATED'

def load_inputs(folder,cfg):
 audit=json.loads((folder/'model_input_audit.json').read_text(encoding='utf-8'))
 if audit.get('feature_event_end','9999')>=f"{cfg['holdout_season']}-01-01":raise ValueError('Feature audit exceeds holdout cutoff')
 if audit.get('target_season')!=cfg['holdout_season'] or audit.get('holdout_labels_loaded') is not False or audit.get('trace',{}).get('status')!='COMPLETE':raise ValueError('Requires a complete chronology-safe model-input run with full PA trace')
 features=collections.defaultdict(dict)
 with (folder/'model_features.csv').open(encoding='utf-8-sig',newline='') as f:
  seen=set()
  for r in csv.DictReader(f):
   key=(r['player_type'],int(r['projection_season']),r['player_id']);fk=(key,r['metric'])
   if fk in seen:raise ValueError('Duplicate player feature key')
   seen.add(fk)
   value=float(r['value']) if r['value'] else None;rel=float(r['reliability'])
   if not finite(rel) or rel<0 or rel>1 or (value is not None and not finite(value)):raise ValueError('Invalid feature or reliability')
   if value is not None and (not r['feature_season'] or int(r['feature_season'])>=key[1]):raise ValueError('Future/same-season player feature leakage')
   if value is not None and float(r['sample_size'])<float(r['minimum_sample']):raise ValueError('Feature sample gate violated')
   features[key][r['metric']]=(value,rel)
 team_features={}
 with (folder/'model_team_context.csv').open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   key=(r['player_type'],int(r['projection_season']),r['source'],r['player_id'])
   if key in team_features:raise ValueError('Duplicate team context key')
   if r['context_season'] and int(r['context_season'])>=key[1]:raise ValueError('Future/same-season team leakage')
   values={k:(float(r[k]),1.0) if r.get(k) and r['context_season'] else (None,0) for k in cfg['player_types'][key[0]]['team_features']}
   if any(v is not None and not finite(v) for v,_ in values.values()):raise ValueError('Nonfinite team feature')
   team_features[key]=values
 rows=read_jsonl(folder/'projection_baselines.jsonl');seen=set()
 for row in rows:
  key=(row['player_type'],row['season'],row['source'],row['player_id'])
  if key in seen:raise ValueError('Duplicate baseline key')
  seen.add(key)
  if row['season'] not in [cfg['fit_season'],cfg['validation_season'],cfg['holdout_season']]:raise ValueError('Unexpected projection season')
  row['features']=features[(row['player_type'],row['season'],row['player_id'])];row['team_features']=team_features.get(key,{})
 labels={}
 for row in read_jsonl(folder/'training_labels.jsonl'):
  if row['season'] not in [cfg['fit_season'],cfg['validation_season']]:raise ValueError('Holdout/future labels in training inputs')
  key=(row['player_type'],row['season'],row['player_id'])
  if key in labels:raise ValueError('Duplicate training label')
  labels[key]=row['metrics']
 return rows,labels,audit

def validate_config(cfg):
 years=[cfg['fit_season'],cfg['validation_season'],cfg['holdout_season']]
 if any(not isinstance(y,int) or isinstance(y,bool) for y in years) or not years[0]<years[1]<years[2]:raise ValueError('Seasons must be chronological')
 for k in ['ridge_strength','minimum_fit_players','minimum_validation_players','minimum_usable_player_features']:
  if not finite(cfg[k]) or cfg[k]<=0:raise ValueError('Invalid fit/sample control')
 if cfg['minimum_mae_gain_pct']<0 or cfg['maximum_rmse_decline_pct']<0:raise ValueError('Invalid validation threshold')
 for typ,s in cfg['player_types'].items():
  if typ not in ['hitter','pitcher'] or s['exposure']!=('PA' if typ=='hitter' else 'IP'):raise ValueError('Invalid player type/exposure')
  for metric,r in s['metrics'].items():
   cap=r.get('maximum_relative_change') if r['kind']=='count' else r.get('maximum_absolute_change')
   if not finite(cap) or cap<=0:raise ValueError('Invalid adjustment cap')


def build_models(rows,labels,cfg):
 grouped=collections.defaultdict(list)
 for row in rows:grouped[(row['player_type'],row['source'],row['season'])].append(row)
 models=[];validation_rows=[];score_rows=[];omissions=[]
 for typ,source in sorted({(row['player_type'],row['source']) for row in rows}):
  for metric in cfg['player_types'][typ]['metrics']:
   model=fit(grouped[(typ,source,cfg['fit_season'])],labels,typ,source,metric,cfg)
   validation,pairs,omitted=paired_scores(grouped[(typ,source,cfg['validation_season'])],labels,model,metric,cfg)
   selected,reason=select(model,validation,cfg);model.update(selected=selected,selection_reason=reason,validation_season=cfg['validation_season'],validation=validation)
   models.append(model);validation_rows.extend(pairs)
   omissions.append(dict(player_type=typ,source=source,metric=metric,phase='validation',counts=omitted))
   for cohort,r in validation.items():score_rows.append(dict(phase='validation_candidate',player_type=typ,source=source,metric=metric,cohort=cohort,selected=selected,selection_reason=reason,n=r['baseline']['n'],baseline_mae=r['baseline']['mae'],adjusted_mae=r['adjusted']['mae'],baseline_rmse=r['baseline']['rmse'],adjusted_rmse=r['adjusted']['rmse'],mae_gain_pct=r['mae_gain_pct'],rmse_gain_pct=r['rmse_gain_pct'],changed_players=r['changed_players']))
 return models,validation_rows,score_rows,omissions

def forecast(rows,models,cfg):
 index={(m['player_type'],m['source'],m['metric']):m for m in models};out=[]
 for row in rows:
  if row['season']!=cfg['holdout_season']:continue
  for metric in cfg['player_types'][row['player_type']]['metrics']:
   model=index[(row['player_type'],row['source'],metric)];base=row['metrics'].get(metric)
   if metric in row.get('excluded_metrics',[]) or not finite(base):pred=None;reason='MISSING_OR_EXCLUDED_BASELINE'
   elif not model['selected']:pred=base;reason='VALIDATION_REJECTED'
   else:pred,reason=candidate(row,model,metric,cfg)
   out.append(dict(season=row['season'],player_type=row['player_type'],source=row['source'],player_id=row['player_id'],name=row['name'],metric=metric,record_id=row['record_id'],baseline=base if finite(base) and metric not in row.get('excluded_metrics',[]) else None,prediction=pred,adjustment_status=reason,model_selected=model['selected'],projection_exposure=row['metrics'].get(cfg['player_types'][row['player_type']]['exposure'])))
 return out

def load_holdout(path,season):
 labels={}
 with closing(sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)) as db:
  db.row_factory=sqlite3.Row
  for typ in ['hitter','pitcher']:
   for r in db.execute('SELECT a.* FROM '+typ+'_actuals a JOIN record_selection rs USING(record_id) WHERE a.season=? AND rs.selected=1',[season]):
    key=(typ,season,r['player_id'])
    if key in labels:raise ValueError('Duplicate selected holdout actual')
    labels[key]=json.loads(r['metrics_json'])
 return labels

def evaluate_holdout(predictions,labels,cfg):
 grouped=collections.defaultdict(list);pair_rows=[];omissions=collections.Counter()
 for r in predictions:
  actual=labels.get((r['player_type'],r['season'],r['player_id']));metric=r['metric'];s=cfg['player_types'][r['player_type']]
  if actual is None:omissions[(r['player_type'],r['source'],metric,'NO_ACTUAL_RECORD')]+=1;continue
  av=actual.get(metric);ae=actual.get(s['exposure'])
  if not finite(r['baseline']) or not finite(r['prediction']) or not finite(av):omissions[(r['player_type'],r['source'],metric,'MISSING_OR_EXCLUDED_METRIC')]+=1;continue
  if not finite(ae) or ae<=0:omissions[(r['player_type'],r['source'],metric,'NONPOSITIVE_OR_MISSING_ACTUAL_EXPOSURE')]+=1;continue
  pair=dict(r,actual=av,actual_exposure=ae,headline=ae>=s['headline_actual_exposure']);pair_rows.append(pair)
  grouped[(r['player_type'],r['source'],metric)].append(pair)
 score_rows=[]
 for (typ,source,metric),pairs in sorted(grouped.items()):
  for cohort in ['all_matched','headline']:
   selected=[r for r in pairs if cohort=='all_matched' or r['headline']]
   b=scores([(r['baseline'],r['actual']) for r in selected]);a=scores([(r['prediction'],r['actual']) for r in selected])
   score_rows.append(dict(phase='frozen_holdout',player_type=typ,source=source,metric=metric,cohort=cohort,n=b['n'],baseline_mae=b['mae'],adjusted_mae=a['mae'],baseline_rmse=b['rmse'],adjusted_rmse=a['rmse'],mae_gain_pct=gain(b['mae'],a['mae']),rmse_gain_pct=gain(b['rmse'],a['rmse']),changed_players=sum(r['baseline']!=r['prediction'] for r in selected)))
 return score_rows,pair_rows,[dict(player_type=t,source=s,metric=m,reason=r,rows=n) for (t,s,m,r),n in sorted(omissions.items())]

def run(args):
 cfg=json.loads(Path(args.config).read_text(encoding='utf-8'));validate_config(cfg)
 root=Path(args.inputs).resolve();out=Path(args.output).resolve()
 if out.exists():raise ValueError('Output must not already exist')
 paths=[root/name for name in REQUIRED_FILES]+[Path(args.config).resolve(),Path(__file__).resolve()]
 if any(out==p or out in p.parents for p in paths):raise ValueError('Output cannot contain input files')
 fingerprints={str(p):sha(p) for p in paths}
 rows,labels,input_audit=load_inputs(root,cfg)
 out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=out.name+'.staging-',dir=out.parent))
 try:
  print('Fitting on 2024; selecting on 2025...',flush=True)
  models,validation_pairs,validation_scores,omissions=build_models(rows,labels,cfg)
  frozen=dict(version=VERSION,config=cfg,models=models,fit_season=cfg['fit_season'],validation_season=cfg['validation_season'],holdout_season=cfg['holdout_season'],input_sha256=fingerprints,no_refit_after_selection=True)
  dump(stage/'frozen_models.json',frozen);frozen_hash=sha(stage/'frozen_models.json')
  predictions=forecast(rows,models,cfg);jsonl(stage/'forecasts_2026.jsonl',predictions)
  forecast_hash=sha(stage/'forecasts_2026.jsonl')
  csv_out(stage/'validation_pairs.csv',validation_pairs);csv_out(stage/'validation_scores.csv',validation_scores)
  holdout_scores=[];holdout_omissions=[];reference_hash=None
  if args.evaluate_holdout:
   print('Models and forecasts frozen. Reading 2026 holdout actuals...',flush=True)
   reference=Path(args.sqlite).resolve();reference_hash=sha(reference)
   # Deliberately occurs only AFTER frozen_models and forecasts are written.
   holdout=load_holdout(reference,cfg['holdout_season'])
   holdout_scores,holdout_pairs,holdout_omissions=evaluate_holdout(predictions,holdout,cfg)
   csv_out(stage/'holdout_scores.csv',holdout_scores);csv_out(stage/'holdout_pairs.csv',holdout_pairs)
   if sha(reference)!=reference_hash:raise ValueError('SQLite changed during holdout evaluation')
  if sha(stage/'frozen_models.json')!=frozen_hash or sha(stage/'forecasts_2026.jsonl')!=forecast_hash:raise ValueError('Frozen model or forecasts changed during evaluation')
  for p,h in fingerprints.items():
   if sha(p)!=h:raise ValueError('Model input changed during build')
  dump(stage/'omissions.json',dict(validation=omissions,holdout=holdout_omissions))
  backup_root=Path(args.backup_root).resolve();backup_root.mkdir(parents=True,exist_ok=True)
  if backup_root==out or out in backup_root.parents:raise ValueError('Backup must be outside output')
  backup=backup_root/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
  summary=dict(version=VERSION,built_at=datetime.now(timezone.utc).isoformat(),fit_season=cfg['fit_season'],validation_season=cfg['validation_season'],holdout_season=cfg['holdout_season'],candidate_models=len(models),selected_models=sum(m['selected'] for m in models),selected=[dict(player_type=m['player_type'],source=m['source'],metric=m['metric'],fit_players=m['fit_players']) for m in models if m['selected']],holdout_evaluated=args.evaluate_holdout,projection_records=len(rows),holdout_forecast_rows=len(predictions),changed_holdout_forecasts=sum(finite(r['baseline']) and finite(r['prediction']) and r['baseline']!=r['prediction'] for r in predictions),frozen_model_sha256=frozen_hash,forecasts_sha256=forecast_hash,reference_sha256=reference_hash,inputs_unchanged=True,backup=str(backup),input_audit_trace=input_audit['trace'],limitations=['Single historical validation season; selection across metrics/sources can overfit. No statistical significance claim.','2026 holdout is used only for reporting; no model, selection, cap, or coefficients are retuned on it.','Per-source and per-metric research forecasts; no new consensus, dollar values, or production projection replacement.','Source projection metrics are used as published. Component coherence is not synthesized in these experimental forecasts.','Count residuals fit rates using actual training PA/IP, then hold projected PA/IP fixed at prediction time. Playing-time errors remain.','Role, zero-baseline, missing-feature and rejected-model fallbacks retain original projections.','Initial feature thresholds, reliability, caps and ridge penalty are fixed controls, not optimized hyperparameters.','Historical sources were retrieved retrospectively, not archived as-of vintages.'])
  dump(stage/'adjustment_backtest_audit.json',summary)
  print('Backing up complete backtest folder...',flush=True);shutil.copytree(stage,backup)
  for p in stage.rglob('*'):
   if p.is_file() and sha(p)!=sha(backup/p.relative_to(stage)):raise ValueError('Backup hash mismatch')
  stage.rename(out);return summary
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',default='config/projection_adjustments_v1_0.json');p.add_argument('--inputs',default='outputs/statcast_model_inputs_2026_v1_0');p.add_argument('--output',default='outputs/projection_adjustments_v1_0');p.add_argument('--backup-root',default='backups');p.add_argument('--evaluate-holdout',action='store_true');p.add_argument('--sqlite',default='data/warehouse_resolved/historical_projection_warehouse.sqlite')
 print(json.dumps(run(p.parse_args()),indent=2))
if __name__=='__main__':main()
