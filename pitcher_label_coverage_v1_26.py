"""Audit historical pitching appearances without modifying training labels."""
import argparse
from collections import Counter
import hashlib
import json
import re
from pathlib import Path
import shutil
import time
from urllib.parse import urlencode
from urllib.request import urlopen

API = 'https://statsapi.mlb.com/api/v1/'
YEARS = set(range(2019, 2026))
SIDES = ('away', 'home')


def mlbid(x):
    s = str(x)
    if not s.isascii() or not s.isdigit() or str(int(s)) != s or int(s) <= 0:
        raise ValueError(f'Invalid MLBAM ID: {x!r}')
    return int(s)


class Cache:
    def __init__(self, root, download, delay, watched):
        self.root, self.download, self.delay, self.watched = root, download, delay, watched

    def get(self, filename, endpoint, **params):
        from standalone_io_v1_0 import dump, load, sha
        url = API + endpoint + ('?' + urlencode(params) if params else '')
        p = self.root / filename
        if not p.exists():
            if not self.download:
                raise FileNotFoundError(filename)
            p.parent.mkdir(parents=True, exist_ok=True)
            time.sleep(self.delay)
            with urlopen(url, timeout=25) as response:
                if response.geturl() != url:
                    raise ValueError('Unexpected redirect')
                payload = json.load(response)
            tmp = p.with_suffix('.tmp')
            dump(tmp, dict(url=url, payload=payload))
            tmp.replace(p)
        digest = sha(p)
        obj = load(p)
        if obj['url'] != url:
            raise ValueError('Cached URL mismatch')
        self.watched[str(p)] = digest
        return obj['payload']


def standings(doc, year):
    teams = {}
    leagues = set()
    for r in doc['records']:
        league = mlbid(r['league']['id'])
        leagues.add(league)
        for t in r['teamRecords']:
            tid = mlbid(t['team']['id'])
            n = t['gamesPlayed']
            if tid in teams or type(n) is not int or not 1 <= n <= 163:
                raise ValueError('Invalid regular-season standings')
            teams[tid] = n
    bounds = (58, 60) if year == 2020 else (161, 163)
    if leagues != {103, 104} or len(teams) != 30 or not all(bounds[0] <= n <= bounds[1] for n in teams.values()):
        raise ValueError('Incomplete season standings')
    return teams


def schedule(doc, year, expected):
    games = {}
    counts = Counter()
    unresolved = []
    signatures = {}
    for day in doc['dates']:
        for g in day['games']:
            pk = mlbid(g['gamePk'])
            if g['gameType'] != 'R' or str(g['season']) != str(year):
                raise ValueError('Duplicate or out-of-scope schedule game')
            state = g['status']['detailedState']
            if state in ('Postponed', 'Cancelled', 'Canceled'):
                continue
            if g['status']['abstractGameState'] != 'Final':
                unresolved.append(pk)
                continue
            t = tuple(mlbid(g['teams'][s]['team']['id']) for s in SIDES)
            if len(set(t)) != 2 or any(i not in expected for i in t):
                raise ValueError('Invalid schedule teams')
            if any(type(g['teams'][s].get('score')) is not int for s in SIDES):
                raise ValueError('Missing final scores')
            signature=t+tuple(g['teams'][s]['score'] for s in SIDES)
            if pk in signatures:
                if signatures[pk]!=signature:
                    raise ValueError('Conflicting duplicate final game')
                continue
            signatures[pk]=signature
            games[pk] = t
            counts.update(t)
    unresolved = sorted(set(unresolved)-games.keys())
    complete = not unresolved and dict(counts) == expected
    return games, complete, unresolved, counts


def pitching_outs(s):
    if not isinstance(s,str) or not re.fullmatch(r'[0-9]+\.[012]',s):
        raise ValueError('Invalid innings in boxscore')
    whole, remainder = s.split('.')
    return int(whole)*3+int(remainder)


