"""Describe fixed failed-model outputs. No fit, revised forecasts, or new adoption test."""
import csv,json,hashlib,math,sys,zipfile,html,shutil,importlib.util
from pathlib import Path
from collections import Counter,defaultdict
import statistics as st
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
V=Path('outputs/2027_usage_transition_validation');S=Path('outputs/2027_usage_transition_registration');P=Path('outputs/2027_game_usage_reconstruction');O=Path('outputs/2027_usage_transition_diagnostic');O.mkdir(exist_ok=False);watch={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def take(p):p=Path(p);watch[str(p.resolve())]=sha(p);return p
def read(p):
 with take(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load(p):return json.loads(take(p).read_text(encoding='utf-8-sig'))
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
def num(x):return None if x in (None,'') else float(x)
def avg(x):return sum(x)/len(x) if x else None
def med(x):return st.median(x) if x else None
for root in [V,S]:
 bank=load(root/'output_sha256.json')
 for n,h in bank.items():assert sha(take(root/n))==h
freeze=load(S/'registration_freeze.json');assert all(sha(S/n)==h for n,h in freeze['registered_files'].items())
contract=dict(task='Diagnostic review of fixed failed challenger only',selection_errors_allowed=[2023,2024,2025],future_2026='Never score; prior published2027 illustrative history only in separate appendix',groups='Pre-origin descriptive proxies; no change to original comparison memberships or guards',pool_counterfactuals='Root/latest/selected node arithmetic only, never new forecast-error or adoption tests',model_fits=0,new_forecasts=False,threshold_changes=False)
dump('diagnostic_contract.json',contract)
preds=read(V/'historical_workload_predictions.csv');models=load(V/'frozen_historical_models.json');panel=load(S/'historical_panel_unscored.json');registration=load(S/'experiment_contract.json')
annual={(int(r['season']),r['role'],r['mlbam_id']):r for r in read(P/'historical_season_usage_2019_2025.csv')}
cert={(int(r['season']),r['mlbam_id']):r for r in read(P/'hitter_participation_certification.csv') if int(r['season'])<=2025}
ms=importlib.util.spec_from_file_location('fixed_model',S/'usage_transition_model.py');m=importlib.util.module_from_spec(ms);ms.loader.exec_module(m)
lab=R/'outputs/training_labels_v1_0';train=take(lab/'training_labels.parquet');hp=take(R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv');ov=R/'outputs/participation_label_overlay_v1_27'
for p in [ov/'report.json',ov/'participation_label_overlay.csv']:take(p)
a,_=apply_overlay(ov,labels(train),train,hp,watch);assert max(k[0] for k in a)<=2025
for role in ['hitter','pitcher']:
 take(Path('outputs/2027_statcast_strengthened_validation')/f'2027_{role}s_working_v1_43.csv');take(R/'outputs/skill_regressed_release_v1_43'/f'projections_2027_{role}s.csv')
features={(int(r['target_season']),r['role'],r['mlbam_id']):r for r in panel}
training_cache={};pool_diagnostics=[];traces=[];state_traces=[];player_rows=[];original_support_audit=[];scorebins=defaultdict(list)
def component(role,vector):return vector[3] if role=='hitter' else (vector[3]+vector[4])/3
def value(role,node):return 162*sum(node['probabilities'][s]*component(role,node['means'][s]) for s in node['probabilities'])
def node_rows(year,role,pool):
 key=(year,role,pool)
 if key not in training_cache:
  rr=[r for r in panel if r['eligible'] and r['role']==role and int(r['target_season'])<year]
  if pool!='GLOBAL':
   bits=pool.split('|');rr=[r for r in rr if r['latest_state']==bits[0]]
   if len(bits)==3:rr=[r for r in rr if r['recent_state']==bits[1] and r['experience']==bits[2]]
  training_cache[key]=rr
 return training_cache[key]
for p in preds:
 y=int(p['season']);role=p['role'];pid=p['mlbam_id'];r=features[y,role,pid];prior=annual.get((y-1,role,pid));prior2=annual.get((y-2,role,pid));metric='PA' if role=='hitter' else 'IP'
 prevstate=m.usage_state(role,prior2);latest=num(prior.get('PA' if role=='hitter' else 'IP')) if prior else None
 if role=='pitcher' and prior and latest is None:latest=float(prior['OUTS'])/3
 name=(prior or annual.get((y,role,pid)) or {}).get('name','')
 positive=p['freshness']=='RECENT_POSITIVE';callup=positive and int(r['prior_positive_seasons'])<2
 active_states=set(m.STATES[role][1:]);rolechange=(prevstate in active_states and p['latest_state'] in active_states and prevstate!=p['latest_state']) or (p['recent_state'] in active_states and p['latest_state'] in active_states and p['recent_state']!=p['latest_state'])
 returner=p['returner']=='EARLIER_SUBSTANTIAL_NO_RECENT_POSITIVE';established=p['history']=='ESTABLISHED'
 group='RETURNER_HISTORY_PROXY' if returner else 'RECENT_CALLUP_PROXY' if callup else 'ROLE_CHANGE_PROXY' if rolechange else 'ESTABLISHED_STABLE' if established else 'OTHER_SPARSE_OR_INACTIVE'
 b=num(p.get('baseline_'+metric));c=num(p.get('candidate_'+metric));truth=num(p.get('actual_'+metric));supported=p['supported']=='True';known=p['target_known']=='True';be=b-truth if known and b is not None else None;ce=c-truth if known and c is not None else None
 row=dict(season=y,role=role,mlbam_id=pid,name=name,metric=metric,primary_diagnostic_group=group,recent_positive=positive,recent_callup_proxy=callup,role_change_proxy=rolechange,returner_proxy=returner,history=p['history'],freshness=p['freshness'],prior_role=p['prior_role'],prior_annual_state=prevstate,latest_state=p['latest_state'],recent_state=p['recent_state'],latest_actual_exposure=latest,baseline=b,candidate=c,actual=truth,baseline_error=be,candidate_error=ce,delta_squared_error=ce*ce-be*be if known and be is not None else None,supported=supported,pool_used=p['pool_used'],fallback_reason=p['fallback_reason'])
 player_rows.append(row)
 if known and be is not None:
  for scope in ['FULL_KNOWN']+(['SUPPORTED'] if supported else ['FALLBACK'])+(['RECENT_POSITIVE_SUPPORTED'] if positive and supported else []):
   for cohort in ['ALL',group]+(['OVERLAP_ROLE_CHANGE'] if rolechange else [])+(['OVERLAP_RECENT_CALLUP'] if callup else []):scorebins[y,role,scope,cohort].append(row)
 if role=='hitter':
  last_label=a.get((y-1,'hitter',pid,'PA'));cc=cert.get((y-1,pid),{})
  original_support_audit.append(dict(season=y,mlbam_id=pid,original_freshness=p['freshness'],original_latest_PA=last_label,original_latest_label_status='MISSING' if last_label is None else 'EXPLICIT_ZERO' if last_label==0 else 'POSITIVE',candidate_latest_state=p['latest_state'],prior_reconstructed_zero_PA_certified=cc.get('certified_zero_PA_exposure')=='True',prior_reconstructed_no_MLB_appearance_certified=cc.get('certified_no_MLB_appearance')=='True',supported=supported,fallback_reason=p['fallback_reason']))
 if not supported:continue
 entry=models[str(y)]['roles'][role];pool=p['pool_used'];node=entry['root'] if pool=='GLOBAL' else entry['nodes'][pool];rr=node_rows(y,role,pool);assert len(rr)==node['n'];q=node['probabilities'];zero_state=m.STATES[role][0];prob=1-q[zero_state];raw=Counter(x['target_state'] for x in rr)
 calc=value(role,node);assert math.isclose(calc,c,abs_tol=1e-8)
 hierarchy='GLOBAL' if pool=='GLOBAL' else 'LATEST_STATE' if '|' not in pool else 'LATEST_RECENT_EXPERIENCE'
 specific='|'.join((p['latest_state'],p['recent_state'],r['experience']));latestrows=node_rows(y,role,p['latest_state']);specificrows=node_rows(y,role,specific)
 def failure(rows):
  n=len(rows);z=sum(x['target_state']==zero_state for x in rows);pos=n-z
  return ';'.join(s for s,fail in [('N_BELOW_200',n<200),('ZERO_BELOW_20',z<20),('POSITIVE_BELOW_20',pos<20)] if fail)
 t=dict(season=y,role=role,mlbam_id=pid,name=name,pool=pool,hierarchy=hierarchy,selected_rows=len(rr),latest_pool_rows=len(latestrows),latest_pool_failure=failure(latestrows),specific_pool_rows=len(specificrows),specific_pool_failure=failure(specificrows),probability_parent_weight=4/(len(rr)+4) if pool=='GLOBAL' else 50/(len(rr)+50),positive_exposure_probability=prob,conditional_active_workload=c/prob if prob else None,unconditional_workload=c,zero_exposure_mixture_reduction=c/prob-c if prob else None,latest_individual_workload=latest,change_from_latest=c-latest if latest is not None else None,root_workload=value(role,entry['root']),latest_state_node_workload=value(role,entry['nodes'][p['latest_state']]) if p['latest_state'] in entry['nodes'] else None,selected_workload=calc,individual_exact_workload_used_as_numeric_predictor=False,recent_positive=positive,primary_diagnostic_group=group)
 traces.append(t)
 for s in m.STATES[role]:
  n=raw[s];mean=162*component(role,node['means'][s]);rawmean=162*avg([component(role,x['target_vector']) for x in rr if x['target_state']==s]) if n else None
  state_traces.append(dict(season=y,role=role,mlbam_id=pid,pool=pool,target_state=s,state_training_rows=n,selected_probability=q[s],raw_cell_state_frequency=n/len(rr),selected_conditional_workload=mean,raw_cell_conditional_workload=rawmean,conditional_mean_parent_weight=0 if pool=='GLOBAL' else 1 if n<20 else 50/(n+50),full_parent_mean_inherited=pool!='GLOBAL' and n<20,contribution_to_candidate=q[s]*mean))
save('player_error_diagnostics.csv',player_rows);save('pooling_trace_by_player.csv',traces);save('pooling_state_contributions.csv',state_traces);save('hitter_guard_label_crosswalk.csv',original_support_audit)
summaries=[]
for (y,role,scope,cohort),rr in sorted(scorebins.items()):
 be=[r['baseline_error'] for r in rr];ce=[r['candidate_error'] for r in rr];bm=avg([x*x for x in be]);cm=avg([x*x for x in ce]);sse=sum(r['delta_squared_error'] for r in rr)
 summaries.append(dict(season=y,role=role,scope=scope,cohort=cohort,n=len(rr),baseline_MSE=bm,candidate_MSE=cm,MSE_ratio=cm/bm if bm else None,baseline_MAE=avg(list(map(abs,be))),candidate_MAE=avg(list(map(abs,ce))),baseline_bias=avg(be),candidate_bias=avg(ce),baseline_over=sum(x>0 for x in be),baseline_under=sum(x<0 for x in be),candidate_over=sum(x>0 for x in ce),candidate_under=sum(x<0 for x in ce),sum_delta_squared_error=sse))
save('error_breakdown_by_fold.csv',summaries)
macro=[]
for role in ['hitter','pitcher']:
 for scope in ['FULL_KNOWN','SUPPORTED','RECENT_POSITIVE_SUPPORTED','FALLBACK']:
  for cohort in sorted({r['cohort'] for r in summaries if r['role']==role and r['scope']==scope}):
   ss=[r for r in summaries if r['role']==role and r['scope']==scope and r['cohort']==cohort];valid=[r['MSE_ratio'] for r in ss if r['MSE_ratio'] is not None]
   macro.append(dict(role=role,scope=scope,cohort=cohort,folds=len(ss),player_seasons=sum(r['n'] for r in ss),mean_fold_MSE_ratio=avg(valid),mean_fold_MSE_change_pct=(avg(valid)-1)*100 if valid else None,mean_fold_baseline_bias=avg([r['baseline_bias'] for r in ss]),mean_fold_candidate_bias=avg([r['candidate_bias'] for r in ss]),sum_delta_squared_error=sum(r['sum_delta_squared_error'] for r in ss)))
save('error_breakdown_summary.csv',macro)
for sign,title in [(1,'largest_error_increases.csv'),(-1,'largest_error_reductions.csv')]:save(title,sorted([r for r in player_rows if r['supported'] and r['actual'] is not None],key=lambda r:-sign*r['delta_squared_error'])[:100])
poolgroups=defaultdict(list)
for t in traces:poolgroups[t['season'],t['role'],t['pool']].append(t)
pool_summary=[]
for (y,role,pool),tt in sorted(poolgroups.items()):
 x=[r['latest_individual_workload'] for r in tt if r['latest_individual_workload'] is not None];pp=[r['selected_workload'] for r in tt]
 assert len({round(v,10) for v in pp})==1
 pool_summary.append(dict(season=y,role=role,pool=pool,players=len(tt),recent_positive_players=sum(r['recent_positive'] for r in tt),training_rows=tt[0]['selected_rows'],one_shared_prediction=pp[0],latest_individual_min=min(x) if x else None,latest_individual_max=max(x) if x else None,latest_individual_span=max(x)-min(x) if x else None,probability_parent_weight=tt[0]['probability_parent_weight'],positive_exposure_probability=tt[0]['positive_exposure_probability']))
save('shared_pool_prediction_ranges.csv',pool_summary)
poolmacro=[]
for role in ['hitter','pitcher']:
 for scope in ['ALL_SUPPORTED','RECENT_POSITIVE_SUPPORTED']:
  tt=[t for t in traces if t['role']==role and (scope=='ALL_SUPPORTED' or t['recent_positive'])]
  pp=[p for p in pool_summary if p['role']==role and (scope=='ALL_SUPPORTED' or p['recent_positive_players'])]
  weights=[s['conditional_mean_parent_weight'] for s in state_traces if s['role']==role and any(t['season']==s['season'] and t['mlbam_id']==s['mlbam_id'] for t in tt)] if False else []
  poolmacro.append(dict(role=role,scope=scope,n=len(tt),global_backoff=sum(t['hierarchy']=='GLOBAL' for t in tt),latest_state_pool=sum(t['hierarchy']=='LATEST_STATE' for t in tt),full_specific_pool=sum(t['hierarchy']=='LATEST_RECENT_EXPERIENCE' for t in tt),latest_pool_zero_support_failures=sum('ZERO_BELOW_20' in t['latest_pool_failure'] for t in tt),specific_pool_zero_support_failures=sum('ZERO_BELOW_20' in t['specific_pool_failure'] for t in tt),median_probability_parent_weight=med([t['probability_parent_weight'] for t in tt]),median_latest_actual=med([t['latest_individual_workload'] for t in tt if t['latest_individual_workload'] is not None]),median_candidate=med([t['selected_workload'] for t in tt]),median_candidate_minus_latest=med([t['change_from_latest'] for t in tt if t['change_from_latest'] is not None]),median_active_conditional_workload=med([t['conditional_active_workload'] for t in tt if t['conditional_active_workload'] is not None]),median_zero_exposure_mixture_reduction=med([t['zero_exposure_mixture_reduction'] for t in tt if t['zero_exposure_mixture_reduction'] is not None])))
save('pooling_summary.csv',poolmacro)
supportaudit=[]
for y in [2023,2024,2025]:
 rr=[r for r in original_support_audit if r['season']==y]
 for group,subset in [('ORIGINAL_KNOWN_ZERO',[r for r in rr if r['original_freshness']=='KNOWN_ZERO_RECENT']),('PRIOR_ZERO_PA_CERTIFIED',[r for r in rr if r['prior_reconstructed_zero_PA_certified']]),('PRIOR_NO_MLB_APPEARANCE_CERTIFIED',[r for r in rr if r['prior_reconstructed_no_MLB_appearance_certified']])]:
  supportaudit.append(dict(origin=y,definition=group,all_cohort_rows=len(subset),supported_rows=sum(r['supported'] for r in subset),fallback_rows=sum(not r['supported'] for r in subset),original_missing_PA_labels=sum(r['original_latest_label_status']=='MISSING' for r in subset),original_explicit_zero_labels=sum(r['original_latest_label_status']=='EXPLICIT_ZERO' for r in subset),required_minimum_per_fold=15,sample_support_if_this_definition_used=sum(r['supported'] for r in subset)>=15,used_for_new_guard_test=False))
save('hitter_subgroup_support_audit.csv',supportaudit)
# Illustrative players: source history appendix only, no candidate forecast or2026 error.
focus=read(P/'focused_2027_history_usage.csv');illustrations=[]
for name,role,pid in [('Sal Stewart','hitter','701398'),('Jacob Misiorowski','pitcher','694819')]:
 for r in focus:
  if r['name']==name and r['role']==role:
   illustrations.append(dict(name=name,role=role,source_season=r['season'],G=r['G'],STARTS=r.get('STARTS'),GS=r.get('GS'),PA=r.get('PA'),IP=r.get('IP'),in_2023_2025_validation_cohort=any(p['role']==role and p['mlbam_id']==pid for p in preds),interpretation='Published source history only.2025 debut means no pre-origin MLB history for scoring folds. No new candidate forecast and no2026 forecast error.'))
save('illustrative_cases_not_scored.csv',illustrations)
recommendation=dict(status='RECOMMENDATION_ONLY_NOT_REGISTERED_NOT_IMPLEMENTED',one_experiment='Player-anchored workload residual estimator',hypothesis='Replacing each player with an absolute peer-group workload mean discarded individual workload variation. Test learning workload change relative to each player latest reconciled workload, rather than another absolute cohort mean.',target='Observed target joint workload/calendar minus the player own prior-season joint workload/prior calendar; include certified zero outcomes as negative residuals. At prediction add the estimated change to the individual prior workload vector.',fixed='Same historical source policy, baseline comparator, full comparison cohort, support floors, prior50 and deterministic pool hierarchy where applicable; no new age/chart/Statcast/minor features and no hyperparameter search.',risk='This is a point-estimate residual model, not a calibrated medical or appearance-probability model. Retain nonappearances, negative changes and uncertainty. No automatic growth increment, minimum workload floor or deletion of injury/role-loss cases.',coherence='Register component-vector construction and nonnegative joint projection rules before testing; derive pitcher G/OUTS from component partitions; do not claim full fantasy counts or team budgets are solved.',guard_prerequisite='Register a consistent pre-origin freshness ledger for both arms using certified zero-PA evidence, keeping original baseline predictions unchanged. Preserve15-row subgroup and2% thresholds. Do not retroactively relabel this failed run or call it a pass.',validation='This recommendation is informed by2023–2025 development errors. A future separately registered test must retain existing earlier-only guards and exclude2026 errors; repeated development folds are not fresh independent validation. Independent prospective evidence would still be needed.',model_fitted=False,projections_changed=False)
dump('one_proposed_experiment.json',recommendation)
summary=dict(status='DIAGNOSTIC_ONLY_V1_43_UNCHANGED',prediction_records=len(player_rows),supported_traces=len(traces),error_breakdown_rows=len(summaries),models_fitted=0,new_candidate_forecasts=0,errors_2026_scored=False,prior_guards_or_memberships_changed=False,source_files_changed=False,pooling_summary=poolmacro,subgroup_support=supportaudit,recommendation=recommendation['one_experiment'])
dump('diagnostic_summary.json',summary)
assert all(sha(p)==h for p,h in watch.items())
dump('source_manifest.json',watch);dump('verification_results.json',dict(source_hashes_verified=len(watch),all_supported_workloads_reproduced_from_frozen_nodes=True,all_shared_pool_predictions_identical=True,no_model_fit=True,no_new_forecast=True,no_2026_errors=True,no_baseline_or_guard_changes=True))
text='WORKLOAD CHALLENGER FAILURE DIAGNOSTIC\n\n'+json.dumps(summary,indent=2)+'''\n\nDEFINITIONS\nError is forecast minus actual; negative bias means underprojection. Fold-mean MSE ratios reproduce the original convention. Summed error contributions and pooled counts are separately labeled. Recent-call-up is a proxy for fewer than two positive MLB seasons in the prior four-year window, not independently verified rookie/service status. Role-change uses only pre-origin annual-to-annual or annual-to-last60 state changes. Returner is the existing observable earlier-substantial/no-recent-positive cohort, not a future signing. Primary diagnostic groups are mutually exclusive in returner/callup/role-change/established/other order; overlap tables are explicitly labeled. These groups do not alter scoring or adoption.\n\nPOOLING MECHANISM\nThe executable uses categorical latest/recent/experience groups, not each player's numeric latest workload. Every player in the same selected pool receives the same workload. Full-specific pools still discard within-group individual variation. Backoff can occur because a pool lacks200 rows or20 zero/positive outcomes. The conditional means additionally inherit their parent in states with fewer than20 cases, or shrink toward the parent with50 pseudo-rows. Probability smoothing and workload-mean smoothing are separate; node-level arithmetic traces do not constitute a new model or forecast-error test.\n\nSUBGROUP SUPPORT\nThe failed guard uses unchanged baseline freshness. Original missing PA is UNKNOWN_RECENT, even when the candidate's separately certified source ledger establishes zero PA. The support crosswalk distinguishes data absence from a definition/mapping mismatch. Existing numerical thresholds and failed decisions are not changed. A future protocol must register consistent as-of zero-versus-missing cohort definitions for both arms, document full-cohort IDs and secondary-role fallbacks, and still fail unsupported guards. Sufficient certified counts do not establish acceptable accuracy and are not a retroactive pass.\n\nILLUSTRATIVE CASES\nStewart and Misiorowski are source-history illustrations only. Their2025 MLB debuts leave them outside the prior-MLB-history scoring pool for2023–2025. No2027 candidate projection is manufactured for this diagnostic, and2026 performance is not used as a forecast-error target. Their histories cannot determine a replacement formula.\n\nONE RECOMMENDATION\n'''+json.dumps(recommendation,indent=2)+'\n'
(O/'DIAGNOSTIC_REPORT.txt').write_text(text,encoding='utf-8')
def tab(rr,cc):return '<div style="overflow:auto"><table><tr>'+''.join('<th>'+html.escape(c.replace('_',' '))+'</th>' for c in cc)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(c,'')))+'</td>' for c in cc)+'</tr>' for r in rr)+'</table></div>'
recent_summary=[r for r in macro if r['scope']=='RECENT_POSITIVE_SUPPORTED']
page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Workload failure diagnostic</title><style>body{font:16px/1.6 system-ui;max-width:1450px;margin:40px auto;padding:20px;color:#183543}table{border-collapse:collapse;font-size:13px;width:100%;margin-bottom:20px}td,th{border:1px solid #cad8e2;padding:9px;text-align:left;vertical-align:top}th{background:#e2edf5}pre{white-space:pre-wrap}</style><h1>Why the workload challenger failed</h1><p>Diagnostic only. No model fitted, forecast changed or adoption guard relaxed.</p><h2>Recently active players</h2>'+tab(recent_summary,['role','cohort','player_seasons','mean_fold_MSE_change_pct','mean_fold_baseline_bias','mean_fold_candidate_bias'])+'<h2>Pooling decisions</h2>'+tab(poolmacro,['role','scope','n','global_backoff','latest_state_pool','full_specific_pool','median_probability_parent_weight','median_candidate_minus_latest','median_zero_exposure_mixture_reduction'])+'<h2>Hitter known-zero support</h2>'+tab(supportaudit,['origin','definition','all_cohort_rows','supported_rows','original_missing_PA_labels','original_explicit_zero_labels','required_minimum_per_fold'])+'<h2>Detailed files</h2><p><a href="error_breakdown_by_fold.csv">Fold/group errors</a> · <a href="player_error_diagnostics.csv">Player-level errors</a> · <a href="pooling_trace_by_player.csv">Pooling trace</a> · <a href="shared_pool_prediction_ranges.csv">Within-pool workload ranges</a> · <a href="hitter_guard_label_crosswalk.csv">Guard-label crosswalk</a> · <a href="one_proposed_experiment.json">One proposed experiment</a></p><h2>Method and limitations</h2><pre>'+html.escape(text)+'</pre></html>'
(O/'diagnostic_report.html').write_text(page,encoding='utf-8')
shutil.copy2(__file__,O/'diagnose_usage_transition.py');dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(summary,indent=2),flush=True)
