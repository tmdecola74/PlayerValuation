"""Repair evidence/report separation using existing reports/cache; no pitch rescan."""
import argparse
import csv
import json
import shutil
from collections import Counter
from pathlib import Path
from actuals_scoring_v1_0 import *


def read_csv(path):
 with Path(path).open(encoding='utf-8-sig',newline='') as f:
  r=csv.DictReader(f);return r.fieldnames,list(r)

def truth(v):return str(v).lower()=='true'

def partition_report_rows(rows):
 primary=[];other=[]
 for row in rows:
  # A blank season reference plus a blank physical terminal count was introduced
  # solely by unioning partial boxscore keys. Keep it outside season comparisons.
  if row.get('fangraphs_actual','')=='' and row.get('terminal_count','')=='':other.append(row)
  else:primary.append(row)
 return primary,other


def repair(source,cache,output,backup_root='backups',event_rows=None):
 source=Path(source).resolve();cache=Path(cache).resolve()
 required=['player_metric_reconciliation.csv','pa_scoring_trace.jsonl','mlb_feed_usage.json','mlb_pa_evidence.jsonl','reconciliation_report.json','source_windows.json']
 if any(not (source/n).is_file() for n in required):raise ValueError('Source must be a complete original reconciliation folder')
 originals={str(p):sha(p) for p in source.rglob('*') if p.is_file()}
 report=json.loads((source/'reconciliation_report.json').read_text(encoding='utf-8'))
 traces=[json.loads(s) for s in (source/'pa_scoring_trace.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
 usage=json.loads((source/'mlb_feed_usage.json').read_text(encoding='utf-8'));payloads={};feed_hashes={}
 for item in usage:
  game=item['game_pk'];year=item['season'];payload=read_cached_feed(cache,game,year)
  if payload is None:raise ValueError('Missing original used game cache: '+str(game))
  path=cache/str(game)/'feed.json'
  if sha(path)!=item['feed_sha256']:raise ValueError('Used feed differs from original run: '+str(game))
  feed_hashes[str(path)]=sha(path);feed_hashes[str(path.parent/'source.json')]=sha(path.parent/'source.json');payloads[game]=payload
 for trace in traces:
  if trace['game_pk'] in payloads:confirm_trace_from_feed(trace,payloads[trace['game_pk']])
 unresolved={(t['season'],role,int(p['batter' if role=='hitter' else 'pitcher'])) for t in traces for role in t.get('unresolved_roles',[]) for p in t['sequence']}
 headers,rows=read_csv(source/'player_metric_reconciliation.csv');primary,evidence_only=partition_report_rows(rows)
 for row in primary:
  key=(int(row['season']),row['player_type'],int(row['mlbam_id']))
  if truth(row.get('sequence_review','')) and key not in unresolved:
   row['sequence_review']='False'
   if row['status']=='MATCH_WITH_SEQUENCE_REVIEW':row['status']='EXACT_TERMINAL_MATCH'
 discrepancy_status={'UNRESOLVED_DIFFERENCE','NO_STATCAST_PLAYER_OBSERVATION','NO_FANGRAPHS_REFERENCE','MATCH_WITH_SEQUENCE_REVIEW'}
 differences=[r for r in primary if r['status'] in discrepancy_status]
 summary=Counter((int(r['season']),r['player_type'],r['status']) for r in primary)
 advisory_candidates=[];advisory_evidence=[]
 evidence=[json.loads(s) for s in (source/'mlb_pa_evidence.jsonl').read_text(encoding='utf-8').splitlines() if s.strip()]
 # Include unknown/advisory cases that the original changed-player filter missed.
 if event_rows and Path(event_rows).is_file():
  originals[str(Path(event_rows).resolve())]=sha(event_rows)
  _,events=read_csv(event_rows)
  windows={r['day']:r for r in json.loads((source/'source_windows.json').read_text(encoding='utf-8'))}
  for row in events:
   w=windows.get(row['source_day'])
   if not w or row['source_run_id']!=w['run_id']:raise ValueError('Event inspection uses a different frozen source run')
   game=int(row['game_pk']);pa=int(row['at_bat_number']);payload=payloads.get(game)
   if payload is None:continue
   for play in payload['liveData'].get('plays',{}).get('allPlays',[]):
    index=play.get('atBatIndex',play.get('about',{}).get('atBatIndex'))
    pair_match=(play.get('matchup',{}).get('batter',{}).get('id')==int(row['batter']) and play.get('matchup',{}).get('pitcher',{}).get('id')==int(row['pitcher']))
    index_match=index is not None and index+1==pa
    if not (pair_match or index_match):continue
    pitches=[p for p in play.get('playEvents',[]) if p.get('isPitch')]
    advisory_candidates.append(dict(game_pk=game,statcast_at_bat_number=pa,mlb_at_bat_index=index,index_match=index_match,matchup_ids_match=pair_match,mlb_terminal_pitch_number=pitches[-1].get('pitchNumber') if pitches else None,statcast_pitch_number=row['pitch_number'],mlb_event=play.get('result',{}).get('eventType'),description=play.get('result',{}).get('description'),classification='CANDIDATE_ONLY_NO_COUNT_CHANGE'))
    advisory_evidence.append(dict(game_pk=game,statcast_event_row=row,index_match=index_match,matchup_ids_match=pair_match,mlb_play=play))
   matches=[p for p in payload['liveData'].get('plays',{}).get('allPlays',[]) if p.get('atBatIndex',p.get('about',{}).get('atBatIndex',-2))+1==pa]
   if len(matches)!=1:continue
   if not any(e['game_pk']==game and e.get('candidate_statcast_at_bat_number')==pa for e in evidence):
    evidence.append(dict(season=int(row['game_date'][:4]),game_pk=game,candidate_statcast_at_bat_number=pa,index_link='CANDIDATE_ONLY_NOT_USED_TO_MOVE_CREDIT',no_pitch_completion=not matches[0].get('pitchIndex'),statcast_event_inspection=row,mlb_play=matches[0]))
 out,stage=stage_output(output,[source,cache],backup_root)
 try:
  shutil.copytree(source,stage,dirs_exist_ok=True)
  csv_out(stage/'player_metric_reconciliation.csv',primary,headers)
  csv_out(stage/'discrepancies.csv',differences,headers)
  csv_out(stage/'mlb_evidence_only.csv',evidence_only,headers)
  csv_out(stage/'advisory_outcome_candidates.csv',advisory_candidates,['game_pk','statcast_at_bat_number','mlb_at_bat_index','index_match','matchup_ids_match','mlb_terminal_pitch_number','statcast_pitch_number','mlb_event','description','classification'])
  stats=[dict(season=y,player_type=r,status=s,metric_rows=n) for (y,r,s),n in sorted(summary.items())]
  csv_out(stage/'reconciliation_summary.csv',stats,['season','player_type','status','metric_rows'])
  for name,data in [('pa_scoring_trace.jsonl',traces),('mlb_pa_evidence.jsonl',evidence),('mlb_advisory_play_evidence.jsonl',advisory_evidence)]:
   with (stage/name).open('w',encoding='utf-8') as f:
    for row in data:f.write(json.dumps(row,allow_nan=False)+'\n')
  players={(int(r['season']),r['player_type'],int(r['mlbam_id'])) for r in differences};links=[]
  for t in traces:
   for role,col in [('hitter','batter'),('pitcher','pitcher')]:
    for pid in {p[col] for p in t['sequence']}:
     if (t['season'],role,pid) in players:links.append(dict(season=t['season'],player_type=role,mlbam_id=pid,game_pk=t['game_pk'],at_bat_number=t['at_bat_number'],trace_status=t['status']))
  csv_out(stage/'discrepancy_pa_links.csv',links,['season','player_type','mlbam_id','game_pk','at_bat_number','trace_status'])
  if not all(sha(p)==h for p,h in (originals|feed_hashes).items()):raise ValueError('Report/cache input changed during repair')
  details=dict(version=VERSION,report_repair_only=True,source_folder=str(source),source_files_unchanged=True,source_report_sha256=originals,used_feed_sha256=feed_hashes,mlb_evidence_only_rows=len(evidence_only),confirmed_inherited_k_sequences=sum('mlb_scoring_confirmation' in t for t in traces),remaining_unresolved_player_seasons=len(unresolved),numeric_differences=sum(r['status']=='UNRESOLVED_DIFFERENCE' for r in primary),note='No new counts calculated and no physical pitch file edited; unknown events remain unresolved. Original fetch-plan priorities preserved, not recomputed.')
  dump(stage/'report_repair_audit.json',details)
  report.update(version=VERSION,report_repaired_at=now(),discrepancy_metric_rows=len(differences),unresolved_sequence_player_seasons=len(unresolved),evidence_confirmed_pa_sequences=details['confirmed_inherited_k_sequences'],mlb_evidence_only_metric_rows=len(evidence_only),summary=stats,inputs_unchanged=True,inputs_unchanged_scope='Source report folder and used cache files; pitch integrity inherited from original run, not rescanned',model_ready=False,status='RECONCILIATION_REVIEW_REQUIRED',original_fetch_plan_not_reprioritized=True)
  dump(stage/'reconciliation_report.json',report)
  backup=finish_output(stage,out,backup_root)
  return details|{'discrepancy_metric_rows':len(differences),'output':str(out),'backup':backup}
 except BaseException:
  shutil.rmtree(stage,ignore_errors=True);raise


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',default='outputs/actuals_statcast_reconciliation_v1_0_targeted');p.add_argument('--cache',default='data/mlb_scoring_evidence_v1_0');p.add_argument('--output',default='outputs/actuals_statcast_reconciliation_v1_0_1');p.add_argument('--backup-root',default='backups');p.add_argument('--event-rows',default='outputs/actuals_event_inspection_v1_0/event_rows.csv')
 a=p.parse_args();r=repair(a.source,a.cache,a.output,a.backup_root,a.event_rows)
 print(json.dumps({k:v for k,v in r.items() if k not in ['source_report_sha256','used_feed_sha256']},indent=2))
if __name__=='__main__':main()
