"""Fixed earlier-only test. Registered model untouched; no 2026 outcomes or releases."""
import csv,json,hashlib,math,sys,shutil,zipfile,html,importlib.util
from pathlib import Path
from collections import Counter,defaultdict
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
from project_2027_v1_31 import project,FIELDS
import projection_phase_v1_42 as phase
S=Path('outputs/2027_player_anchored_workload_registration');O=Path('outputs/2027_player_anchored_workload_validation');O.mkdir(exist_ok=False);watch={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def take(p):p=Path(p);watch[str(p.resolve())]=sha(p);return p
def load(p):return json.loads(take(p).read_text(encoding='utf-8-sig'))
def read(p):
 with take(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
reg=load(S/'registration_freeze.json');outbank=load(S/'output_sha256.json')
for n,h in reg['files'].items():assert sha(take(S/n))==h
for n,h in outbank.items():assert sha(take(S/n))==h
registered=load(S/'experiment_contract.json');guards=load(S/'preserved_guard_contract.json');assert guards['core']==phase.CONTRACT==registered['guards']['core']
contract=dict(date='2026-11-27',build='DIAGNOSTIC_INFORMED_DEVELOPMENT_TEST_NOT_FRESH_INDEPENDENT_VALIDATION',model=registered['version'],origins=[2023,2024,2025],training='Fixed registered panel with target<origin; targets never after2025',planned_calendar=162,baseline='Exact project() accepted workload using original certified overlay only; no candidate-only zero certificates injected into A history',truth='Registered normalized target vector multiplied by its label calendar; separate candidate-only zero certificates supply common target truth to both arms, never rewrite baseline history',membership='Freeze status, support, target availability and per-metric/cohort pools before computing errors. All supported and fallback members appear in full-cohort reporting. Quarantined targets are explicitly unscored.',core_guard='Invoke unchanged projection_phase_v1_42.gate with WORKLOAD and internal aliases only. Same minimum folds/rows, improvement/recent/low-history thresholds.',extra_guards='Original pitcher prior-role/freshness and G/GS count safeguards; hitter freshness with same subgroup support and2% cap. Report unsupported safeguards as failures.',complete_count_protection='No modified full stat lines. Fantasy-count and team-opportunity protections remain pending and block adoption even if workload passes; no count guard is declared passed without a test.',forbidden=['2026 forecast errors','fitting or modifying registered hyperparameters','current depth chart features','rejected fits or Statcast methods','2027 forecast adoption'],production_changed=False)
contract['freshness_protocol']='Use the registered shared pre-origin ledger for both arms; preserve original context alongside it and keep baseline numerical forecasts unchanged. Do not reclassify the old failed experiment.'
contract['evidence_status']='Development informed by prior2023–2025 diagnostics, not independent validation.'
dump('evaluation_contract.json',contract)
datafreeze=load(S/'prepared_data_freeze.json');assert all(sha(take(S/n))==h for n,h in datafreeze['files'].items())
panel=load(S/'historical_panel_unscored.json');assert all(r['target_season']<=2025 for r in panel)
ledger={(int(r['target_season']),r['role'],r['mlbam_id']):r for r in read(S/'shared_preorigin_freshness_ledger.csv')}
ms=importlib.util.spec_from_file_location('frozen_usage_model',S/'player_anchored_workload.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
lab=R/'outputs/training_labels_v1_0';train=take(lab/'training_labels.parquet');hp=take(R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv');ov=R/'outputs/participation_label_overlay_v1_27'
for p in [ov/'report.json',ov/'participation_label_overlay.csv',R/'projection_phase_v1_42.py',R/'project_2027_v1_31.py']:take(p)
a,_=apply_overlay(ov,labels(train),train,hp,watch);assert max(k[0] for k in a)<=2025
old=read(R/'outputs/projection_phase_v1_42/historical_player_predictions.csv');saved={(int(r['season']),r['player_type'],r['mlbam_id']):r for r in old}
for role in ['hitter','pitcher']:
 take(Path('outputs/2027_statcast_strengthened_validation')/f'2027_{role}s_working_v1_43.csv');take(R/'outputs/skill_regressed_release_v1_43'/f'projections_2027_{role}s.csv')
take(R/'outputs/projection_phase_v1_42/frozen_choices.json');take(R/'outputs/skill_regressed_release_v1_43/publication_freeze.json')
preds=[];models={};support=[];baseline_checks=0;bins=defaultdict(list);membership=[];fallbacks=[]
for origin in [2023,2024,2025]:
 model=m.fit(panel,origin);models[str(origin)]=model
 for role,entry in model['roles'].items():
  assert entry['max_target_season']<origin and entry['max_target_season']<=2025
  support.append(dict(origin=origin,role=role,max_training_target=entry['max_target_season'],training_rows=entry['support']['n'],global_support=entry['support']['supported'],support_reasons=';'.join(entry['support']['reasons']),supported_pools=len(entry['nodes']),root_state_counts=json.dumps(entry['support']['state_counts'])))
 for r in [r for r in panel if r['target_season']==origin]:
  role=r['role'];pid=r['mlbam_id'];b=project(a,role,pid,origin);assert b is not None;original=saved[origin,role,pid]
  # Replay the entire accepted weighted-history vector against saved historical baseline fields.
  for metric in FIELDS[role]:
   x=b.get(metric);y=float(original['baseline__'+metric]) if original.get('baseline__'+metric) not in ('',None) else None
   assert x==y or x is not None and y is not None and math.isclose(x,y,abs_tol=1e-8,rel_tol=1e-8),(origin,role,pid,metric,x,y)
   baseline_checks+=1
  ctx=phase.context(a,role,pid,origin);original_freshness=ctx['freshness'];shared=ledger[origin,role,pid];assert shared['original_freshness']==original_freshness;ctx['freshness']=shared['shared_freshness'];target_known=r['target_vector'] is not None and r['target_state']!='UNKNOWN'
  features={k:r[k] for k in ['role','target_season','max_feature_season','anchor_season','anchor_vector','latest_state','recent_state','experience','fallback_reason']}
  if not r['eligible'] and not features['fallback_reason']:features['fallback_reason']=r['eligibility_reason']
  result=m.predict(model,features,162);supported=result['status']=='EXPERIMENTAL_WORKLOAD_ONLY' and r['eligible'] and target_known
  assert supported or result['workload'] is None
  truth=dict(zip(m.FIELDS[role],[v*r['target_calendar'] for v in r['target_vector']])) if target_known else {}
  if role=='pitcher' and truth:truth['IP']=(truth['START_OUTS']+truth['RELIEF_OUTS'])/3
  metrics=['PA'] if role=='hitter' else ['IP','G','GS']
  pp={metric:result['workload'][metric] if supported else b.get(metric) for metric in metrics}
  rr=dict(season=origin,role=role,mlbam_id=pid,history=ctx['history'],original_freshness=original_freshness,freshness=ctx['freshness'],prior_role=ctx['prior_role'],returner=ctx['returner'],latest_state=r['latest_state'],recent_state=r['recent_state'],registered_eligible=r['eligible'],prediction_status=result['status'],fallback_reason=result['reason'],pool_used=result.get('pool'),pool_rows=result.get('pool_rows'),target_known=target_known,supported=supported,anchor_vector_json=json.dumps(r['anchor_vector']),mean_residual_json=json.dumps(result.get('mean_residual')),raw_workload_json=json.dumps(result.get('raw_workload')),feasibility_changed=result.get('feasibility_changed',False),**{'baseline_'+metric:b.get(metric) for metric in metrics},**{'candidate_'+metric:pp[metric] for metric in metrics},**{'actual_'+metric:truth.get(metric) for metric in metrics})
  preds.append(rr)
  if not supported:fallbacks.append(dict(season=origin,role=role,mlbam_id=pid,reason=result['reason'],target_scored=target_known,baseline_retained=True))
  cohorts=list(dict.fromkeys(['ALL',ctx['history'],ctx['freshness'],ctx['prior_role'],ctx['returner']]))
  for metric in metrics:
   bv=b.get(metric);cv=pp[metric];actual=truth.get(metric)
   if not target_known or None in (bv,cv,actual):continue
   pool='SUPPORTED' if supported else 'FALLBACK'
   for cohort in cohorts:
    bins[origin,role,metric,cohort,pool].append((pid,bv,cv,actual))
    bins[origin,role,metric,cohort,'FULL_COHORT'].append((pid,bv,cv,actual))
 print('Built unscored predictions and memberships for',origin,flush=True)
# No errors computed above. Freeze all fitted models, predictions and exact scoring IDs now.
dump('frozen_historical_models.json',models);save('historical_workload_predictions.csv',preds);save('training_support.csv',support);save('fallback_inventory.csv',fallbacks)
for (year,role,metric,cohort,pool),rr in sorted(bins.items()):membership.append(dict(season=year,role=role,metric=metric,cohort=cohort,pool=pool,n=len(rr),membership_sha256=phase.keyhash([x[0] for x in rr]),mlbam_ids=';'.join(sorted(x[0] for x in rr))))
save('frozen_scoring_memberships.csv',membership)
dump('pre_scoring_freeze.json',dict(stage='BEFORE_ERROR_CALCULATION',files={n:sha(O/n) for n in ['evaluation_contract.json','frozen_historical_models.json','historical_workload_predictions.csv','frozen_scoring_memberships.csv']},selection_max_year=2025,registered_model_sha256=sha(S/'player_anchored_workload.py')))
scores=[]
for (year,role,metric,cohort,pool),rr in sorted(bins.items()):
 for i,method in [(1,'weighted_actuals'),(2,'freshness_workload')]:
  errors=[r[i]-r[3] for r in rr];n=len(errors);mse=sum(e*e for e in errors)/n
  scores.append(dict(season=year,role=role,experiment='WORKLOAD',metric=metric,cohort=cohort,pool=pool,method=method,method_label='V1_43' if method=='weighted_actuals' else 'PLAYER_ANCHORED_RESIDUAL',n=n,membership_sha256=phase.keyhash([x[0] for x in rr]),mse=mse,rmse=math.sqrt(mse),mae=sum(abs(e) for e in errors)/n,bias=sum(errors)/n))
save('historical_scores.csv',scores)
scorebank={(r['season'],r['role'],r['metric'],r['cohort'],r['pool'],r['method']):r for r in scores}
ratios=[]
for row in scores:
 if row['method']!='freshness_workload':continue
 base=scorebank[row['season'],row['role'],row['metric'],row['cohort'],row['pool'],'weighted_actuals'];assert row['membership_sha256']==base['membership_sha256'] and row['n']==base['n']
 ratios.append(dict(season=row['season'],role=row['role'],metric=row['metric'],cohort=row['cohort'],pool=row['pool'],n=row['n'],membership_sha256=row['membership_sha256'],baseline_MSE=base['mse'],candidate_MSE=row['mse'],MSE_ratio=row['mse']/base['mse'] if base['mse'] else None,baseline_MAE=base['mae'],candidate_MAE=row['mae'],baseline_bias=base['bias'],candidate_bias=row['bias']))
save('paired_error_ratios.csv',ratios)
gates=[];extras=[]
for role in ['hitter','pitcher']:
 mainmetric='PA' if role=='hitter' else 'IP';core=phase.gate(scores,role,'WORKLOAD',2026);reason=[]
 groups=['RECENT_POSITIVE','KNOWN_ZERO_RECENT']+(['STARTER','SWING','RELIEVER'] if role=='pitcher' else [])
 for group in groups:
  rr=[r for r in ratios if r['role']==role and r['metric']==mainmetric and r['cohort']==group and r['pool']=='SUPPORTED' and r['n']>=15 and r['MSE_ratio'] is not None]
  mean=sum(r['MSE_ratio'] for r in rr)/len(rr) if rr else None;status='UNSUPPORTED' if mean is None else 'PASS' if mean<=1.02 else 'FAIL'
  extras.append(dict(role=role,guard='ROLE_OR_FRESHNESS',metric=mainmetric,cohort=group,minimum_n=15,maximum_mean_MSE_ratio=1.02,supported_folds=len(rr),mean_MSE_ratio=mean,status=status))
  if status!='PASS':reason.append(('UNSUPPORTED_GUARD_' if status=='UNSUPPORTED' else 'SUBGROUP_WORKLOAD_GUARD_')+group)
 if role=='pitcher':
  for metric in ['G','GS']:
   rr=[r for r in ratios if r['role']==role and r['metric']==metric and r['cohort']=='ALL' and r['pool']=='SUPPORTED' and r['n']>=30 and r['MSE_ratio'] is not None];mean=sum(r['MSE_ratio'] for r in rr)/len(rr) if rr else None;status='UNSUPPORTED' if mean is None else 'PASS' if mean<=1.02 else 'FAIL'
   extras.append(dict(role=role,guard='OPPORTUNITY_COUNT',metric=metric,cohort='ALL',minimum_n=30,maximum_mean_MSE_ratio=1.02,supported_folds=len(rr),mean_MSE_ratio=mean,status=status))
   if status!='PASS':reason.append('OPPORTUNITY_COUNT_GUARD_'+metric)
 if not all(r['global_support'] for r in support if r['role']==role):reason.append('UNSUPPORTED_COMPONENT_FIT')
 gates.append(dict(role=role,core_guard=core,extra_guard_reasons=reason,workload_pass=core['eligible'] and not reason,full_count_guards='NOT_EVALUATED_NO_COMPLETE_COUNT_REPLACEMENT',team_opportunity_checks='NOT_IMPLEMENTED',adoptable=False,baseline_changed=False))
save('extra_guard_results.csv',extras);dump('workload_decision.json',gates)
folds=[r for r in ratios if r['cohort']=='ALL' and r['metric']==('PA' if r['role']=='hitter' else 'IP')]
save('fold_workload_summary.csv',folds)
summary=dict(status='DEVELOPMENT_TEST_COMPLETE_NOT_ADOPTED',origins=[2023,2024,2025],players_by_role=dict(Counter(r['role'] for r in preds)),prediction_rows=len(preds),supported_rows=sum(r['supported'] for r in preds),fallback_rows=len(fallbacks),unscored_quarantined_rows=sum(not r['target_known'] for r in preds),baseline_fields_replayed=baseline_checks,models_fitted=3,maximum_fit_target=2024,forecast_errors_2026_scored=False,registered_model_changed=False,thresholds_changed=False,production_changed=False,role_decisions=[dict(role=g['role'],mean_objective_MSE_ratio=g['core_guard']['mean_mse_ratio'],workload_pass=g['workload_pass'],core_reasons=g['core_guard']['reasons'],extra_reasons=g['extra_guard_reasons']) for g in gates],conditional_complete_count_build_triggered=any(g['workload_pass'] for g in gates))
summary['evidence_status']='Diagnostic-informed development; not fresh independent validation'
summary['feasibility_adjusted_supported_rows']=sum(r['supported'] and r['feasibility_changed'] for r in preds)
summary['shared_freshness_used_for_both_arms']=True
dump('validation_summary.json',summary)
dump('count_and_team_protection_status.json',dict(status='NO_FORECAST_ADOPTION',workload_pass_roles=[g['role'] for g in gates if g['workload_pass']],fantasy_count_guards='Not declared passed; no complete count replacement built or published',team_opportunity_checks='Required before adoption',conditional_next_step='Separately specify and implement coherent full counts and team budgets for any workload-pass role; otherwise no such build triggered'))
pre=load(O/'pre_scoring_freeze.json');assert all(sha(O/n)==h for n,h in pre['files'].items());assert all(sha(p)==h for p,h in watch.items())
dump('source_manifest.json',watch);dump('verification_results.json',dict(original_registered_files_unchanged=True,source_hashes_verified=len(watch),all_origin_training_targets_strictly_earlier=True,panel_target_maximum=2025,fitted_target_maximum=2024,baseline_fields_exactly_replayed=baseline_checks,all_scoring_memberships_frozen_before_errors=True,paired_memberships_identical=True,full_cohort_fallbacks_retained=True,no_hyperparameter_changes=True,no_2026_errors=True,no_forecast_changes=True))
text='PLAYER-ANCHORED WORKLOAD DEVELOPMENT VALIDATION\n\n'+json.dumps(summary,indent=2)+'''\n\nMETHOD\nThe frozen executable model was used unchanged. For2023 train targets2020–2022;2024 uses2020–2023;2025 uses2020–2024. The pre-scoring freeze binds models, all predictions and exact metric/cohort memberships before error calculation. The baseline accepted workload vector is independently replayed against the saved original historical vectors. Candidate-only nonappearance certificates supply shared truth and candidate states; they are not injected into baseline history. Planned calendar is162; realized target calendar is used only to invert registered labels to observed counts.\n\nMEMBERSHIPS\nSUPPORTED is the frozen eligible candidate with known target. FALLBACK keeps the entire baseline workload. FULL_COHORT includes both on common known targets. Quarantined targets remain in prediction reporting but are unscored. Secondary pitcher batting is unsupported by design, not silently removed from full-cohort reporting. Sparse pool backoff is the registered model rule; pool and training support are exposed. No source year2026 is a scoring target.\n\nGUARDS\nThe original phase.gate implementation applies workload mean improvement, fold/sample, recent and low-history requirements without alteration. The previous role/freshness and pitcher G/GS safeguards retain their thresholds. Unsupported safeguards are explicit failures. Internal method aliases weighted_actuals/freshness_workload only execute original guard math; report labels identify V1_43 and PLAYER_ANCHORED_RESIDUAL.\n\nCOUNTS AND ADOPTION\nThis model emits workload only. It does not alter skill rates or publish incomplete replacement stat lines. Full fantasy-count and team-opportunity safeguards are not claimed to pass; adoption remains blocked. A passing workload role would trigger a separately specified complete-count/team handling build. Failed workload roles do not trigger that conditional build. The shared freshness ledger is used for both arms without modifying baseline numbers or old failed-run decisions. Feasibility edits and fallbacks are exposed. Current charts, international estimates, age/skill-development adjustments and rejected models remain inactive. This design was informed by already reviewed2023–2025 diagnostics, so these results are development evidence and not fresh independent validation.\n'''
(O/'READ_ME.txt').write_text(text,encoding='utf-8')
def tab(rr,cc):return '<div style="overflow:auto"><table><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in cc)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(c,'')))+'</td>' for c in cc)+'</tr>' for r in rr)+'</table></div>'
page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Player-anchored development validation</title><style>body{font:16px/1.6 system-ui;max-width:1300px;margin:40px auto;padding:20px;color:#183441}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:10px;border:1px solid #ccd9e2;text-align:left}th{background:#e1edf5}pre{white-space:pre-wrap}</style><h1>Player-anchored development test:2023–2025</h1><p>November27,2026 · No2026 errors · Unchanged v1.43 working forecast</p><h2>Role decisions</h2>'+tab(summary['role_decisions'],['role','mean_objective_MSE_ratio','workload_pass','core_reasons','extra_reasons'])+'<h2>Fold results, including fallbacks</h2>'+tab(folds,['season','role','pool','n','baseline_MSE','candidate_MSE','MSE_ratio'])+'<h2>Additional protections</h2>'+tab(extras,['role','guard','metric','cohort','supported_folds','mean_MSE_ratio','status'])+'<p><a href="historical_workload_predictions.csv">All historical predictions</a> · <a href="fallback_inventory.csv">Fallback inventory</a> · <a href="training_support.csv">Training support</a> · <a href="frozen_scoring_memberships.csv">Frozen memberships</a></p><h2>Method and limits</h2><pre>'+html.escape(text)+'</pre></html>'
(O/'validation_report.html').write_text(page,encoding='utf-8')
shutil.copy2(__file__,O/'validate_player_anchored_workload.py');shutil.copy2(S/'player_anchored_workload.py',O/'frozen_player_anchored_workload.py')
dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(summary,indent=2),flush=True)
