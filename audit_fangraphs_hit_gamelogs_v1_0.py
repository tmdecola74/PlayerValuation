"""Compare supplied FanGraphs game logs against the frozen targeted MLB audit. Read-only."""
import argparse,csv,json,hashlib,shutil,tempfile
from pathlib import Path
from collections import Counter
from datetime import date

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:
  r=csv.reader(f);headers=next(r);rows=list(r)
 if any(len(row)!=len(headers) for row in rows):raise ValueError('Ragged CSV')
 return headers,rows

def integer(v):
 if not str(v).isdigit():raise ValueError('Missing/noninteger count: '+str(v))
 return int(v)

def csvout(p,rows,headers):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=headers);w.writeheader();w.writerows(rows)

def audit(log_dir,prior,output,feeds=None):
 log_dir,prior,output=map(lambda p:Path(p).resolve(),(log_dir,prior,output))
 if output.exists():raise FileExistsError(output)
 h,rr=read(prior/'season_comparisons.csv');cases=[dict(zip(h,r)) for r in rr]
 logs=json.loads((prior/'normalized_game_logs.json').read_text())
 h,rr=read(prior/'game_log_comparisons.csv');recons=[dict(zip(h,r)) for r in rr]
 targets={(r['season'],r['player_type'],r['mlbam_id']) for r in cases}
 fingerprints={str(p):sha(p) for p in [prior/'season_comparisons.csv',prior/'normalized_game_logs.json',prior/'game_log_comparisons.csv']}
 supplied={};warnings=[]
 for p in sorted(log_dir.glob('fangraphs-game-log-*.csv')):
  headers,rr=read(p);duplicates={h:n for h,n in Counter(headers).items() if n>1}
  if any(h!='GS' for h in duplicates):raise ValueError('Ambiguous duplicate heading')
  if duplicates:warnings.append(dict(file=p.name,duplicate_headers=duplicates,policy='Unused GS duplicates retained in original source only'))
  required=['Date','MLBAMID','NameASCII','H'];
  if any(headers.count(h)!=1 for h in required):raise ValueError('Missing/duplicate required heading')
  records=[{h:row[i] for i,h in enumerate(headers) if h not in duplicates} for row in rr]
  if not records:raise ValueError('Empty log')
  ids={r['MLBAMID'] for r in records};years={str(date.fromisoformat(r['Date']).year) for r in records}
  if len(ids)!=1 or len(years)!=1:raise ValueError('Mixed identities/seasons')
  role='pitcher' if 'IP' in headers else 'hitter';key=(next(iter(years)),role,next(iter(ids)))
  if key not in targets or key in supplied:raise ValueError('Unexpected/duplicate target log')
  if any(r.get('G')!='1' for r in records):raise ValueError('Non-individual game row')
  for r in records:
   if role=='hitter' and integer(r['H'])!=sum(integer(r[m]) for m in ['1B','2B','3B','HR']):raise ValueError('Incoherent hit components')
  supplied[key]=(p,records);fingerprints[str(p)]=sha(p)
 if set(supplied)!=targets:raise ValueError('Missing target logs')
 seasons=[];allrows=[];diffs=[];unmatched=[];date_groups=[]
 for c in cases:
  target=(c['season'],c['player_type'],c['mlbam_id']);p,records=supplied[target];m=c['metric']
  ml=[r for r in logs if (str(r['season']),r['player_type'],str(r['mlbam_id']))==target]
  ml_by_date={d:[r for r in ml if r['date']==d] for d in {r['date'] for r in ml}}
  fg_by_date={d:[r for r in records if r['Date']==d] for d in {r['Date'] for r in records}}
  metric_rows=[]
  for day in sorted(set(ml_by_date)|set(fg_by_date)):
   left=fg_by_date.get(day,[]);right=ml_by_date.get(day,[])
   if len(left)!=1 or len(right)!=1:
    if len(left)==len(right) and len(left)>1:
     fg_total=sum(integer(r[m]) for r in left);mlb_total=sum(integer(r[m]) for r in right)
     date_groups.append(dict(season=c['season'],mlbam_id=c['mlbam_id'],metric=m,date=day,fg_rows=len(left),mlb_rows=len(right),fangraphs_date_total=fg_total,mlb_date_total=mlb_total,difference=fg_total-mlb_total,status='DATE_AGGREGATE_ONLY_NO_GAME_ASSIGNMENT'))
    else:unmatched.append(dict(season=c['season'],mlbam_id=c['mlbam_id'],metric=m,date=day,fg_rows=len(left),mlb_rows=len(right),fangraphs_count=sum(integer(r[m]) for r in left) if left else None,mlb_count=sum(integer(r[m]) for r in right) if right else None,status='UNMATCHED_DATE_NO_GUESS'))
    continue
   f,l=left[0],right[0];value=integer(f[m]);delta=value-integer(l[m]);game=str(l['game_pk'])
   recon=[r for r in recons if (r['season'],r['player_type'],r['mlbam_id'],r['metric'],r['game_pk'])==target+(m,game)]
   if len(recon)!=1:raise ValueError('Missing/ambiguous frozen game comparison')
   rv=recon[0]['reconstructed_evidence']
   row=dict(season=c['season'],player_type=c['player_type'],mlbam_id=c['mlbam_id'],name=c['name'],metric=m,date=day,game_pk=game,team=f['Team'],opponent=f['Opp'],fangraphs_game_count=value,mlb_game_count=integer(l[m]),reconstructed_game_count=rv,fg_minus_mlb=delta,status='DIFFERENCE' if delta else 'MATCH',source_file=p.name)
   allrows.append(row);metric_rows.append(row)
   if delta:diffs.append(row)
  fgsum=sum(integer(r[m]) for r in records)
  if sum(r['fg_minus_mlb'] for r in metric_rows)!=fgsum-integer(c['mlb_season_count']):raise ValueError('Located game differences do not fully bridge season difference')
  if fgsum!=integer(c['fangraphs_season_count']):raise ValueError('New FanGraphs log does not reproduce original supplied season total')
  if sum(integer(r[m]) for r in ml)!=integer(c['mlb_season_count']):raise ValueError('Frozen MLB sums inconsistent')
  seasons.append(dict(season=c['season'],player_type=c['player_type'],mlbam_id=c['mlbam_id'],name=c['name'],metric=m,fangraphs_original=integer(c['fangraphs_season_count']),fangraphs_log_sum=fgsum,reconstructed=integer(c['reconstructed_season_count']),mlb_log_sum=integer(c['mlb_season_count']),differing_game_rows=sum(r['fg_minus_mlb']!=0 for r in metric_rows),difference_sum=sum(r['fg_minus_mlb'] for r in metric_rows)))
 inspections=[];plays=[];feed_paths=[]
 if feeds:
  feeds=Path(feeds)
  for g in sorted({r['game_pk'] for r in diffs}):
   p=feeds/f'{g}.json';meta=feeds/f'{g}.source.json';mdata=json.loads(meta.read_text())
   if sha(p)!=mdata['sha256']:raise ValueError('Feed hash mismatch')
   d=json.loads(p.read_bytes())
   if str(d['gamePk'])!=g or d['gameData']['game']['type']!='R':raise ValueError('Wrong feed game/type')
   target_rows=[r for r in diffs if r['game_pk']==g];expected_dates={r['date'] for r in target_rows}
   if expected_dates!={d['gameData']['datetime']['officialDate']}:raise ValueError('Wrong game date')
   for side,t in d['liveData']['boxscore']['teams'].items():
    for role,group in [('hitter','batting'),('pitcher','pitching')]:
     if sum(integer(p['stats'].get(group,{}).get('hits',0)) for p in t['players'].values())!=integer(t['teamStats'][group]['hits']):raise ValueError('Player/team hit sum mismatch')
   for r in target_rows:
    matches=[(side,t['players']['ID'+r['mlbam_id']]) for side,t in d['liveData']['boxscore']['teams'].items() if 'ID'+r['mlbam_id'] in t['players']]
    if len(matches)!=1:raise ValueError('Feed player ambiguity')
    side,player=matches[0];stat=player['stats']['batting' if r['player_type']=='hitter' else 'pitching']
    v=integer(stat['hits']) if r['metric']=='H' else integer(stat['hits'])-sum(integer(stat[x]) for x in ['doubles','triples','homeRuns']) if r['metric']=='1B' else integer(stat[{'2B':'doubles','3B':'triples','HR':'homeRuns'}[r['metric']]])
    inspections.append(dict(**r,mlb_feed_boxscore=v,feed_agrees_with_frozen_mlb=v==r['mlb_game_count']))
   for play in d['liveData']['plays']['allPlays']:
    for r in target_rows:
     if r['player_type']!='hitter' or str(play['matchup']['batter']['id'])!=r['mlbam_id']:continue
     res=play['result'];pitcher=str(play['matchup']['pitcher']['id'])
     plays.append(dict(game_pk=g,date=r['date'],batter=r['name'],batter_id=r['mlbam_id'],pitcher_id=pitcher,paired_discrepant_pitcher=any(x['player_type']=='pitcher' and x['mlbam_id']==pitcher for x in target_rows),at_bat_index=play['about']['atBatIndex'],inning=play['about']['inning'],half=play['about']['halfInning'],event=res.get('event'),event_type=res.get('eventType'),description=res.get('description'),evidence_status='MLB_PLAY_ONLY_NOT_FANGRAPHS_PLAY_ALIGNMENT'))
   feed_paths.extend([p,meta]);fingerprints.update({str(p):sha(p),str(meta):sha(meta)})
 plays=list({(r['game_pk'],r['batter_id'],r['at_bat_index']):r for r in plays}.values())
 if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Input changed')
 output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
 try:
  for name,rows in [('season_comparisons',seasons),('game_comparisons',allrows),('differing_games',diffs),('game_boxscore_inspections',inspections),('mlb_target_batter_plays',plays),('doubleheader_date_aggregates',date_groups)]:
   if rows:csvout(stage/(name+'.csv'),rows,list(rows[0]))
  for p,_ in supplied.values():
   q=stage/'source_files'/p.name;q.parent.mkdir(exist_ok=True);shutil.copyfile(p,q)
  for p in feed_paths:
   q=stage/'mlb_game_feeds'/p.name;q.parent.mkdir(exist_ok=True);shutil.copyfile(p,q)
  report=dict(version='1.0.0',target_player_season_roles=len(targets),selected_metric_rows=len(cases),compared_game_metric_rows=len(allrows),differing_metric_rows=len(diffs),distinct_games=len({r['game_pk'] for r in diffs}),all_fangraphs_logs_reproduce_original_season_totals=True,unmatched_or_ambiguous_dates=unmatched,doubleheader_date_aggregates=date_groups,source_heading_warnings=warnings,counts_modified=False,model_ready=False,limitations=['Game log differences locate dates, not individual scoring decisions.','MLB play candidates are not FanGraphs play alignment or proof of dated scoring revisions.','Two zero-hit Wainwright appearances have no frozen MLB role game-log entry.','No original actuals reference or Statcast file is changed.'])
  (stage/'audit_report.json').write_text(json.dumps(report,indent=2));(stage/'input_hashes.json').write_text(json.dumps(fingerprints,indent=2))
  stage.rename(output);return report
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--logs',required=True);p.add_argument('--prior',required=True);p.add_argument('--output',required=True);p.add_argument('--feeds');a=p.parse_args();print(json.dumps(audit(a.logs,a.prior,a.output,a.feeds),indent=2))
