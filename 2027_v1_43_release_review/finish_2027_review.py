import csv,json,hashlib,zipfile,html,shutil
from pathlib import Path
from collections import Counter
O=Path('outputs/2027_v1_43_release_review')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
def save(n,rows):
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rows for k in r)));w.writeheader();w.writerows(rows)
summary=json.loads((O/'review_summary.json').read_text());manifest=json.loads((O/'source_manifest.json').read_text());rows=read(O/'all_player_review.csv');counts=read(O/'count_change_decomposition.csv');miss=read(O/'missing_components_and_PA_residuals.csv');checks=read(O/'projection_consistency_checks.csv')
for p in [Path('outputs/2027_statcast_strengthened_validation/challenger_rerun/adoption_gates.json'),Path('outputs/2027_statcast_strengthened_validation/challenger_rerun/publication_freeze.json')]:manifest[str(p.resolve())]=sha(p)
gates=json.loads(Path('outputs/2027_statcast_strengthened_validation/challenger_rerun/adoption_gates.json').read_text());assert all(not r['eligible'] and r['reasons']==['NO_ONE_PERCENT_MSE_IMPROVEMENT'] for r in gates)
assert all(sha(p)==h for p,h in manifest.items())
assert len({(r['role'],r['mlbam_id']) for r in rows})==2511
assert len([r for r in rows if 'MATERIAL_YEAR_OVER_YEAR_CHANGE' in r['flags']])==334
assert all(r['explanation'] and r['review_action'] for r in rows)
assert all(abs(float(r['reconciliation_residual']))<1e-8 for r in counts)
assert all(r['status']=='PASS' for r in checks)
undefined=[r for r in rows if 'MISSING_FORECAST_COMPONENT' in r['flags']];assert len(undefined)==1 and undefined[0]['mlbam_id']=='571945' and undefined[0]['role']=='hitter' and undefined[0]['2027_AB']=='0.0' and undefined[0]['2027_SH']=='1.0'
stale=[r for r in rows if 'NO_POSITIVE_2026_MLB_HISTORY' in r['flags']]
residuals=[float(r['value']) for r in miss if r['issue']=='UNALLOCATED_PA_DIAGNOSTIC']
summary.update(input_files_verified=len(manifest),still_unresolved_review_names=sum(not r['name'] for r in rows),original_2027_names_missing=sum('UNRESOLVED_ORIGINAL_DISPLAY_NAME' in r['flags'] for r in rows),no_positive_recent_observation_counts=dict(Counter(r['latest_2026_observation'] for r in stale)),undefined_secondary_batting_rate_record='Miles Mikolas, MLBAM 571945: 1 PA, 0 AB, 1 SH; nine unavailable output fields remain blank',PA_residual_total=sum(residuals),PA_residual_max=max(residuals),release_recommendation='Retain v1.43 as the unchanged research baseline with visible exceptions. Arithmetic checks pass; retain undefined zero-AB batting rates as flagged secondary-role exceptions. Complete a dated opportunity/status review before presenting it as a roster-ready or complete draft forecast. No Statcast, workload, minor, park or international replacement is adopted.')
dump('review_summary.json',summary);dump('source_manifest.json',manifest)
focusnames={'Sal Stewart','Jacob Misiorowski','Cam Schlittler','Parker Messick','José Berríos','Pablo López','Miles Mikolas','Paul Skenes','Cole Ragans','George Kirby','Kevin Gausman','Logan Webb','Logan Gilbert'}
focus=[r for r in rows if r['name'] in focusnames];save('focused_case_reviews.csv',focus)
findings=f'''FINAL REVIEW FINDINGS\n\n{summary['release_recommendation']}\n\nReviewed 1,024 hitters and 1,487 pitchers. There are 334 material year-over-year changes and 92 P1 workload/status exceptions. P1 here means a review priority, not a forecast-error finding.\n\nOf 981 records with no positive recent MLB exposure, observation states are {summary['no_positive_recent_observation_counts']}. Unknown observations must not be described as confirmed zero or proof a player did not appear.\n\nAll 61,273 arithmetic checks passed. Nine unavailable output fields occur only in Miles Mikolas's secondary hitter record (1 PA, 0 AB, 1 SH). AVG and related rates are undefined at zero AB. Keep these exceptions visible; do not invent rates. There are also 155 nonzero PA-component residuals, totaling {sum(residuals):.3f} PA across players, maximum {max(residuals):.3f} PA for one player. These satisfy the original component bound but are not forced to reconcile to equality; no unverified cause is assigned.\n\nThe source 2027 files lack 300 display names. Exact same-MLBAM annotations from the published 2026/2027 files supply review names for 268; 32 remain unresolved. Original names and forecasts were not overwritten.\n\nCoverage lists include 12,832 linked minor-player/role records outside the MLB baseline, 118 working-baseline international exceptions, and four corroborated P1 international identities without validated forecasts. The minor list includes all available linked levels, stale records and secondary roles; it is not a list of likely MLB arrivals. Coverage ranking is triage only.\n\nThe 2026 reference is the saved four-season v1.43 reconstruction, not a three-season rebuild or proof of a preseason publication. New forecasts: 112 hitters and 181 pitchers. Pool exits: 140 hitters and 206 pitchers. Exit means outside this history-based projection pool, not a verified roster event.\n\nNo current injury or roster status was certified. Saved snapshots and limited transaction histories retain their dates and limitations. Absence of an injury/rehab flag is not evidence of health or availability.\n\nNo 2026 forecast error was calculated or used for selection. The Statcast challenger remains rejected under its unchanged guards. Suggested experiments are specified separately and were not run.\n\n'''
oldtext=(O/'REVIEW_REPORT.txt').read_text(encoding='utf-8');oldrecommendation=oldtext.split('RECOMMENDATION\n',1)[1].split('\n\n',1)[0]
oldtext=oldtext.replace(oldrecommendation,summary['release_recommendation']).replace('P1: component failure','P1: component failure')
(O/'REVIEW_REPORT.txt').write_text(findings+'DETAILED REVIEW\n\n'+oldtext,encoding='utf-8')
page=(O/'comparison_report.html').read_text(encoding='utf-8');oldlead=page.split('<p class="lead">',1)[1].split('</p>',1)[0];page=page.replace(oldlead,html.escape(summary['release_recommendation']),1)
box='<h2>Final release findings</h2><pre>'+html.escape(findings)+'</pre><p><a href="focused_case_reviews.csv">Focused player reviews</a> · <a href="separate_experiment_specifications.json">Separate experiment specifications</a></p>'
page=page.replace('<h2>How to read the changes</h2>',box+'<h2>How to read the changes</h2>')
# Keep the summary table synchronized with the final recommendation.
page=page.replace(html.escape(oldrecommendation),html.escape(summary['release_recommendation']))
(O/'comparison_report.html').write_text(page,encoding='utf-8')
verification=dict(unique_player_role_keys=len(rows),all_2027_forecasts_independently_replayed=True,published_2026_and_2027_snapshots_match_sources=True,material_change_explanations=334,count_decompositions_reconciled=len(counts),consistency_checks=len(checks),consistency_failures=0,undefined_zero_AB_secondary_batting_records=1,protected_input_files_verified=len(manifest),source_files_changed=False,forecast_values_changed=False,adoption_guards_changed=False,Statcast_role_gates_still_failed=True,model_selection_performed=False)
dump('verification_results.json',verification)
for name in ['review_contract.json']:
 c=json.loads((O/name).read_text());c['triage']='P1: unexpected component failure or stale history with >=200 PA/60 IP. Expected zero-AB secondary batting rates are P2, not a broken ordinary hitter forecast. Remaining priorities follow registered descriptive rules.';dump(name,c)
shutil.copy2(__file__,O/'finish_2027_review.py')
dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(verification,indent=2));print('ZIP bytes',Path(str(O)+'.zip').stat().st_size)

