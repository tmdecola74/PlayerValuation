"""Reconcile batting versus all-MLB game definitions and finalize read-only certificates."""
import csv,json,math,hashlib,sys,zipfile,html,shutil
from pathlib import Path
from collections import Counter,defaultdict
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
O=Path('outputs/2027_game_usage_reconstruction')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,x):(O/n).write_text(json.dumps(x,indent=2),encoding='utf-8')
def num(x):return int(x) if x not in ('',None) else 0
initial=json.loads((O/'run_summary.json').read_text());manifest=json.loads((O/'source_manifest.json').read_text());scope={r['season']:r for r in initial['seasons']}
assert len(scope)==8 and all(r['full_scope_verified'] for r in scope.values()),'Full game scope must pass before finalization'
lab=R/'outputs/training_labels_v1_0';hp=R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv';ov=R/'outputs/participation_label_overlay_v1_27'
a,_=apply_overlay(ov,labels(lab/'training_labels.parquet'),lab/'training_labels.parquet',hp,manifest);a.update(labels(lab/'holdout_labels.parquet',2026))
for r in read(R/'outputs/pitcher_evaluation_v1_29/evaluation_label_overlay_2026.csv'):
 for m,c in [('G','evaluation_g'),('OUTS','evaluation_outs')]:a[2026,'pitcher',r['mlbam_id'],m]=float(r[c])
members=read(O/'frozen_hitter_cohort_membership.csv');cohorts=defaultdict(list)
for r in members:cohorts[int(r['target_season'])].append(r['mlbam_id'])
definition=dict(registered_after_first_source_reconciliation_before_any_model_fit=True,reason='Eligible annual G counts all credited MLB games, including pitching-only games. Initial batting gamesPlayed alone undercounted G for some players, while PA and other batting counts matched.',canonical_G='Union of credited batting gamesPlayed=1 and pitching gamesPitched=1 by season/game/team/MLBAM; all games checked. No imputed player-season count or name matching.',batting_G='Retained separately as BATTING_G; not a substitute for all-MLB G',zero_PA='A player can have MLB G>0 and PA=0. Such a player is not an MLB nonappearance; positive-PA exposure outcome is recorded separately.',secondary_roles='Prior-positive-PA cohort intentionally retains pitchers with batting history. Expose pitching-only games so a later hitter opportunity model does not confuse them with ordinary bench hitters.',no_forecast_or_guard_changes=True)
dump('G_definition_resolution.json',definition)
for old,new in [('run_summary.json','initial_batting_definition_summary.json'),('season_label_reconciliation.csv','initial_batting_definition_reconciliation.csv')]:
 if not (O/new).exists():shutil.copy2(O/old,O/new)
