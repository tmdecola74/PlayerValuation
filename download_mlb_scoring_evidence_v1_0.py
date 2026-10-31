"""Resumable MLB game evidence download from a reconciliation fetch plan."""
import argparse
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from urllib.request import Request,urlopen
from actuals_scoring_v1_0 import *


def fetch(url,timeout=120):
 with urlopen(Request(url,headers={'User-Agent':'PlayerValuation/1.0 historical scoring audit'}),timeout=timeout) as response:
  data=response.read(32*1024*1024+1)
  if len(data)>32*1024*1024:raise ValueError('MLB game response exceeds 32 MiB')
  return data


def download(plan,cache,scope='player_changes',max_games=25,pause=1,fetcher=fetch):
 if max_games<0 or pause<0:raise ValueError('Nonnegative max-games/pause required')
 cache=Path(cache).resolve();cache.mkdir(parents=True,exist_ok=True);lock=cache/'download.lock'
 fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
 complete=0;skipped=0;failed=[];attempted=0
 try:
  indexed={}
  for line,row in checked_rows(plan):
   game=integer(row['game_pk'],'game_pk');year=integer(row['season'],'season')
   if game in indexed:raise ValueError('Duplicate fetch-plan game')
   indexed[game]=(year,row['priority'])
  for game,(year,priority) in sorted(indexed.items()):
   if scope=='player_changes' and priority!='PLAYER_CHANGE_OR_INVALID_PA':continue
   if scope=='all_review_games' and priority=='FULL_COVERAGE_ONLY':continue
   existing=cache/str(game)
   if existing.exists():
    if read_cached_feed(cache,game,year) is None:raise ValueError('Incomplete cached directory: '+str(existing))
    skipped+=1;continue
   if max_games and attempted>=max_games:break
   attempted+=1;directory=Path(tempfile.mkdtemp(prefix=str(game)+'.staging-',dir=cache))
   url=f'https://statsapi.mlb.com/api/v1.1/game/{game}/feed/live'
   try:
    error=None
    for retry in range(3):
     try:
      raw=fetcher(url);payload=validate_feed(json.loads(raw),game,year);break
     except Exception as exc:
      error=exc
      if retry==2:raise
      time.sleep(min(4,2**retry))
    (directory/'feed.json').write_bytes(raw)
    dump(directory/'source.json',dict(game_pk=game,season=year,url=url,retrieved_at=now(),sha256=sha(directory/'feed.json')))
    os.replace(directory,existing);complete+=1
    print(f'{year} game {game}: cached',flush=True)
   except Exception as exc:
    failed.append(dict(game_pk=game,error=str(exc)));shutil.rmtree(directory,ignore_errors=True)
    print(f'game {game}: FAILED {exc}',flush=True)
   time.sleep(pause)
  return dict(completed_this_run=complete,verified_skipped=skipped,failed=failed,cache=str(cache),scope=scope,max_games=max_games)
 finally:lock.unlink(missing_ok=True)


def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',required=True);p.add_argument('--cache',default='data/mlb_scoring_evidence_v1_0');p.add_argument('--scope',choices=['player_changes','all_review_games','all_games'],default='player_changes');p.add_argument('--max-games',type=int,default=25,help='New games this run; 0 means all selected games');p.add_argument('--pause-seconds',type=float,default=1)
 a=p.parse_args();r=download(a.plan,a.cache,a.scope,a.max_games,a.pause_seconds);print(json.dumps(r,indent=2));return 1 if r['failed'] else 0
if __name__=='__main__':raise SystemExit(main())
