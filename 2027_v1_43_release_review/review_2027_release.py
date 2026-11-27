"""Read-only release review; diagnostics do not select or change forecasts."""
import csv,json,math,hashlib,sys,html,zipfile,itertools,shutil
from pathlib import Path
from collections import defaultdict,Counter
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
from project_2027_v1_31 import project,FIELDS,LARGE
import projection_phase_v1_42 as phase
O=Path('outputs/2027_v1_43_release_review');O.mkdir(exist_ok=True)
manifest={}
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def track(p):
 p=Path(p);manifest[str(p.resolve())]=sha(p);return p
def read(p):
 with track(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load(p):return json.loads(track(p).read_text(encoding='utf-8-sig'))
def dump(n,x):(O/n).write_text(json.dumps(x,indent=2),encoding='utf-8')
def save(n,rows):
 if not rows:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
def num(x):return None if x in ('',None) else float(x)
contract=dict(purpose='Descriptive release review only; no changes to projections, adoption guards or model selection',comparison='Published 2026 v1.43 (2022–2025) versus working 2027 v1.43 (2023–2026)',material_thresholds=LARGE,triage='P1: component failure, or stale history with >=200 PA/60 IP; P2: material delta, sparse/role/injury/international/rehab/large recent workload divergence; P3: remaining exceptions. Rank within tier by normalized material delta, then forecast exposure. These are review priorities, not adoption criteria.',sparse='Fewer than two positive MLB seasons or <200 MLB AB/<300 MLB outs in 2023–2026',stale='No positive 2026 MLB exposure; missing is not zero',rehab='Recorded rehab transactions and affiliate/year overlaps are evidence only; short annual MiLB stints are candidates, not proven rehab samples.',injury_roster='Existing dated/undated evidence only; no claim of current status or future opportunity',count_decomposition='Exact symmetric Shapley decomposition; hit components use PA x AB/PA x component/AB, other counts PA or decimal IP x count/exposure; this is an algebraic attribution, not causal talent inference.',history_attribution='Exact changes in weighted seasonal exposure contributions, including missing-versus-zero handling; season labels never used as 2026 forecast errors',selection_through=2025,statcast='Rejected GB/LD/FB challenger inactive',minor_park_international='No new translation or playing-time substitution',production_changed=False)
dump('review_contract.json',contract)
old={};new={};missing=[];checks=[];decomp=[];allrows=[];exceptions=[];history=[];worktrace=[];skilltrace=[]
for role in FIELDS:
 old[role]={r['mlbam_id']:r for r in read(Path('outputs/published_2026_after_workload_test')/f'2026_{role}_projections_v1_43.csv')}
 new[role]={r['mlbam_id']:r for r in read(Path('outputs/2027_statcast_strengthened_validation')/f'2027_{role}s_working_v1_43.csv')}
 assert len(old[role])==(1052 if role=='hitter' else 1512) and len(new[role])==(1024 if role=='hitter' else 1487)
 # Bind snapshots to their published originals rather than compare two arbitrary exports.
 saved=read(R/'outputs/skill_regressed_release_v1_43/frozen_2026_forecasts.csv') if role=='hitter' else saved
 bank26={r['mlbam_id']:r for r in saved if r['player_type']==role}
 pub27={r['mlbam_id']:r for r in read(R/'outputs/skill_regressed_release_v1_43'/f'projections_2027_{role}s.csv')}
 assert old[role].keys()==bank26.keys() and new[role].keys()==pub27.keys()
 for pid,r in old[role].items():assert all(num(r.get(m))==num(bank26[pid].get('release__'+m)) for m in FIELDS[role])
 for pid,r in new[role].items():assert all(num(r.get(m))==num(pub27[pid].get(m)) for m in FIELDS[role])
lab=R/'outputs/training_labels_v1_0';ov=R/'outputs/participation_label_overlay_v1_27';hp=R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv'
for p in [lab/'training_labels.parquet',lab/'holdout_labels.parquet',ov/'report.json',ov/'participation_label_overlay.csv',hp,R/'project_2027_v1_31.py',R/'projection_phase_v1_42.py']:track(p)
a,_=apply_overlay(ov,labels(lab/'training_labels.parquet'),lab/'training_labels.parquet',hp,manifest)
a.update(labels(lab/'holdout_labels.parquet',2026))
for r in read(R/'outputs/pitcher_evaluation_v1_29/evaluation_label_overlay_2026.csv'):
 for m,c in [('G','evaluation_g'),('OUTS','evaluation_outs')]:a[2026,'pitcher',r['mlbam_id'],m]=float(r[c])
prior=load(R/'outputs/projection_phase_v1_42/frozen_choices.json')['skill_population']
namebank=defaultdict(set)
for source in [old,new]:
 for role,bank in source.items():
  for pid,r in bank.items():
   if r.get('name'):namebank[pid].add(r['name'])
inj=defaultdict(list);depth=defaultdict(list);trans=defaultdict(list);rehab=defaultdict(list);intl=defaultdict(list);minor=defaultdict(list)
for r in read('outputs/minor_history_2027_player_review/injury_snapshot_evidence.csv'):inj[r['MLBAMID']].append(r)
for r in read('outputs/minor_history_2027_player_review/depth_snapshot_evidence.csv'):depth[r['mlbam_id']].append(r)
for r in read('outputs/minor_history_2027_player_review/official_transaction_evidence.csv'):trans[r['mlbam_id']].append(r)
for r in read('outputs/minor_history_2027_player_review/verified_rehab_affiliate_year_overlaps.csv'):rehab[r['role'],r['mlbam_id']].append(r)
for r in read('outputs/2027_statcast_strengthened_validation/international_coverage_exceptions.csv'):intl[r['role'],r['mlbam_id']].append(r)
for role in FIELDS:
 for r in read(Path('outputs/minor_league_coverage_min0')/f'{role}s_stints_linkable.csv'):
  if 2023<=int(r['Season'])<=2026:minor[role,r['MLBAMID']].append(r)
p1=read('outputs/minor_history_2027_research/P1_corroborated_identity_and_status.csv')
returners=read('outputs/minor_history_2027_research/priority_returner_status_review.csv')
for x in returners:intl[x['verified_primary_role'],x['mlbam_id']].append(x)
def get(y,role,pid,m):return a.get((y,role,pid,m))
def exposure(y,role,pid):
 v=get(y,role,pid,'PA' if role=='hitter' else 'OUTS');return v if v is None or role=='hitter' else v/3
def roleof(g,gs):return 'UNKNOWN' if not g or gs is None else 'STARTER' if gs/g>=.5 else 'RELIEVER' if gs==0 else 'SWING'
def shapley(oldf,newf):
 n=len(oldf);ans=[0.]*n
 for perm in itertools.permutations(range(n)):
  vals=list(oldf);before=math.prod(vals)
  for i in perm:
   vals[i]=newf[i];after=math.prod(vals);ans[i]+=(after-before)/math.factorial(n);before=after
 return ans
def check(role,pid,test,actual,expected=None,passed=None,detail=''):
 ok=passed if passed is not None else (actual is None and expected is None or actual is not None and expected is not None and math.isclose(actual,expected,rel_tol=1e-8,abs_tol=1e-8))
 checks.append(dict(role=role,mlbam_id=pid,test=test,observed=actual,expected=expected,status='PASS' if ok else 'FAIL',detail=detail));return ok
def validate(role,pid,r):
 v={m:num(r.get(m)) for m in FIELDS[role]};fail=[]
 for m,x in v.items():
  if x is None:missing.append(dict(role=role,mlbam_id=pid,metric=m,issue='MISSING_FORECAST_COMPONENT'))
  elif not check(role,pid,'NONNEGATIVE_FINITE_'+m,x,passed=math.isfinite(x) and x>=0):fail.append(m)
 def eq(m,deps,fn):
  if all(v.get(d) is not None for d in deps):
   if not check(role,pid,m,v.get(m),fn()):fail.append(m)
 def bound(test,cond):
  if not check(role,pid,test,None,passed=cond):fail.append(test)
 if role=='hitter':
  eq('H',['1B','2B','3B','HR'],lambda:sum(v[m] for m in ['1B','2B','3B','HR']))
  eq('AVG',['H','AB'],lambda:v['H']/v['AB'] if v['AB'] else None)
  eq('OBP',['H','BB','HBP','AB','SF'],lambda:(v['H']+v['BB']+v['HBP'])/(v['AB']+v['BB']+v['HBP']+v['SF']) if sum(v[m] for m in ['AB','BB','HBP','SF']) else None)
  eq('SLG',['1B','2B','3B','HR','AB'],lambda:sum(i*v[m] for i,m in enumerate(['1B','2B','3B','HR'],1))/v['AB'] if v['AB'] else None)
  eq('OPS',['OBP','SLG'],lambda:v['OBP']+v['SLG'])
  if all(v[m] is not None for m in ['H','AB']):bound('H_LE_AB',v['H']<=v['AB']+1e-8)
  if all(v[m] is not None for m in ['PA','AB','BB','HBP','SF','SH']):
   parts=sum(v[m] for m in ['AB','BB','HBP','SF','SH']);bound('PA_COMPONENT_BOUND',parts<=v['PA']+1e-8)
   # A smaller sum is permitted by the original model; expose rather than assert equality.
   if abs(v['PA']-parts)>1e-8:missing.append(dict(role=role,mlbam_id=pid,metric='PA_COMPONENT_RESIDUAL',issue='UNALLOCATED_PA_DIAGNOSTIC',value=v['PA']-parts))
 else:
  eq('OUTS',['IP'],lambda:v['IP']*3)
  eq('ERA',['ER','IP'],lambda:9*v['ER']/v['IP'] if v['IP'] else None)
  eq('WHIP',['H','BB','IP'],lambda:(v['H']+v['BB'])/v['IP'] if v['IP'] else None)
  eq('SV_plus_HLD',['SV','HLD'],lambda:v['SV']+v['HLD'])
  for test,needed,fn in [('GS_LE_G',['GS','G'],lambda:v['GS']<=v['G']+1e-8),('QS_LE_GS',['QS','GS'],lambda:v['QS']<=v['GS']+1e-8),('QS_LE_IP_DIV6',['QS','IP'],lambda:v['QS']<=v['IP']/6+1e-8),('HR_LE_H',['HR','H'],lambda:v['HR']<=v['H']+1e-8)]:
   if all(v[m] is not None for m in needed):bound(test,fn())
 return fail
for role in FIELDS:
 for pid,r in new[role].items():
  name=r['name'] or old[role].get(pid,{}).get('name','') or (next(iter(namebank[pid])) if len(namebank[pid])==1 else '');b=old[role].get(pid);e='PA' if role=='hitter' else 'IP';v={m:num(r.get(m)) for m in FIELDS[role]};flags=[]
  replay,supported,trace=phase.skill_candidate(project(a,role,pid,2027),a,role,pid,2027,prior)
  assert all(num(r.get(m))==replay.get(m) or num(r.get(m)) is not None and replay.get(m) is not None and math.isclose(num(r[m]),replay[m],rel_tol=1e-12,abs_tol=1e-12) for m in FIELDS[role])
  for t in trace:skilltrace.append(dict(role=role,mlbam_id=pid,name=name,**t))
  fail=validate(role,pid,r)
  if fail:flags.append('CONSISTENCY_FAILURE')
  absent=[m for m in FIELDS[role] if v[m] is None]
  if absent:flags.append('MISSING_FORECAST_COMPONENT')
  secondary_zero_ab=role=='hitter' and v['AB']==0 and pid in new['pitcher']
  if secondary_zero_ab:flags.append('SECONDARY_ROLE_ZERO_AB_UNDEFINED_RATES')
  pa_residual=v['PA']-sum(v[m] for m in ['AB','BB','HBP','SF','SH']) if role=='hitter' and all(v[m] is not None for m in ['PA','AB','BB','HBP','SF','SH']) else None
  if pa_residual is not None and abs(pa_residual)>1e-8:flags.append('UNALLOCATED_PA_COMPONENT_RESIDUAL')
  pos=[y for y in range(2023,2027) if (exposure(y,role,pid) or 0)>0];last=max(pos) if pos else None;recent=exposure(2026,role,pid)
  raw=sum(get(y,role,pid,'AB' if role=='hitter' else 'OUTS') or 0 for y in range(2023,2027))
  if len(pos)<2 or raw<(200 if role=='hitter' else 300):flags.append('SPARSE_MLB_HISTORY')
  if not recent:flags.append('NO_POSITIVE_2026_MLB_HISTORY')
  if not r['name']:flags.append('UNRESOLVED_ORIGINAL_DISPLAY_NAME')
  if not supported:flags.append('SKILL_GROUP_BASELINE_FALLBACK')
  if intl[role,pid]:flags.append('INTERNATIONAL_HISTORY_UNTRANSLATED')
  if inj[pid]:flags.append('INJURY_SNAPSHOT_REQUIRES_REVIEW')
  if rehab[role,pid]:flags.append('REHAB_AFFILIATE_YEAR_OVERLAP')
  minors=minor[role,pid];short=[m for m in minors if 0<float(m.get('PA' if role=='hitter' else 'OUTS') or 0)<(50 if role=='hitter' else 60)]
  if short and raw>=(400 if role=='hitter' else 300):flags.append('SHORT_MINOR_STINT_POSSIBLE_REHAB')
  if minors:flags.append('MINOR_HISTORY_NOT_IN_WORKING_BASELINE')
  if recent and v[e] is not None and abs(v[e]-recent)>=(100 if role=='hitter' else 35) and (recent>=(200 if role=='hitter' else 60) or v[e]>=(200 if role=='hitter' else 60)):flags.append('FORECAST_VS_LATEST_WORKLOAD_DIVERGENCE')
  roles=[]
  for y in range(2022,2027):
   exp=exposure(y,role,pid);g=get(y,role,pid,'G');gs=get(y,role,pid,'GS');rr=roleof(g,gs) if role=='pitcher' else 'HITTER';roles.append((y,rr))
   history.append(dict(role=role,mlbam_id=pid,name=name,season=y,exposure=exp,exposure_unit=e,observation='UNKNOWN' if exp is None else 'KNOWN_ZERO' if exp==0 else 'POSITIVE',G=g,GS=gs,observed_role=rr,**{m:get(y,role,pid,m) for m in (['AB','H','HR','BB','R','RBI','SB'] if role=='hitter' else ['H','ER','SO','BB','HR','QS'])}))
  knownroles=[(y,rr) for y,rr in roles if y>=2023 and rr not in ['UNKNOWN','HITTER'] and (exposure(y,role,pid) or 0)>=20]
  if len({rr for _,rr in knownroles})>1:flags.append('MLB_ROLE_CHANGE')
  minorroles={roleof(float(m.get('G') or 0),num(m.get('GS'))) for m in minors if role=='pitcher' and float(m.get('OUTS') or 0)>=60}
  if role=='pitcher' and knownroles and any(m not in ('UNKNOWN',knownroles[-1][1]) for m in minorroles):flags.append('MINOR_MLB_ROLE_DIFFERENCE')
  tx=trans[pid];retired=[t for t in tx if 'retired' in t['description'].lower()]
  if retired:flags.append('SAVED_RETIREMENT_TRANSACTION_REQUIRES_STATUS_REVIEW')
  bvals={m:num(b.get(m)) for m in FIELDS[role]} if b else {};deltas={m:v[m]-bvals[m] if b and v[m] is not None and bvals[m] is not None else None for m in FIELDS[role]}
  normalized={m:abs(deltas[m])/th for m,th in LARGE.items() if deltas.get(m) is not None};score=max(normalized.values(),default=0);material=[m for m,z in normalized.items() if z>=1]
  if material:flags.append('MATERIAL_YEAR_OVER_YEAR_CHANGE')
  if not b:flags.append('NEW_TO_FORECAST_POOL')
  for metric in (['H','1B','2B','3B','HR','R','RBI','SB','BB','HBP','SF','SH','AB'] if role=='hitter' else ['SO','ER','H','BB','HR','W','SV','HLD','QS','GS','G']):
   if not b or any(x in (None,0) for x in [bvals.get(e),v.get(e)]) or bvals.get(metric) is None or v.get(metric) is None:continue
   E0,E1=bvals[e],v[e];n0,n1=bvals[metric],v[metric]
   if role=='hitter' and metric in ['H','1B','2B','3B','HR'] and bvals['AB'] and v['AB']:
    parts=shapley([E0,bvals['AB']/E0,n0/bvals['AB']],[E1,v['AB']/E1,n1/v['AB']]);op,share,rate=parts;den='AB';q0=n0/bvals['AB'];q1=n1/v['AB']
   else:
    op,rate=shapley([E0,n0/E0],[E1,n1/E1]);share=0;den=e;q0=n0/E0;q1=n1/E1
   assert math.isclose(op+share+rate,n1-n0,abs_tol=1e-8,rel_tol=1e-8)
   decomp.append(dict(role=role,mlbam_id=pid,name=name,metric=metric,projection_2026=n0,projection_2027=n1,delta=n1-n0,playing_time_effect=op,AB_per_PA_effect=share,component_rate_effect=rate,rate_denominator=den,rate_2026=q0,rate_2027=q1,reconciliation_residual=(n1-n0)-op-share-rate))
  # Full, exact year-by-year arithmetic of the accepted workload; missing years are omitted, confirmed zero years retained.
  contrib={}
  for target in [2026,2027]:
   pairs=[(y,w,exposure(y,role,pid)) for y,w in zip(range(target-4,target),[1,2,3,4])];known=[(y,w,x) for y,w,x in pairs if x is not None];den=sum(w for y,w,x in known)
   contrib[target]={y:w*x/den for y,w,x in known};expected=sum(contrib[target].values())
   out=bvals.get(e) if target==2026 else v[e]
   if out is not None:assert math.isclose(out,expected,rel_tol=1e-8,abs_tol=1e-8),(role,pid,target,out,expected)
  for y in range(2022,2027):worktrace.append(dict(role=role,mlbam_id=pid,name=name,source_season=y,actual_exposure=exposure(y,role,pid),contribution_to_2026=contrib[2026].get(y,0),contribution_to_2027=contrib[2027].get(y,0),contribution_delta=contrib[2027].get(y,0)-contrib[2026].get(y,0),exposure_unit=e))
  tier=1 if fail or (absent and not secondary_zero_ab) or (not recent and v[e]>=(200 if role=='hitter' else 60)) else 2 if material or any(f not in ['MINOR_HISTORY_NOT_IN_WORKING_BASELINE','NEW_TO_FORECAST_POOL'] for f in flags) else 3
  biggest=max(normalized,key=normalized.get) if normalized else ''
  note=f"{e}: {bvals.get(e,0):.1f} to {v[e]:.1f}. " if b else f"New 2027 forecast, {v[e]:.1f} {e}. "
  if b:
   wt=sorted([(abs(contrib[2027].get(y,0)-contrib[2026].get(y,0)),y,contrib[2027].get(y,0)-contrib[2026].get(y,0)) for y in range(2022,2027)],reverse=True)[:2]
   note+='Largest workload contributions: '+', '.join(f'{y}: {d:+.1f} {e}' for _,y,d in wt)+'. '
  if biggest:note+=f"Largest normalized change: {biggest} {deltas[biggest]:+.3f}. "
  primary='HR' if role=='hitter' else 'SO'
  part=next((d for d in reversed(decomp) if d['role']==role and d['mlbam_id']==pid and d['metric']==primary),None)
  if part:note+=f"{primary} change {part['delta']:+.2f}: PA/IP contribution {part['playing_time_effect']:+.2f}, AB-share contribution {part['AB_per_PA_effect']:+.2f}, component-rate contribution {part['component_rate_effect']:+.2f}. "
  if secondary_zero_ab:note+='This is the batting-side record of a projected pitcher: zero AB makes batting rates undefined. Do not invent rates or treat it as a complete hitter forecast. '
  if pa_residual is not None and abs(pa_residual)>1e-8:note+=f'{pa_residual:.3f} projected PA is unallocated among AB/BB/HBP/SF/SH; permitted by the original bound, explicitly exposed rather than imputed. '
  if not recent:note+=f'No positive 2026 MLB {e}; weighted older history remains, not a verified 2027 opportunity. '
  if intl[role,pid]:note+='Overseas performance has no validated translation in this forecast. '
  if len(pos)<2:note+=f'Only {len(pos)} positive MLB seasons in the four-year window. '
  if len({rr for _,rr in knownroles})>1:note+='Observed MLB role sequence: '+', '.join(f'{y} {rr}' for y,rr in knownroles)+'. '
  if inj[pid]:note+='Saved injury report: '+' | '.join(x.get('Injury / Surgery','')+'; '+x.get('Latest Update','') for x in inj[pid])+' (capture date uncertified; no current status inferred). '
  if retired:note+='Saved transaction records retirement; any later return has not been checked in this review. '
  if rehab[role,pid]:note+='Recorded rehab/affiliate-year overlap does not isolate annual rehab statistics. '
  if minors:note+='Minor data exists but is not an input to the working baseline. '
  row=dict(role=role,mlbam_id=pid,name=name,name_annotation='EXACT_SAME_MLBAM_NAME_FROM_PUBLISHED_FORECASTS' if name and not r['name'] else 'ORIGINAL_2027_NAME' if r['name'] else 'UNRESOLVED',priority=f'P{tier}',review_score=score,largest_normalized_change_metric=biggest,material_metrics=';'.join(material),flags=';'.join(flags),positive_MLB_seasons=len(pos),last_positive_MLB_season=last,latest_2026_exposure=recent,latest_2026_observation='UNKNOWN' if recent is None else 'KNOWN_ZERO' if recent==0 else 'POSITIVE',raw_skill_exposure=raw,minor_stints=len(minors),injury_snapshot_rows=len(inj[pid]),rehab_overlap_rows=len(rehab[role,pid]),PA_component_residual=pa_residual,known_role_sequence=';'.join(f'{y}:{rr}' for y,rr in knownroles),explanation=note,review_action='Keep batting rates undefined; flag secondary-role record separately' if secondary_zero_ab else 'Resolve component failure before broad release' if fail or absent else 'Verify opportunity/status before draft valuation; retain numeric baseline' if not recent or intl[role,pid] or retired else 'Review flagged history and retain baseline unless a separately tested method passes guards',**{f'2026_{m}':bvals.get(m) for m in FIELDS[role]},**{f'2027_{m}':v[m] for m in FIELDS[role]},**{f'delta_{m}':deltas[m] for m in FIELDS[role]})
  allrows.append(row)
  if flags:exceptions.append(row)
 print('Reviewed',role,len(new[role]),flush=True)
ranked=sorted(exceptions,key=lambda r:(r['priority'],-r['review_score'],-r['2027_PA' if r['role']=='hitter' else '2027_IP'],int(r['mlbam_id'])))
for i,r in enumerate(ranked,1):r['rank']=i
save('ranked_exception_list.csv',ranked);save('all_player_review.csv',allrows);save('count_change_decomposition.csv',decomp);save('MLB_history_trace.csv',history);save('workload_contribution_trace.csv',worktrace);save('skill_shrinkage_trace_2027.csv',skilltrace);save('projection_consistency_checks.csv',checks);save('missing_components_and_PA_residuals.csv',missing)
save('largest_changes_all_exposures.csv',sorted(allrows,key=lambda r:-r['review_score']))
sub=[r for r in allrows if max(r.get('2026_PA' if r['role']=='hitter' else '2026_IP') or 0,r['2027_PA' if r['role']=='hitter' else '2027_IP'])>=(200 if r['role']=='hitter' else 60)]
save('largest_changes_substantial_exposure.csv',sorted(sub,key=lambda r:-r['review_score']))
save('forecast_pool_exits.csv',[dict(role=role,mlbam_id=pid,name=r['name'],reason='No positive MLB exposure remaining in 2023–2026 forecast window; no roster inference',old_exposure=r['PA' if role=='hitter' else 'IP']) for role in FIELDS for pid,r in old[role].items() if pid not in new[role]])
coverage=[]
for (role,pid),ss in minor.items():
 if (pid not in new[role]) and any(float(s.get('PA' if role=='hitter' else 'OUTS') or 0)>0 for s in ss):
  latest=max(int(s['Season']) for s in ss);latestss=[s for s in ss if int(s['Season'])==latest];coverage.append(dict(role=role,mlbam_id=pid,name=ss[0]['NameASCII'],gap='LINKED_MINOR_PLAYER_NO_MLB_BASELINE',latest_season=latest,levels=';'.join(sorted({s['Level'] for s in latestss})),latest_exposure=sum(float(s.get('PA' if role=='hitter' else 'OUTS') or 0) for s in latestss),exposure_unit='PA' if role=='hitter' else 'OUTS',future_opportunity='UNKNOWN_NOT_ZERO',action='Keep outside forecast; requires separately validated coverage method and opportunity evidence'))
for r in p1:coverage.append(dict(role=r['role'],mlbam_id=r['mlbam_id'],name=r['name'],gap='PRIORITY_INTERNATIONAL_UNVALIDATED',latest_season=2026,levels=r['league'],future_opportunity='UNKNOWN_NOT_ZERO',action='No synthetic forecast or minor coefficient; independent prior or transition evidence required',identity_status=r['identity_status'],snapshot_market_status=r['market_status'],snapshot_as_of=r['as_of'],source=r['status_source']))
coverage.sort(key=lambda r:(r['gap']!='PRIORITY_INTERNATIONAL_UNVALIDATED',-int(r['latest_season']),not any(level in r['levels'].split(';') for level in ['AAA','AA']),-float(r.get('latest_exposure') or 0)))
for i,r in enumerate(coverage,1):r.update(coverage_review_rank=i,ranking_basis='International priority, latest source year, upper-minor presence, source exposure; not arrival probability')
save('coverage_gap_list.csv',coverage)
save('international_exception_list.csv',[dict(role=role,mlbam_id=pid,name=next((r.get('name','') for r in rr if r.get('name')),''),in_working_forecast=pid in new[role],issues=';'.join(sorted({r.get('issues','') or r.get('status','') for r in rr})),action='Unvalidated overseas history; baseline retained where present; no opportunity inferred') for (role,pid),rr in intl.items()])
for n,rr in [('injury_snapshot_evidence.csv',[r for ss in inj.values() for r in ss]),('depth_snapshot_evidence.csv',[r for ss in depth.values() for r in ss]),('saved_transaction_evidence.csv',[r for ss in trans.values() for r in ss]),('rehab_overlap_evidence.csv',[r for ss in rehab.values() for r in ss]),('P1_identity_status_snapshot.csv',p1),('returner_status_snapshot.csv',returners)]:save(n,rr)
failures=[r for r in checks if r['status']=='FAIL'];assert not failures
assert all(sha(p)==h for p,h in manifest.items())
summary=dict(working_forecast='2027 v1.43 unchanged',comparison_2026='Published 2026 v1.43 unchanged 2022–2025 history',players_reviewed=len(allrows),by_role=dict(Counter(r['role'] for r in allrows)),matched_by_role={role:len(new[role].keys()&old[role].keys()) for role in FIELDS},new_by_role={role:len(new[role].keys()-old[role].keys()) for role in FIELDS},exited_by_role={role:len(old[role].keys()-new[role].keys()) for role in FIELDS},exceptions=len(ranked),priority_counts=dict(Counter(r['priority'] for r in ranked)),flag_counts=dict(Counter(f for r in allrows for f in r['flags'].split(';') if f)),consistency_checks=len(checks),consistency_failures=len(failures),missing_forecast_components=sum(r['issue']=='MISSING_FORECAST_COMPONENT' for r in missing),PA_residuals=sum(r['issue']=='UNALLOCATED_PA_DIAGNOSTIC' for r in missing),count_changes_reconciled=len(decomp),coverage_only_minor_players=sum(r['gap']=='LINKED_MINOR_PLAYER_NO_MLB_BASELINE' for r in coverage),P1_international_coverage_only=len(p1),input_files_verified=len(manifest),forecast_values_changed=False,model_selection_performed=False,**{'2026_forecast_errors_used':False},release_recommendation='Retain v1.43 as research baseline with visible exceptions. Do not certify this as a roster-ready or complete draft forecast; refresh opportunity/status evidence and resolve missing components before such a release. No Statcast, workload, minor, park or international replacement adopted.')
dump('review_summary.json',summary);dump('source_manifest.json',manifest)
dump('separate_experiment_specifications.json',dict(status='SPECIFIED_NOT_RUN',not_authorized_by_this_review='No formula, threshold, production forecast or player-specific override changed',experiments=[dict(name='MLB opportunity and stale history coverage',trigger='Positive PA/IP survives from older MLB seasons with no positive latest season, or documented non-MLB/retirement evidence',candidate='Externally timestamped availability/roster evidence kept separate from skill; define missingness, returner, injury and nonappearance rules before testing',validation='Earlier-only rolling origins through 2025; retain existing adoption guards, >=3 supported folds and common player samples; 2026 forecast errors excluded; no handpicked-player fitting',rejected_workload_model='Remains inactive; this is not permission to reactivate it'),dict(name='Minor-history coverage and rehab robustness',trigger='Minor-only prospects lack forecasts and MLB players have available but inactive minor history',candidate='Separately registered complete skill-plus-opportunity approach, with documented rehab, role and sample policies; do not merge previously reviewed minor coefficients automatically',validation='Earlier-only common-cohort complete-projection evaluation under unchanged guards, followed by player review'),dict(name='International coverage',trigger='Corroborated identity does not imply validated MLB translation or workload',candidate='Independently justified league/component priors or more transition evidence; explicit uncertainty; no minor coefficient substitution',validation='No adoption until independently specified evidence supports eligible earlier-only tests')]))
def cell(x):
 if x is None:return '—'
 if isinstance(x,float):return f'{x:,.3f}'
 return html.escape(str(x))
def table(rows,cols):return '<table><thead><tr>'+''.join('<th>'+html.escape(c.replace('_',' '))+'</th>' for c in cols)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+cell(r.get(c))+'</td>' for c in cols)+'</tr>' for r in rows)+'</tbody></table>'
top=sorted(sub,key=lambda r:-r['review_score'])[:30]
sections=[]
for role in FIELDS:
 ss=sorted([r for r in sub if r['role']==role],key=lambda r:-r['review_score'])[:15]
 cols=['name','mlbam_id']+(['2026_PA','2027_PA','delta_HR','delta_AVG','delta_OPS'] if role=='hitter' else ['2026_IP','2027_IP','delta_SO','delta_ERA','delta_WHIP'])+['explanation']
 sections.append('<h2>Largest '+role+' changes with substantial exposure</h2>'+table(ss,cols))