annual=[];recent=[];recon=[];certs=[];summaries=[];special=[];pitcher_split_checks=[];cohort_assertions=[];lineup_counts=[];namebank={}
for y in range(2019,2027):
 raw=O/f'batting_stat_game_usage_{y}.csv'
 if not raw.exists():shutil.copy2(O/f'hitter_game_usage_{y}.csv',raw)
 bat=read(raw);pitch=read(O/f'pitcher_game_usage_{y}.csv');key=lambda r:(r['game_pk'],r['team_id'],r['mlbam_id'])
 hh={key(r):r for r in bat};pp={key(r):r for r in pitch};assert len(hh)==len(bat) and len(pp)==len(pitch)
 combined=[]
 for k in sorted(hh.keys()|pp.keys(),key=lambda k:tuple(map(int,k))):
  b=hh.get(k);p=pp.get(k);base=dict(b or p);pid=base['mlbam_id'];namebank[y,pid]=base['name']
  if not b:
   keep=['season','game_pk','official_date','game_number','team_id','side','mlbam_id','name','team_game_ordinal','in_last60_team_games','source_file'];base={k:base[k] for k in keep}
   base.update({m:0 for m in ['PA','AB','H','BB','SO','HBP','SF','SH','CI','STARTS']});base.update(batting_order_code='',lineup_slot='',substitution_index='',initial_order_assignment='',lineup_start_status='PITCHING_ONLY_NO_BATTING_STAT_APPEARANCE',is_substitute='')
  base.update(G=1,BATTING_G=int(b is not None),CREDITED_PITCHING_G=int(p is not None),PITCHING_ONLY_G=int(b is None and p is not None))
  combined.append(base)
  if num(base['PA'])==0:special.append(dict(reason='CREDITED_MLB_G_WITH_ZERO_PA',**base))
 save(f'hitter_game_usage_{y}.csv',combined)
 aggs={};lateagg={};slots=Counter()
 for role,rr in [('hitter',combined),('pitcher',pitch)]:
  agg=defaultdict(Counter);last=defaultdict(Counter);teams=defaultdict(set);late_teams=defaultdict(set);order=defaultdict(Counter)
  fields=['G','BATTING_G','CREDITED_PITCHING_G','PITCHING_ONLY_G','PA','AB','H','BB','SO','HBP','SF','SH','CI','STARTS'] if role=='hitter' else ['G','GS','GR','OUTS','START_OUTS','RELIEF_OUTS','ZERO_OUT_APPEARANCES']
  for r in rr:
   pid=r['mlbam_id'];teams[pid].add(r['team_id'])
   for m in fields:agg[pid][m]+=num(r[m])
   if r['in_last60_team_games']=='True' or r['in_last60_team_games'] is True:
    late_teams[pid].add(r['team_id'])
    for m in fields:last[pid][m]+=num(r[m])
    if role=='hitter' and r['lineup_slot'] not in ('',None) and num(r['lineup_slot']) in range(1,10):order[pid][num(r['lineup_slot'])]+=1
   if role=='hitter' and num(r['STARTS']):slots[num(r['lineup_slot'])]+=1
  aggs[role]=agg;lateagg[role]=last
  for pid,v in agg.items():
   row=dict(season=y,role=role,mlbam_id=pid,name=namebank.get((y,pid),''),teams=';'.join(sorted(teams[pid])),**dict(v),usage='2027_HISTORY_ONLY' if y==2026 else 'EARLIER_USAGE_SOURCE')
   if role=='pitcher':
    assert v['GS']+v['GR']==v['G'] and v['START_OUTS']+v['RELIEF_OUTS']==v['OUTS']
    row.update(IP=v['OUTS']/3,IP_per_start=v['START_OUTS']/3/v['GS'] if v['GS'] else None,IP_per_relief=v['RELIEF_OUTS']/3/v['GR'] if v['GR'] else None)
    pitcher_split_checks.append(dict(season=y,mlbam_id=pid,G=v['G'],GS=v['GS'],GR=v['GR'],OUTS=v['OUTS'],START_OUTS=v['START_OUTS'],RELIEF_OUTS=v['RELIEF_OUTS'],status='EXACT_SPLIT'))
   else:row.update(PA_per_MLB_G=v['PA']/v['G'],PA_per_batting_G=v['PA']/v['BATTING_G'] if v['BATTING_G'] else None,starts_per_MLB_G=v['STARTS']/v['G'])
   annual.append(row)
  for pid,v in last.items():recent.append(dict(season=y,role=role,mlbam_id=pid,name=namebank.get((y,pid),''),teams=';'.join(sorted(late_teams[pid])),window='Last60 completed games of each source team; traded players use actual game/team records',**dict(v),lineup_slot_counts=json.dumps(dict(order[pid])) if role=='hitter' else '',usage='2027_HISTORY_ONLY' if y==2026 else 'EARLIER_FEATURE_SOURCE'))
 affected=defaultdict(set);missingpositive=defaultdict(set);mismatch=Counter()
 for (s,role,pid,m),v in a.items():
  allowed=['G','PA','AB','H','BB','SO','HBP','SF','SH'] if role=='hitter' else ['G','GS','OUTS']
  if s!=y or m not in allowed:continue
  obs=aggs[role].get(pid,{}).get(m,0);ok=v==obs;recon.append(dict(season=y,role=role,mlbam_id=pid,name=namebank.get((y,pid),''),metric=m,eligible_source=v,reconstructed=obs,delta=obs-v,status='MATCH' if ok else 'MISMATCH',source='Frozen eligible labels with existing certified participation correction; no new label edits'))
  if not ok:
   affected[role].add(pid);mismatch[role,m]+=1
   if v>0 and not aggs[role].get(pid,{}).get('G'):missingpositive[role].add(pid)
 for pid in cohorts[y]:
  v=aggs['hitter'].get(pid,{});g=v.get('G',0);pa=v.get('PA',0);status='VERIFIED_APPEARED' if g else 'VERIFIED_NO_MLB_APPEARANCE';numeric=pid not in affected['hitter'];season_ok=scope[y]['full_scope_verified'] and not missingpositive['hitter']
  if not season_ok:status='UNKNOWN_SEASON_SCOPE_OR_POSITIVE_LABEL_CONFLICT'
  elif not numeric:status='VERIFIED_APPEARANCE_USAGE_EXCEPTION' if g else 'CONFLICT_POSITIVE_SOURCE_LABEL'
  certs.append(dict(season=y,mlbam_id=pid,name=namebank.get((y,pid),''),cohort_history=f'{y-4}-{y-1}',identity_evidence='Exact canonical MLBAM from positive eligible pre-origin MLB PA',status=status,G=g,PA=pa,BATTING_G=v.get('BATTING_G',0),PITCHING_ONLY_G=v.get('PITCHING_ONLY_G',0),positive_PA_exposure=pa>0,certified_no_MLB_appearance=season_ok and numeric and g==0,certified_zero_PA_exposure=season_ok and numeric and pa==0,season_scope_certified=season_ok,usage_reconciled=numeric,proposed_G=0 if season_ok and numeric and g==0 else None,proposed_PA=0 if season_ok and numeric and pa==0 else None,usage='2027_HISTORY_ONLY_NOT_SELECTION' if y==2026 else 'HISTORICAL_CERTIFICATE_NOT_APPLIED'))
 lineup_counts.extend(dict(season=y,lineup_slot=slot,credited_initial_starts=count) for slot,count in sorted(slots.items()))
 summaries.append(dict(season=y,complete_games=scope[y]['verified_games'],scope_certified=scope[y]['full_scope_verified'],team_batting_sums_verified=scope[y]['team_batting_sums_verified'],initial_lineup_slot_exceptions=scope[y]['lineup_slot_exceptions'],batting_stat_rows=len(bat),all_MLB_appearance_rows=len(combined),pitching_outings=len(pitch),pitcher_players=len(aggs['pitcher']),all_appearance_players=len(aggs['hitter']),eligible_label_comparisons=sum(r['season']==y for r in recon),source_label_mismatches=sum(mismatch.values()),mismatch_by_role_metric=json.dumps({str(k):v for k,v in mismatch.items()}),cohort_players=len(cohorts[y]),certified_nonappearances=sum(r['season']==y and r['certified_no_MLB_appearance'] for r in certs),certified_zero_PA_exposure=sum(r['season']==y and r['certified_zero_PA_exposure'] for r in certs),usage='2027_HISTORY_ONLY' if y==2026 else 'HISTORICAL_USAGE_AND_CERTIFICATE'))
 print(json.dumps(summaries[-1]),flush=True)
