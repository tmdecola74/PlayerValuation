"""Frozen v1.43 replay and separately specified, adoption-gated Statcast experiment."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS']:os.environ[k]='1'
import sys,csv,json,math,hashlib,shutil
from pathlib import Path
from collections import defaultdict,Counter
import numpy as np
import duckdb
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
from project_2027_v1_31 import project,FIELDS,WEIGHTS
import projection_phase_v1_42 as phase
from recent_skill_core_v1_23 import checked
O=Path('outputs/2027_v1_43_statcast_challenger');O.mkdir(exist_ok=False)
FEATURES=['gb_rate','ld_rate','fb_rate'];TARGETS={'hitter':['1B','2B','3B'],'pitcher':['SO','BB']}
CONTRACT={'version':'2027_V1_43_STATCAST_BB_0.1','status':'SEPARATE_RESEARCH_NOT_PRODUCTION','registered_before_loading_or_scoring':True,'baseline':'Exact v1.43 skill-regressed 2027 release; player history 2023–2026, fixed population priors through 2025','features':FEATURES,'feature_definition':'Official exported fraction of all BBE; BBE>=30 and existing v1.21 masks. Historical rows must additionally pass v1.22 RESEARCH_ELIGIBLE_RECONCILED_DEFINITION. No archive proxy substitution.','excluded_feature_families':'direction/pull-air, EV, bat tracking, baserunning, pitch arsenal and other unresolved or short-history families are audited but not predictors','targets':TARGETS,'feature_pooling':'Within prior four source years, BBE x 1:2:3:4 exposure weighting; all three metrics from a complete compatible source season; unknown not zero.','training':'Residual target count/exposure minus exact historical v1.43-style component rate. Train only on eligible targets strictly earlier than origin. Targets 2024 and 2025 available; 2026 targets prohibited.','model':'Single fixed ridge per role, penalty 20, intercept unpenalized; earlier training-weighted standardization, z clipped [-4,4], sample weights=min(target denominator,600) normalized to mean 1; minimum100 training players/seasons. No hyperparameter or feature search.','application':'Half predicted residual x frozen forecast denominator, capped to plus/minus half baseline count. Hitters adjust 1B/2B/3B while holding HR fixed and respecting AB; pitchers adjust SO/BB and recompute WHIP.','anchors':'PA/AB/IP/OUTS, HR, pitcher H/ER/ERA/W/SV/HLD/G/GS/QS and hitter R/RBI/SB/BB/HBP/SF/SH unchanged; no workload, minor, park or international changes','guards':phase.CONTRACT,'guard_comparator':'V1_43 versus STATCAST_RESEARCH using original phase.gate math; internal aliases weighted_actuals/skill_regression map to those arms only for executing unchanged guard code','historical_scoring':'2024 warmup unsupported without earlier compatible Statcast targets. 2025 is the first possible out-of-sample forecast. Unsupported warmup does not count as a supported fold.','2026_source_quality':'Structural sample/range/BBE checks only; no saved full 2026 event reconciliation. 2026-dependent Statcast production adjustments forbidden until source definition/event scope is reviewed.','release_policy':'Publish replayed baseline, exploratory candidate, adoption-gated candidate and long differences. Failed role gates or missing inputs retain entire baseline vector. Exploratory values never silently replace production.','2026_MLB_targets_fit_or_score':False,'2026_data_usage':'2027 player history/input audit only; frozen decision and model hashes written before opening holdout labels','Steamer_read':False,'production_changes':False,'limitations':['Retrospective source vintages','At most one independent earlier-supported scoring origin with supplied official definitions','No new MLB opportunity for minor/international-only players','Metric eligibility differs and missing features are explicit','No inference that a CSV family existing means its scope is validated']}
(O/'experiment_contract.json').write_text(json.dumps(CONTRACT,indent=2))
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2))
pub=R/'outputs/skill_regressed_release_v1_43';boardroot=R/'outputs/statcast_leaderboards_v1_21';scope=R/'outputs/statcast_scope_audit_v1_22';lab=R/'outputs/training_labels_v1_0';overlay=R/'outputs/participation_label_overlay_v1_27';hp=R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv'
watch={};take=lambda root,n:checked(root,n,watch)
train=take(lab,'training_labels.parquet');take(pub,'publication_freeze.json');choices=take(R/'outputs/projection_phase_v1_42','frozen_choices.json');take(overlay,'report.json');take(overlay,'participation_label_overlay.csv');take(hp.parent,hp.name)
for role in TARGETS:take(pub,f'projections_2027_{role}s.csv')
for root,n in [(boardroot,'source_inventory.json'),(boardroot,'leaderboard_build_report.json'),(scope,'scope_audit_report.json'),(scope,'feature_eligibility_decisions.csv')]:take(root,n)
historical_path=take(boardroot,'historical/leaderboard_features.parquet');future_path=take(boardroot,'quarantine_2026/leaderboard_features.parquet')
for p in [R/'project_2027_v1_31.py',R/'projection_phase_v1_42.py',R/'skill_regressed_release_v1_43.py']:watch[str(p)]=sha(p)
a,_=apply_overlay(overlay,labels(train),train,hp,watch);assert max(k[0] for k in a)<=2025
prior=json.loads(choices.read_text())['skill_population'];assert prior==phase.population(a,2026)
inventory=json.loads((boardroot/'source_inventory.json').read_text());snapshots=[]
for s in inventory['sources']:
 p=boardroot/'source_snapshots'/s['file'];assert sha(p)==s['sha256'];watch[str(p)]=sha(p)
 for y,n in s['row_counts_by_season'].items():snapshots.append(dict(source_id=s['source_id'],family=s['family'],role=s['player_type'],season=y,source_rows=n,source_file=str(p),sha256=s['sha256'],source_scope=s.get('filter_settings','UNKNOWN')))
save('statcast_source_inventory.csv',snapshots)
decisions={}
for r in read(scope/'feature_eligibility_decisions.csv'):
 if r['family']=='batted_ball' and r['metric'] in FEATURES:decisions[int(r['source_season']),r['player_type'],r['mlbam_id'],r['metric']]=r['audit_decision']
boards={};metric_audit=[];feature_rows=[];source_quality=[]
for path,allowed in [(historical_path,{2023,2024,2025}),(future_path,{2026})]:
 with duckdb.connect() as db:
  db.read_parquet(str(path)).create_view('b')
  assert db.execute('SELECT count(*) FROM (SELECT source_season,player_type,mlbam_id,family,metric,count(*) n FROM b GROUP BY ALL HAVING n>1)').fetchone()[0]==0
  assert set(y for y, in db.execute('SELECT DISTINCT source_season FROM b').fetchall())==allowed
  for y,role,fam,m,eligible,reason,n,players in db.execute('SELECT source_season,player_type,family,metric,eligible,reason,count(*),count(DISTINCT mlbam_id) FROM b GROUP BY ALL ORDER BY ALL').fetchall():
   metric_audit.append(dict(season=y,role=role,family=fam,metric=m,existing_eligible=eligible,source_reason=reason,rows=n,distinct_players=players,challenger_predictor=fam=='batted_ball' and m in FEATURES))
  cur=db.execute("SELECT * FROM b WHERE family='batted_ball' AND metric IN ('gb_rate','ld_rate','fb_rate','pu_rate')");columns=[c[0] for c in cur.description];raw=[dict(zip(columns,r)) for r in cur.fetchall()]
 grouped=defaultdict(dict)
 for r in raw:grouped[int(r['source_season']),r['player_type'],str(r['mlbam_id'])][r['metric']]=r
 for key,dd in grouped.items():
  y,role,pid=key;reasons=[]
  for m in FEATURES:
   r=dd.get(m);status=decisions.get((*key,m),'NO_HISTORICAL_SCOPE_DECISION') if y<2026 else 'STRUCTURAL_ONLY_2026_EVENT_SCOPE_PENDING'
   eligible=bool(r and r['eligible'] and r['sample_eligible'] and r['definition_supported'] and r['value'] is not None and math.isfinite(r['value']) and 0<=r['value']<=1 and r['denominator'] is not None and r['denominator']>=30 and r['sample_basis']=='EXPORTED_BBE' and r['definition']=='EXPORTED_FRACTION_OF_ALL_BBE' and r['unit']=='fraction')
   admit=eligible and (status=='RESEARCH_ELIGIBLE_RECONCILED_DEFINITION' if y<2026 else True)
   if not admit:reasons.append(m+':'+(status if eligible else (str(r['reason']) if r else 'MISSING_METRIC')))
   feature_rows.append(dict(season=y,role=role,mlbam_id=pid,metric=m,value=r['value'] if r else None,BBE=r['denominator'] if r else None,existing_eligible=eligible,scope_status=status,research_admitted=admit,source_file=r['source_id'] if r else '',source_row=r['source_row'] if r else ''))
  if not reasons:
   ds={float(dd[m]['denominator']) for m in FEATURES}
   if len(ds)!=1:reasons.append('INCONSISTENT_BBE_DENOMINATORS')
   if sum(dd[m]['value'] for m in FEATURES)>1.0005001:reasons.append('GB_LD_FB_SUM_EXCEEDS_ONE')
   pu=dd.get('pu_rate')
   if pu and pu['value'] is not None and abs(sum(dd[m]['value'] for m in FEATURES)+pu['value']-1)>.0005001:reasons.append('GB_LD_FB_PU_SUM_NOT_ONE')
  status='RESEARCH_COMPLETE' if not reasons else 'BUNDLE_EXCLUDED'
  if not reasons:boards[key]=dict(values=[float(dd[m]['value']) for m in FEATURES],BBE=float(dd[FEATURES[0]]['denominator']))
  source_quality.append(dict(season=y,role=role,mlbam_id=pid,status=status,reasons=';'.join(reasons),historical_definition_reconciled=y<2026 and not reasons,production_source_approved=False,interpretation='Historical definition eligibility is research permission, not adoption. 2026 has structural-only permission.'))
save('statcast_metric_availability.csv',metric_audit);save('statcast_selected_feature_audit.csv',feature_rows);save('statcast_source_bundle_audit.csv',source_quality)
baseline_cache={};prior_cache={};ctx_cache={}
def baseline(y,role,pid):
 key=y,role,pid
 if key not in baseline_cache:
  if y not in prior_cache:prior_cache[y]=phase.population(a,y) if y<2027 else prior
  b=project(a,role,pid,y)
  if b is None:return None,False
  c,s,t=phase.skill_candidate(b,a,role,pid,y,prior_cache[y]);baseline_cache[key]=c,s
 return baseline_cache[key]
def features(y,role,pid):
 obs=[(s,w,boards[s,role,pid]) for s,w in zip(range(y-4,y),WEIGHTS) if (s,role,pid) in boards]
 if not obs:return None,[],0
 den=sum(w*r['BBE'] for s,w,r in obs)
 return [sum(w*r['BBE']*r['values'][j] for s,w,r in obs)/den for j in range(3)],[s for s,w,r in obs],den
def cases(y,role):
 den='AB' if role=='hitter' else 'OUTS'
 for pid in phase.ids_before(a,role,y):
  b,s=baseline(y,role,pid);x,ss,d=features(y,role,pid);td=a.get((y,role,pid,den));truth=[a.get((y,role,pid,m)) for m in TARGETS[role]]
  if not s or x is None or not td or not b[den] or None in truth or any(b.get(m) is None for m in TARGETS[role]):continue
  assert max(ss)<y
  yield dict(pid=pid,target=y,x=x,residual=[v/td-b[m]/b[den] for v,m in zip(truth,TARGETS[role])],weight=min(td,600))
fit_support=[]
def fit(origin):
 model={}
 for role in TARGETS:
  training=[r for y in [2024,2025] if y<origin for r in cases(y,role)]
  years=sorted({r['target'] for r in training});entry=dict(n=len(training),target_years=years,max_target_year=max(years) if years else None,coefficients=None)
  if len(training)>=100:
   x=np.array([r['x'] for r in training]);t=np.array([r['residual'] for r in training]);w=np.array([r['weight'] for r in training],dtype=float);mu=np.average(x,axis=0,weights=w);sd=np.sqrt(np.average((x-mu)**2,axis=0,weights=w));sd=np.where(sd<1e-8,1,sd);z=np.column_stack((np.ones(len(x)),np.clip((x-mu)/sd,-4,4)));w/=w.mean();penalty=20*np.eye(4);penalty[0,0]=0;beta=np.linalg.solve(z.T@(z*w[:,None])+penalty,z.T@(t*w[:,None]));entry['coefficients']=dict(mean=mu.tolist(),scale=sd.tolist(),beta=beta.tolist())
  assert not years or max(years)<origin and max(years)<=2025
  fit_support.append(dict(origin=origin,role=role,n=len(training),training_years=';'.join(map(str,years)),max_target_year=entry['max_target_year'],model_supported=entry['coefficients'] is not None));model[role]=entry
 return model
def apply(b,s,x,model,role):
 out=dict(b)
 if not s:return out,'BASELINE_SKILL_GROUP_UNSUPPORTED'
 if x is None:return out,'NO_COMPLETE_ELIGIBLE_STATCAST_HISTORY'
 if model is None:return out,'INSUFFICIENT_EARLIER_TRAINING'
 den='AB' if role=='hitter' else 'OUTS';needed=TARGETS[role]+(['HR','BB','HBP','SF'] if role=='hitter' else ['H','IP'])
 if not b.get(den) or any(b.get(m) is None for m in needed):return out,'MISSING_BASELINE_COMPONENT'
 z=np.r_[1,np.clip((np.array(x)-model['mean'])/model['scale'],-4,4)];delta=z@np.array(model['beta'])
 for m,d in zip(TARGETS[role],delta):out[m]=float(b[m]+np.clip(.5*b[den]*d,-.5*b[m],.5*b[m]))
 if role=='hitter':
  non=sum(out[m] for m in TARGETS[role]);capacity=max(0,out['AB']-out['HR'])
  if non>capacity:
   for m in TARGETS[role]:out[m]*=capacity/non
  out['H']=sum(out[m] for m in ['1B','2B','3B','HR']);out['AVG']=out['H']/out['AB'];out['SLG']=sum(i*out[m] for i,m in enumerate(['1B','2B','3B','HR'],1))/out['AB'];out['OBP']=(out['H']+out['BB']+out['HBP'])/(out['AB']+out['BB']+out['HBP']+out['SF']);out['OPS']=out['OBP']+out['SLG']
 else:out['WHIP']=3*(out['H']+out['BB'])/out['OUTS']
 phase.verify_vector(out,role)
 mutable=set(TARGETS[role])|({'H','AVG','OBP','SLG','OPS'} if role=='hitter' else {'WHIP'})
 assert all(out[m]==b[m] for m in FIELDS[role] if m not in mutable)
 return out,'EXPLORATORY_STATCAST_APPLIED'
historical=[];bins=defaultdict(list);historical_models={}
for origin in [2024,2025]:
 model=fit(origin);historical_models[str(origin)]=model
 for role in TARGETS:
  for pid in phase.ids_before(a,role,origin):
   b,s=baseline(origin,role,pid);x,ss,den=features(origin,role,pid);c,status=apply(b,s,x,model[role]['coefficients'],role);ctx=phase.context(a,role,pid,origin);supported=status=='EXPLORATORY_STATCAST_APPLIED'
   metrics=tuple(dict.fromkeys(phase.RATES[role]+(('H','HR') if role=='hitter' else ('SO','ER','BB','H','HR'))))
   for m in metrics:
    if m.endswith('_PER_OUTS'):
     primitive=m.removesuffix('_PER_OUTS');num=a.get((origin,role,pid,primitive));d=a.get((origin,role,pid,'OUTS'));truth=num/d if num is not None and d else None
    else:truth=a.get((origin,role,pid,m))
    bv=phase.rate(role,m,b);cv=phase.rate(role,m,c)
    if None in [truth,bv,cv]:continue
    historical.append(dict(origin=origin,role=role,mlbam_id=pid,metric=m,actual=truth,baseline=bv,challenger=cv,status=status,source_feature_years=';'.join(map(str,ss)),model_max_target=model[role]['max_target_year']))
    for cohort in ['ALL',ctx['history']]:bins[origin,role,m,cohort,'SUPPORTED' if supported else 'FALLBACK'].append((pid,bv-truth,cv-truth))
 print('Completed historical origin',origin,flush=True)
scores=[];gate_rows=[]
for (y,role,m,cohort,pool),rr in sorted(bins.items()):
 for j,method in enumerate(['V1_43','STATCAST_RESEARCH']):
  errors=[r[j+1] for r in rr];n=len(rr);row=dict(season=y,role=role,experiment='SKILL',metric=m,cohort=cohort,pool=pool,method=method,n=n,membership_sha256=phase.keyhash([r[0] for r in rr]),mse=sum(e*e for e in errors)/n,rmse=math.sqrt(sum(e*e for e in errors)/n),mae=sum(abs(e) for e in errors)/n,bias=sum(errors)/n);scores.append(row);gate_rows.append(dict(row,method=['weighted_actuals','skill_regression'][j]))
gates=[]
for role in TARGETS:
 g=phase.gate(gate_rows,role,'SKILL',2026);g['comparison']='STATCAST_RESEARCH_vs_V1_43';g['internal_guard_aliases']={'weighted_actuals':'V1_43','skill_regression':'STATCAST_RESEARCH'};g['production_source_2026_review_passed']=False;g['adoptable_for_2027']=False;g['release_reason']='2026_STATCAST_EVENT_SCOPE_PENDING' if g['eligible'] else ';'.join(g['reasons'])+';2026_STATCAST_EVENT_SCOPE_PENDING';gates.append(g)
save('historical_metric_predictions.csv',historical);save('historical_scores.csv',scores);dump('adoption_gates.json',gates)
final_model=fit(2026);save('model_training_support.csv',fit_support);dump('frozen_models.json',dict(feature_names=FEATURES,targets=TARGETS,historical=historical_models,final=final_model))
freeze_names=['experiment_contract.json','adoption_gates.json','frozen_models.json'];frozen={n:sha(O/n) for n in freeze_names};dump('publication_freeze.json',dict(selection_max_year=2025,models_max_target_year=2025,holdout_labels_opened=False,frozen_files=frozen,approved_role_adjustments=[],source_2026_event_review_complete=False))
# Only after model/decision freeze, 2026 actuals become 2027 player history.
hold=take(lab,'holdout_labels.parquet');a.update(labels(hold,2026));ep=R/'outputs/pitcher_evaluation_v1_29';cert=json.loads(take(ep,'report.json').read_text());assert cert['season_certified'] and cert['complete_pool_scored']
ovrows=read(take(ep,'evaluation_label_overlay_2026.csv'));assert len(ovrows)==cert['preseason_pool']
for r in ovrows:
 assert r['season']=='2026' and r['status'] in ['VERIFIED_APPEARED','VERIFIED_NO_APPEARANCE']
 for m,col in [('G','evaluation_g'),('OUTS','evaluation_outs')]:
  key=2026,'pitcher',r['mlbam_id'],m;v=float(r[col]);assert a.get(key,v)==v;a[key]=v
counts=Counter((y,role,m) for y,role,pid,m in a if 2023<=y<=2026);save('fangraphs_eligible_metric_coverage.csv',[dict(season=y,role=r,metric=m,eligible_players=n) for (y,r,m),n in sorted(counts.items())])
player_coverage=[];fg_missing=[];differences=[];release_summary=[];component_trace=[];international=[]
previous_exceptions=Path('outputs/minor_history_2027_research/research_exceptions.csv');inherited=defaultdict(list)
if previous_exceptions.exists():
 watch[str(previous_exceptions)]=sha(previous_exceptions)
 for r in read(previous_exceptions):
  if 'INTERNATIONAL' in r['issue']:inherited[r['role'],r['mlbam_id']].append(r['issue'])
for role in TARGETS:
 src=read(pub/f'projections_2027_{role}s.csv');assert set(r['mlbam_id'] for r in src)==set(phase.ids_before(a,role,2027));exploratory=[];selected=[];replayed=[];replayfields=0;roleGate=next(g for g in gates if g['role']==role)
 for r in src:
  pid=r['mlbam_id'];b,s=baseline(2027,role,pid)
  for m in FIELDS[role]:
   v=float(r[m]) if r[m]!='' else None;assert (v is None)==(b[m] is None)
   if v is not None:assert math.isclose(v,b[m],rel_tol=1e-9,abs_tol=1e-9),(role,pid,m,v,b[m])
   replayfields+=1
  phase.verify_vector(b,role);x,ss,den=features(2027,role,pid);c,status=apply(b,s,x,final_model[role]['coefficients'],role)
  flags=['RESEARCH_ONLY_NOT_ADOPTED','2026_STATCAST_EVENT_SCOPE_PENDING']
  if 2026 not in ss:flags.append('NO_ELIGIBLE_2026_STATCAST_BUNDLE')
  if s is False:flags.append('BASELINE_SKILL_FALLBACK')
  flags+=inherited[role,pid]
  cov=dict(role=role,mlbam_id=pid,name=r['name'],feature_complete=x is not None,eligible_Statcast_source_years=';'.join(map(str,ss)),has_2026_Statcast=2026 in ss,BBE_recency_weighted_exposure=den,exploratory_status=status,approved_status='V1_43_FALLBACK_ADOPTION_GUARDS',inherited_exceptions=r.get('exceptions',''),additional_exceptions=';'.join(flags))
  for y in range(2023,2027):
   d=a.get((y,role,pid,'AB' if role=='hitter' else 'OUTS'));cov[str(y)+'_MLB_skill_exposure']=d;cov[str(y)+'_Statcast_bundle']=source_status=next((z['status'] for z in source_quality if z['season']==y and z['role']==role and z['mlbam_id']==pid),'NO_STATCAST_SOURCE_ROW')
   for m in FIELDS[role]:
    if (y,role,pid,m) not in a:fg_missing.append(dict(role=role,mlbam_id=pid,season=y,metric=m,status='NO_ELIGIBLE_LABEL; unknown or excluded, not zero'))
  player_coverage.append(cov);replayed.append(dict(r));exploratory.append(dict(r,**{m:c[m] for m in FIELDS[role]},projection_source='STATCAST_BB_EXPLORATORY_ON_V1_43',statcast_status=status,statcast_source_years=cov['eligible_Statcast_source_years'],statcast_exceptions=';'.join(flags),release_status='RESEARCH_ONLY_NOT_ADOPTED'))
  selected.append(dict(r,projection_source='V1_43_PRESERVED_AFTER_STATCAST_TEST',statcast_status='BASELINE_FALLBACK_ROLE_GUARDS',statcast_rejection_reason=roleGate['release_reason'],statcast_input_status=status,international_translation_active=False,park_context_active=False,workload_experiment_active=False))
  for j,m in enumerate(FEATURES):component_trace.append(dict(role=role,mlbam_id=pid,name=r['name'],feature=m,pooled_value=x[j] if x is not None else None,source_seasons=';'.join(map(str,ss)),model_max_target=final_model[role]['max_target_year'],status=status))
  for m in FIELDS[role]:
   bv=b[m];cv=c[m]
   if bv is not None and cv is not None and not math.isclose(bv,cv,abs_tol=1e-12,rel_tol=1e-12):differences.append(dict(role=role,mlbam_id=pid,name=r['name'],metric=m,v1_43=bv,exploratory_challenger=cv,exploratory_delta=cv-bv,approved_candidate=bv,approved_delta=0,status='EXPLORATORY_DIFFERENCE_ONLY; approved value retains baseline'))
  if inherited[role,pid]:international.append(dict(role=role,mlbam_id=pid,name=r['name'],status='INTERNATIONAL_HISTORY_UNTRANSLATED',issues=';'.join(inherited[role,pid]),projection_action='Baseline retained; no minor/international coefficient substitution'))
 shutil.copy2(pub/f'projections_2027_{role}s.csv',O/f'2027_{role}s_v1_43_baseline.csv')
 save(f'2027_{role}s_statcast_exploratory.csv',exploratory);save(f'2027_{role}s_after_adoption_guards.csv',selected)
 release_summary.append(dict(role=role,players=len(src),baseline_fields_replayed=replayfields,feature_complete=sum(r['feature_complete'] for r in player_coverage if r['role']==role),research_adjusted=sum(r['statcast_status']=='EXPLORATORY_STATCAST_APPLIED' for r in exploratory),has_2026_Statcast=sum(r['has_2026_Statcast'] for r in player_coverage if r['role']==role),approved_adjusted=0,international_exceptions=sum(r['role']==role for r in international)))
save('player_input_coverage.csv',player_coverage);save('fangraphs_missing_or_ineligible_player_metrics.csv',fg_missing);save('pooled_statcast_player_inputs.csv',component_trace);save('baseline_vs_statcast_differences.csv',differences);save('international_coverage_exceptions.csv',international)
save('largest_exploratory_changes.csv',sorted(differences,key=lambda r:abs(r['exploratory_delta']),reverse=True)[:200])
assert all(sha(O/n)==h for n,h in frozen.items()) and all(sha(p)==h for p,h in watch.items())
save('release_summary.csv',release_summary);dump('source_manifest.json',watch)
dump('validation_results.json',dict(baseline_vectors_replayed=sum(r['players'] for r in release_summary),baseline_fields_replayed=sum(r['baseline_fields_replayed'] for r in release_summary),original_baseline_copies_byte_identical=all(sha(O/f'2027_{role}s_v1_43_baseline.csv')==sha(pub/f'projections_2027_{role}s.csv') for role in TARGETS),role_guard_code_unchanged=True,source_files_unchanged=True,forecast_2026_errors_scored=False,models_fit_2026_targets=False,model_decision_freeze_unchanged_after_2026_history_read=True,production_files_changed=False,workload_changed=False,minor_or_park_or_international_coefficients_used=False,approved_numeric_changes=0,exploratory_changed_cells=len(differences),protected_source_files=len(watch)))
print(json.dumps(release_summary,indent=2));print(json.dumps(gates,indent=2))