text='''2027 v1.43 PLAYER RELEASE REVIEW\n\nRECOMMENDATION\n'''+summary['release_recommendation']+'\n\n'+json.dumps(summary,indent=2)+'''\n\nMETHOD AND LIMITATIONS\nThe published 2026 comparison is the actual saved 2022–2025 four-season v1.43 file, not the pending three-season rebuild and not an archived preseason release. The 2027 forecast uses 2023–2026 player history. The entire working baseline was independently replayed; original forecast files were not edited. No 2026 forecast error was scored, and no new adoption decision was fitted from this review.\n\nCount differences are exactly separated into projected PA/IP, AB share (hit components only), and component rates. Rate changes reflect weighted history, regression and exposure composition; they do not prove a change in underlying talent. Count units are fractional expectations. IP is decimal innings, not baseball .1/.2 notation.\n\nWorkload traces show each source-year contribution, including the 2022 exit, the 2026 entry and reweighting of retained years. Unknown exposure is omitted by the existing model; a certified zero is retained. History and shrinkage traces explain the model mechanically, not a probability of playing.\n\nSaved injury/depth snapshots have uncertified capture dates; saved transactions cover only previously reviewed players. Their absence never means healthy, active or guaranteed opportunity. Rehab overlaps are affiliate/year evidence, not isolated rehab counts. No current roster or injury status has been asserted. International snapshots retain their evidence dates; no current market claims are made.\n\nMinor data counts cover the existing exactly linked intake only, not every prospect or every unlinked source player. Minor and overseas histories remain inactive in this baseline; coverage lists are not automatic draft candidates. Four P1 identities are carried from the later corroborated review, superseding earlier unresolved queues.\n\nRANKING\nPriority is descriptive review urgency, then largest absolute delta divided by existing material-review thresholds. Not a talent ranking or model confidence score. Full lists preserve low-volume exceptions; substantial lists use >=200 PA or >=60 IP in either projection. Rate deltas for tiny denominators should not be interpreted as draft impact. Existing guards and coefficients are unchanged.\n\n'''
for r in ranked[:40]:text+=f"{r['rank']}. {r['priority']} {r['role']} {r['name'] or r['mlbam_id']}: {r['explanation']} Flags: {r['flags']}\n\n"
(O/'REVIEW_REPORT.txt').write_text(text,encoding='utf-8')
page='''<!doctype html><html lang="en"><meta charset="utf-8"><title>2027 projection release review</title><style>body{font:16px/1.55 system-ui;margin:40px auto;max-width:1500px;padding:0 24px;color:#182b3a;background:#f7fafc}h1,h2{color:#153d55}table{border-collapse:collapse;width:100%;background:white;font-size:13px;margin-bottom:28px}td,th{border:1px solid #d4dfe6;padding:9px;text-align:left;vertical-align:top}th{background:#e4eef5;position:sticky;top:0}.lead{background:#e5f0ed;padding:22px;border-left:6px solid #397d68}a{color:#155c87}pre{white-space:pre-wrap}</style><h1>2027 v1.43: player-level release review</h1><p class="lead">'''+html.escape(summary['release_recommendation'])+'''</p><p>All 2,511 working forecasts were reviewed and independently replayed. Numeric forecasts and adoption guards remain unchanged. This compares the published four-season 2026 and 2027 baselines. No 2026 forecast-error decisions or Statcast changes.</p>'''+table([dict(measure=k,value=v) for k,v in summary.items() if not isinstance(v,dict)],['measure','value'])+'''<h2>How to read the changes</h2><p>PA/IP changes reflect the accepted weighted history. Counting-stat changes are separated exactly into playing time, AB share where relevant, and component rates. A rate change is an arithmetic explanation, not proof of a talent change. Injury and roster snapshots are historical evidence with dates/limitations, not current status certification.</p><p><a href="ranked_exception_list.csv">Full ranked exception list</a> · <a href="count_change_decomposition.csv">Count decomposition</a> · <a href="workload_contribution_trace.csv">Workload sources</a> · <a href="MLB_history_trace.csv">MLB history</a> · <a href="skill_shrinkage_trace_2027.csv">Skill regression trace</a> · <a href="coverage_gap_list.csv">Missing forecast coverage</a> · <a href="projection_consistency_checks.csv">Consistency checks</a></p>'''+''.join(sections)+'<h2>Priority exceptions</h2>'+table(ranked[:60],['rank','priority','role','name','flags','explanation','review_action'])+'<h2>Separate experiments specified, not run</h2><p>Opportunity/stale-history treatment, minor-history and rehab robustness, and international translation evidence are documented separately. Any candidate must pass the existing earlier-only validation guards; no individual exception has changed a forecast.</p><h2>Full notes</h2><pre>'+html.escape(text.split('METHOD AND LIMITATIONS\n',1)[1].split('\n\n1.',1)[0])+'</pre></html>'
(O/'comparison_report.html').write_text(page,encoding='utf-8')
(O/'READ_ME.txt').write_text('Open comparison_report.html for recommendation and summaries. ranked_exception_list.csv contains every flagged working player; all_player_review.csv also includes unflagged players. Coverage gaps and forecast pool exits are separate so absent forecasts are not confused with zero projections. All source paths and hashes are in source_manifest.json. This package contains review outputs only; no forecast was modified. See REVIEW_REPORT.txt for scope and evidence limitations.',encoding='utf-8')
shutil.copy2(__file__,O/'review_2027_release.py')
dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(summary,indent=2))


