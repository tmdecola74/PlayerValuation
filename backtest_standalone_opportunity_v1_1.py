"""Versioned opportunity overlay; rolling historical selection, no 2026 labels read."""
import argparse,copy,hashlib,json,shutil
from pathlib import Path
from collections import defaultdict
import numpy as np
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite
from standalone_opportunity_v1_1 import train,forecast,selection,apply,DISCLOSURE

FIELDS=['season','player_type','mlbam_id','method','metric','prediction']
def old_forecasts(root):
 out={}
 for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in csvrows(root/name):
   if r['method']!='selected_standalone':continue
   k=(int(r['season']),r['player_type'],r['mlbam_id']);v=out.setdefault(k,{})
   if r['metric'] in v:raise ValueError('Duplicate v1.0 forecast')
   v[r['metric']]=float(r['prediction']) if r['prediction']!='' else None
 return out

def evidence(path,rows):
 if path is None:return {},0
 root=Path(path).resolve();watched=verify(root)
 if str(root/'confirmed_nonappearance.csv') not in watched:raise ValueError('Nonappearance decisions must be registered in evidence manifest')
 mapping={(r['target_season'],r['player_type'],r['mlbam_id']):r for r in rows};seen=set()
 for e in csvrows(root/'confirmed_nonappearance.csv'):
  k=(int(e['season']),e['player_type'],e['mlbam_id']);proof=(root/e['evidence_file']).resolve()
  if k in seen or not 2016<=k[0]<=2025 or k not in mapping or e['status']!='CONFIRMED_NO_MLB_APPEARANCE' or not e['source'].strip() or root not in proof.parents or str(proof) not in watched:raise ValueError('Invalid/unverified nonappearance evidence')
  seen.add(k);r=mapping[k];exp='PA' if k[1]=='hitter' else 'OUTS'
  if any(k.startswith('y_') and not k.startswith('y_eligible_') and r.get('y_eligible_'+k[2:]) and finite(v) and v>0 for k,v in r.items()):raise ValueError('Nonappearance conflicts with recorded appearance/outcomes')
  for m in ['G',exp]:r['y_'+m]=0;r['y_eligible_'+m]=1
 return watched,len(seen)

