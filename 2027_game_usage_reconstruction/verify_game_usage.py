"""Independent structural and edge-case checks; source exceptions remain quarantined."""
import csv,json,hashlib,zipfile,shutil,html
from pathlib import Path
from collections import Counter
import duckdb
O=Path('outputs/2027_game_usage_reconstruction')
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def dump(n,v):(O/n).write_text(json.dumps(v,indent=2),encoding='utf-8')
summary=json.loads((O/'run_summary.json').read_text());manifest=json.loads((O/'source_manifest.json').read_text());verify=json.loads((O/'verification_results.json').read_text());checks=[];diagnostic=[]
with duckdb.connect() as d:
 for y in range(2019,2027):
  h=str(O/f'hitter_game_usage_{y}.csv');p=str(O/f'pitcher_game_usage_{y}.csv')
  for name,path in [('h',h),('p',p)]:d.read_csv(path).create_view(name,replace=True)
  duplicate_h=d.execute('SELECT count(*) FROM (SELECT game_pk,team_id,mlbam_id,count(*) n FROM h GROUP BY ALL HAVING n<>1)').fetchone()[0]
  duplicate_p=d.execute('SELECT count(*) FROM (SELECT game_pk,team_id,mlbam_id,count(*) n FROM p GROUP BY ALL HAVING n<>1)').fetchone()[0]
  bad_starts=d.execute('SELECT count(*) FROM (SELECT game_pk,team_id,sum(STARTS) s,count(DISTINCT CASE WHEN STARTS=1 THEN lineup_slot END) n FROM h GROUP BY 1,2 HAVING s<>9 OR n<>9)').fetchone()[0]
  bad_split=d.execute('SELECT count(*) FROM p WHERE GS+GR<>G OR START_OUTS+RELIEF_OUTS<>OUTS OR GS NOT IN (0,1)').fetchone()[0]
  bad_flags=d.execute('SELECT count(*) FROM h WHERE G<>1 OR BATTING_G NOT IN (0,1) OR CREDITED_PITCHING_G NOT IN (0,1) OR (BATTING_G=0 AND CREDITED_PITCHING_G=0) OR (PITCHING_ONLY_G=1 AND PA<>0) OR (STARTS=1 AND substitution_index<>0)').fetchone()[0]
  assert duplicate_h==duplicate_p==bad_starts==bad_split==bad_flags==0
  checks.append(dict(season=y,duplicate_hitter_keys=duplicate_h,duplicate_pitcher_keys=duplicate_p,starting_lineup_failures=bad_starts,pitcher_partition_failures=bad_split,appearance_flag_failures=bad_flags,status='PASS'))
  if y==2023:
   rr=d.execute('SELECT mlbam_id,game_pk,G,OUTS,number_of_pitches FROM p WHERE mlbam_id=677020 AND game_pk=717170').fetchall();assert len(rr)==1 and rr[0][2]==1 and rr[0][3]==0
   diagnostic.append(dict(case='Josh Walker credited no-out appearance',season=y,evidence=json.dumps(rr),result='PRESERVED'))
  if y==2024:
   rr=d.execute('SELECT game_pk,team_id,mlbam_id,G,PA,batting_order_code FROM h WHERE mlbam_id=643376 AND game_pk=746942 ORDER BY team_id').fetchall();assert len(rr)==2 and len({r[1] for r in rr})==2
   diagnostic.append(dict(case='Danny Jansen same game for both teams',season=y,evidence=json.dumps(rr),result='BOTH_GAME_TEAM_RECORDS_PRESERVED_NOT_DEDUPLICATED_ACROSS_TEAMS'))
  if y==2026:
   for pid in [680777,815873]:
    rr=d.execute('SELECT name,mlbam_id,game_pk,official_date,PA,AB,BB,HBP,SF,SH,CI,source_file FROM h WHERE mlbam_id=? AND PA<>AB+BB+HBP+SF+SH+CI',[pid]).fetchall()
    for r in rr:diagnostic.append(dict(case='One observed PA not allocated among boxscore components',season=y,mlbam_id=pid,game_pk=r[2],source_date=str(r[3]),evidence=json.dumps(r,default=str),result='SOURCE_DISCREPANCY_QUARANTINED_NOT_REPAIRED'))
   rr=d.execute('SELECT G,PA,BATTING_G,CREDITED_PITCHING_G,PITCHING_ONLY_G FROM h WHERE mlbam_id=694819 LIMIT 1').fetchone();assert rr==(1,0,0,1,1)
   diagnostic.append(dict(case='Misiorowski pitching-only game is MLB appearance with zero PA',season=y,evidence=json.dumps(rr),result='SEPARATE_APPEARANCE_AND_PA_LABELS'))
save('independent_structural_checks.csv',checks);save('edge_case_verification.csv',diagnostic)
# Trace the two unresolved 2026 PA records in previously audited pitch archives where available.
windows=read('outputs/2027_statcast_strengthened_validation/archive_window_inventory.csv');manifest[str(Path('outputs/2027_statcast_strengthened_validation/archive_window_inventory.csv').resolve())]=sha('outputs/2027_statcast_strengthened_validation/archive_window_inventory.csv')
events=[]
with duckdb.connect() as d:
 for date,game,pid in [('2026-04-03',823732,680777),('2026-09-23',824784,815873)]:
  w=next(r for r in windows if r['day']==date);p=Path(w['parquet_path']);assert sha(p)==w['parquet_hash'];manifest[str(p.resolve())]=w['parquet_hash']
  d.read_parquet(str(p)).create_view('p',replace=True)
  cur=d.execute('SELECT game_pk,at_bat_number,pitch_number,batter,pitcher,events,description,type FROM p WHERE game_pk=? AND batter=? AND events IS NOT NULL ORDER BY at_bat_number,pitch_number',[game,pid]);cc=[x[0] for x in cur.description]
  for row in cur.fetchall():events.append(dict(source_date=date,**dict(zip(cc,row))))
