"""Register one diagnostic-informed candidate. Historical data never fitted or scored."""
import csv,json,hashlib,math,sys,shutil,zipfile,html,importlib.util,copy
from pathlib import Path
from collections import Counter
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
import projection_phase_v1_42 as phase
Q=Path('outputs/2027_usage_transition_registration');P=Path('outputs/2027_game_usage_reconstruction');D=Path('outputs/2027_usage_transition_diagnostic');O=Path('outputs/2027_player_anchored_workload_registration');O.mkdir(exist_ok=True);watch={}
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
ms=importlib.util.spec_from_file_location('anchored','work/player_anchored_workload.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
shutil.copy2(take('work/player_anchored_workload.py'),O/'player_anchored_workload.py')
oldfreeze=load(Q/'registration_freeze.json');assert all(sha(take(Q/n))==h for n,h in oldfreeze['registered_files'].items())
proposal=load(D/'one_proposed_experiment.json');oldguards=load(Q/'preserved_guard_contract.json');assert oldguards['core']==phase.CONTRACT
contract=dict(version=m.VERSION,date='2026-11-27',status='REGISTERED_EXECUTABLE_UNSCORED_NO_HISTORICAL_FIT',informed_by='Reviewed2023–2025 usage-transition development errors; not fresh independent validation',hypothesis='Retain individual workload variation by predicting a signed workload change relative to the player own latest reconciled season, rather than replacing the player with an absolute peer mean.',arms=['A_UNCHANGED_V1_43','B_PLAYER_ANCHORED_RESIDUAL'],origins=[2023,2024,2025],training_targets=[2020,2021,2022,2023,2024,2025],chronology='Fit strictly earlier targets, maximum2025. Origin2026 means final coefficient freeze through2025, not evaluation of2026. No2026 target errors, forecasts or new2027 predictions in this build.',anchor='Latest prior completed season only: source season Y-1, normalized by that season observed maximum team games. Missing is unknown; use zero only with source-reconciled zero or the separate certified participation ledger. No fallback to an older or peak season.',response='Residual = target joint workload/target observed calendar minus anchor joint workload/anchor observed calendar. Preserve signed components, all nonappearances and declines. Unknown/conflicting rows remain excluded/fallback, never imputed.',estimator='One unconditional residual mean per registered pool; root sample mean and child (sum residual+50×parent mean)/(n+50). Preserve root→latest_state→latest/recent/experience hierarchy. No search or fitted coefficient multiplying the anchor; anchor coefficient fixed at1.',departure_from_failed_model='Replace absolute probability-weighted conditional workload means with a signed residual point estimator plus personal anchor. No state-probability output: nonappearance risk enters through observed zero target residuals, not a claim of calibrated medical probabilities.',settings=m.SETTINGS,states=m.STATES,fields=m.FIELDS,support='Retain >=200 known global/cell cases, >=20 positive and20 zero, >=20 each active global state, pitcher >=50 pure-start and100 pure-relief target seasons. Same deterministic sparse-pool backoff; no support threshold reduction.',states_and_secondary_roles='Retain frozen pre-origin state definitions, last60 source and history bins. Retain predictor-time secondary pitcher batting fallback (>=5 pitching G and <100 PA). No current charts, age, injury features, translations or Statcast.',projection='Prediction normalized = own anchor + selected mean residual; multiply by explicit planned calendar(default162). Clip negative components to0, with no positive workload floor. Hitter BATTING_G<=MLB_G and STARTS<=BATTING_G; pitcher G=GS+GR and OUTS=START_OUTS+RELIEF_OUTS. Infeasible positive PA without batting G or positive outing outs without corresponding appearances returns full-baseline fallback. Expose raw vector and feasibility edits.',freshness_protocol='Build a shared pre-origin ledger for BOTH comparator arms: reconciled positive exposure =>RECENT_POSITIVE; reconciled/certified zero=>KNOWN_ZERO_RECENT; otherwise UNKNOWN_RECENT. Keep separate actual MLB appearance and exposure labels. Do not inject ledger zeros into baseline historical numeric inputs or change baseline forecasts.',exceptions='Jansen2024 excluded as a target and required latest anchor for2025. Jeffers/Keys2026 remain quarantined outside this historical build. Do not repair source counts.',comparison='Preserve frozen full cohort, eligible target policy and fallback reporting. Future scorer must use shared ledger and identical metric memberships for both arms. Preserve baseline original-context columns for provenance; do not rewrite old failed-run guards.',guards=oldguards,guard_limits_unchanged=True,adoption='No automatic adoption. Full count, skill preservation and team-opportunity handling remain mandatory future work even after any workload pass.',present_build='Register code/contracts before panel preparation; synthetic tests and historical label/support counts only. No historical fitting, forecast-error scoring, calibrated uncertainty intervals or forecasts.',illustrations='Stewart and Misiorowski remain unscored published-history illustrations; no new numerical candidate projection for them.',future_validation='Existing earlier-only guards remain necessary; repeated2023–2025 development tests are not an untouched holdout. Any future independent evidence must be labeled separately.')
dump('experiment_contract.json',contract);dump('preserved_guard_contract.json',oldguards)
dump('registration_freeze.json',dict(stage='BEFORE_HISTORICAL_PANEL_BUILD_AND_ANY_FIT',files={n:sha(O/n) for n in ['experiment_contract.json','player_anchored_workload.py','preserved_guard_contract.json']},historical_fit=False,historical_errors_scored=False))
oldpanel=load(Q/'historical_panel_unscored.json');vr=load(Q/'verification_results.json');assert sha(Q/'historical_panel_unscored.json')==vr['real_panel_hash']
annual={(int(r['season']),r['role'],r['mlbam_id']):r for r in read(P/'historical_season_usage_2019_2025.csv')}
hcert={(int(r['season']),r['mlbam_id']):r for r in read(P/'hitter_participation_certification.csv') if int(r['season'])<=2025}
pzero={(int(r['season']),r['mlbam_id']) for r in read(Q/'candidate_only_pitcher_nonappearance_certificate.csv')}
cal={int(r['season']):int(r['maximum_observed_team_games']) for r in read(Q/'label_calendar_normalization.csv')}
lab=R/'outputs/training_labels_v1_0';train=take(lab/'training_labels.parquet');hp=take(R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv');ov=R/'outputs/participation_label_overlay_v1_27'
for p in [ov/'report.json',ov/'participation_label_overlay.csv',R/'projection_phase_v1_42.py']:take(p)
a,_=apply_overlay(ov,labels(train),train,hp,watch);assert max(k[0] for k in a)<=2025
for role in ['hitter','pitcher']:
 take(Path('outputs/2027_statcast_strengthened_validation')/f'2027_{role}s_working_v1_43.csv');take(R/'outputs/skill_regressed_release_v1_43'/f'projections_2027_{role}s.csv')
def anchor(y,role,pid):
 row=annual.get((y,role,pid));certificate=hcert.get((y,pid),{})
 if row:
  if row['source_reconciliation_status']!='SOURCE_RECONCILED':return None,'SOURCE_QUARANTINED',None
  v=[float(row.get('G' if f=='MLB_G' else f) or 0)/cal[y] for f in m.FIELDS[role]]
  return v,'RECONCILED_ANNUAL_ROW',float(row.get('G') or 0)>0
 if role=='hitter':known=certificate.get('certified_zero_PA_exposure')=='True'
 else:known=(y,pid) in pzero or (a.get((y,role,pid,'G'))==0 and a.get((y,role,pid,'OUTS'))==0)
 if known:
  if role=='hitter':assert float(certificate['G'])==0,'Missing annual row with actual MLB G requires review'
  return [0.]*len(m.FIELDS[role]),'CERTIFIED_ZERO_PARTICIPATION',False
 return None,'UNKNOWN_NOT_ZERO',None
def main(role,v):return None if v is None else v[3] if role=='hitter' else (v[3]+v[4])/3
panel=[];ledger=[];exposure=[]
for r in oldpanel:
 y=int(r['target_season']);role=r['role'];pid=r['mlbam_id'];v,basis,appeared=anchor(y-1,role,pid);new=dict(r,anchor_season=y-1,anchor_calendar=cal[y-1],anchor_vector=v,anchor_basis=basis)
 eligible=r['eligible'] and v is not None;new['eligible']=eligible
 if r['eligible'] and v is None:new['fallback_reason']='UNKNOWN_OR_QUARANTINED_ANCHOR';new['eligibility_reason']=new['fallback_reason']
 target=r['target_vector'];new['residual_vector']=[target[i]-v[i] for i in range(len(v))] if target is not None and v is not None else None
 if v is not None:assert m.valid_vector(role,v)
 if new['residual_vector'] is not None:assert all(math.isclose(new['residual_vector'][i]+v[i],target[i],abs_tol=1e-10) for i in range(len(v)))
 panel.append(new)
 oldctx=phase.context(a,role,pid,y);e=main(role,v);fresh='UNKNOWN_RECENT' if e is None else 'RECENT_POSITIVE' if e>0 else 'KNOWN_ZERO_RECENT'
 ledger.append(dict(target_season=y,source_season=y-1,role=role,mlbam_id=pid,original_freshness=oldctx['freshness'],shared_freshness=fresh,anchor_basis=basis,source_exposure_normalized=e,prior_credited_MLB_or_pitching_appearance=appeared,group_label_changed=fresh!=oldctx['freshness'],applies_to='BOTH_ARMS_FOR_FUTURE_TEST_ONLY',baseline_numeric_history_changed=False,candidate_eligible=eligible))
 if eligible:
  delta=main(role,new['residual_vector']);t=main(role,target)
  exposure.append(dict(target_season=y,role=role,mlbam_id=pid,anchor_main_normalized=e,target_main_normalized=t,signed_change_normalized=delta,decline=delta<0,zero_exposure_target=t==0,positive_anchor_to_zero_target=e>0 and t==0))
assert {(r['target_season'],r['role'],r['mlbam_id']) for r in oldpanel}=={(r['target_season'],r['role'],r['mlbam_id']) for r in panel}
dump('historical_panel_unscored.json',panel)
save('historical_panel_inventory.csv',[dict(**{k:v for k,v in r.items() if k not in ['target_vector','anchor_vector','residual_vector']},anchor_vector_json=json.dumps(r['anchor_vector']),target_vector_json=json.dumps(r['target_vector']),signed_residual_json=json.dumps(r['residual_vector'])) for r in panel])
save('shared_preorigin_freshness_ledger.csv',ledger);save('signed_change_label_audit.csv',exposure)
support=[]
for origin in [2023,2024,2025,2026]:
 for role in ['hitter','pitcher']:
  rr=[r for r in panel if r['role']==role and r['eligible'] and r['target_season']<origin];ss=m.support(rr,role)
  support.append(dict(origin=origin,role=role,training_rows=len(rr),max_training_target=max(r['target_season'] for r in rr),positive=ss['positive'],zero=ss['zero'],state_counts=json.dumps(ss['state_counts']),global_support=ss['supported'],support_failures=';'.join(ss['reasons']),historical_fit=False))
save('support_preflight_without_fit.csv',support)
subgroups=[]
for y in [2023,2024,2025]:
 for role in ['hitter','pitcher']:
  for fresh in ['RECENT_POSITIVE','KNOWN_ZERO_RECENT','UNKNOWN_RECENT']:
   rr=[r for r in ledger if r['target_season']==y and r['role']==role and r['shared_freshness']==fresh]
   subgroups.append(dict(origin=y,role=role,shared_freshness=fresh,full_cohort_n=len(rr),candidate_eligible_n=sum(r['candidate_eligible'] for r in rr),minimum_guard_n=15,sample_support=sum(r['candidate_eligible'] for r in rr)>=15,guard_accuracy_tested=False,old_failed_run_reclassified=False))
save('future_subgroup_support_inventory.csv',subgroups)
# Synthetic fixtures prove algebra and safety, not historical accuracy.
synthetic=[];hv={'NO_PA':[0,0,0,0],'LIMITED_OR_BENCH':[40,40,8,80],'PART_TIME_STARTER':[90,90,45,280],'REGULAR_STARTER':[145,145,140,620]};pv={'NO_PITCHING_APPEARANCE':[0,0,0,0,0],'RELIEF':[60,0,60,0,180],'SWING_OR_LIMITED':[40,8,32,100,90],'ROTATION':[30,30,0,540,0]}
for role,values in [('hitter',hv),('pitcher',pv)]:
 for state,target in values.items():
  for i in range(125):
   av=([145,145,140,620] if role=='hitter' else [30,30,0,540,0]) if state==m.STATES[role][0] else target
   av=[x/162 for x in av];tv=[x/162 for x in target]
   synthetic.append(dict(role=role,target_season=2020,max_feature_season=2019,anchor_season=2019,eligible=True,latest_state='REGULAR_STARTER' if role=='hitter' else 'ROTATION',recent_state='UNKNOWN',experience='ESTABLISHED',target_state=state,anchor_vector=av,target_vector=tv,residual_vector=[t-x for t,x in zip(tv,av)],pure_start=role=='pitcher' and state=='ROTATION',pure_relief=role=='pitcher' and state=='RELIEF'))
tests=[]
def test(name,condition):
 assert condition,name;tests.append(dict(test=name,status='PASS',basis='SYNTHETIC_OR_STRUCTURAL_NOT_HISTORICAL_ERRORS'))
def reject(name,fn):
 try:fn()
 except ValueError:test(name,True);return
 raise AssertionError(name)
model=m.fit(synthetic,2023)
hf=dict(role='hitter',target_season=2023,max_feature_season=2022,anchor_season=2022,latest_state='REGULAR_STARTER',recent_state='UNKNOWN',experience='ESTABLISHED',fallback_reason='',anchor_vector=[145/162,145/162,140/162,620/162])
pf=dict(hf,role='pitcher',latest_state='ROTATION',anchor_vector=[30/162,30/162,0,540/162,0])
high=m.predict(model,hf);low=m.predict(model,dict(hf,anchor_vector=[110/162,110/162,90/162,400/162]));pt=m.predict(model,pf)
test('same_pool_retains_individual_PA_difference',high['status']==low['status']=='EXPERIMENTAL_WORKLOAD_ONLY' and math.isclose(high['workload']['PA']-low['workload']['PA'],220,abs_tol=1e-9))
test('nonappearances_keep_negative_residuals',any(r['target_state']=='NO_PA' and r['residual_vector'][3]<0 for r in synthetic))
test('negative_change_can_reduce_projection',high['workload']['PA']<620)
test('no_growth_bonus_or_positive_PA_floor',m.predict(model,dict(hf,anchor_vector=[0,0,0,0]))['workload']['PA']==0)
test('pitching_joint_identities',math.isclose(pt['workload']['G'],pt['workload']['GS']+pt['workload']['GR']) and math.isclose(pt['workload']['OUTS'],pt['workload']['IP']*3))
test('no_calibrated_probability_claim',high['probability_output'] is None)
test('no_unknown_anchor_zero_imputation',m.predict(model,dict(hf,anchor_vector=None))['workload'] is None)
test('secondary_role_full_fallback',m.predict(model,dict(hf,fallback_reason='SECONDARY_PITCHER_BATTING'))['workload'] is None)
test('unsupported_root_full_fallback',m.predict(m.fit(synthetic[:20],2023),hf)['workload'] is None)
test('sparse_cell_parent_backoff',m.predict(model,dict(hf,latest_state='PART_TIME_STARTER'))['pool']=='GLOBAL')
reject('future_target_rejected_even_if_ineligible',lambda:m.fit(synthetic+[dict(synthetic[0],target_season=2026,eligible=False)],2023))
reject('feature_cutoff_leak_rejected',lambda:m.fit([dict(r,anchor_season=2020) for r in synthetic],2023))
reject('future_trained_prediction_rejected',lambda:m.predict(model,dict(hf,target_season=2020,max_feature_season=2019,anchor_season=2019)))
reject('unregistered_origin2027_rejected',lambda:m.fit(synthetic,2027))
reject('string_eligibility_rejected',lambda:m.fit([dict(synthetic[0],eligible='False')],2023))
reject('changed_residual_identity_rejected',lambda:m.fit([dict(r,residual_vector=[1]*len(r['residual_vector'])) for r in synthetic],2023))
reject('stale_prediction_anchor_rejected',lambda:m.predict(model,dict(hf,anchor_season=2021)))
reject('stale_training_anchor_rejected',lambda:m.fit([dict(r,anchor_season=2018) for r in synthetic],2023))
test('positive_PA_requires_batting_appearance',not m.valid_vector('hitter',[0,0,0,1]))
test('credited_zero_out_pitcher_remains_valid',m.valid_vector('pitcher',[1,0,1,0,0]))
test('positive_start_outs_require_a_start',not m.valid_vector('pitcher',[1,0,1,1,0]))
bad=copy.deepcopy(model);bad['roles']['pitcher']['root']['mean_residual']=[0,-2,0,2,0];bad['roles']['pitcher']['nodes']={}
test('infeasible_outing_returns_full_baseline',m.predict(bad,pf)['workload'] is None)
test('actual_panel_has_no_2026_targets',all(r['target_season']<=2025 and r['anchor_season']<r['target_season'] for r in panel))
test('baseline_cohort_membership_preserved',len(panel)==len(oldpanel))
test('same_eligibility_preserved',all(r['eligible']==s['eligible'] for r,s in zip(panel,oldpanel)))
test('Jansen_target_and_latest_anchor_quarantined',all(not r['eligible'] for r in panel if r['role']=='hitter' and r['mlbam_id']=='643376' and r['target_season'] in [2024,2025]))
save('executable_tests.csv',tests)
illustrations=read(D/'illustrative_cases_not_scored.csv');save('illustrative_cases_not_scored.csv',illustrations)
counts=[]
for role in ['hitter','pitcher']:
 rr=[r for r in exposure if r['role']==role];counts.append(dict(role=role,eligible_rows=len(rr),negative_primary_residuals=sum(r['decline'] for r in rr),zero_primary_exposure_targets=sum(r['zero_exposure_target'] for r in rr),positive_anchor_to_zero_targets=sum(r['positive_anchor_to_zero_target'] for r in rr)))
save('decline_and_nonappearance_retention.csv',counts)
summary=dict(status='REGISTERED_EXECUTABLE_UNSCORED',panel_rows=len(panel),eligible_rows=sum(r['eligible'] for r in panel),cohort_and_eligibility_unchanged=True,historical_fits=0,historical_errors_scored=0,new_forecasts=0,synthetic_and_structural_tests=len(tests),retained_declines_and_zeros=counts,baseline_changed=False,guards_thresholds_changed=False,old_failed_run_reclassified=False,independent_validation_claimed=False)
dump('registration_summary.json',summary)
reg=load(O/'registration_freeze.json');assert all(sha(O/n)==h for n,h in reg['files'].items());assert all(sha(p)==h for p,h in watch.items())
dump('source_manifest.json',watch);dump('verification_results.json',dict(source_hashes_verified=len(watch),registered_files_unchanged=True,no_historical_fit=True,no_historical_error_score=True,no_2026_error=True,no_new_candidate_forecast=True,all_residual_identities_checked=True,original_membership_and_eligibility_preserved=True,baseline_numeric_history_unchanged=True,guard_thresholds_unchanged=True))
text='PLAYER-ANCHORED WORKLOAD RESIDUAL EXPERIMENT\n\n'+json.dumps(summary,indent=2)+'''\n\nDECISION AND DESIGN\nOne diagnostic-informed experiment is registered, not fitted to historical players. The candidate predicts signed workload change and adds that change to each player's own latest reconciled workload. This replaces the rejected absolute peer mean with an individual offset. Nonappearance and declining seasons remain, including large negative residuals. There is no universal growth bonus, positive PA/IP floor, new injury feature or chart assumption.\n\nEXPOSURE AND COHERENCE\nAnchors and targets are normalized by their own observed source-season calendars, preserving the prior calendar policy. Hitter G/PA and pitcher start/relief components remain joint vectors. Only nonnegative feasibility projection is applied, with no positive workload floor. Infeasible positive counts without matching appearances fall back to the entire baseline. Raw vectors/feasibility edits are exposed for a future scored build. The estimator is an unconditional residual point estimator; it does not advertise calibrated role/medical probabilities or uncertainty intervals.\n\nSHARED FRESHNESS LEDGER\nBoth arms will use the same pre-origin cohort labels: positive, certified zero, or unknown. Original context labels and their provenance remain in the ledger, and the baseline's original numerical inputs/forecasts stay untouched. This fixes a comparison-protocol mapping issue identified in the failed test, not a shortage of all absence evidence. The15-row and2% subgroup thresholds are unchanged. The old failed run is not retroactively relabeled or declared a pass.\n\nSCOPE\nThe entire17907-record historical comparison pool and prior eligibility rules are retained. Danny Jansen2024 is quarantined as a target and a required latest anchor; Jeffers/Keys2026 remain outside this historical build. Secondary pitcher batting retains its pre-origin fallback. No current charts, age curves, minor/international translations or rejected Statcast predictors enter. Stewart and Misiorowski remain in an unscored source-history appendix, with no candidate projections.\n\nTESTING AND LIMITS\nThe executable's tests fit synthetic examples only. They check preserved individual workload differences within a shared pool, retained declines/nonappearances, chronology, sparse support and coherent outputs. Historical label/support counts are not accuracy tests. No historical estimator was fitted, no historical forecast errors were scored, and no2026 errors were used. Support floors, prior50 and deterministic pool backoff are fixed before scoring. Full fantasy counts and team-opportunity constraints are still pending future work; no forecast adoption is authorized by this registration.\n\nNEXT BUILD\nRun this frozen candidate against unchanged v1.43 for2023/2024/2025 with strictly earlier training and shared freshness labels. Freeze metric memberships before errors, carry every fallback, and retain all prior workload/count/role/freshness guards. Treat results as diagnostic-informed development on already reviewed seasons, not fresh independent validation. Only after workload passes may complete-count and team-opportunity work be separately implemented/reviewed.\n'''
(O/'READ_ME.txt').write_text(text,encoding='utf-8')
def tab(rr,cc):return '<div style="overflow:auto"><table><tr>'+''.join('<th>'+html.escape(c.replace('_',' '))+'</th>' for c in cc)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(c,'')))+'</td>' for c in cc)+'</tr>' for r in rr)+'</table></div>'
page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Player-anchored workload registration</title><style>body{font:16px/1.6 system-ui;max-width:1250px;margin:40px auto;padding:20px;color:#183441}table{border-collapse:collapse;font-size:13px;width:100%}td,th{border:1px solid #cad8e2;padding:10px;text-align:left}th{background:#e3edf5}pre{white-space:pre-wrap}</style><h1>Player-anchored workload: registered and unscored</h1><p>One new candidate. Own latest workload plus learned signed change. v1.43 unchanged.</p><h2>Declines and zero outcomes retained</h2>'+tab(counts,['role','eligible_rows','negative_primary_residuals','zero_primary_exposure_targets','positive_anchor_to_zero_targets'])+'<h2>Future subgroup sample support</h2>'+tab(subgroups,['origin','role','shared_freshness','full_cohort_n','candidate_eligible_n','minimum_guard_n','sample_support'])+'<p><a href="experiment_contract.json">Frozen contract</a> · <a href="shared_preorigin_freshness_ledger.csv">Shared freshness ledger</a> · <a href="executable_tests.csv">Executable checks</a> · <a href="support_preflight_without_fit.csv">Training support</a></p><h2>Method and limitations</h2><pre>'+html.escape(text)+'</pre></html>'
(O/'registration_report.html').write_text(page,encoding='utf-8')
shutil.copy2(__file__,O/'register_player_anchored_workload.py');dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(summary,indent=2),flush=True)