def actuals(rows):return {(int(r['target_season']),r['player_type'],str(r['mlbam_id']),k[2:]):v for r in rows for k,v in r.items() if k.startswith('y_') and not k.startswith('y_eligible_') and r.get('y_eligible_'+k[2:]) and finite(v)}
def summary(predictions,truth):
 groups=defaultdict(dict)
 for r in predictions:
  k=(int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric'])
  if r['method'] in groups[k]:raise ValueError('Duplicate forecast key')
  groups[k][r['method']]=r['prediction']
 errors=defaultdict(list);pairs=[]
 for k,methods in sorted(groups.items()):
  if k not in truth or not all(finite(methods.get(m)) for m in ['v1_0','v1_1']):continue
  y,role,pid,metric=k
  for method,v in methods.items():errors[y,role,metric,method].append((pid,v-truth[k]))
  pairs.append(dict(season=y,player_type=role,mlbam_id=pid,metric=metric,actual=truth[k],v1_0=methods['v1_0'],v1_1=methods['v1_1']))
 scores=[]
 for (y,role,metric,method),items in sorted(errors.items()):
  e=np.array([e for _,e in items]);scores.append(dict(season=y,player_type=role,metric=metric,method=method,n=len(items),mae=float(abs(e).mean()),rmse=float(np.sqrt((e*e).mean())),bias=float(e.mean()),membership_sha256=hashlib.sha256(json.dumps([p for p,_ in items]).encode()).hexdigest()))
 return scores,pairs

def scorewrite(stage,predictions,rows,prefix):
 s,p=summary(predictions,actuals(rows));write(stage/(prefix+'_scores.csv'),s,['season','player_type','metric','method','n','mae','rmse','bias','membership_sha256']);write(stage/(prefix+'_paired_predictions.csv'),p,['season','player_type','mlbam_id','metric','actual','v1_0','v1_1']);return len(p)

def build(matrix,baseline,config,output,backups,participation_evidence=None):
 matrix,baseline,config=map(lambda p:Path(p).resolve(),(matrix,baseline,config));watched=verify(matrix);watched.update(verify(baseline));watched[str(config)]=sha(config);settings=load(config);oldmodel=load(baseline/'frozen_models.json');freeze=load(baseline/'freeze_manifest.json')
 if sha(baseline/'frozen_models.json')!=freeze['models_sha256'] or sha(baseline/'frozen_2026_forecasts.csv')!=freeze['forecasts_sha256']:raise ValueError('v1.0 freeze mismatch')
 for filename,key in [('training_matrix.parquet','training_matrix_sha256'),('holdout_features.parquet','holdout_features_sha256'),('feature_schema.json','feature_schema_sha256')]:
  if sha(matrix/filename)!=oldmodel[key]:raise ValueError('v1.0 and v1.1 matrix/schema mismatch')
 if settings['first_origin']!=2019 or settings['holdout_year']!=2026:raise ValueError('Unsupported chronology')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];rows=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_features.parquet'),allow,False,2026)
 if any(r['target_season']!=2026 or any(k.startswith('y_') for k in r) for r in hold):raise ValueError('Evaluation features contain labels or incorrect season')
 if not all('y_'+m in r and 'y_eligible_'+m in r for r in rows for m in ['G','GS']):raise ValueError('Frozen matrix lacks G/GS labels. Rebuild lagged matrix with existing G/GS label fields.')
 ew,n=evidence(participation_evidence,rows);watched.update(ew);c=copy.deepcopy(oldmodel['config']);c.update(settings);old=old_forecasts(baseline);history=[];choices_log=[];audit=[];allpred=[];diagnostics=[]
 output,backups,stage=start(output,backups,[matrix,baseline,config]+([participation_evidence] if participation_evidence else []))
 try:
  for y in range(2019,2027):
   print(f'{y}: fitting opportunity models on target years before {y}',flush=True);fitting=[r for r in rows if r['target_season']<y];testing=hold if y==2026 else [r for r in rows if r['target_season']==y];bundle,fa=train(fitting,allow,c);pp=forecast(bundle,testing)
   for a in fa:
    if any(yr>=y for yr in a['fit_years']):raise ValueError('Fit chronology violation')
    audit.append(dict(origin=y,**a))
   choices={role+'_'+component:selection([h for h in history if h['season']<y],role,component,c) for role,component in [('hitter','volume'),('pitcher','volume'),('pitcher','saves')]};choices_log.append(dict(season=y,choices=choices));fold=defaultdict(list)
   for r in testing:
    key=(y,r['player_type'],r['mlbam_id']);role=key[1];volume='PA' if role=='hitter' else 'OUTS'
    if key not in old:raise ValueError('Frozen v1.0 candidate missing')
    original=old[key];d=pp[key];new=apply(original,d,role,choices)
    for method,v in [('v1_0',original),('v1_1',new)]:
     for metric,value in v.items():allpred.append(dict(season=y,player_type=role,mlbam_id=key[2],method=method,metric=metric,prediction=value))
    diagnostic=dict(season=y,player_type=role,mlbam_id=key[2],volume_application_supported=finite(original.get(volume)) and original[volume]>0,**d)
    if y<2026:
     for m in ['G','GS','SV']:diagnostic['actual_'+m]=r.get('y_'+m) if r.get('y_eligible_'+m) else None
     for component,metric,value in [('volume',volume,d['volume'])]+([('saves','SV',d.get('saves'))] if role=='pitcher' else []):
      a=r.get('y_'+metric)
      if r.get('y_eligible_'+metric) and finite(a) and finite(value) and finite(original.get(metric)):
       effective=value if component!='volume' or original[metric]>0 else original[metric];err=(original[metric]-a,effective-a);fold[role,component].append(err)
       if component=='saves' and finite(r.get('x_actual_lag1_SV')) and r['x_actual_lag1_SV']>=5:fold[role,'saves_relevant'].append(err)
    diagnostics.append(diagnostic)
   for (role,component),errors in fold.items():
    e=np.array(errors);history.append(dict(season=y,player_type=role,component=component,n=len(e),v1_mse=float((e[:,0]**2).mean()),candidate_mse=float((e[:,1]**2).mean()),v1_mae=float(abs(e[:,0]).mean()),candidate_mae=float(abs(e[:,1]).mean())))
   if y==2026:final=bundle;finalchoices=choices
  historical=[r for r in allpred if r['season']<2026];evaluation=[r for r in allpred if r['season']==2026];write(stage/'historical_forecasts.csv',historical,FIELDS);write(stage/'frozen_2026_forecasts.csv',evaluation,FIELDS);scorewrite(stage,historical,rows,'historical');write(stage/'opportunity_diagnostics.csv',diagnostics,sorted(set().union(*(r.keys() for r in diagnostics))))
  if participation_evidence:shutil.copytree(participation_evidence,stage/'participation_evidence_snapshot')
  dump(stage/'frozen_models.json',dict(version='1.1.0',training_matrix_sha256=sha(matrix/'training_matrix.parquet'),holdout_features_sha256=sha(matrix/'holdout_features.parquet'),models=final,choices=finalchoices,settings=settings,v1_0_models_sha256=freeze['models_sha256'],label_reference_sha256=oldmodel['label_reference_sha256'],evaluation_disclosure=DISCLOSURE));dump(stage/'rolling_choices.json',choices_log);dump(stage/'candidate_scores.json',history);dump(stage/'fit_chronology.json',audit);dump(stage/'freeze_manifest.json',dict(models_sha256=sha(stage/'frozen_models.json'),forecasts_sha256=sha(stage/'frozen_2026_forecasts.csv'),evaluation_labels_read=False))
  statuses={k:v['model']['ridge_status'] for k,v in final['models'].items()};report=dict(version='1.1.0',status='OPPORTUNITY_MODELS_FROZEN_RESEARCH_ONLY',v1_0_preserved=True,inputs_unchanged=True,evaluation_labels_read=False,evaluation_disclosure=DISCLOSURE,confirmed_nonappearance_rows=n,final_choices=finalchoices,model_statuses=statuses,external_projections_used=False,limitations=['Missing labels are unknown, not nonappearance. Participation unsupported without both verified classes; neutral multiplier 1 leaves conditional forecasts.','Prior-history candidates only; no complete preseason roster, prospect or injury model.','GS/G thresholds: starter >=0.5, reliever <=0.1, otherwise swing; invalid/missing role stays UNKNOWN.','Clipped ridge probabilities are not calibrated. No team save allocation or offseason role information.','2020 excluded from opportunity target fitting/selection; prior volume normalized by fixed 162/60.','2026 is a previously reviewed evaluation set. No claim of new independent holdout validation.'])
  dump(stage/'opportunity_build_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_baselines_v1_0');p.add_argument('--config',default='config/standalone_opportunity_v1_1.json');p.add_argument('--output',default='outputs/standalone_opportunity_v1_1');p.add_argument('--backup-root',default='backups');p.add_argument('--participation-evidence');a=p.parse_args();print(json.dumps(build(a.matrix,a.baseline,a.config,a.output,a.backup_root,a.participation_evidence),indent=2))
