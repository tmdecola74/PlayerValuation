"""Independent anchored-vector/error checks. No refit or modified choice."""
import csv,json,hashlib,math,zipfile,html,shutil
from pathlib import Path
from collections import defaultdict,Counter
O=Path('outputs/2027_player_anchored_workload_validation');S=Path('outputs/2027_player_anchored_workload_registration')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
rows=read(O/'historical_workload_predictions.csv');models=json.loads((O/'frozen_historical_models.json').read_text());panel=json.loads((S/'historical_panel_unscored.json').read_text());features={(int(r['target_season']),r['role'],r['mlbam_id']):r for r in panel};ledger={(int(r['target_season']),r['role'],r['mlbam_id']):r for r in read(S/'shared_preorigin_freshness_ledger.csv')}
assert len({(r['season'],r['role'],r['mlbam_id']) for r in rows})==8917
recomputed=0;fallbackchecks=0;edited=0;feasible_fallbacks=[];errorbins=defaultdict(list)
for r in rows:
 year=int(r['season']);role=r['role'];pid=r['mlbam_id'];f=features[year,role,pid];e=models[r['season']]['roles'][role];metrics=['PA'] if role=='hitter' else ['IP','G','GS'];supported=r['supported']=='True';known=r['target_known']=='True'
 assert e['max_target_season']<year<=2025 and f['anchor_season']==year-1
 assert r['freshness']==ledger[year,role,pid]['shared_freshness'] and r['original_freshness']==ledger[year,role,pid]['original_freshness']
 if supported or r['fallback_reason'].startswith('INFEASIBLE_'):
  specific='|'.join((r['latest_state'],r['recent_state'],f['experience']));pool=specific if specific in e['nodes'] else r['latest_state'] if r['latest_state'] in e['nodes'] else 'GLOBAL';node=e['root'] if pool=='GLOBAL' else e['nodes'][pool]
  fields=['MLB_G','BATTING_G','STARTS','PA'] if role=='hitter' else ['G','GS','GR','START_OUTS','RELIEF_OUTS'];raw={m:162*(f['anchor_vector'][i]+node['mean_residual'][i]) for i,m in enumerate(fields)};v={m:max(x,0) for m,x in raw.items()}
  if role=='hitter':
   v['BATTING_G']=min(v['BATTING_G'],v['MLB_G']);v['STARTS']=min(v['STARTS'],v['BATTING_G']);bad=v['PA']>0 and v['BATTING_G']<=0
  else:
   v['G']=v['GS']+v['GR'];v['OUTS']=v['START_OUTS']+v['RELIEF_OUTS'];v['IP']=v['OUTS']/3;bad=(v['GS']<=0 and v['START_OUTS']>0) or (v['GR']<=0 and v['RELIEF_OUTS']>0)
  if supported:
   assert not bad and pool==r['pool_used'];assert json.loads(r['anchor_vector_json'])==f['anchor_vector']
   stored=json.loads(r['raw_workload_json']);assert all(math.isclose(raw[m],stored[m],abs_tol=1e-9) for m in fields)
   changed=any(abs(v[m]-raw[m])>1e-8 for m in fields);assert changed==(r['feasibility_changed']=='True');edited+=changed
   for metric in metrics:assert math.isclose(float(r['candidate_'+metric]),v[metric],abs_tol=1e-8,rel_tol=1e-10);recomputed+=1
  else:
   assert bad;feasible_fallbacks.append(dict(season=year,role=role,mlbam_id=pid,reason=r['fallback_reason'],pool=pool,raw_workload_json=json.dumps(raw),interpretation='Invalid raw opportunity combination; full baseline retained; not a forecast replacement'))
 if not supported:
  for metric in metrics:assert r['candidate_'+metric]==r['baseline_'+metric];fallbackchecks+=1
 if not known:continue
 for metric in metrics:
  if any(r.get(prefix+metric,'')=='' for prefix in ['actual_','baseline_','candidate_']):continue
  truth=float(r['actual_'+metric]);ee=(float(r['baseline_'+metric])-truth,float(r['candidate_'+metric])-truth)
  for scope in ['SUPPORTED' if supported else 'FALLBACK','FULL_COHORT']:errorbins[year,role,metric,scope].append((pid,*ee))
save('feasibility_fallback_trace.csv',feasible_fallbacks)
scorechecks=0
for r in read(O/'historical_scores.csv'):
 if r['cohort']!='ALL':continue
 rr=errorbins[int(r['season']),r['role'],r['metric'],r['pool']];idx=1 if r['method']=='weighted_actuals' else 2;ee=[x[idx] for x in rr]
 assert len(rr)==int(r['n']) and hashlib.sha256(json.dumps(sorted(x[0] for x in rr)).encode()).hexdigest()==r['membership_sha256']
 for metric,val in [('mse',sum(x*x for x in ee)/len(ee)),('mae',sum(abs(x) for x in ee)/len(ee)),('bias',sum(ee)/len(ee))]:assert math.isclose(val,float(r[metric]),abs_tol=1e-8,rel_tol=1e-10);scorechecks+=1
