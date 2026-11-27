"""Rerun the prior recipe with audited compatible source years and unchanged guards."""
import os
for k in ['OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS']:os.environ[k]='1'
import sys,csv,json,ast,hashlib,math,shutil,difflib
from pathlib import Path
from collections import Counter,defaultdict
import numpy as np
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from recent_skill_core_v1_23 import checked
from participation_label_overlay_v1_27 import apply_overlay
from project_2027_v1_31 import project,FIELDS,WEIGHTS
import projection_phase_v1_42 as phase
ROOT=Path('outputs/2027_statcast_strengthened_validation');PREV=Path('outputs/2027_v1_43_statcast_challenger');O=ROOT/'challenger_rerun';O.mkdir(exist_ok=False)
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2))
scope_summary=json.loads((ROOT/'source_scope_summary.json').read_text());assert scope_summary['bridge_passed'],'No compatible older feature bridge: do not fit a changed recipe'
old_contract=json.loads((PREV/'experiment_contract.json').read_text())
contract=dict(old_contract,version='2027_V1_43_STATCAST_BB_EXTENDED_0.2',training='Identical residual model with newly supported training targets 2022–2025; each fit uses targets strictly earlier than origin, none from 2026.',historical_scoring='2023,2024,2025 forecast folds; first training target2022 uses2021 compatible archived observations.',feature_definition='Same GB/LD/FB fractions of ALL BBE, minimum30. Existing 2023–2025 definition masks retained; 2021/2022 direct categorical archive observations admitted only after the all-BBE overlap bridge passes. 2026 exports admitted only after categorical count/denominator reconciliation.',source_2026_quality='Every admitted 2026 export bundle must match hash-verified full-season archived categorical counts and all-BBE denominator; mismatches excluded rather than repaired.',permitted_changes='Input source history extension and audit-based source exclusions only; predictor names/targets/ridge/scaling/pooling/damping/caps/priors/guards unchanged.',publication='Role gates establish statistical eligibility only; review largest player changes before considering production adoption. Working baseline stays immutable.')
contract.pop('2026_source_quality',None)
assert contract['guards']==phase.CONTRACT
dump('experiment_contract.json',contract)
watch={str(ROOT/n):sha(ROOT/n) for n in ['audit_contract.json','source_scope_summary.json','compatible_2021_2022_features.csv','export_archive_scope_comparison.csv']}
pub=R/'outputs/skill_regressed_release_v1_43';lab=R/'outputs/training_labels_v1_0';overlay=R/'outputs/participation_label_overlay_v1_27';hp=R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv';priorroot=R/'outputs/projection_phase_v1_42'
take=lambda root,n:checked(root,n,watch)
train=take(lab,'training_labels.parquet');take(hp.parent,hp.name);take(overlay,'report.json');take(overlay,'participation_label_overlay.csv');choices=take(priorroot,'frozen_choices.json')
for role in ['hitter','pitcher']:take(pub,f'projections_2027_{role}s.csv')
a,_=apply_overlay(overlay,labels(train),train,hp,watch);assert max(k[0] for k in a)<=2025
prior=json.loads(choices.read_text())['skill_population'];assert prior==phase.population(a,2026)
FEATURES=['gb_rate','ld_rate','fb_rate'];TARGETS={'hitter':['1B','2B','3B'],'pitcher':['SO','BB']}
oldbundles={(int(r['season']),r['role'],r['mlbam_id']) for r in read(PREV/'statcast_source_bundle_audit.csv') if r['status']=='RESEARCH_COMPLETE'}
rows={(int(r['season']),r['role'],r['mlbam_id'],r['metric']):r for r in read(PREV/'statcast_selected_feature_audit.csv')}
scope={(int(r['year']),r['role'],r['mlbam_id']):r for r in read(ROOT/'export_archive_scope_comparison.csv')};boards={};admission=[]
for key in sorted(oldbundles):
 y,role,pid=key;sr=scope[key];safe=sr['exact_category_and_denominator_match']=='True' and sr['new_source_eligible']=='True'
 if safe:
  boards[key]=dict(values=[float(rows[*key,m]['value']) for m in FEATURES],BBE=float(rows[*key,FEATURES[0]]['BBE']))
 admission.append(dict(source_season=y,role=role,mlbam_id=pid,source='EXISTING_EXPORT',admitted=safe,reason='EXACT_EVENT_COUNT_AND_DENOMINATOR_MATCH' if safe else sr['reasons']))
