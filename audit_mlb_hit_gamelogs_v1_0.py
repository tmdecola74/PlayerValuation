"""Compare targeted MLB regular-season player game logs with frozen game totals.
No source corrections; requests are cached, resumable, hashed and backed up.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
import shutil
import tempfile
import time
from collections import defaultdict, Counter
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

VERSION='1.0.0'
HIT_METRICS={'H','1B','2B','3B','HR'}
GROUP={'hitter':'hitting','pitcher':'pitching'}
FIELDS={'H':'hits','2B':'doubles','3B':'triples','HR':'homeRuns'}


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()


def now():return datetime.now(timezone.utc).isoformat()


def number(v):
    try:n=Decimal(str(v))
    except Exception:raise ValueError('Invalid integer: '+repr(v)) from None
    if not n.is_finite() or n<0 or n!=int(n):raise ValueError('Invalid nonnegative integer: '+repr(v))
    return int(n)


def read_csv(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as f:
        r=csv.DictReader(f)
        if not r.fieldnames or len(set(r.fieldnames))!=len(r.fieldnames):raise ValueError('Invalid CSV headings')
        rows=list(r)
        if any(None in x or any(v is None for v in x.values()) for x in rows):raise ValueError('Malformed CSV')
        return rows


def write_csv(path,rows,fields):
    with Path(path).open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)


def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')


def metric(stat,name):
    if name=='1B':
        v=number(stat['hits'])-sum(number(stat[f]) for f in ('doubles','triples','homeRuns'))
        if v<0:raise ValueError('Negative derived singles')
        return v
    return number(stat[FIELDS[name]])


def block(payload,kind,group):
    blocks=[b for b in payload.get('stats',[]) if b.get('type',{}).get('displayName','').lower()==kind.lower()
            and b.get('group',{}).get('displayName')==group]
    if len(blocks)!=1:raise ValueError('Missing/ambiguous stats type or role block')
    b=blocks[0]
    if 'totalSplits' in b and number(b['totalSplits'])!=len(b.get('splits',[])):
        raise ValueError('Truncated/paginated response')
    return b


def check_split(s,year,pid):
    if number(s.get('season'))!=year or s.get('gameType')!='R':raise ValueError('Wrong split season/game type')
    if number(s.get('player',{}).get('id'))!=pid:raise ValueError('Wrong split player identity')
    if number(s.get('sport',{}).get('id'))!=1:raise ValueError('Non-MLB split')


def normalize(payload,year,role,pid,kind,metrics):
    b=block(payload,kind,GROUP[role]);splits=b.get('splits',[])
    if not splits:raise ValueError('Empty player statistics response')
    for s in splits:check_split(s,year,pid)
    if kind=='gameLog':
        rows={}
        for s in splits:
            game=number(s.get('game',{}).get('gamePk'))
            if game<=0 or game in rows:raise ValueError('Duplicate/invalid game key; no implicit aggregation')
            day=date.fromisoformat(s['date'])
            if day.year!=year:raise ValueError('Game-log date outside season')
            rows[game]=dict(date=day.isoformat(),values={m:metric(s['stat'],m) for m in metrics})
        return rows
    if kind!='season':raise ValueError('Unsupported request kind')
    if len(splits)==1:
        chosen=splits;policy='SINGLE_SEASON_SPLIT'
    else:
        # An aggregate split must be explicitly teamless; otherwise sum distinct team splits.
        aggregate=[s for s in splits if not s.get('team',{}).get('id')]
        if len(aggregate)==1:chosen=aggregate;policy='EXPLICIT_TEAMLESS_AGGREGATE'
        elif aggregate:raise ValueError('Ambiguous aggregate season splits')
        else:
            ids=[number(s['team']['id']) for s in splits]
            if len(ids)!=len(set(ids)):raise ValueError('Repeated team season splits')
            chosen=splits;policy='SUM_DISTINCT_MLB_TEAM_SPLITS'
    values={m:sum(metric(s['stat'],m) for s in chosen) for m in metrics}
    games=sum(number(s['stat']['gamesPlayed']) for s in chosen)
    return dict(values=values,games=games,policy=policy)


def request_url(year,role,pid,kind):
    return f'https://statsapi.mlb.com/api/v1/people/{pid}/stats?'+urlencode(dict(
        stats=kind,group=GROUP[role],season=year,gameType='R',sportIds=1,limit=1000))


def fetch(url):
    with urlopen(Request(url,headers={'User-Agent':'PlayerValuation/1.0 targeted historical audit'}),timeout=45) as r:
        b=r.read(16*1024*1024+1)
    if len(b)>16*1024*1024:raise ValueError('Response exceeds 16 MiB')
    return b


def cached_response(cache,target,kind,metrics,download,fetcher=fetch):
    year,role,pid=target;directory=cache/str(year)/role/str(pid)/kind
    url=request_url(year,role,pid,kind)
    if directory.exists():
        raw=directory/'response.json';meta=directory/'source.json'
        if not raw.is_file() or not meta.is_file():raise ValueError('Incomplete cache directory: '+str(directory))
        m=json.loads(meta.read_text())
        if m.get('url')!=url or m.get('sha256')!=sha(raw) or m.get('target')!=list(target) or m.get('kind')!=kind:
            raise ValueError('Cached request hash/identity mismatch')
        payload=json.loads(raw.read_text(encoding='utf-8'))
        normalize(payload,year,role,pid,kind,metrics)
        return payload,raw,meta
    if not download:raise ValueError('Missing cache; run with --download: '+url)
    directory.parent.mkdir(parents=True,exist_ok=True)
    stage=Path(tempfile.mkdtemp(prefix=kind+'.staging-',dir=directory.parent))
    try:
        for attempt in range(3):
            try:
                b=fetcher(url);payload=json.loads(b);normalize(payload,year,role,pid,kind,metrics);break
            except Exception:
                if attempt==2:raise
                time.sleep(attempt+1)
        (stage/'response.json').write_bytes(b)
        dump(stage/'source.json',dict(target=list(target),kind=kind,url=url,retrieved_at=now(),sha256=sha(stage/'response.json')))
        stage.rename(directory)
        return payload,directory/'response.json',directory/'source.json'
    finally:
        if stage.exists():shutil.rmtree(stage)


def build(discrepancies,game_totals,output,cache='data/mlb_hit_gamelogs_v1_0',backup_root='backups',
          download=False,fetcher=fetch,pause=0.2):
    paths=[Path(x).resolve() for x in (discrepancies,game_totals)]
    output,cache,backup_root=map(lambda p:Path(p).resolve(),(output,cache,backup_root))
    if output.exists():raise FileExistsError('Choose a new output folder')
    if pause<0:raise ValueError('Nonnegative pause required')
    for a,b in [(output,cache),(output,backup_root),(cache,backup_root)]:
        if a==b or a in b.parents or b in a.parents:raise ValueError('Overlapping output/cache/backup folders')
    if any(output==p or output in p.parents or cache==p or cache in p.parents for p in paths):raise ValueError('Output/cache overlaps input')
    fingerprints={str(p):sha(p) for p in paths}
    cases={};targets=defaultdict(set)
    for r in read_csv(paths[0]):
        if r['metric'] not in HIT_METRICS:continue
        key=(number(r['season']),r['player_type'],number(r['mlbam_id']),r['metric'])
        if key[0]>=2026 or key[1] not in GROUP or key[2]<=0:raise ValueError('Invalid/holdout target')
        if key in cases:raise ValueError('Duplicate discrepancy key')
        if int(r['evidence_count'])-int(r['fangraphs_actual'])!=int(r['final_difference']):raise ValueError('Bad baseline difference arithmetic')
        cases[key]=r;targets[key[:3]].add(key[3])
    if not cases:raise ValueError('No hit/type differences selected')
    local={};local_sums=Counter()
    for r in read_csv(paths[1]):
        key=(number(r['season']),r['player_type'],number(r['mlbam_id']),r['metric'])
        if key not in cases:continue
        game=number(r['game_pk']);gkey=key+(game,)
        if game<=0 or gkey in local:raise ValueError('Duplicate/invalid reconstructed game key')
        raw,rule=number(r['terminal_count']),number(r['rule_count'])
        if r['metric_admitted'] not in ('True','False') or r['cached_mlb'] not in ('True','False'):raise ValueError('Invalid game evidence boolean')
        admitted=r['metric_admitted']=='True'
        if admitted and r['cached_mlb']!='True':raise ValueError('Admitted metric without cache')
        value=number(r['mlb_count']) if admitted else rule
        local[gkey]=dict(raw=raw,rule=rule,evidence=value)
        for label,v in [('raw',raw),('rule',rule),('evidence',value)]:local_sums[key+(label,)]+=v
    for key,c in cases.items():
        actual=tuple(local_sums[key+(label,)] for label in ['raw','rule','evidence'])
        expected=tuple(number(c[f]) for f in ['terminal_count','rule_count','evidence_count'])
        if actual!=expected:raise ValueError('Game totals do not reproduce selected baseline case: '+str(key))
    cache.mkdir(parents=True,exist_ok=True);lock=cache/'download.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY);os.close(fd)
    normalized=[];comparisons=[];season_rows=[];mismatched=set();cachefiles=set()
    try:
        for i,(target,metrics) in enumerate(sorted(targets.items()),1):
            year,role,pid=target
            print(f'[{i}/{len(targets)}] {year} {role} {pid}: game log and season total',flush=True)
            log,lp,lm=cached_response(cache,target,'gameLog',metrics,download,fetcher)
            season,sp,sm=cached_response(cache,target,'season',metrics,download,fetcher)
            for p in (lp,lm,sp,sm):fingerprints[str(p)]=sha(p);cachefiles.add(p)
            logs=normalize(log,year,role,pid,'gameLog',metrics)
            total=normalize(season,year,role,pid,'season',metrics)
            # MLB season G can include appearances absent from role-specific game logs.
            # Certify only selected hit totals, and expose participation-count differences.
            for m in sorted(metrics):
                logsum=sum(row['values'][m] for row in logs.values())
                if logsum!=total['values'][m]:raise ValueError('Game-log sum differs from MLB season total')
                key=target+(m,);case=cases[key]
                fg=number(case['fangraphs_actual']);recon=number(case['evidence_count'])
                metricgames={k[-1] for k in local if k[:4]==key}
                differences=0;missing_evidence=0
                for game in sorted(set(logs)|metricgames):
                    gkey=key+(game,);left=local.get(gkey);right=logs.get(game)
                    # Missing appearances are unknown, never silently observed zero.
                    lv=left['evidence'] if left else None;rv=right['values'][m] if right else None
                    delta=rv-lv if rv is not None and lv is not None else None
                    status='GAME_MATCH' if delta==0 else 'GAME_METRIC_DIFFERENCE' if delta is not None else 'MISSING_RECONSTRUCTED_GAME' if left is None else 'MISSING_MLB_GAME_LOG_ENTRY'
                    if status!='GAME_MATCH':differences+=1;mismatched.add((year,game))
                    if delta is None:missing_evidence+=1
                    comparisons.append(dict(season=year,player_type=role,mlbam_id=pid,name=case['name'],metric=m,
                                            game_pk=game,date=right['date'] if right else '',
                                            reconstructed_terminal=left['raw'] if left else None,
                                            reconstructed_rule=left['rule'] if left else None,
                                            reconstructed_evidence=lv,mlb_game_log_count=rv,
                                            mlb_minus_reconstructed=delta,status=status))
                if differences==0:
                    status='GAME_LOGS_AND_RECONSTRUCTION_AGREE_SOURCE_SEASON_TOTAL_DISAGREEMENT' if logsum!=fg else 'ALL_THREE_AGREE'
                else:status='SPECIFIC_GAME_REVIEW_REQUIRED'
                season_rows.append(dict(season=year,player_type=role,mlbam_id=pid,name=case['name'],metric=m,
                                        fangraphs_season_count=fg,reconstructed_season_count=recon,
                                        mlb_game_log_sum=logsum,mlb_season_count=total['values'][m],
                                        mlb_minus_reconstructed=logsum-recon,mlb_minus_fangraphs=logsum-fg,
                                        mismatched_games=differences,missing_game_comparisons=missing_evidence,
                                        log_games=len(logs),season_games=total['games'],game_count_agrees=len(logs)==total['games'],season_policy=total['policy'],status=status))
            for game,row in sorted(logs.items()):
                normalized.append(dict(season=year,player_type=role,mlbam_id=pid,game_pk=game,date=row['date'],**row['values']))
            if pause:time.sleep(pause)
        if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Input or response cache changed during audit')
        output.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
        try:
            write_csv(stage/'season_comparisons.csv',season_rows,list(season_rows[0]))
            write_csv(stage/'game_log_comparisons.csv',comparisons,list(comparisons[0]))
            diff=[r for r in comparisons if r['status']!='GAME_MATCH']
            write_csv(stage/'mismatched_games.csv',diff,list(comparisons[0]))
            fields=['season','game_pk','priority','url']
            plan=[dict(season=y,game_pk=g,priority='PLAYER_SEASON_DIFFERENCE',url=f'https://statsapi.mlb.com/api/v1.1/game/{g}/feed/live') for y,g in sorted(mismatched)]
            write_csv(stage/'game_fetch_plan.csv',plan,fields)
            dump(stage/'normalized_game_logs.json',normalized)
            # Bundle the complete request cache selected by this run, not all unrelated cache history.
            for p in sorted(cachefiles):
                q=stage/'source_responses'/p.relative_to(cache);q.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,q)
                if sha(q)!=fingerprints[str(p)]:raise ValueError('Evidence copy hash mismatch')
            shutil.copyfile(paths[0],stage/'baseline_discrepancies.csv')
            dump(stage/'input_hashes.json',fingerprints)
            backup=backup_root/(output.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
            report=dict(version=VERSION,built_at=now(),status='REVIEW_REQUIRED',model_ready=False,
                        selected_metric_differences=len(cases),player_season_roles=len(targets),requests=len(targets)*2,
                        game_metric_comparisons=len(comparisons),mismatched_game_metric_rows=len(diff),
                        specific_games_to_inspect=len(mismatched),season_statuses=dict(Counter(r['status'] for r in season_rows)),
                        baseline_game_totals_reproduced=True,mlb_log_sums_match_mlb_season_totals=True,
                        game_count_warning_rows=sum(not r['game_count_agrees'] for r in season_rows),
                        inputs_unchanged=True,counts_modified=False,output=str(output),backup=str(backup),
                        limitations=['Retrospective MLB retrieval, not an archived as-of scoring vintage.',
                                     'Matching present MLB and reconstructed counts cannot locate the origin of a differing FanGraphs season total without FanGraphs game-level evidence.',
                                     'A source disagreement is not proof of when or why a scoring revision occurred.',
                                     'Missing game entries are unknown, not zero; pagination, duplicate games, bad identities and sum mismatches fail validation.',
                                     'MLB season gamesPlayed may include participation absent from role-specific game logs; game-count differences are reported and no all-appearance completeness claim is made.',
                                     'Only selected hit metrics are tested. No PA/TBF, IP/ER or model-readiness certification.',
                                     'Older supplied game totals are accepted only when every selected season terminal/rule/evidence total reproduces the current discrepancy baseline.'])
            dump(stage/'gamelog_audit_report.json',report)
            (stage/'gamelog_audit_report.md').write_text('# Targeted MLB hit game-log audit\n\n'+
                f'{len(cases)} metrics across {len(targets)} player-season roles. {len(mismatched)} games require inspection.\n\n'+
                'No counts changed. Read season_comparisons.csv and mismatched_games.csv. A matching MLB log and reconstructed season with a different FanGraphs total is retained as a source disagreement.\n',encoding='utf-8')
            if any(sha(p)!=h for p,h in fingerprints.items()):raise ValueError('Inputs changed before publication')
            backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
            tree=lambda d:{str(p.relative_to(d)):sha(p) for p in d.rglob('*') if p.is_file()}
            if tree(stage)!=tree(backup):raise ValueError('Complete backup verification failed')
            if output.exists():raise FileExistsError('Output created during run')
            stage.rename(output)
            return report
        finally:
            if stage.exists():shutil.rmtree(stage)
    finally:lock.unlink(missing_ok=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--discrepancies',default='outputs/actuals_statcast_reconciliation_v1_0_error_evidence/discrepancies.csv')
    p.add_argument('--game-totals',default='outputs/actuals_final_difference_audit_v1_0_1/game_metric_comparisons.csv')
    p.add_argument('--cache',default='data/mlb_hit_gamelogs_v1_0')
    p.add_argument('--output',default='outputs/mlb_hit_gamelog_audit_v1_0')
    p.add_argument('--backup-root',default='backups')
    p.add_argument('--download',action='store_true',help='Fetch only missing request cache entries')
    a=p.parse_args();print(json.dumps(build(a.discrepancies,a.game_totals,a.output,a.cache,a.backup_root,a.download),indent=2))

if __name__=='__main__':main()