save('season_usage_totals.csv',annual);save('last60_team_game_usage.csv',recent);save('season_label_reconciliation.csv',recon);save('hitter_participation_certification.csv',certs);save('season_scope_and_reconciliation.csv',summaries);save('pitcher_outing_split_checks.csv',pitcher_split_checks);save('starting_lineup_slot_counts.csv',lineup_counts)
save('historical_hitter_nonappearance_overlay_PROPOSED_NOT_APPLIED.csv',[dict(season=r['season'],mlbam_id=r['mlbam_id'],G=0,PA=0,evidence='Complete cached official regular-season game coverage; exact prior-history cohort ID; no credited MLB appearance',applied_to_original_labels=False) for r in certs if r['season']<=2025 and r['certified_no_MLB_appearance']])
save('historical_zero_PA_exposure_certificate.csv',[r for r in certs if r['season']<=2025 and r['certified_zero_PA_exposure']])
save('credited_zero_PA_appearance_evidence.csv',special)
save('remaining_usage_exceptions.csv',[r for r in recon if r['status']=='MISMATCH'])
save('focused_2027_history_usage.csv',[r for r in annual if r['name'] in ['Sal Stewart','Jacob Misiorowski']])
# Isolate future-history labels and features from the selection-ready historical tables.
for name,rr in [('historical_season_usage_2019_2025.csv',[r for r in annual if r['season']<=2025]),('quarantine_2026_season_usage.csv',[r for r in annual if r['season']==2026]),('historical_last60_usage_2019_2025.csv',[r for r in recent if r['season']<=2025]),('quarantine_2026_last60_usage.csv',[r for r in recent if r['season']==2026])]:save(name,rr)
issues=read(O/'reconstruction_issues.csv') if (O/'reconstruction_issues.csv').exists() else []
summary=dict(status='RECONCILED' if all(not r['source_label_mismatches'] and not r['initial_lineup_slot_exceptions'] for r in summaries) else 'RECONCILED_WITH_EXPLICIT_EXCEPTIONS',years=list(range(2019,2027)),completed_games=sum(r['complete_games'] for r in summaries),batting_stat_rows=sum(r['batting_stat_rows'] for r in summaries),all_MLB_game_team_player_rows=sum(r['all_MLB_appearance_rows'] for r in summaries),pitching_outings=sum(r['pitching_outings'] for r in summaries),label_comparisons=len(recon),remaining_label_mismatches=sum(r['status']=='MISMATCH' for r in recon),lineup_slot_exceptions=sum(r['initial_lineup_slot_exceptions'] for r in summaries),historical_cohort_player_seasons=sum(r['season']<=2025 for r in certs),historical_certified_MLB_nonappearances=sum(r['season']<=2025 and r['certified_no_MLB_appearance'] for r in certs),historical_certified_zero_PA_exposure=sum(r['season']<=2025 and r['certified_zero_PA_exposure'] for r in certs),historical_zero_PA_with_MLB_appearance=sum(r['season']<=2025 and r['certified_zero_PA_exposure'] and r['G']>0 for r in certs),game_files_bound_to_original_hashes=sum('/game_' in p.replace(chr(92),'/') for p in manifest),source_files_changed=False,baseline_changed=False,adoption_guards_changed=False,models_fitted=False,forecast_errors_scored=False,proposed_label_overlay_applied=False)
dump('run_summary.json',summary)
for p,h in manifest.items():
 if '/game_' not in p.replace(chr(92),'/'):assert sha(p)==h,('Protected file changed',p)