def boxscore(doc, expected):
    result = set()
    listed = set()
    for side, tid in zip(SIDES, expected):
        block = doc['teams'][side]
        if mlbid(block['team']['id']) != tid:
            raise ValueError('Boxscore team mismatch')
        ids = list(map(mlbid, block['pitchers']))
        if not ids or len(ids) != len(set(ids)):
            raise ValueError('Missing or duplicate pitcher list')
        lines = set()
        credited = set()
        outs = 0
        for row in block['players'].values():
            stats = row['stats'].get('pitching', {})
            if not stats:
                continue
            pid = mlbid(row['person']['id'])
            if pid in lines or 'inningsPitched' not in stats:
                raise ValueError('Invalid pitching line')
            lines.add(pid)
            player_outs = pitching_outs(stats['inningsPitched'])
            gp = stats.get('gamesPitched')
            if type(gp) is not int or gp not in (0, 1):
                raise ValueError('Missing or invalid gamesPitched')
            if gp:
                credited.add(pid)
            elif player_outs or any(stats.get(field, 0) != 0 for field in
                                    ('gamesStarted', 'numberOfPitches', 'battersFaced', 'outs')):
                raise ValueError('Non-appearance line has pitching activity')
            outs += player_outs
        if (lines != set(ids) or listed.intersection(ids) or
                outs != pitching_outs(block['teamStats']['pitching']['inningsPitched'])):
            raise ValueError('Pitching lines do not reconcile with pitcher lists')
        listed.update(ids)
        result.update(credited)
    return result


def classify(pid, actual_g, outs, appearances, complete, people):
    n = appearances.get(pid, 0)
    known_positive = (actual_g or 0) > 0 or (outs or 0) > 0
    if (n and actual_g == 0) or complete and (
            (actual_g is not None and actual_g != n) or (not n and known_positive)):
        return 'CONFLICT', None
    if n:
        return 'VERIFIED_APPEARED', n if complete else None
    if not complete:
        return 'UNKNOWN_INCOMPLETE_SEASON', None
    if pid not in people:
        return 'UNKNOWN_IDENTITY', None
    return 'VERIFIED_NO_APPEARANCE', 0


