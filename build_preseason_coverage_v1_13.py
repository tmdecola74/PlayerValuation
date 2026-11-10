"""Freeze a reconciliation candidate and preseason universe; no 2026 label reads."""
import argparse,json,shutil,csv
from pathlib import Path
from collections import Counter
from standalone_io_v1_0 import load,sha,dump,verify,start,finish,table,csvrows,tree
from projection_release_v1_11_1 import HOME,CONS,META,METRICS,flat,parquet,emit,canonical_catalog,market_assets
from projection_release_audit_v1_12 import checked_file
from consensus_policy_v1_13 import POLICY,CANDIDATE,checked,reconcile
from preseason_universe_v1_13 import dated_evidence,assemble_universe,EVIDENCE_FIELDS,CUTOFF

DEFAULTS=dict(run='outputs/projection_release_2026_v1_11_1',labels='outputs/training_labels_v1_0',matrix='outputs/standalone_lagged_features_v1_0',warehouse='data/historical_duckdb_v1_0_bulk/player_valuation.duckdb',draft_inputs='data/valuation_inputs_dc_v1_1',policy='config/consensus_reconciliation_v1_13.json',preseason_evidence=None,output='outputs/preseason_coverage_v1_13',backup_root='backups')

def build(a):
 run,labels,matrix=map(lambda p:Path(p).resolve(),[a.run,a.labels,a.matrix]);watched=verify(run);report=load(run/'projection_release_report.json')
 if report['version']!='1.11.1' or report['models_fitted'] or report['choices_changed']:raise ValueError('Require accepted unchanged v1.11.1 release')
 for n,h in load(run/'forecast_freeze.json').items():
  p=(run/n).resolve()
  if run not in p.parents or sha(p)!=h:raise ValueError('Projection freeze mismatch')
 bindings=load(run/'input_hashes.json');training_path=checked_file(labels,'training_labels.parquet',watched);features_path=checked_file(matrix,'holdout_features.parquet',watched);label_report=checked_file(labels,'label_build_report.json',watched)
 if load(label_report)['reference_sha256']!=report['label_reference_sha256']:raise ValueError('Historical reference differs from release')
 for p in [training_path,features_path]:
  if bindings.get(str(p))!=sha(p):raise ValueError('Historical/feature source binding mismatch')
 catalog,names,w=canonical_catalog(a.warehouse);watched.update(w)
 if sha(a.warehouse)!=report['warehouse_sha256']:raise ValueError('Warehouse differs from release')
 assets,w=market_assets(a.draft_inputs,catalog)
 for p,h in w.items():
  if bindings.get(p)!=h:raise ValueError('Reviewed draft input changed since release: '+p)
 watched.update(w);policy=checked(load(a.policy));watched[str(Path(a.policy).resolve())]=sha(a.policy);policy_hash=sha(a.policy)
 evidence,w=dated_evidence(a.preseason_evidence,catalog,names);watched.update(w)
 originals=[]
 for role in METRICS:originals += [r for r in load(run/f'source_{role}_consensus.json') if int(r['season'])==2026]
 provenance={}
 for r in csvrows(run/'source_metric_provenance.csv'):
  if int(r['season'])!=2026:continue
  k=r['player_type'],r['player_id'],r['metric']
  if k in provenance:raise ValueError('Duplicate component provenance')
  provenance[k]=r
 records=load(run/'coherent_projection_records.json');old_quarantine={(r['player_type'],r['player_id']) for r in csvrows(run/'consensus_component_exceptions.csv')}
 inputs=[run,labels,matrix,a.warehouse,a.draft_inputs,a.policy]+([a.preseason_evidence] if a.preseason_evidence else [])
 out,backups,stage=start(a.output,a.backup_root,inputs)
 try:
  print('Testing fixed arithmetic reconciliation against preserved source components...',flush=True)
  candidates=[];ledger=[];cases=[];seen=set()
  for r in originals:
   role,pid=r['player_type'],r['player_id'];key=role,pid
   if key in seen:raise ValueError('Duplicate original consensus identity')
   seen.add(key);v,entries,decision=reconcile(r,{m:provenance.get((role,pid,m)) for m in r['metrics']},policy)
   identity=dict(season=2026,player_type=role,player_id=pid,mlbam_id=catalog.get(pid),name=r['name'],original_quarantined=key in old_quarantine,policy_version=policy['version'],policy_sha256=policy_hash)
   cases.append(dict(**identity,**decision))
   if v is None:continue
   candidates.append(flat(CANDIDATE,role,pid,catalog.get(pid),r['name'],'ORIGINAL_PRESEASON_CANONICAL',r.get('teams',[]),v))
   for entry in entries:ledger.append(dict(**identity,**{k:v for k,v in entry.items() if k!='policy_version'}))
  shutil.copyfile(run/'source_metric_provenance.csv',stage/'original_metric_provenance.csv')
  for role in METRICS:shutil.copyfile(run/f'source_{role}_consensus.json',stage/f'original_{role}_consensus.json')
  dump(stage/'original_consensus_records.json',originals);dump(stage/'candidate_projection_records.json',candidates);dump(stage/'policy_frozen.json',policy)
  for role in METRICS:
   rr=[r for r in candidates if r['player_type']==role];fields=META+METRICS[role]+(['K'] if role=='pitcher' else [])
   emit(stage,f'reconciled_consensus_{role}s_2026.csv',rr,fields);parquet(stage/f'reconciled_consensus_{role}s_2026.parquet',rr,fields)
   adapter=[dict(season=2026,player_type=role,player_id=r['player_id'],name=r['name'],mlbam_ids=[r['mlbam_id']] if r['mlbam_id'] else [],teams=json.loads(r['teams']),projection_source=CANDIDATE,metrics={m:r.get(m) for m in METRICS[role]}) for r in rr if r['valuation_ready']]
   dump(stage/f'reconciled_consensus_{role}_valuation_candidate.json',adapter)
   for extension in ['csv','parquet']:shutil.copyfile(run/f'homegrown_{role}s_2026.{extension}',stage/f'homegrown_{role}s_2026.{extension}')
  emit(stage,'reconciliation_component_ledger.csv',ledger);emit(stage,'reconciliation_adjustments.csv',[r for r in ledger if r['changed']]);emit(stage,'reconciliation_cases.csv',cases);emit(stage,'remaining_consensus_quarantine.csv',[r for r in cases if r['status']=='QUARANTINED'],list(cases[0]) if cases else ['status'])
  print('Building universe from preseason sources and prior history; no target labels...',flush=True)
  universe,asset_coverage,dated=assemble_universe(originals,records,candidates,assets,table(training_path),table(features_path),catalog,names,evidence)
  dump(stage/'preseason_universe.json',universe);emit(stage,'preseason_universe.csv',universe);emit(stage,'draft_asset_coverage.csv',asset_coverage);emit(stage,'dated_preseason_evidence_used.csv',dated,['universe_id']+EVIDENCE_FIELDS);emit(stage,'preseason_evidence_TEMPLATE.csv',[],EVIDENCE_FIELDS)
  emit(stage,'preseason_classification_review.csv',[r for r in universe if r['preseason_evidence_present'] and r['preseason_stratum'] in ['COLD_START_UNCLASSIFIED_PRESEASON_SOURCE','RETURNER_CANDIDATE_OLDER_HISTORY','OTHER_ROLE_HISTORY_REVIEW','CONFLICTING_PRESEASON_CLASSES_REVIEW']])
  emit(stage,'preseason_coverage_exceptions.csv',[r for r in universe if r['preseason_evidence_present'] and (not r['homegrown_forecast_present'] or r['preseason_stratum'] in ['IDENTITY_UNRESOLVED','CONFLICTING_PRESEASON_CLASSES_REVIEW'])])
  home_hashes={n:sha(run/n) for n in [f'homegrown_{role}s_2026.{ext}' for role in METRICS for ext in ['csv','parquet']]}
  if any(sha(stage/n)!=h for n,h in home_hashes.items()):raise ValueError('Accepted homegrown export changed')
  dump(stage/'forecast_and_universe_freeze.json',tree(stage))
  result=dict(version='1.13.0',status='RECONCILIATION_CANDIDATE_AND_PRESEASON_UNIVERSE_FROZEN',candidate_adopted=False,models_fitted=False,selection_changed=False,homegrown_forecasts_modified=False,evaluation_outcomes_read=False,universe_uses_2026_outcomes=False,effective_date=CUTOFF,date_basis='User-confirmed preseason source dates; retrospective retrieval, no independent archive certification',policy=policy,homegrown_export_sha256=home_hashes,source_release=str(run),source_release_sha256=sha(run/'projection_release_report.json'),source_warehouse_sha256=sha(a.warehouse),label_reference_sha256=report['label_reference_sha256'],training_labels_sha256=sha(training_path),original_consensus_rows=len(originals),candidate_rows=len(candidates),recovered_original_quarantine=sum(r['original_quarantined'] and r['status']=='CANDIDATE_AVAILABLE' for r in cases),remaining_quarantine=sum(r['status']=='QUARANTINED' for r in cases),adjustment_counts=dict(Counter(r['metric'] for r in ledger if r['changed'])),universe_rows=len(universe),preseason_evidence_rows=sum(r['preseason_evidence_present'] for r in universe),strata=dict(Counter(r['preseason_stratum'] for r in universe)),dated_evidence_rows=len(evidence),draft_assets=len(assets),inputs_unchanged=True,limitations=['This is an arithmetic research candidate, not a replacement for established consensus or homegrown forecasts. Fixed one-stat guards are policy assumptions, not proof of source rounding.','All original source metrics, including unexported metrics, remain in original_consensus_records.json. The candidate exports only the versioned released metric schema.','Missing counts are never zero-filled. H may be summed from complete hit types, OUTS derived from IP, and SO aliased from K under the existing schema. No playing-time forecast is supplied for cold starts.','Historical-only identities remain in the universe but are explicitly marked as lacking current preseason evidence. Presence does not imply active-roster status.','Prospect and international-arrival classes require dated evidence; unknown classes remain unknown. Date fields are claims validated for cutoff compliance, not independent historical certification.','No new skill/workload model is fitted. Future candidates require historical folds; 2026 remains previously reviewed evaluation-only.'])
  dump(stage/'preseason_coverage_build_report.json',result);backup=finish(out,backups,stage,watched);return dict(result,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in DEFAULTS.items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(build(p.parse_args()),indent=2))
if __name__=='__main__':main()