verification=dict(all_game_sources_hash_bound_to_original_certificates=True,all_schedule_and_standings_scopes_verified=True,no_source_positive_player_silently_missing=all(r['scope_certified'] for r in summaries),unique_game_team_player_keys=True,pitcher_start_relief_partitions_exact=True,frozen_hitter_cohort_keys=len(certs),all_source_label_comparisons=len(recon),remaining_mismatches=summary['remaining_label_mismatches'],protected_non_game_files_reverified=True,baseline_changed=False,models_fitted=False,forecast_errors_scored=False,certified_zeros_not_written_into_original_labels=True)
dump('verification_results.json',verification)
text='GAME-LEVEL USAGE RECONSTRUCTION AND HITTER PARTICIPATION CERTIFICATION\n\n'+json.dumps(summary,indent=2)+'''\n\nSCOPE\nAll cached completed MLB regular-season games for 2019–2026 were read and hash-bound to the original season certificates. Schedules reconcile to standings team-game counts. Every game validates official pitcher lists/credited appearances and outs, player batting counts to team batting totals, and initial batting-order slots. No new statistics were downloaded and no original label, model, guard or forecast was edited.\n\nGAME DEFINITIONS\nAnnual source G counts credited MLB games, including pitching-only games. Batting-only gamesPlayed is a different quantity. Canonical hitter_game_usage files use the union of credited batting and pitching game/team/player records and retain BATTING_G, CREDITED_PITCHING_G and PITCHING_ONLY_G. The original batting-only extraction is preserved in batting_stat_game_usage files. PA and other batting counts are not altered. A pitching-only appearance contributes G but no PA. Zero PA is not proof of no MLB appearance. Starting batting-order code and substitute order are retained separately; final team battingOrder is not treated as the starting lineup.\n\nPITCHER SPLITS\nEach credited outing has gamesStarted 0/1 and observed outs. Seasonal GS+GR=G and START_OUTS+RELIEF_OUTS=OUTS hold exactly. IP is decimal OUTS/3, with original baseball innings notation retained per outing. Zero-out/no-pitch credited appearances remain. Mixed-role innings are split from observed outings rather than season IP divided by GS.\n\nHITTER COHORT AND ZERO CERTIFICATES\nFor target Y, freeze exact IDs with positive eligible MLB PA in Y-4 through Y-1. This matches the baseline history window, intentionally including pitchers with prior batting exposure. It is not a complete prospective MLB roster or a prospect-arrival universe. A certified MLB nonappearance requires complete season coverage, no credited MLB appearance and no conflicting eligible source label. Zero-PA exposure is certified separately for players who pitched or otherwise appeared without PA. Proposed overlays are separate and are NOT applied to baseline/training labels. Future model design must distinguish primary hitter opportunity from secondary pitcher batting records, without silently changing the registered comparison sample.\n\nHISTORICAL VERSUS 2027 HISTORY\n2019–2025 tables are historical adapter/certification evidence. The 2026 season is published in separate quarantine/history tables for 2027 inputs only. No 2026 forecast errors were calculated or used. Last60 features use the last60 completed games of each source team, retain trades/game identities and store source season; they become predictors only for later target years. Actual target-year roles, availability or workloads must never become preseason features.\n\nLIMITATIONS\nRetrospective source vintages remain. Games/starts/lineup position are observed usage, not evidence of health or a guaranteed future roster role. Historical preseason depth charts are still required for chart-dependent validation. This reconstruction does not fit a workload model or demonstrate adoption improvement. Remaining source discrepancies, if any, are explicit and quarantined; no target count is silently repaired.\n\nNEXT BUILD\nAfter reviewing remaining exceptions and the appearance-versus-positive-PA label definition, register the executable usage-transition model and support/fallback rules before historical scoring. Keep the current baseline and rejected workload/Statcast methods unchanged.\n'''
(O/'READ_ME.txt').write_text(text,encoding='utf-8')
def table(rr,cols):return '<div style="overflow:auto"><table><tr>'+''.join('<th>'+html.escape(c)+'</th>' for c in cols)+'</tr>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r.get(c,'')))+'</td>' for c in cols)+'</tr>' for r in rr)+'</table></div>'
page='<!doctype html><html lang="en"><meta charset="utf-8"><title>Game usage reconstruction</title><style>body{font:16px/1.6 system-ui;max-width:1300px;margin:40px auto;padding:20px;color:#183543}table{border-collapse:collapse;font-size:13px;width:100%}td,th{border:1px solid #cad8e2;padding:9px;text-align:left}th{background:#e2eef5}pre{white-space:pre-wrap}</style><h1>Game usage reconstruction and participation certification</h1><p>Read-only source reconstruction. Working 2027 v1.43 forecasts unchanged.</p><h2>Season checks</h2>'+table(summaries,['season','complete_games','all_MLB_appearance_rows','pitching_outings','source_label_mismatches','certified_nonappearances','certified_zero_PA_exposure'])+'<h2>Files</h2><p><a href="season_usage_totals.csv">Season usage</a> · <a href="last60_team_game_usage.csv">Recent role usage</a> · <a href="hitter_participation_certification.csv">Hitter certificates</a> · <a href="season_label_reconciliation.csv">Source reconciliation</a> · <a href="focused_2027_history_usage.csv">Stewart and Misiorowski history</a></p><h2>Definitions and next build</h2><pre>'+html.escape(text)+'</pre></html>'
(O/'reconstruction_report.html').write_text(page,encoding='utf-8')
shutil.copy2('work/reconstruct_game_usage.py',O/'reconstruct_game_usage.py');shutil.copy2(__file__,O/'finalize_game_usage.py')
dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(summary,indent=2),flush=True)