save('2026_PA_exception_archived_event_trace.csv',events)
exceptions=read(O/'remaining_usage_exceptions.csv');affected={(r['season'],r['role'],r['mlbam_id']) for r in exceptions}
for name in ['season_usage_totals.csv','last60_team_game_usage.csv','historical_season_usage_2019_2025.csv','quarantine_2026_season_usage.csv','historical_last60_usage_2019_2025.csv','quarantine_2026_last60_usage.csv']:
 rr=read(O/name)
 for r in rr:r['source_reconciliation_status']='QUARANTINED_SOURCE_DISCREPANCY_DO_NOT_FIT' if (r['season'],r['role'],r['mlbam_id']) in affected else 'SOURCE_RECONCILED'
 save(name,rr)
annual=read(O/'season_usage_totals.csv');save('usage_rows_quarantined.csv',[r for r in annual if r['source_reconciliation_status'].startswith('QUARANTINED')]);save('historical_source_reconciled_season_usage.csv',[r for r in annual if int(r['season'])<=2025 and r['source_reconciliation_status']=='SOURCE_RECONCILED'])
certs=read(O/'hitter_participation_certification.csv');members=read(O/'frozen_hitter_cohort_membership.csv')
assert {(r['season'],r['mlbam_id']) for r in certs}=={(r['target_season'],r['mlbam_id']) for r in members}
assert len({(r['season'],r['mlbam_id']) for r in certs})==len(certs)
for r in certs:
 if r['certified_no_MLB_appearance']=='True':assert r['G']=='0' and r['PA']=='0' and r['season_scope_certified']=='True' and r['usage_reconciled']=='True'
 if r['certified_zero_PA_exposure']=='True':assert r['PA']=='0' and r['season_scope_certified']=='True' and r['usage_reconciled']=='True'
verify.update(independent_season_structural_checks_passed=8,all_game_team_starting_orders_have_exactly_nine_credited_starters=True,known_no_pitch_and_same_game_two_team_edge_cases_preserved=True,cohort_membership_exactly_preserved=True,certified_zeros_require_reconciled_usage=True,unresolved_player_seasons_explicitly_quarantined=len(affected),historical_unresolved_player_seasons=sum(int(y)<=2025 for y,r,p in affected),future_2026_unresolved_player_seasons=sum(int(y)==2026 for y,r,p in affected))
dump('verification_results.json',verify);dump('source_manifest.json',manifest)
notes='''\n\nINDEPENDENT CHECKS AND EXCEPTION DISPOSITION\nAll eight seasons passed an independent check of unique game/team/player keys, exactly nine credited initial batting-order starters per team/game, valid appearance flags and exact pitching outing partitions. Josh Walker's credited zero-out appearance is preserved. Danny Jansen's 2024 game 746942 contains separate Toronto and Boston records; both are retained. The frozen annual source still reports 94 G versus 92 reconstructed G, so his 2024 hitter usage remains quarantined. No unsupported correction is applied.\n\nThe two 2026 PA differences are localized to Ryan Jeffers in game 823732 (April 3) and Sean Keys in game 824784 (September 23). Each official boxscore reports 4 PA while AB/BB/HBP/SF/SH/CI account for 3. The original season labels match the smaller annual tally. Archived event traces are supplied as evidence, but no unverified cause or substitute PA is assigned. These player-seasons remain quarantined from the new usage inputs; 2026 is history-only, never a scoring target.\n\nAnnual and last60 files carry source_reconciliation_status. historical_source_reconciled_season_usage.csv excludes the one unresolved historical player-season. It is a source-reconciled dataset, not authorization to fit or change the comparison sample silently. The next model contract must explicitly define shared supported memberships, role-state labels, secondary pitcher batting treatment and fallbacks before scoring.\n'''
text=(O/'READ_ME.txt').read_text(encoding='utf-8');(O/'READ_ME.txt').write_text(text+notes,encoding='utf-8')
page=(O/'reconstruction_report.html').read_text(encoding='utf-8');page=page.replace('</html>','<h2>Independent verification and exceptions</h2><pre>'+html.escape(notes)+'</pre></html>');(O/'reconstruction_report.html').write_text(page,encoding='utf-8')
shutil.copy2(__file__,O/'verify_game_usage.py')
dump('output_sha256.json',{p.name:sha(p) for p in O.iterdir() if p.is_file() and p.name!='output_sha256.json'})
with zipfile.ZipFile(str(O)+'.zip','w',zipfile.ZIP_DEFLATED) as z:
 for p in O.iterdir():z.write(p,arcname=O.name+'/'+p.name)
with zipfile.ZipFile(str(O)+'.zip') as z:assert z.testzip() is None
print(json.dumps(verify,indent=2));print('Event traces',json.dumps(events,indent=2));print('ZIP bytes',Path(str(O)+'.zip').stat().st_size)
