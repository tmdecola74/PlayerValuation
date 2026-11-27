"""Independent checks and readable diagnostic findings; no candidate refit."""
import csv,json,hashlib,math,statistics as st,zipfile,html,shutil
from pathlib import Path
from collections import defaultdict
O=Path('outputs/2027_usage_transition_diagnostic');V=Path('outputs/2027_usage_transition_validation')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
def mean(x):return sum(x)/len(x)
rows=read(O/'player_error_diagnostics.csv');traces=read(O/'pooling_trace_by_player.csv');states=read(O/'pooling_state_contributions.csv');breakdown=read(O/'error_breakdown_summary.csv');guard=read(V/'extra_guard_results.csv')
groups=defaultdict(list)
for r in rows:
 if r['recent_positive']!='True' or r['supported']!='True' or r['actual']=='':continue
 v=float(r['latest_actual_exposure']);role=r['role']
 band=('PA<200' if v<200 else 'PA200–399' if v<400 else 'PA400–599' if v<600 else 'PA>=600') if role=='hitter' else ('IP<40' if v<40 else 'IP40–99' if v<100 else 'IP100–149' if v<150 else 'IP>=150')
 groups[r['season'],role,'LATEST_WORKLOAD',band].append(r)
 groups[r['season'],role,'LATEST_ROLE',r['latest_state']].append(r)
bandrows=[]
for (year,role,kind,band),rr in sorted(groups.items()):
 be=[float(r['baseline_error']) for r in rr];ce=[float(r['candidate_error']) for r in rr];bm=mean([v*v for v in be]);cm=mean([v*v for v in ce]);bandrows.append(dict(season=year,role=role,kind=kind,band=band,n=len(rr),MSE_ratio=cm/bm if bm else None,baseline_bias=mean(be),candidate_bias=mean(ce),candidate_over=sum(v>0 for v in ce),candidate_under=sum(v<0 for v in ce),baseline_MAE=mean(list(map(abs,be))),candidate_MAE=mean(list(map(abs,ce)))))
save('active_error_by_latest_workload_and_role.csv',bandrows)
bandmacro=[]
for role,kind,band in sorted({(r['role'],r['kind'],r['band']) for r in bandrows}):
 rr=[r for r in bandrows if (r['role'],r['kind'],r['band'])==(role,kind,band)];valid=[r['MSE_ratio'] for r in rr if r['MSE_ratio'] is not None]
 bandmacro.append(dict(role=role,kind=kind,band=band,folds=len(rr),n=sum(r['n'] for r in rr),mean_fold_MSE_change_pct=100*(mean(valid)-1) if valid else None,mean_fold_baseline_bias=mean([r['baseline_bias'] for r in rr]),mean_fold_candidate_bias=mean([r['candidate_bias'] for r in rr]),candidate_over=sum(r['candidate_over'] for r in rr),candidate_under=sum(r['candidate_under'] for r in rr)))
save('active_workload_band_summary.csv',bandmacro)
statebank=defaultdict(list)
for s in states:statebank[s['season'],s['role'],s['mlbam_id']].append(s)
validated=0;borrow=[]
for t in traces:
 ss=statebank[t['season'],t['role'],t['mlbam_id']];value=float(t['selected_workload']);contrib=sum(float(s['contribution_to_candidate']) for s in ss)
 assert math.isclose(contrib,value,abs_tol=1e-8);assert math.isclose(sum(float(s['selected_probability']) for s in ss),1,abs_tol=1e-12)
 assert all(0<=float(s['conditional_mean_parent_weight'])<=1 for s in ss)
 weight=sum(float(s['contribution_to_candidate'])*float(s['conditional_mean_parent_weight']) for s in ss)/value if value else 0
 borrow.append(dict(season=t['season'],role=t['role'],mlbam_id=t['mlbam_id'],recent_positive=t['recent_positive'],arithmetic_conditional_parent_contribution_share=weight,probability_parent_weight=t['probability_parent_weight'],definition='Algebraic local parent contribution, not independent evidence weight or causal error effect'));validated+=1
save('conditional_parent_borrowing_trace.csv',borrow)
for role in ['hitter','pitcher']:
 r=next(r for r in breakdown if r['role']==role and r['scope']=='RECENT_POSITIVE_SUPPORTED' and r['cohort']=='ALL');g=next(g for g in guard if g['role']==role and g['cohort']=='RECENT_POSITIVE')
 assert math.isclose(float(r['mean_fold_MSE_ratio']),float(g['mean_MSE_ratio']),abs_tol=1e-12)