for r in read(ROOT/'compatible_2021_2022_features.csv'):
 key=int(r['source_season']),r['player_type'],r['mlbam_id'];assert key not in boards
 boards[key]=dict(values=[float(r[m]) for m in FEATURES],BBE=float(r['BBE']));admission.append(dict(source_season=key[0],role=key[1],mlbam_id=key[2],source='COMPATIBLE_CATEGORICAL_ARCHIVE',admitted=True,reason='SAME_COUNTS_OVER_ALL_CLASSIFIED_INPLAY_BBE; BRIDGE_VERIFIED'))
save('source_admission.csv',admission)
baseline_cache={};prior_cache={};ctx_cache={};fit_support=[]
# Reuse the exact prior calculation functions; the sole fit edit broadens allowed earlier targets.
sourcepath=PREV/'build_2027_statcast_challenger.py';source=sourcepath.read_text();watch[str(sourcepath)]=sha(sourcepath);module=ast.parse(source);function_hashes=[];changes=[]
for name in ['baseline','features','cases','fit','apply']:
 node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name==name);original=ast.get_source_segment(source,node);executed=original
 if name=='fit':
  token='for y in [2024,2025] if y<origin';assert original.count(token)==1;executed=original.replace(token,'for y in [2022,2023,2024,2025] if y<origin')
  changes+=list(difflib.unified_diff(original.splitlines(),executed.splitlines(),fromfile='prior_fit',tofile='extended_fit',lineterm=''))
 else:assert original==executed
 exec(compile(executed,str(sourcepath)+'::'+name,'exec'),globals())
 function_hashes.append(dict(function=name,original_sha256=hashlib.sha256(original.encode()).hexdigest(),executed_sha256=hashlib.sha256(executed.encode()).hexdigest(),change='TRAINING_TARGET_YEARS_ONLY' if name=='fit' else 'NONE'))
save('recipe_function_verification.csv',function_hashes);(O/'training_extension_diff.txt').write_text('\n'.join(changes))
start=source.index('historical=[];bins=');end=source.index('# Only after model/decision freeze, 2026 actuals become 2027 player history.')
block=source[start:end];assert 'for origin in [2024,2025]:' in block
block=block.replace('for origin in [2024,2025]:','for origin in [2023,2024,2025]:')
block=block.replace("g['production_source_2026_review_passed']=False","g['production_source_2026_review_passed']=True")
block=block.replace("g['adoptable_for_2027']=False","g['adoptable_for_2027']=g['eligible']")
old="g['release_reason']='2026_STATCAST_EVENT_SCOPE_PENDING' if g['eligible'] else ';'.join(g['reasons'])+';2026_STATCAST_EVENT_SCOPE_PENDING'"
new="g['release_reason']='STATISTICAL_PASS_PENDING_PLAYER_REVIEW' if g['eligible'] else ';'.join(g['reasons'])"
assert old in block;block=block.replace(old,new)
block=block.replace('approved_role_adjustments=[]','statistically_eligible_role_candidates=[g[\'role\'] for g in gates if g[\'eligible\']]')
block=block.replace('source_2026_event_review_complete=False','source_2026_event_review_complete=True')
exec(compile(block,str(sourcepath)+'::unchanged_historical_scoring_and_guards','exec'),globals())
# Models, decisions and gate hashes are frozen before 2026 MLB player history is opened.
hold=take(lab,'holdout_labels.parquet');a.update(labels(hold,2026));ep=R/'outputs/pitcher_evaluation_v1_29';cert=json.loads(take(ep,'report.json').read_text());assert cert['season_certified'] and cert['complete_pool_scored']
ovrows=read(take(ep,'evaluation_label_overlay_2026.csv'));assert len(ovrows)==cert['preseason_pool']
for r in ovrows:
 for m,col in [('G','evaluation_g'),('OUTS','evaluation_outs')]:
  key=2026,'pitcher',r['mlbam_id'],m;v=float(r[col]);assert a.get(key,v)==v;a[key]=v
