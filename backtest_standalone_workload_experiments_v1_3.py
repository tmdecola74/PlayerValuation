"""Two separate workload experiments; historical selection, frozen references, no 2026 outcomes read."""
import argparse,copy,csv,json,shutil
from pathlib import Path
from collections import defaultdict
from standalone_io_v1_0 import *
from standalone_models_v1_0 import finite
from standalone_role_workload_v1_2 import ROLES,with_probabilities,fit_workload,predict_workload,prior_role
from role_workload_io_v1_2 import read_labels,verify_join
from standalone_workload_experiments_v1_3 import *
from workload_experiments_io_v1_3 import *

def build(matrix,baseline,opportunity,labels_root,config,output,backups):
 matrix,baseline,opportunity,labels_root,config=map(lambda p:Path(p).resolve(),(matrix,baseline,opportunity,labels_root,config));watched={}
 for root in [matrix,baseline,opportunity,labels_root]:watched.update(verify(root))
 watched[str(config)]=sha(config);s=load(config);old=load(baseline/'frozen_models.json');freeze=load(baseline/'freeze_manifest.json');ref=load(labels_root/'label_build_report.json')
 if s['evaluation_year']!=2026 or s['first_origin']!=2019 or s['direction_penalty']<=0:raise ValueError('Unsupported chronology/settings')
 if sha(baseline/'frozen_models.json')!=freeze['models_sha256'] or sha(baseline/'frozen_2026_forecasts.csv')!=freeze['forecasts_sha256'] or sha(opportunity/'frozen_models.json')!=old['v1_1_models_sha256']:raise ValueError('Frozen release mismatch')
 for filename,key in [('training_matrix.parquet','training_matrix_sha256'),('holdout_features.parquet','holdout_features_sha256'),('feature_schema.json','feature_schema_sha256')]:
  if sha(matrix/filename)!=old[key]:raise ValueError('Frozen v1.2 matrix/schema mismatch')
 if sha(labels_root/'training_labels.parquet')!=old['training_labels_sha256'] or ref['reference_sha256']!=old['label_reference_sha256'] or ref.get('primary_source')!='FROZEN_FANGRAPHS_ACTUALS':raise ValueError('Frozen actual-reference mismatch')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];rows=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_features.parquet'),allow,False,2026)
 if any(r['target_season']!=2026 or any(k.startswith('y_') for k in r) for r in hold):raise ValueError('Evaluation features contain labels/wrong year')
 truth=verify_join(rows,read_labels(labels_root,'training'));base=read_baseline(baseline);bank=probability_bank(baseline,rows+hold,freeze);baseconfig=old['workload_model']['config'];expertsettings=old['settings'];participant={}
 for r in iter_csv(opportunity/'opportunity_diagnostics.csv'):
  key=(int(r['season']),r['player_type'],r['mlbam_id']);p=float(r['participation_probability']) if r['participation_probability']!='' else None
  if key in participant or (p is not None and (not finite(p) or not 0<=p<=1)):raise ValueError('Invalid frozen participation source')
  participant[key]=p
 pitchers=[r for r in rows if r['player_type']=='pitcher'];hold_pitchers=[r for r in hold if r['player_type']=='pitcher'];arms={};armhold={}
 for arm in ['prior_role','categorical']:
  arms[arm]=with_probabilities(pitchers,[bank[r['target_season'],r['mlbam_id']][arm]['probabilities'] for r in pitchers]);armhold[arm]=with_probabilities(hold_pitchers,[bank[2026,r['mlbam_id']][arm]['probabilities'] for r in hold_pitchers])
 output,backups,stage=start(output,backups,[matrix,baseline,opportunity,labels_root,config]);histories=defaultdict(list);choice_log=[];audit=[];predictions=[];change_details=[];classifications=[];expert_details=[]
 try:
  # Full selected projections are streamed, avoiding copies of every candidate's count vector.
  with (stage/'historical_forecasts.csv').open('w',encoding='utf-8',newline='') as hf,(stage/'frozen_2026_forecasts.csv').open('w',encoding='utf-8',newline='') as ef:
   writers=[csv.DictWriter(f,fieldnames=FULL_FIELDS) for f in [hf,ef]]
   for w in writers:w.writeheader()
   for year in range(2019,2027):
    print(f'{year}: separate probability-input and workload-change experiments; fit target years < {year}',flush=True);testing=hold if year==2026 else [r for r in rows if r['target_season']==year];expected={};models={}
    for arm in ['prior_role','categorical']:
     fitting=[r for r in arms[arm] if r['target_season']<year];current=armhold[arm] if year==2026 else [r for r in arms[arm] if r['target_season']==year]
     for r in fitting+current:
      latest=bank[r['target_season'],r['mlbam_id']][arm]['latest_fit_year']
      if latest is not None and latest>=r['target_season']:raise ValueError('Probability input is not chronological OOF')
     bundle=fit_workload(fitting,allow,baseconfig,expertsettings);mix,values=predict_workload(bundle,current);models[arm]=bundle
     for name,m in [('POOLED',bundle['pooled'])]+[(name,x['model']) for name,x in bundle['experts'].items()]:
      if any(y>=year for y in m['fit_target_seasons']):raise ValueError('Expert fit chronology violation')
      audit.append(dict(origin=year,experiment='probability_'+arm,component=name,fit_years=m['fit_target_seasons'],n_fit=m['n_fit'],status=m['ridge_status']))
     for i,r in enumerate(current):
      key=(year,'pitcher',r['mlbam_id']);p=participant.get(key);conditional=mix[i];v=None if p is None or conditional is None else p*conditional;expected[arm,key]=v;expert_details.append(dict(season=year,mlbam_id=r['mlbam_id'],probability_arm=arm,conditional_OUTS=conditional,participation_probability=p,candidate_OUTS=v,starter_OUTS=values['STARTER'][i],reliever_OUTS=values['RELIEVER'][i],swing_OUTS=values['SWING'][i]))
    change,ca=fit_change([r for r in rows if r['target_season']<year],allow,baseconfig,s);cp=predict_change(change,testing,s)
    for a in ca:
     if any(y>=year for y in a['fit_years']):raise ValueError('Change model fit chronology violation')
     audit.append(dict(origin=year,experiment='change',**a))
    prob_gates={name:gates(histories['probability_'+name],year,s) for name in ['control','frozen']};prob_adopt=all(g['adopt'] for g in prob_gates.values());change_gates={role:gates(histories['change_'+role],year,s) for role in ['hitter','pitcher']};choice_log.append(dict(season=year,probability_experiment=dict(adopt=prob_adopt,comparisons=prob_gates),change_experiment=change_gates));fold=defaultdict(list)
    for r in testing:
     key=(year,r['player_type'],r['mlbam_id']);role=r['player_type'];metric='PA' if role=='hitter' else 'OUTS'
     if key not in base or key not in participant:raise ValueError('Missing frozen baseline/participation candidate')
     original=base[key];b=original.get(metric);p=participant[key];d=cp[key];raw_change=None if p is None or d['conditional_volume'] is None else p*d['conditional_volume'];control=effective(expected.get(('prior_role',key)),b) if role=='pitcher' else b;categorical=effective(expected.get(('categorical',key)),b) if role=='pitcher' else b;change_value=effective(raw_change,b);selected_probability=categorical if prob_adopt and role=='pitcher' else b;selected_change=change_value if change_gates[role]['adopt'] else b
     values=dict(zip(METHODS,[b,control,categorical,change_value,selected_probability,selected_change]));predictions.append(dict(season=year,player_type=role,mlbam_id=r['mlbam_id'],metric=metric,change_supported=d['support']=='AVAILABLE' and finite(p) and finite(b) and b>0,probability_supported=role=='pitcher' and finite(expected.get(('categorical',key))) and finite(b) and b>0,**values))
     for method,value in [('frozen_v1_2',b),('selected_probability_experiment',selected_probability),('selected_change_experiment',selected_change)]:
      v=volume_overlay(original,value,role)
      if v.get('SV')!=original.get('SV'):raise ValueError('Frozen saves changed')
      for name,prediction in v.items():writers[int(year==2026)].writerow(dict(season=year,player_type=role,mlbam_id=r['mlbam_id'],method=method,metric=name,prediction=prediction))
     detail=dict(season=year,player_type=role,mlbam_id=r['mlbam_id'],participation_probability=p,**d)
     if year<2026:
      a=truth.get(key+(metric,));detail['actual_volume']=a;detail['actual_change']=None if a is None or d['anchor'] is None else a-d['anchor']
      if a is not None and finite(b):
       guard=(prior_role(r)=='STARTER') if role=='pitcher' else d['anchor'] is not None and d['anchor']>=s['hitter_guard_prior_PA']
       if role=='pitcher' and finite(categorical) and finite(control):
        for name,comp in [('control',control),('frozen',b)]:
         item=(r['mlbam_id'],a,comp,categorical);fold['probability_'+name,'all'].append(item)
         if guard:fold['probability_'+name,'guard'].append(item)
       if finite(change_value):
        item=(r['mlbam_id'],a,b,change_value);fold['change_'+role,'all'].append(item)
        if guard:fold['change_'+role,'guard'].append(item)
     change_details.append(detail)
     if role=='pitcher':
      state=bank[year,r['mlbam_id']];classification=state['prior_role'];classifications.append(dict(season=year,mlbam_id=r['mlbam_id'],prior_role=classification['prior_role'],classification_label=classification['predicted_role'],classification_policy='FROZEN_PRIOR_ROLE_FOR_ALL_EXPERIMENTS',latest_role_fit_year=classification['latest_fit_year'],**{'prior_p_'+name:classification['probabilities'][i] for i,name in enumerate(ROLES)},**{'categorical_p_'+name:state['categorical']['probabilities'][i] for i,name in enumerate(ROLES)}))
    for (name,cohort),items in fold.items():histories[name].append(gate_statistics(year,cohort,items))
    if year==2026:final=dict(probability_models=models,change_models=change,probability_choice=dict(adopt=prob_adopt,comparisons=prob_gates),change_choices=change_gates)
  write(stage/'workload_predictions.csv',predictions,['season','player_type','mlbam_id','metric','change_supported','probability_supported']+METHODS);write(stage/'classification_and_probability_inputs.csv',classifications,list(classifications[0]));write(stage/'expert_predictions.csv',expert_details,list(expert_details[0]));write(stage/'change_predictions.csv',change_details,sorted(set().union(*(r.keys() for r in change_details))));write_scores(stage,[r for r in predictions if r['season']<2026],rows,truth,'historical');dump(stage/'historical_gate_evidence.json',dict(histories));dump(stage/'rolling_choices.json',choice_log);dump(stage/'fit_audit.json',audit)
  frozen=dict(version='1.3.0',settings=s,models=final,evaluation_disclosure=DISCLOSURE,source_v1_2_model_sha256=freeze['models_sha256'],source_role_probabilities_sha256=freeze['role_predictions_sha256'],source_v1_1_model_sha256=old['v1_1_models_sha256'],feature_schema_sha256=sha(matrix/'feature_schema.json'),training_matrix_sha256=sha(matrix/'training_matrix.parquet'),holdout_features_sha256=sha(matrix/'holdout_features.parquet'),training_labels_sha256=sha(labels_root/'training_labels.parquet'),label_reference_sha256=ref['reference_sha256'])
  dump(stage/'frozen_models.json',frozen);dump(stage/'freeze_manifest.json',{name:sha(stage/name) for name in ['frozen_models.json','frozen_2026_forecasts.csv','historical_forecasts.csv','workload_predictions.csv','classification_and_probability_inputs.csv','change_predictions.csv']})
  report=dict(version='1.3.0',status='SEPARATE_EXPERIMENTS_FROZEN_RESEARCH_ONLY',earlier_releases_preserved=True,saves_preserved_exactly=True,classification_policy='FROZEN_PRIOR_ROLE_FOR_ALL_EXPERIMENTS',classification_gate_weakened=False,evaluation_outcomes_read=False,inputs_unchanged=True,evaluation_disclosure=DISCLOSURE,final_probability_choice=final['probability_choice'],final_change_choices=final['change_choices'],limitations=['No combined winning-model ensemble or production replacement is published; selected experiments are separate.','Probability experiment must pass workload gates against both prior-probability control and frozen v1.2. It does not change hard classification labels.','Change modeling is conditional on observed appearance and known strict lag-1 exposure. Missing source/target exposure is not zero.','Probability magnitudes are research estimates, not guaranteed calibrated. Source 2020 volume normalization fixed 162/60; target 2020 excluded from fitting/selection.','Inherited participation support and prospect/injury/roster-universe limitations remain.','Repeated historical model comparisons can overfit. 2026 is disclosed evaluation data, not new independent holdout evidence.'])
  dump(stage/'workload_experiments_build_report.json',report);backup=finish(output,backups,stage,watched);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--opportunity',default='outputs/standalone_opportunity_v1_1');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--config',default='config/standalone_workload_experiments_v1_3.json');p.add_argument('--output',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.matrix,a.baseline,a.opportunity,a.labels,a.config,a.output,a.backup_root),indent=2))