def run(a):
    from contact_workload_audit_v1_24 import BASE, registered, rows
    from recent_skill_core_v1_23 import checked, emit
    from recent_skill_inputs_v1_23 import labels
    from standalone_io_v1_0 import dump, finish, load, sha, start

    parent, lab, cache_root = (Path(x).resolve() for x in (a.parent,a.labels,a.cache))
    watch = {}
    freeze = load(checked(parent,'forecast_freeze.json',watch))
    source = registered(parent,'historical_forecasts.csv',watch,freeze)
    training = checked(lab,'training_labels.parquet',watch)
    binding = load(checked(parent,'input_hashes.json',watch))
    if binding.get(str(training)) != watch[str(training)]:
        raise ValueError('Training labels do not match frozen forecast binding')
    actual = labels(training)
    applied_corrections = []
    if 2023 in a.seasons:
        correction_path = Path("config/pitcher_label_corrections.json").resolve()
        watch[str(correction_path)] = sha(correction_path)
        correction = load(correction_path)
        key = (
            correction["season"], correction["player_type"],
            correction["mlbam_id"], correction["metric"],
        )
        if (key != (2023, "pitcher", "677020", "G")
                or correction["old_value"] != 13
                or correction["new_value"] != 14
                or actual.get(key) != 13):
            raise ValueError("Walker correction does not match the frozen label")
        actual = {**actual, key: correction["new_value"]}
        applied_corrections.append(correction)
    pool = {y:set() for y in a.seasons}
    for r in rows(source):
        if r['method']==BASE and r['player_type']=='pitcher' and r['metric']=='OUTS':
            y=int(r['season'])
            if y not in YEARS:
                raise ValueError('Unexpected historical forecast year')
            if y in pool:
                pid=mlbid(r['mlbam_id'])
                if pid in pool[y]:
                    raise ValueError('Duplicate forecast pitcher-season')
                pool[y].add(pid)
    if not all(pool.values()):
        raise ValueError('Empty requested preseason pool')
    if any(cache_root==p or p in cache_root.parents or cache_root in p.parents for p in (parent,lab)):
        raise ValueError('Cache must be separate from frozen forecast and label folders')
    out,bak,stage = start(a.output,a.backup_root,[parent,lab,cache_root])
    try:
        cache=Cache(cache_root,a.download,a.delay,watch)
        audits, reports, issues = [], [], []
        def issue(y, scope, key, e):
            issues.append(dict(season=y,scope=scope,key=key,detail=str(e)))
        for y, ids in sorted(pool.items()):
            games, schedule_ok, unresolved, counts, expected = {}, False, [], {}, {}
            try:
                expected=standings(cache.get(f'{y}/standings.json','standings',leagueId='103,104',
                                              season=y,standingsTypes='regularSeason'),y)
                games,schedule_ok,unresolved,counts=schedule(
                    cache.get(f'{y}/schedule.json','schedule',sportId=1,season=y,gameTypes='R'),y,expected)
                if not schedule_ok:
                    issue(y,'schedule',y,f'Team count mismatch or unfinished games: {unresolved}')
            except (OSError, ValueError, KeyError, TypeError) as e:
                issue(y,'schedule_or_standings',y,e)
            appearances=Counter()
            verified=0
            for pk, teams in sorted(games.items()):
                try:
                    appearances.update(boxscore(cache.get(f'{y}/game_{pk}.json',f'game/{pk}/boxscore'),teams))
                    verified+=1
                except (OSError, ValueError, KeyError, TypeError) as e:
                    issue(y,'boxscore',pk,e)
            complete=bool(schedule_ok and games and verified==len(games))
            # Cross-check every eligible positive historical games/outs label, including
            # pitchers outside the forecast pool, before treating any absence as zero.
            conflicts=[]
            if complete:
                for (season, typ, pid, metric), value in actual.items():
                    if season!=y or typ!='pitcher' or metric not in ('G','OUTS'):
                        continue
                    n=appearances.get(mlbid(pid),0)
                    if metric=='G' and value!=n or metric=='OUTS' and value>0 and not n:
                        conflicts.append(pid)
                        issue(y,'label_conflict',pid,f'{metric}={value}; boxscore G={n}')
            safe=complete and not conflicts
            people=set()
            missing=sorted(ids-set(appearances))
            if safe:
                for i in range(0,len(missing),50):
                    batch=missing[i:i+50]
                    arg=','.join(map(str,batch))
                    tag=hashlib.sha256(arg.encode()).hexdigest()[:20]
                    try:
                        result=[mlbid(r['id']) for r in cache.get(
                            f'{y}/people_{tag}.json','people',personIds=arg)['people']]
                        if not set(result)<=set(batch) or len(set(result))!=len(result):
                            raise ValueError('Unexpected IDs in person lookup')
                        people.update(result)
                    except (OSError,ValueError,KeyError,TypeError) as e:
                        issue(y,'identity_batch',tag,e)
            totals=Counter()
            for pid in sorted(ids):
                k=y,'pitcher',str(pid)
                g,outs=actual.get(k+('G',)),actual.get(k+('OUTS',))
                state,n=classify(pid,g,outs,appearances,safe,people)
                if complete and not safe and state=='UNKNOWN_INCOMPLETE_SEASON':
                    state='UNKNOWN_LABEL_RECONCILIATION'
                if str(pid) in conflicts:
                    state,n='CONFLICT',None
                totals[state]+=1
                audits.append(dict(season=y,mlbam_id=pid,status=state,proposed_G=n,
                                   proposed_OUTS=0 if n==0 else None,existing_G=g,existing_OUTS=outs,
                                   observed_boxscore_G=appearances.get(pid,0),season_certified=safe,
                                   appearance_identity_verified=pid in appearances or pid in people))
            reports.append(dict(season=y,pool=len(ids),schedule_final_games=len(games),boxscores_verified=verified,
                                source_complete=complete,
                                standings_team_counts=expected,schedule_team_counts=counts,
                                season_certified=safe,conflicting_pitchers=len(set(conflicts)),statuses=dict(totals)))
            print(f'{y}: {verified}/{len(games)} boxscores, certified={safe}, proposed zeros={totals["VERIFIED_NO_APPEARANCE"]}',flush=True)
        emit(stage/'pitcher_label_coverage.csv',audits)
        emit(stage/'coverage_issues.csv',issues)
        report=dict(version='1.26.1',scope='MLB regular season, 2019–2025 historical only',
                    labels_modified=False,models_refitted=False,seasons=reports)
        report["applied_label_corrections"] = applied_corrections
        dump(stage/'report.json',report)
        return dict(report,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',default='outputs/recent_history_skills_v1_23')
    p.add_argument('--labels',default='outputs/training_labels_v1_0')
    p.add_argument('--cache',default='cache/pitcher_appearance_mlb')
    p.add_argument('--output',default='outputs/pitcher_label_coverage_v1_26')
    p.add_argument('--backup-root',default='backups')
    p.add_argument('--seasons',nargs='+',type=int,choices=sorted(YEARS),default=sorted(YEARS))
    p.add_argument('--download',action='store_true',help='Fetch missing official responses; default is offline')
    p.add_argument('--delay',type=float,default=.35)
    a=p.parse_args()
    if not .25 <= a.delay <= 10:
        p.error('--delay must be .25–10 seconds')
    print(json.dumps(run(a),indent=2))
