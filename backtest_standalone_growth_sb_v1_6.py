"""Separate historically selected workload-growth and SB opportunity experiments."""
import argparse,csv,json,shutil
from pathlib import Path
from collections import defaultdict
from contextlib import ExitStack
from standalone_io_v1_0 import load,sha,dump,start,finish,write
from standalone_growth_sb_v1_6 import *
from growth_sb_io_v1_6 import sources,forecast,frozen_hashes,FIELDS,replay
from growth_sb_scores_v1_6 import summaries,SCORE_FIELDS,COVERAGE_FIELDS,PAIR_FIELDS,direction_scores,DIRECTION_FIELDS


def write_scores(stage,c,items,actual,external=None,available=None,maximum=2026):
 with ExitStack() as stack:
  ww=[]
  for name,fields in [('category_scores.csv',SCORE_FIELDS),('category_coverage.csv',COVERAGE_FIELDS),('comparison_pairs.csv',PAIR_FIELDS)]:
   f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();ww.append(w)
  return summaries(c,items,actual,*ww,external,available,maximum)


def build(run15,run14,source,matrix,baseline,labels,config,output,backups):
 print('Verifying frozen v1.5 and earlier releases...',flush=True);c=sources(run15,run14,source,matrix,baseline,labels);config=Path(config).resolve();s=load(config);c['watched'][str(config)]=sha(config)
 if s['first_origin']!=2019 or s['evaluation_year']!=2026 or s['minimum_selection_folds']<2 or s['binary_penalty']<=0 or s['SB_calendar_era_start']!=2023 or s['source_2020_multiplier']!=2.7:raise ValueError('Unsupported settings or chronology')
 rows=prepared(c,s);allow=load(c['matrix']/'feature_schema.json')['predictor_allowlist'];base=load(c['baseline']/'frozen_models.json')['workload_model']['config'];actual=c['actual_training'];items={};history=defaultdict(list);choices=[];audit=[];frequencies={}
 output,backups,stage=start(output,backups,[run15,run14,source,matrix,baseline,labels,config])
 try:
  for year in range(2019,2027):
   print(f'{year}: separate growth/SB fits on earlier target seasons; holds and saves fixed',flush=True);models,aa=fit_models(rows,actual,allow,base,s,year);audit+=aa;current=[r for r in rows if r['target_season']==year];pp=predict_models(models,current,c['base15'],s);choice=dict(season=year,**{r:selection(history[r],year,r,s) for r in ['pitcher','hitter']});choices.append(choice);frequencies[str(year)]=models['pitcher']['occurrence']['frequency']
   for k,d in pp.items():
    old=c['base15'][k].get(d['metric']);items[k]=dict(**d,baseline=old,selected=d['candidate'] if choice[k[1]]['adopt'] else old,v1_3_change_candidate=c['predictions'][k]['workload_change_candidate'] if k[1]=='pitcher' else None)
   add_history(year,items,c['rows'],actual,history,s)
   if year==2026:final=models
  if choices!=replay(c,items,actual,s):raise ValueError('Internal selection replay mismatch')
  fields=['season','player_type','mlbam_id']+sorted(set().union(*(d.keys() for d in items.values())));write(stage/'experiment_predictions.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**d) for k,d in items.items()],fields);dump(stage/'rolling_choices.json',choices);dump(stage/'historical_gate_evidence.json',history);dump(stage/'fit_audit.json',audit);dump(stage/'direction_frequencies.json',frequencies)
  checks=[]
  with ExitStack() as stack:
   ww=[]
   for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();ww.append(w)
   for k,d in sorted(items.items()):
    for method in FULL_METHODS:
     v=forecast(c,k,d,method);checks.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,coherence_pass=True,saves_preserved=True,holds_preserved=True,zero_OUTS_positive_SV_or_HLD=k[1]=='pitcher' and v.get('OUTS')==0 and any(finite(v.get(m)) and v[m]>0 for m in ['SV','HLD'])))
     for m,x in v.items():ww[int(k[0]==2026)].writerow(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=method,metric=m,prediction=x))
  write(stage/'preservation_audit.csv',checks,list(checks[0]));shutil.copyfile(c['run15']/'classification_and_probability_inputs.csv',stage/'classification_and_probability_inputs.csv');counts=write_scores(stage,c,items,actual,maximum=2025);write(stage/'growth_direction_scores.csv',direction_scores(items,actual,frequencies,2025),DIRECTION_FIELDS)
  frozen=dict(version='1.6.0',settings=s,models=final,final_choices=choices[-1],source_hashes=frozen_hashes(c),evaluation_disclosure=DISCLOSURE)
  dump(stage/'frozen_models.json',frozen);dump(stage/'freeze_manifest.json',{n:sha(stage/n) for n in ['frozen_models.json','experiment_predictions.csv','rolling_choices.json','fit_audit.json','historical_forecasts.csv','frozen_2026_forecasts.csv','classification_and_probability_inputs.csv','direction_frequencies.json']})
  report=dict(version='1.6.0',status='SEPARATE_GROWTH_SB_EXPERIMENTS_FROZEN_RESEARCH_ONLY',v1_5_preserved=True,saves_preserved_exactly=True,holds_preserved_exactly=True,classification_labels_preserved=True,experiments_combined=False,evaluation_outcomes_read=False,inputs_unchanged=True,final_choices=choices[-1],final_model_support={r:final[r]['supported'] for r in ['pitcher','hitter']},**counts,evaluation_disclosure=DISCLOSURE,limitations=['Workload growth/decline is conditional on observed appearance and known prior OUTS. Missing/nonreturn outcomes are not zero.','Role-specific growth/decline log magnitudes use chronological predicted role probabilities at forecast time. Hard roles remain frozen; sparse experts fall back to pooled models.','SB opportunity is a proxy: non-HR hits plus walks plus HBP. It is not measured stealable-base opportunities or an attempts/success model.','SB retains frozen v1.5 PA and on-base components. No hitter component other than SB is changed.','Workload changes scale pitcher components except accepted HLD and SV, which remain fixed. ERA/WHIP remain coherent with scaled numerators/denominators.','Separate selected experiments are published; no combined winning-model ensemble is inferred.','No new injury, roster, prospect, bullpen hierarchy, sprint-speed or team-policy dataset is introduced. Retrospective vintages and participation limitations remain.'])
  dump(stage/'growth_sb_build_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run15',default='outputs/standalone_holds_attribution_v1_5');p.add_argument('--run14',default='outputs/standalone_combined_v1_4');p.add_argument('--source',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--config',default='config/standalone_growth_sb_v1_6.json');p.add_argument('--output',default='outputs/standalone_growth_sb_v1_6');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.run15,a.run14,a.source,a.matrix,a.baseline,a.labels,a.config,a.output,a.backup_root),indent=2))
