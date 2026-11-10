"""Audit, conditionally support reconciled exports, prioritize gaps, define entry branch."""
import argparse,csv,json,shutil
from pathlib import Path
from collections import Counter
from standalone_io_v1_0 import load,dump,sha,verify,tree,csvrows,start,finish
from projection_release_v1_11_1 import HOME,META,METRICS,emit,parquet
from consensus_policy_v1_13 import POLICY,CANDIDATE,checked
from reconciliation_audit_v1_14 import audit,SUPPORTED
from coverage_priorities_v1_14 import priorities
from entry_branch_v1_14 import intake,CONFIG,POPULATION,HISTORY,CONTEXT,CUTOFFS
from draft_source_registry_v1_14 import eligible_records,PROFILES

DEFAULTS=dict(source='outputs/preseason_coverage_v1_13',accepted_release='outputs/projection_release_2026_v1_11_1',policy='config/consensus_reconciliation_v1_13.json',branch_population=None,branch_history=None,branch_context=None,branch_cutoffs=None,output='outputs/draft_projection_sources_v1_14',backup_root='backups')

def build(a):
 source,accepted=map(lambda p:Path(p).resolve(),[a.source,a.accepted_release]);watched=verify(source);watched.update(verify(accepted));r=load(source/'preseason_coverage_build_report.json');policy=checked(load(a.policy));policy_hash=sha(a.policy)
 if r['version']!='1.13.0' or r['models_fitted'] or r['homegrown_forecasts_modified'] or r['universe_uses_2026_outcomes'] or r['evaluation_outcomes_read']:raise ValueError('Require outcome-blind frozen v1.13 source build')
 if sha(accepted/'projection_release_report.json')!=r['source_release_sha256']:raise ValueError('Accepted homegrown source binding mismatch')
 if load(source/'policy_frozen.json')!=policy or r['policy']!=policy:raise ValueError('Frozen reconciliation policy mismatch')
 bindings=load(source/'input_hashes.json')
 if bindings.get(str(Path(a.policy).resolve()))!=policy_hash:raise ValueError('Use the exact original v1.13 policy file and path')
 watched[str(Path(a.policy).resolve())]=policy_hash
 for n,h in load(source/'forecast_and_universe_freeze.json').items():
  p=(source/n).resolve()
  if source not in p.parents or sha(p)!=h:raise ValueError('v1.13 freeze mismatch')
 for n,h in r['homegrown_export_sha256'].items():
  if sha(source/n)!=h or sha(accepted/n)!=h:raise ValueError('Accepted homegrown export differs')
 originals=load(source/'original_consensus_records.json');candidates=load(source/'candidate_projection_records.json');universe=load(source/'preseason_universe.json');assets=csvrows(source/'draft_asset_coverage.csv');accepted_rows=load(accepted/'coherent_projection_records.json');home=[r for r in accepted_rows if r['projection_source']==HOME]
 provenance={}
 for row in csvrows(source/'original_metric_provenance.csv'):
  if int(row['season'])!=2026:continue
  key=row['player_type'],row['player_id'],row['metric']
  if key in provenance:raise ValueError('Duplicate original provenance')
  provenance[key]=row
 branch_rows,folds,branch_report,w=intake(a.branch_population,a.branch_history,a.branch_context,a.branch_cutoffs);watched.update(w)
 inputs=[source,accepted,a.policy]+[p for p in [a.branch_population,a.branch_history,a.branch_context,a.branch_cutoffs] if p]
 out,backups,stage=start(a.output,a.backup_root,inputs)
 try:
  print('Independently auditing component ledger, anchors, caps and contributor replay...',flush=True)
  result,maxima,failures=audit(originals,candidates,source/'reconciliation_component_ledger.csv',provenance,policy_hash)
  cases=csvrows(source/'reconciliation_cases.csv');original_keys={(r['player_type'],r['player_id']) for r in originals};candidate_keys={(r['player_type'],r['player_id']) for r in candidates};case_keys=set()
  for row in cases:
   key=row['player_type'],row['player_id'];case_keys.add(key);available=row['status']=='CANDIDATE_AVAILABLE'
   if row['status'] not in ['CANDIDATE_AVAILABLE','QUARANTINED'] or key not in original_keys or available!=(key in candidate_keys) or row['policy_sha256']!=policy_hash:failures.append(dict(player_type=key[0],player_id=key[1],metric='',reason='CASE_STATUS_OR_POLICY_MISMATCH'))
  if len(case_keys)!=len(cases) or case_keys!=original_keys or len(candidates)!=r['candidate_rows'] or len(originals)!=r['original_consensus_rows']:failures.append(dict(player_type='',player_id='',metric='',reason='SOURCE_OR_CASE_POPULATION_COUNT_MISMATCH'))
  result.update(audit_pass=not failures,failure_rows=len(failures),failure_reasons=dict(Counter(x['reason'] for x in failures)));supported=not failures
  emit(stage,'adjustment_maxima.csv',maxima);emit(stage,'reconciliation_audit_failures.csv',failures,['player_type','player_id','metric','reason']);dump(stage/'reconciliation_audit_report.json',result)
  # Preserve complete original references; no mutation of earlier candidate status.
  for name in ['original_consensus_records.json','original_metric_provenance.csv','reconciliation_adjustments.csv','remaining_consensus_quarantine.csv']:shutil.copyfile(source/name,stage/name)
  for role in METRICS:
   for ext in ['csv','parquet']:shutil.copyfile(accepted/f'homegrown_{role}s_2026.{ext}',stage/f'homegrown_{role}s_2026.{ext}')
  dump(stage/'homegrown_projection_records.json',home);promoted=[]
  if supported:
   promoted=[dict(row,projection_source=SUPPORTED,projection_key=row['projection_key'].replace(CANDIDATE,SUPPORTED,1)) for row in candidates]
   dump(stage/'reconciled_consensus_projection_records.json',promoted)
   for role in METRICS:
    rr=[r for r in promoted if r['player_type']==role];fields=META+METRICS[role]+(['K'] if role=='pitcher' else [])
    emit(stage,f'reconciled_consensus_{role}s_2026.csv',rr,fields);parquet(stage/f'reconciled_consensus_{role}s_2026.parquet',rr,fields)
  registry=dict(version='1.14.0',season=2026,effective_date=r['effective_date'],date_basis=r['date_basis'],default_source=None,no_automatic_blending_or_fallback=True,technical_support_basis='INDEPENDENT_LEDGER_ANCHOR_COHERENCE_AUDIT_NOT_2026_ACCURACY_SELECTION',IP_units='DECIMAL_INNINGS_EXPECTED_OUTS_DIVIDED_BY_3',required_platform_eligibility='Provide the correct platform preseason eligibility separately; NFBC eligibility is not Yahoo eligibility',sources={'homegrown':dict(supported=True,status='ACCEPTED_FROZEN',record_file='homegrown_projection_records.json'),'reconciled_consensus':dict(supported=supported,status='SUPPORTED_ARITHMETIC_EXPORT' if supported else 'AUDIT_FAILED_NOT_EXPORTED',record_file='reconciled_consensus_projection_records.json' if supported else None,policy_version=policy['version'],policy_sha256=policy_hash),'original_published_reference':dict(supported=False,status='REFERENCE_ONLY',record_file='original_consensus_records.json')})
  for name,rows in [('homegrown',home)]+([('reconciled_consensus',promoted)] if supported else []):
   for profile in PROFILES:
    players,excluded=eligible_records(rows,profile);dump(stage/f'{name}_{profile}_valuation_input.json',players);emit(stage,f'{name}_{profile}_exclusions.csv',excluded,['player_type','player_id','name','reason','missing_metrics_json'])
  print('Prioritizing preseason coverage gaps from ADP and original projected workloads...',flush=True)
  market,nonmarket,unknown=priorities(universe,assets,originals,home)
  for name,rows in [('nfbc_coverage_priorities.csv',market),('nonmarket_workload_priorities.csv',nonmarket),('low_or_unknown_workload_review.csv',unknown)]:emit(stage,name,rows)
  shutil.copyfile(source/'preseason_universe.json',stage/'preseason_universe.json')
  if sha(stage/'preseason_universe.json')!=sha(source/'preseason_universe.json'):raise ValueError('Frozen universe changed')
  print('Writing dated entry-branch contract and historical fold plan; no models fitted...',flush=True)
  dump(stage/'entry_branch_contract.json',CONFIG);dump(stage/'entry_branch_intake_report.json',branch_report);emit(stage,'entry_branch_fold_plan.csv',folds)
  for name,fields in [('population',POPULATION),('history',HISTORY),('context',CONTEXT),('cutoffs',CUTOFFS)]:emit(stage,f'entry_branch_{name}_TEMPLATE.csv',[],fields)
  for name,rows in branch_rows.items():emit(stage,f'entry_branch_validated_{name}.csv',rows)
  dump(stage/'projection_source_registry.json',registry);dump(stage/'source_registry_freeze.json',tree(stage))
  report=dict(version='1.14.0',status='DRAFT_SOURCES_READY_FOR_EXPLICIT_SOURCE_INTEGRATION' if supported else 'AUDIT_FAILED_RECONCILED_SOURCE_NOT_EXPORTED',reconciliation_supported=supported,effective_date=r['effective_date'],date_basis=r['date_basis'],homegrown_export_sha256=r['homegrown_export_sha256'],preseason_universe_sha256=sha(source/'preseason_universe.json'),review_priority_policy=dict(primary='PRESEASON_NFBC_ADP_ASCENDING',ties='PLAYER_TYPE_THEN_PROJECTED_WORKLOAD_DESCENDING',ADP_bands=[150,345,750],nonmarket_review_floors=dict(PA=100,IP=20),scope='REVIEW_QUEUES_ONLY_NOT_FORECAST_POPULATION_SELECTION'),support_is_arithmetic_not_performance_selection=True,accepted_homegrown_modified=False,earlier_releases_modified=False,preseason_universe_modified=False,selection_uses_2026_outcomes=False,evaluation_outcomes_read=False,models_fitted=False,original_consensus_rows=len(originals),supported_consensus_rows=len(promoted),remaining_source_quarantine=len(originals)-len(candidates),ledger_audit=result,nfbc_gap_assets=len(market),nfbc_gap_bands=dict(Counter(x['ADP_band'] for x in market)),nonmarket_workload_priorities=len(nonmarket),low_or_unknown_workload_rows=len(unknown),branch_intake_status=branch_report['status'],branch_fit_ready=False,inputs_unchanged=True,limitations=['Supported means the reconciled export passed technical provenance, arithmetic and anchored-count checks; it does not establish superiority or alter accepted homegrown forecasts.','NFBC review ordering uses only preseason ADP and original published projected PA/IP. No actual-season outcome determines inclusion or priority.','Nonmarket review thresholds of 100 PA/20 IP only partition a review queue; they do not delete players from the frozen universe. PA and IP are not combined into one numerical utility.','No prospect/international/returner forecast is generated. Dated minor/overseas/roster/availability inputs and historical label/translation work are still required.','2026 remains previously reviewed evaluation data; no new model or policy is selected on those results.'])
  dump(stage/'draft_sources_build_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in DEFAULTS.items():p.add_argument('--'+n.replace('_','-'),default=v)
 print(json.dumps(build(p.parse_args()),indent=2))
if __name__=='__main__':main()
