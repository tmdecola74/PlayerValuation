"""Reconcile cached MLB usage and certify a fixed hitter cohort. No forecasts fitted."""
import csv,json,hashlib,sys,math,zipfile,html,shutil
from pathlib import Path
from collections import Counter,defaultdict
R=Path('D:/JonAPythonClass/pycharm/PlayerValuation');sys.path.insert(0,str(R))
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
from pitcher_label_coverage_v1_26 import standings,schedule,boxscore,pitching_outs
O=Path('outputs/2027_game_usage_reconstruction');O.mkdir(exist_ok=True)
watch={};issues=[];reconciliation=[];seasons=[];totals=[];certs=[];late=[];special=[];games_out=[]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def take(p):p=Path(p);watch[str(p.resolve())]=sha(p);return p
def read(p):
 with take(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def load(p):return json.loads(take(p).read_text(encoding='utf-8-sig'))
def dump(n,x):(O/n).write_text(json.dumps(x,indent=2),encoding='utf-8')
def save(n,rr):
 if not rr:return
 with (O/n).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def issue(y,game,team,pid,code,detail,severity='REVIEW'):
 issues.append(dict(season=y,game_pk=game,team_id=team,mlbam_id=pid,code=code,detail=str(detail),severity=severity))
contract=dict(version='GAME_USAGE_0.1',registered_before_reconstruction=True,years=list(range(2019,2027)),scope='MLB regular season only. 2019–2025 historical adapter/certification; 2026 separate 2027-history-only outputs.',hitter_cohort='For target Y, freeze exact MLBAM IDs with positive eligible MLB PA in any of Y-4..Y-1, matching baseline history policy. Includes secondary-role batting records; no roster/debut/prospect expansion.',appearance='Credited batting gamesPlayed=1, including zero-PA appearances; roster listing is not appearance. Pitching gamesPitched=1, including zero-out/no-pitch appearances.',starts='Batting initial order code 100..900 ending00, corroborated with isSubstitute where present. A starting batting-order assignment is distinct from credited G. Pitching gamesStarted splits actual outing outs; never season IP/GS.',lineup='Store each batting order code, slot, substitution index and starting flag; no inference from final team battingOrder alone.',late_window='Last60 completed regular-season team games in each source season, sorted officialDate/gameNumber/gamePk; trades remain in game/team records. No target-season features.',zero_policy='Only certify absent members of frozen prior-positive-PA cohort when full-season schedule/standings and every game validate and no eligible source positive label contradicts absence. Numeric mismatches quarantine affected player usage. Unknown is not zero.',identity='Canonical positive MLBAM from eligible prior-history labels; source role and each boxscore person.id exact. No name-only links and no current roster requirement for historical nonappearance.',source='Read-only existing cached official MLB JSON wrappers, bound to original certification hashes; no new download or current depth charts',forecast_changes=False,model_fits=False,forecast_errors_scored=False)
dump('build_contract.json',contract)
lab=R/'outputs/training_labels_v1_0';train=take(lab/'training_labels.parquet');hold=take(lab/'holdout_labels.parquet');hp=take(R/'outputs/recent_history_skills_v1_23/historical_forecasts.csv');ov=R/'outputs/participation_label_overlay_v1_27'
for p in [ov/'report.json',ov/'participation_label_overlay.csv',R/'pitcher_label_coverage_v1_26.py',R/'participation_label_overlay_v1_27.py']:
 take(p)
a,_=apply_overlay(ov,labels(train),train,hp,watch);a.update(labels(hold,2026))
for r in read(R/'outputs/pitcher_evaluation_v1_29/evaluation_label_overlay_2026.csv'):
 for m,c in [('G','evaluation_g'),('OUTS','evaluation_outs')]:a[2026,'pitcher',r['mlbam_id'],m]=float(r[c])
for role in ['hitter','pitcher']:
 take(Path('outputs/2027_statcast_strengthened_validation')/f'2027_{role}s_working_v1_43.csv');take(R/'outputs/skill_regressed_release_v1_43'/f'projections_2027_{role}s.csv')
take(R/'projection_phase_v1_42.py');take(R/'outputs/projection_phase_v1_42/frozen_choices.json')
cohorts={y:sorted({pid for (s,role,pid,m),v in a.items() if y-4<=s<y and role=='hitter' and m=='PA' and v>0},key=int) for y in range(2019,2027)}
save('frozen_hitter_cohort_membership.csv',[dict(target_season=y,mlbam_id=p,identity_basis='EXACT_PRE_ORIGIN_POSITIVE_ELIGIBLE_MLB_PA',prior_positive_seasons=';'.join(str(s) for s in range(y-4,y) if (a.get((s,'hitter',p,'PA')) or 0)>0),history_window=f'{y-4}-{y-1}') for y,pp in cohorts.items() for p in pp])
def integer(s,k,default=None):
 v=s.get(k,default)
 if type(v) is not int or v<0:raise ValueError(f'{k} must be nonnegative integer, got {v!r}')
 return v
def lineup(code,sub):
 if code in (None,''):return None,None,None
 c=str(code)
 if not c.isdigit():raise ValueError('Non-numeric batting order '+c)
 k=int(c);slot=k//100;replacement=k%100
 return slot,replacement,slot in range(1,10) and replacement==0
def aggregate(rows,role,y):
 agg={}
 for r in rows:
  p=r['mlbam_id'];v=agg.setdefault(p,Counter())
  for m in (['G','PA','AB','H','BB','SO','HBP','SF','SH','CI','STARTS'] if role=='hitter' else ['G','GS','GR','OUTS','START_OUTS','RELIEF_OUTS','ZERO_OUT_APPEARANCES']):v[m]+=r[m]
  v['LINEUP_UNKNOWN']+=int(role=='hitter' and r['lineup_slot'] is None) if role=='hitter' else 0
 for p,v in agg.items():
  row=dict(season=y,role=role,mlbam_id=p,name=next(r['name'] for r in rows if r['mlbam_id']==p),**dict(v))
  if role=='pitcher':
   assert v['GS']+v['GR']==v['G'] and v['START_OUTS']+v['RELIEF_OUTS']==v['OUTS']
   row.update(IP=v['OUTS']/3,IP_per_start=v['START_OUTS']/3/v['GS'] if v['GS'] else None,IP_per_relief=v['RELIEF_OUTS']/3/v['GR'] if v['GR'] else None)
  else:row.update(PA_per_G=v['PA']/v['G'] if v['G'] else None,starting_share=v['STARTS']/v['G'] if v['G'] else None)
  totals.append(row)
 return agg
for y in range(2019,2027):
 root=R/'cache/pitcher_appearance_mlb'/str(y);certroot=R/'outputs'/('pitcher_label_coverage_2023_corrected' if y==2023 else f'pitcher_label_coverage_{y}_v1_26_1')
 if y==2026:certroot=R/'outputs/pitcher_evaluation_v1_29'
 original=load(certroot/'report.json');bound=load(certroot/'input_hashes.json');bound={str(Path(k).resolve()):v for k,v in bound.items()}
 def cached(p):
  raw=p.read_bytes();h=hashlib.sha256(raw).hexdigest();key=str(p.resolve());assert bound.get(key)==h,('Source hash not bound',key);watch[key]=h;doc=json.loads(raw);assert doc['url'].startswith('https://statsapi.mlb.com/api/v1/');return doc['payload']
 std=cached(root/'standings.json');sch=cached(root/'schedule.json');expected=standings(std,y);games,complete,unresolved,counts=schedule(sch,y,expected);assert complete and not unresolved
 meta={}
 for d in sch['dates']:
  for g in d['games']:
   if g['gamePk'] in games:meta[g['gamePk']]=dict(date=g.get('officialDate') or d['date'],number=g.get('gameNumber',1),doubleheader=g.get('doubleHeader','N'))
 teamorder=defaultdict(list)
 for game,teams in games.items():
  for tid in teams:teamorder[tid].append(game)
 ordinal={}
 for tid,gg in teamorder.items():
  for i,g in enumerate(sorted(gg,key=lambda g:(meta[g]['date'],meta[g]['number'],g)),1):ordinal[tid,g]=i
 hrows=[];prows=[];game_bad=0;start_bad=0;teamchecks=0;credited_pitch=Counter();seenkeys=set()
 for index,(game,teams) in enumerate(sorted(games.items()),1):
  p=root/f'game_{game}.json'
  try:
   doc=cached(p);credited=boxscore(doc,teams)
   stagedh=[];stagedp=[]
   for side,tid in zip(['away','home'],teams):
    b=doc['teams'][side];sums=Counter();slots=Counter();batlist=set(map(str,b['batters']));pitchlist=set(map(str,b['pitchers']))
    for key,player in b['players'].items():
     pid=str(player['person']['id']);assert key=='ID'+pid
     bs=player['stats'].get('batting',{});ps=player['stats'].get('pitching',{});name=player['person']['fullName'];base=dict(season=y,game_pk=game,official_date=meta[game]['date'],game_number=meta[game]['number'],team_id=tid,side=side,mlbam_id=pid,name=name,team_game_ordinal=ordinal[tid,game],in_last60_team_games=ordinal[tid,game]>len(teamorder[tid])-60,source_file=str(p))
     if bs:
      gp=integer(bs,'gamesPlayed');assert gp in [0,1]
      vals={m:integer(bs,k,0) for m,k in [('PA','plateAppearances'),('AB','atBats'),('H','hits'),('BB','baseOnBalls'),('SO','strikeOuts'),('HBP','hitByPitch'),('SF','sacFlies'),('SH','sacBunts'),('CI','catchersInterference')]}
      for m,v in vals.items():sums[m]+=v
      slot,repl,initial=lineup(player.get('battingOrder'),player.get('gameStatus',{}).get('isSubstitute'))
      if initial:slots[slot]+=1
      if gp:
       assert pid in batlist or vals['PA']==0,('Unlisted active batter',pid)
       if vals['PA'] and slot not in range(1,10):raise ValueError(('PA with no valid batting slot',pid,slot))
       if initial and player.get('gameStatus',{}).get('isSubstitute') is True:issue(y,game,tid,pid,'INITIAL_ORDER_SUBSTITUTE_FLAG_CONFLICT',player['gameStatus'])
       stagedh.append(dict(base,G=1,**vals,batting_order_code=player.get('battingOrder'),lineup_slot=slot,substitution_index=repl,initial_order_assignment=initial,STARTS=int(initial is True),lineup_start_status='INITIAL_BATTING_ORDER' if initial else 'SUBSTITUTE_BATTING_SLOT' if slot in range(1,10) else 'NO_BATTING_SLOT_CREDITED_APPEARANCE',is_substitute=player.get('gameStatus',{}).get('isSubstitute')))
      elif vals['PA']:raise ValueError(('PA with no credited batting G',pid))
     if ps:
      gp=integer(ps,'gamesPitched');gs=integer(ps,'gamesStarted');outs=integer(ps,'outs');assert outs==pitching_outs(ps['inningsPitched'])
      if gp:
       assert gs in [0,1] and pid in pitchlist
       stagedp.append(dict(base,G=1,GS=gs,GR=1-gs,OUTS=outs,START_OUTS=outs if gs else 0,RELIEF_OUTS=outs if not gs else 0,ZERO_OUT_APPEARANCES=int(outs==0),IP_decimal=outs/3,IP_baseball=ps['inningsPitched'],number_of_pitches=ps.get('numberOfPitches'),batters_faced=ps.get('battersFaced'),pitching_role='START' if gs else 'RELIEF'))
    for m,k in [('PA','plateAppearances'),('AB','atBats'),('H','hits'),('BB','baseOnBalls'),('SO','strikeOuts'),('HBP','hitByPitch'),('SF','sacFlies'),('SH','sacBunts'),('CI','catchersInterference')]:
     target=integer(b['teamStats']['batting'],k,0);assert sums[m]==target,('Team batting sum',m,sums[m],target)
    teamchecks+=1
    if set(slots)!=set(range(1,10)) or any(v!=1 for v in slots.values()):
     start_bad+=1;issue(y,game,tid,'','INITIAL_LINEUP_SLOTS_REQUIRE_REVIEW',dict(slots))
    teamprows=[r for r in stagedp if r['team_id']==tid]
    assert sum(r['GS'] for r in teamprows)==1,('Team pitcher starts',tid)
   assert {int(r['mlbam_id']) for r in stagedp}==credited
   for role,rr in [('hitter',stagedh),('pitcher',stagedp)]:
    for r in rr:
     k=(role,game,r['team_id'],r['mlbam_id']);assert k not in seenkeys;seenkeys.add(k)
   hrows.extend(stagedh);prows.extend(stagedp)
   games_out.append(dict(season=y,game_pk=game,date=meta[game]['date'],away=teams[0],home=teams[1],source_hash=watch[str(p.resolve())],status='VERIFIED'))
  except Exception as e:
   game_bad+=1;issue(y,game,'','','GAME_RECONSTRUCTION_FAILED',repr(e),'BLOCKING');games_out.append(dict(season=y,game_pk=game,status='FAILED',detail=repr(e)))
 safe=game_bad==0 and teamchecks==2*len(games)
 save(f'hitter_game_usage_{y}.csv',hrows);save(f'pitcher_game_usage_{y}.csv',prows)
 ha=aggregate(hrows,'hitter',y);pa=aggregate(prows,'pitcher',y)
 # Exact per-player season reconciliation for all eligible source labels, not only cohort members.
 affected=defaultdict(set);positive_missing=defaultdict(set);mismatch=Counter()
 for role,agg,metrics in [('hitter',ha,['G','PA','AB','H','BB','SO','HBP','SF','SH']),('pitcher',pa,['G','GS','OUTS'])]:
  for (s,typ,pid,m),v in a.items():
   if s!=y or typ!=role or m not in metrics:continue
   observed=agg.get(pid,{}).get(m,0);ok=observed==v
   reconciliation.append(dict(season=y,role=role,mlbam_id=pid,metric=m,source_label=v,reconstructed=observed,difference=observed-v,status='MATCH' if ok else 'MISMATCH',source='ELIGIBLE_LABEL_WITH_EXISTING_CERTIFIED_OVERLAY'))
   if not ok:
    mismatch[role,m]+=1;affected[role].add(pid)
    if v>0 and not agg.get(pid,{}).get('G'):positive_missing[role].add(pid)
 for role,rr in [('hitter',hrows),('pitcher',prows)]:
  grouped=defaultdict(list)
  for r in rr:
   if r['in_last60_team_games']:grouped[r['mlbam_id']].append(r)
  for pid,xx in grouped.items():
   v=Counter()
   for r in xx:
    for m in (['G','PA','STARTS'] if role=='hitter' else ['G','GS','GR','OUTS','START_OUTS','RELIEF_OUTS']):v[m]+=r[m]
   late.append(dict(season=y,role=role,mlbam_id=pid,name=xx[0]['name'],teams=';'.join(sorted({str(r['team_id']) for r in xx})),window='Last60 completed games of each source team; actual game/team/player records only',**dict(v),lineup_slot_counts=json.dumps(dict(Counter(r['lineup_slot'] for r in xx if r.get('lineup_slot') in range(1,10)))) if role=='hitter' else '',source_usage_reconciled=pid not in affected[role],usage_scope='2027_HISTORY_ONLY' if y==2026 else 'PRE_ORIGIN_FEATURE_SOURCE'))
 for pid in cohorts[y]:
  v=ha.get(pid,{});g=v.get('G',0);sourceg=a.get((y,'hitter',pid,'G'));sourcepa=a.get((y,'hitter',pid,'PA'));status='VERIFIED_APPEARED' if g else 'VERIFIED_NO_APPEARANCE'
  # Source numerical disagreements are not silent corrections. Full absence safety requires no missing positive source player.
  if not safe or positive_missing['hitter']:status='UNKNOWN_SEASON_SCOPE_OR_POSITIVE_LABEL_CONFLICT'
  elif pid in affected['hitter']:status='APPEARANCE_VERIFIED_USAGE_RECONCILIATION_PENDING' if g else 'CONFLICT_TARGET_LABEL'
  certs.append(dict(season=y,mlbam_id=pid,status=status,observed_G=g,observed_PA=v.get('PA',0),source_G=sourceg,source_PA=sourcepa,certified_nonappearance=status=='VERIFIED_NO_APPEARANCE',proposed_G=0 if status=='VERIFIED_NO_APPEARANCE' else None,proposed_PA=0 if status=='VERIFIED_NO_APPEARANCE' else None,season_scope_complete=safe,identity_basis='EXACT_PRE_ORIGIN_POSITIVE_ELIGIBLE_MLB_PA',cohort_history=f'{y-4}-{y-1}',usage='2027_HISTORY_ONLY' if y==2026 else 'HISTORICAL_CERTIFICATION_NOT_APPLIED_TO_BASELINE'))
 for r in hrows:
  if r['PA']==0 or r['lineup_slot'] not in range(1,10):special.append(dict(role='hitter',reason='ZERO_PA_CREDITED_G' if r['PA']==0 else 'NO_VALID_BATTING_SLOT',**r))
 for r in prows:
  if r['OUTS']==0 or r['number_of_pitches']==0:special.append(dict(role='pitcher',reason='ZERO_OUT_OR_NO_PITCH_CREDITED_G',**r))
 seasons.append(dict(season=y,scheduled_completed_games=len(games),verified_games=len(games)-game_bad,team_batting_sums_verified=teamchecks,full_scope_verified=safe,lineup_slot_exceptions=start_bad,hitter_usage_rows=len(hrows),pitcher_usage_rows=len(prows),hitter_players=len(ha),pitcher_players=len(pa),hitter_source_usage_mismatches=sum(v for (role,m),v in mismatch.items() if role=='hitter'),pitcher_source_usage_mismatches=sum(v for (role,m),v in mismatch.items() if role=='pitcher'),source_positive_hitters_missing=len(positive_missing['hitter']),source_positive_pitchers_missing=len(positive_missing['pitcher']),cohort_players=len(cohorts[y]),hitter_status_counts=dict(Counter(r['status'] for r in certs if r['season']==y)),usage='2027_HISTORY_ONLY' if y==2026 else 'HISTORICAL_ADAPTER_ONLY'))
 print(json.dumps(seasons[-1]),flush=True)
save('season_scope_and_reconciliation.csv',seasons);save('season_usage_totals.csv',totals);save('last60_team_game_usage.csv',late);save('hitter_participation_certification.csv',certs);save('historical_hitter_nonappearance_overlay_PROPOSED_NOT_APPLIED.csv',[r for r in certs if r['season']<=2025 and r['certified_nonappearance']]);save('season_label_reconciliation.csv',reconciliation);save('reconstruction_issues.csv',issues);save('special_appearance_evidence.csv',special);save('game_scope_inventory.csv',games_out)
dump('run_summary.json',dict(status='REVIEW_REQUIRED' if any(not s['full_scope_verified'] or s['lineup_slot_exceptions'] or s['hitter_source_usage_mismatches'] or s['pitcher_source_usage_mismatches'] for s in seasons) else 'RECONCILED',seasons=seasons,issue_counts=dict(Counter(r['code'] for r in issues)),models_fitted=False,forecast_errors_scored=False,baseline_changed=False))
dump('source_manifest.json',watch)
print('Reconstruction complete; inspect issues before release.',flush=True)
