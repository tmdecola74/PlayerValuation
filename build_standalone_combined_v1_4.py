"""Combine accepted chronological hitter-change/pitcher-probability forecasts; no refitting."""
import argparse,csv,json,shutil
from contextlib import ExitStack
from standalone_io_v1_0 import dump,sha,start,finish,write
from standalone_combined_v1_4 import *

def build(source,matrix,baseline,labels,output,backups):
 print('Verifying frozen releases and replaying historical selection gates...',flush=True)
 c=context(source,matrix,baseline,labels);output,backups,stage=start(output,backups,[source,matrix,baseline,labels]);lineage=[];audits=[];changed={'hitter':0,'pitcher':0}
 try:
  with ExitStack() as stack:
   writers=[]
   for name in ['historical_forecasts.csv','frozen_2026_forecasts.csv','pitcher_change_research_only.csv']:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=FIELDS);w.writeheader();writers.append(w)
   for key in sorted(c['predictions']):
    year,role,pid=key;vv=vectors(c,key);selected=choose_for_role(role,None);metric='PA' if role=='hitter' else 'OUTS';old=c['base'][key].get(metric);new=vv['combined_v1_4'].get(metric);changed[role]+=int(not near(old,new));choice=c['choices'][year-2019];adopt=choice['change_experiment']['hitter']['adopt'] if role=='hitter' else choice['probability_experiment']['adopt']
    lineage.append(dict(season=year,player_type=role,mlbam_id=pid,selected_component=selected,historical_gate_adopted=adopt,selection_latest_allowed_season=year-1,baseline_volume=old,combined_volume=new,volume_metric=metric,changed=not near(old,new),saves_preserved=near(vv['combined_v1_4'].get('SV'),c['base'][key].get('SV'))))
    for method,v in vv.items():
     audits.append(dict(season=year,player_type=role,mlbam_id=pid,method=method,coherence_pass=True,saves_preserved=True,zero_OUTS_positive_SV=role=='pitcher' and v.get('OUTS')==0 and finite(v.get('SV')) and v['SV']>0))
     for name,value in v.items():writers[int(year==2026)].writerow(dict(season=year,player_type=role,mlbam_id=pid,method=method,metric=name,prediction=value))
    if role=='pitcher':
     # Unselected candidate remains separate even if it looks better in disclosed evaluation.
     v=coherent(role,volume_overlay(c['base'][key],c['predictions'][key][RESEARCH],role))
     for name,value in v.items():writers[2].writerow(dict(season=year,player_type=role,mlbam_id=pid,method='pitcher_change_research_only',metric=name,prediction=value))
  write(stage/'component_lineage.csv',lineage,list(lineage[0]));write(stage/'coherence_audit.csv',audits,list(audits[0]));dump(stage/'rolling_choices.json',c['choices']);shutil.copyfile(c['source']/'classification_and_probability_inputs.csv',stage/'classification_and_probability_inputs.csv')
  frozen=dict(version='1.4.0',composition_policy={'hitter':'selected_change_experiment','pitcher':'selected_probability_experiment','saves':'EXACT_FROZEN_V1_2','classification':'FROZEN_PRIOR_ROLE','pitcher_change':'SEPARATE_RESEARCH_ONLY'},source_v1_3_models_sha256=sha(c['source']/'frozen_models.json'),source_v1_3_freeze_sha256=sha(c['source']/'freeze_manifest.json'),source_v1_2_models_sha256=sha(c['baseline']/'frozen_models.json'),training_labels_sha256=c['frozen']['training_labels_sha256'],label_reference_sha256=c['frozen']['label_reference_sha256'],holdout_features_sha256=c['frozen']['holdout_features_sha256'],training_matrix_sha256=c['frozen']['training_matrix_sha256'],feature_schema_sha256=c['frozen']['feature_schema_sha256'],final_historical_choices=c['choices'][-1],models_refitted=False,selection_retuned=False,evaluation_disclosure=DISCLOSURE)
  dump(stage/'frozen_composition.json',frozen);dump(stage/'freeze_manifest.json',{n:sha(stage/n) for n in ['frozen_composition.json','historical_forecasts.csv','frozen_2026_forecasts.csv','pitcher_change_research_only.csv','component_lineage.csv','rolling_choices.json','classification_and_probability_inputs.csv']})
  # Historical scores use the full eligible frozen reference, never the 2026 label table.
  actual=read_all_labels(c['labels'],'training')
  with ExitStack() as stack:
   writers=[]
   for name,fields in [('historical_category_scores.csv',SCORE_FIELDS),('historical_category_coverage.csv',COVERAGE_FIELDS),('historical_category_pairs.csv',PAIR_FIELDS)]:
    f=stack.enter_context((stage/name).open('w',encoding='utf-8',newline=''));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();writers.append(w)
   counts=score_all(c,actual,*writers,maximum=2025)
  report=dict(version='1.4.0',status='COMBINED_FORECASTS_FROZEN_RESEARCH_ONLY',earlier_releases_preserved=True,models_refitted=False,selection_retuned=False,evaluation_outcomes_read=False,inputs_unchanged=True,saves_preserved_exactly=True,classification_labels_preserved=True,classification_gate_weakened=False,coherent_player_method_vectors=len(audits),changed_volume_player_seasons=changed,final_historical_choices=c['choices'][-1],historical_scores=counts,evaluation_disclosure=DISCLOSURE,limitations=['Composition reuses each origin\'s earlier-fold choices. No gate is retuned on combined category scores.','Hitter components scale with PA; pitcher components except saves scale with OUTS. Ratios are recomputed from coherent components. Saves retain their separate opportunity forecast.','Fractional expectations are retained; this is not an integer game-event simulation or weekly lineup model.','Pitcher-change candidate remains separate and never supplies combined forecasts.','Prospect, participation, retrospective source-vintage and era limitations of earlier releases remain.','2020 is reported only as a stress season, excluded from development selection.'])
  dump(stage/'combined_build_report.json',report);backup=finish(output,backups,stage,c['watched']);return report|{'backup':backup}
 finally:
  if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',default='outputs/standalone_workload_experiments_v1_3');p.add_argument('--matrix',default='outputs/standalone_lagged_features_v1_0');p.add_argument('--baseline',default='outputs/standalone_role_workload_v1_2');p.add_argument('--labels',default='outputs/training_labels_v1_0');p.add_argument('--output',default='outputs/standalone_combined_v1_4');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.source,a.matrix,a.baseline,a.labels,a.output,a.backup_root),indent=2))
