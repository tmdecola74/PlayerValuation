"""Independent calculations from frozen outputs; never refit or change a choice."""
import csv,json,hashlib,math,zipfile,html,shutil
from pathlib import Path
from collections import defaultdict,Counter
O=Path('outputs/2027_usage_transition_validation')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
preds=read(O/'historical_workload_predictions.csv');models=json.loads((O/'frozen_historical_models.json').read_text());scores=read(O/'historical_scores.csv');summary=json.loads((O/'validation_summary.json').read_text());gates=json.loads((O/'workload_decision.json').read_text())
assert len({(r['season'],r['role'],r['mlbam_id']) for r in preds})==len(preds)
recalculated=0;fallback_metrics=0;errors=defaultdict(list)
for r in preds:
 year=int(r['season']);role=r['role'];supported=r['supported']=='True';known=r['target_known']=='True';fields=['PA'] if role=='hitter' else ['IP','G','GS']
 entry=models[r['season']]['roles'][role];assert entry['max_target_season']<year<=2025
 if supported:
  node=entry['root'] if r['pool_used']=='GLOBAL' else entry['nodes'][r['pool_used']];q=node['probabilities'];assert math.isclose(sum(q.values()),1,abs_tol=1e-12)
  names=['MLB_G','BATTING_G','STARTS','PA'] if role=='hitter' else ['G','GS','GR','START_OUTS','RELIEF_OUTS']
  vv={m:162*sum(q[s]*node['means'][s][i] for s in q) for i,m in enumerate(names)}
  if role=='pitcher':vv['IP']=(vv['START_OUTS']+vv['RELIEF_OUTS'])/3
  for m in fields:assert math.isclose(float(r['candidate_'+m]),vv[m],abs_tol=1e-8,rel_tol=1e-10);recalculated+=1
 else:
  for m in fields:assert r['candidate_'+m]==r['baseline_'+m];fallback_metrics+=1
 if not known:continue
 for metric in fields:
  if any(r.get(p+metric,'')=='' for p in ['actual_','baseline_','candidate_']):continue
  actual=float(r['actual_'+metric]);e=(float(r['baseline_'+metric])-actual,float(r['candidate_'+metric])-actual)
  for pool in ['SUPPORTED' if supported else 'FALLBACK','FULL_COHORT']:errors[year,role,metric,pool].append((r['mlbam_id'],*e))
score_checks=0
for r in scores:
 if r['cohort']!='ALL':continue
 rr=errors[int(r['season']),r['role'],r['metric'],r['pool']];i=1 if r['method']=='weighted_actuals' else 2;ee=[row[i] for row in rr]
 assert len(rr)==int(r['n']);assert hashlib.sha256(json.dumps(sorted(row[0] for row in rr)).encode()).hexdigest()==r['membership_sha256']
 for key,value in [('mse',sum(e*e for e in ee)/len(ee)),('mae',sum(abs(e) for e in ee)/len(ee)),('bias',sum(ee)/len(ee))]:assert math.isclose(value,float(r[key]),abs_tol=1e-8,rel_tol=1e-10);score_checks+=1
assert sum(r['target_known']=='False' for r in preds)==1
assert all(not g['workload_pass'] and not g['adoptable'] for g in gates)
verification=json.loads((O/'verification_results.json').read_text());verification.update(independent_workload_values_recomputed=recalculated,independent_fallback_metric_checks=fallback_metrics,independent_aggregate_error_checks=score_checks,independent_training_cutoff_checks=True,conditional_complete_count_build_triggered=False)
dump('verification_results.json',verification)
fallback_summary=[dict(season=y,role=role,reason=reason,rows=n) for (y,role,reason),n in sorted(Counter((r['season'],r['role'],r['fallback_reason']) for r in preds if r['supported']=='False').items())];save('fallback_summary.csv',fallback_summary)
ratios=read(O/'paired_error_ratios.csv');decision=[]
for g in gates:
 role=g['role'];ratio=g['core_guard']['mean_mse_ratio'];recent=next(r for r in read(O/'extra_guard_results.csv') if r['role']==role and r['cohort']=='RECENT_POSITIVE')
 full=[float(r['MSE_ratio']) for r in ratios if r['role']==role and r['pool']=='FULL_COHORT' and r['cohort']=='ALL' and r['metric']==('PA' if role=='hitter' else 'IP')]
 decision.append(dict(role=role,supported_mean_MSE_change_pct=(ratio-1)*100,full_cohort_mean_MSE_change_pct=(sum(full)/len(full)-1)*100,recent_positive_mean_MSE_change_pct=(float(recent['mean_MSE_ratio'])-1)*100,workload_adoption_guards_pass=False,recommendation='Retain unchanged v1.43; fixed candidate not adopted'))
save('decision_summary.csv',decision)
notes='''\n\nFINAL REVIEW\nNeither role cleared all workload protections, so the conditional complete-count/team-opportunity build is not triggered. The hitter average improvement does not justify adoption: among supported players with recent positive MLB exposure, mean PA MSE worsened25.46%. Its known-zero-recent subgroup lacks the required sample support; that safeguard is reported unsupported, never waived. Pitcher mean IP MSE worsened3.35%, with low-history/recent-origin and role/freshness protections failing; the GS count guard also failed. No method was revised after these errors were seen.\n\nAll8917 registered scoring-period player-seasons remain in prediction reporting:8134 supported and783 fallback, including one quarantined target without a score. Fallback values equal the baseline. FULL_COHORT score tables include all8916 known-target records on exactly paired memberships. Hitter rates of improvement differ slightly between supported-only and full-cohort means because the unchanged fallback rows contribute error.\n\nThe independent verification recomputed candidate workload directly from frozen node probabilities/means, checked all fallback workload values, and recalculated ALL-cohort error statistics and membership hashes. It did not refit a model. This test is development evidence over previously reviewed years, not a new untouched holdout.\n'''
p=O/'READ_ME.txt';p.write_text(p.read_text(encoding='utf-8')+notes,encoding='utf-8')
p=O/'validation_report.html';p.write_text(p.read_text(encoding='utf-8').replace('</html>','<h2>Final review and independent verification</h2><pre>'+html.escape(notes)+'</pre><p><a href="decision_summary.csv">Readable decision summary</a> · <a href="fallback_summary.csv">Fallback totals</a></p></html>'),encoding='utf-8')
pre=json.loads((O/'pre_scoring_freeze.json').read_text());assert all(sha(O/n)==h for n,h in pre['files'].items())
watch=json.loads((O/'source_manifest.json').read_text());assert all(sha(p)==h for p,h in watch.items())
shutil.copy2(__file__,O/'verify_usage_transition_validation.py');dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(verification,indent=2));print(json.dumps(decision,indent=2));print('ZIP bytes',Path(str(O)+'.zip').stat().st_size)