ratios=read(O/'paired_error_ratios.csv');gates=json.loads((O/'workload_decision.json').read_text());summary=json.loads((O/'validation_summary.json').read_text());extras=read(O/'extra_guard_results.csv');decisions=[]
for g in gates:
 role=g['role'];mean=g['core_guard']['mean_mse_ratio'];full=[float(r['MSE_ratio']) for r in ratios if r['role']==role and r['cohort']=='ALL' and r['pool']=='FULL_COHORT' and r['metric']==('PA' if role=='hitter' else 'IP')];active=next(r for r in extras if r['role']==role and r['cohort']=='RECENT_POSITIVE')
 decisions.append(dict(role=role,supported_mean_fold_MSE_change_pct=100*(mean-1),full_cohort_mean_fold_MSE_change_pct=100*(sum(full)/len(full)-1),recent_positive_mean_fold_MSE_change_pct=100*(float(active['mean_MSE_ratio'])-1),workload_guards_pass=g['workload_pass'],forecast_adopted=False,next_step='Separate coherent hitter-count and team-opportunity implementation/review' if g['workload_pass'] else 'Retain v1.43; failed subgroup protections remain binding',evidence='Development informed by prior errors; not fresh independent validation'))
save('decision_summary.csv',decisions)
assert next(g['workload_pass'] for g in gates if g['role']=='hitter') and not next(g['workload_pass'] for g in gates if g['role']=='pitcher')
assert len(feasible_fallbacks)==21 and edited==summary['feasibility_adjusted_supported_rows']==331
fallback=[dict(season=y,role=role,reason=reason,n=n) for (y,role,reason),n in sorted(Counter((r['season'],r['role'],r['fallback_reason']) for r in rows if r['supported']=='False').items())];save('fallback_summary.csv',fallback)
notes='''\n\nFINAL DEVELOPMENT REVIEW\nThe hitter workload candidate passes the registered core and additional workload safeguards: mean supported PA MSE falls31.47%, with9.50% improvement among recent-positive players. The shared known-zero subgroup is now supported under the pre-registered ledger; both arms use the same grouping and the thresholds remain unchanged. This does not relabel the previous failed experiment. The result supports a separate hitter complete-count/team-opportunity build, not immediate forecast adoption.\n\nPitcher mean supported IP MSE falls2.88%, but the low-history guard fails (mean MSE worsens6.30%) and the swing-role guard fails (+9.11%). These safeguards remain binding. Do not adopt the pitcher method, weaken thresholds or tune the frozen model after these results.\n\nAll8917 player-seasons remain visible. There are8113 supported predictions and804 full-baseline fallbacks, including one unscored quarantined target. Of the fallbacks,21 are new infeasible component combinations detected by the registered rules; independent recalculation verifies those conditions.331 supported rows receive the predeclared nonnegative/coherence projection. Full-cohort known-target reporting includes all8916 scored records on paired identical memberships. No fallbacks are discarded to improve results.\n\nThe independent checker reconstructs raw anchors plus frozen mean residuals, reapplies the registered feasibility rules, verifies all fallback workload values, and recalculates ALL-cohort MSE/MAE/bias and membership hashes. Source code, data, baseline files and guard thresholds remain unchanged. No2026 target or new2027 candidate projection is included; Stewart and Misiorowski remain unscored illustrations.\n\nThese2023–2025 seasons informed the design. The fold construction is strictly earlier-only, but that does not turn this development test into fresh independent validation. Coherent fantasy counts, team budgets, player-level review and independent evidence remain unresolved steps before any adoption.\n'''
p=O/'READ_ME.txt';p.write_text(p.read_text(encoding='utf-8')+notes,encoding='utf-8')
p=O/'validation_report.html';page=p.read_text(encoding='utf-8');page=page.replace('<h2>Role decisions</h2>','<h2>Development result</h2><pre>'+html.escape(notes)+'</pre><h2>Role decisions</h2>');p.write_text(page,encoding='utf-8')
verification=json.loads((O/'verification_results.json').read_text());verification.update(independent_candidate_values_recomputed=recomputed,independent_fallback_metric_checks=fallbackchecks,independent_aggregate_error_checks=scorechecks,infeasible_fallbacks_independently_verified=len(feasible_fallbacks),feasibility_edits_independently_verified=edited,shared_ledger_verified_for_both_arms=True,independent_validation_claimed=False,forecast_adoption=False)
dump('verification_results.json',verification)
pre=json.loads((O/'pre_scoring_freeze.json').read_text());assert all(sha(O/n)==h for n,h in pre['files'].items());watch=json.loads((O/'source_manifest.json').read_text());assert all(sha(p)==h for p,h in watch.items())
shutil.copy2(__file__,O/'verify_player_anchored_validation.py');dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(decisions,indent=2));print(json.dumps(verification,indent=2));print('ZIP bytes',Path(str(O)+'.zip').stat().st_size)