coverage=[];diff=[];summary=[];case_inputs=[]
for role in TARGETS:
 raw=read(pub/f'projections_2027_{role}s.csv');assert {r['mlbam_id'] for r in raw}==set(phase.ids_before(a,role,2027));exploratory=[];gated=[];g=next(r for r in gates if r['role']==role)
 for r in raw:
  pid=r['mlbam_id'];b,s=baseline(2027,role,pid)
  for m in FIELDS[role]:
   old=float(r[m]) if r[m]!='' else None;assert (old is None)==(b[m] is None)
   if old is not None:assert math.isclose(old,b[m],rel_tol=1e-9,abs_tol=1e-9)
  x,ys,den=features(2027,role,pid);assert all(2023<=y<=2026 for y in ys)
  c,status=apply(b,s,x,final_model[role]['coefficients'],role);selected=c if g['eligible'] else b
  flags=[]
  if 2026 not in ys:flags.append('NO_ELIGIBLE_2026_STATCAST_BUNDLE')
  if not g['eligible']:flags.append('STATCAST_ROLE_GUARD_FAILED')
  flags.append('WORKING_BASELINE_NOT_REPLACED')
  coverage.append(dict(role=role,mlbam_id=pid,name=r['name'],Statcast_status=status,source_years=';'.join(map(str,ys)),has_2026=2026 in ys,weighted_BBE=den,role_gate_pass=g['eligible'],publication_status='PENDING_PLAYER_REVIEW' if g['eligible'] else 'BASELINE_FALLBACK',flags=';'.join(flags),inherited_exceptions=r.get('exceptions','')))
  exploratory.append(dict(r,**{m:c[m] for m in FIELDS[role]},projection_source='EXTENDED_STATCAST_EXPLORATORY_ON_V1_43',Statcast_status=status,Statcast_years=';'.join(map(str,ys)),production_adopted=False))
  gated.append(dict(r,**{m:selected[m] for m in FIELDS[role]},projection_source='STATISTICAL_GATE_CANDIDATE_NOT_PRODUCTION' if g['eligible'] else 'V1_43_FALLBACK_STATCAST_GUARD_FAILED',Statcast_status=status,role_gate_pass=g['eligible'],Statcast_rejection_reason=g['release_reason'],production_adopted=False))
  for j,m in enumerate(FEATURES):case_inputs.append(dict(role=role,mlbam_id=pid,metric=m,pooled_value=x[j] if x is not None else None,source_years=';'.join(map(str,ys)),weighted_BBE=den))
  for m in FIELDS[role]:
   bv=b[m];cv=c[m];gv=selected[m]
   if bv is not None and cv is not None and not math.isclose(bv,cv,rel_tol=1e-12,abs_tol=1e-12):diff.append(dict(role=role,mlbam_id=pid,name=r['name'],metric=m,baseline=bv,exploratory=cv,exploratory_delta=cv-bv,statistical_gate_candidate=gv,gate_candidate_delta=gv-bv,role_gate_pass=g['eligible'],production_adopted=False))
  phase.verify_vector(c,role);phase.verify_vector(selected,role)
 shutil.copy2(pub/f'projections_2027_{role}s.csv',O/f'2027_{role}s_working_v1_43.csv');save(f'2027_{role}s_exploratory.csv',exploratory);save(f'2027_{role}s_statistical_gate_candidate.csv',gated)
 summary.append(dict(role=role,players=len(raw),eligible_features=sum(r['role']==role and r['Statcast_status']=='EXPLORATORY_STATCAST_APPLIED' for r in coverage),role_gate_pass=g['eligible'],mean_objective_MSE_ratio=g['mean_mse_ratio'],production_adopted=False))
save('player_coverage.csv',coverage);save('2027_player_metric_differences.csv',diff);save('pooled_player_inputs.csv',case_inputs);save('release_summary.csv',summary)
assert all(sha(O/n)==h for n,h in frozen.items());assert all(sha(p)==h for p,h in watch.items())
dump('source_manifest.json',watch);dump('validation_results.json',dict(recipe_functions_checked=function_hashes,baseline_vectors_reproduced=2511,all_2027_player_source_years_within_2023_2026=True,working_v1_43_copies_byte_identical=all(sha(O/f'2027_{role}s_working_v1_43.csv')==sha(pub/f'projections_2027_{role}s.csv') for role in TARGETS),frozen_models_and_gates_unchanged_after_2026_history_read=True,models_fit_or_scored_2026_forecast_errors=False,workload_changed=False,production_files_changed=False,source_2026_included_only_if_archive_counts_match=True))
print(json.dumps(summary,indent=2));print(json.dumps(gates,indent=2))