sample=next(p for p in read(O/'shared_pool_prediction_ranges.csv') if p['season']=='2024' and p['role']=='hitter' and p['pool']=='REGULAR_STARTER|REGULAR_STARTER|ESTABLISHED')
audit=read(O/'hitter_subgroup_support_audit.csv');support_numbers={r['origin']:int(r['supported_rows']) for r in audit if r['definition']=='PRIOR_ZERO_PA_CERTIFIED'}
findings=dict(conclusion='The failed challenger replaced different personal workloads with common role-group averages; latest numeric PA/IP was not a predictor. This is not simply excessive weighting of older individual seasons.',global_pool_backoffs=0,full_specific_pool_can_still_erase_individual_variation=True,example_2024_established_regular_hitters=dict(players=int(sample['players']),shared_PA=float(sample['one_shared_prediction']),previous_PA_min=float(sample['latest_individual_min']),previous_PA_max=float(sample['latest_individual_max'])),hitter_zero_guard_cause='No original explicit prior PA=0 rows exist in the tested hitter cohort. Certified prior zeros live separately and retain UNKNOWN_RECENT under the unchanged baseline freshness mapping.',certified_prior_zero_supported_counts_by_fold=support_numbers,thresholds_unchanged=True,failed_test_not_reclassified=True,new_model_or_hyperparameter_tested=False)
assert all(t['hierarchy']!='GLOBAL' for t in traces)
dump('principal_findings.json',findings)
lead=f'''PRINCIPAL FINDINGS\n\nThe failed challenger did not retain each player's numeric recent workload. It assigned a shared workload to everyone in a categorical role pool. In2024, {sample['players']} established regular hitters with prior workloads from {float(sample['latest_individual_min']):.0f} to {float(sample['latest_individual_max']):.0f} PA all received {float(sample['one_shared_prediction']):.1f} PA. The source code and all8,134 supported traces confirm this behavior. None used the global pool: the loss of detail occurred even in the full latest/recent/experience pools.\n\nAmong recently active hitters, median probability shrinkage toward a parent was5.8%; among pitchers8.3%. These weights alone do not explain the failure. The absolute conditional workloads were peer averages with no individual PA/IP anchor. Parent conditional-mean borrowing is traced separately; its share is arithmetic, not a causal attribution of error. Large prior workloads can be pulled down while small prior workloads are pushed up. Workload-band tables show both directions; aggregate bias alone hides this compression.\n\nFor recently active established/stable hitters, mean fold MSE worsened44.39%; the recent-callup proxy was nearly unchanged (+0.04%), and the role-change proxy worsened15.09%. Recently active pitcher groups worsened2.40%,12.65% and10.67%, respectively. These are descriptive partitions/proxies with sample sizes, not new adoption tests. Returners are reported separately outside the recent-positive subset.\n\nThe known-zero hitter guard has a definition mismatch, not an absence of all supporting evidence. Its original freshness label has zero explicit-zero rows in each scoring fold. The separate pre-origin certificate supplies {support_numbers['2023']}, {support_numbers['2024']} and {support_numbers['2025']} supported prior-zero-PA cases. All have missing original PA, so unchanged freshness calls them unknown. A later preregistered protocol can align the cohort ledger without changing baseline numbers or15-row/2% thresholds. That is not a retroactive pass: the active-player accuracy failure remains.\n\nRecommend exactly one next experiment: learn workload change around each player's own latest reconciled workload instead of replacing it with an absolute group mean. Retain certified nonappearances as negative-change outcomes and do not add a universal growth bonus. Register the joint-vector/feasibility, shared cohort ledger, support and fallback rules before a separate test. This recommendation is informed by already reviewed development errors and is not fresh independent validation. No such model was built or tested here.\n\nStewart and Misiorowski remain unscored source-history illustrations. Their2025 debuts kept them outside these prior-MLB-history scoring folds. No2027 challenger projection was manufactured and no2026 projection error was calculated.\n\n'''
p=O/'DIAGNOSTIC_REPORT.txt';p.write_text(lead+p.read_text(encoding='utf-8'),encoding='utf-8')
def table(rr,cc):return '<div style="overflow:auto"><table><tr>'+''.join('<th>'+html.escape(c.replace('_',' '))+'</th>' for c in cc)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(c,'')))+'</td>' for c in cc)+'</tr>' for r in rr)+'</table></div>'
p=O/'diagnostic_report.html';page=p.read_text(encoding='utf-8');page=page.replace('<h2>Recently active players</h2>','<h2>Principal findings</h2><pre>'+html.escape(lead)+'</pre><h2>Where workload became too high or too low</h2>'+table([r for r in bandmacro if r['kind']=='LATEST_WORKLOAD'],['role','band','n','mean_fold_MSE_change_pct','mean_fold_baseline_bias','mean_fold_candidate_bias','candidate_over','candidate_under'])+'<p>Positive bias means overprojection; negative bias means underprojection. Bands are descriptive, not candidate settings. Role/group tables and overlapping cohorts do not change original memberships or guards.</p><h2>Recently active players</h2>');p.write_text(page,encoding='utf-8')
v=json.loads((O/'verification_results.json').read_text());v.update(independent_state_contribution_sums_verified=validated,active_error_ratios_match_original_guard_results=True,zero_guard_mapping_audited=True,global_backoff_count_verified_zero=True);dump('verification_results.json',v)
watch=json.loads((O/'source_manifest.json').read_text());assert all(sha(p)==h for p,h in watch.items())
shutil.copy2(__file__,O/'finish_usage_diagnostic.py');dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(findings,indent=2));print(json.dumps([r for r in bandmacro if r['kind']=='LATEST_WORKLOAD'],indent=2));print('ZIP bytes',Path(str(O)+'.zip').stat().st_size)
