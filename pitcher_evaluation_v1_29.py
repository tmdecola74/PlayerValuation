"""Audit and score the frozen 2026 pitcher forecast. Never trains or selects."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import shutil

from pitcher_label_coverage_v1_26 import Cache, boxscore, mlbid, pitching_outs, schedule, standings
from contact_workload_audit_v1_24 import registered, rows
from recent_skill_core_v1_23 import checked, emit, member
from recent_skill_inputs_v1_23 import labels
from standalone_io_v1_0 import dump, finish, load, start

YEAR = 2026
METHODS = ('accepted_ip', 'two_part_ip', 'role_hybrid_ip')
ROLES = ('STARTER', 'RELIEVER', 'SWING', 'UNKNOWN')
COUNTS = ('G', 'OUTS')


def verified_box(doc, teams):
    ids = boxscore(doc, teams)
    out = {}
    for side in ('away','home'):
        for p in doc['teams'][side]['players'].values():
            pid = mlbid(p['person']['id'])
            s = p['stats'].get('pitching',{})
            if pid in ids and s.get('gamesPitched')==1:
                if pid in out:
                    raise ValueError('Duplicate credited pitcher')
                out[pid] = pitching_outs(s['inningsPitched'])
    if out.keys()!=ids:
        raise ValueError('Credited pitcher list mismatch')
    return out


def outcomes(frozen, actual, gs, outs, people, certified):
    for pid,r in sorted(frozen.items()):
        k = YEAR,'pitcher',str(pid)
        old_g, old_outs = (actual.get(k+(m,)) for m in COUNTS)
        g, o = gs[pid], outs[pid]
        if not certified:
            state, g, o = 'UNKNOWN_SEASON_NOT_CERTIFIED',None,None
        elif g>0:
            state = 'VERIFIED_APPEARED'
        elif pid in people:
            state = 'VERIFIED_NO_APPEARANCE'
        else:
            state, g, o = 'UNKNOWN_IDENTITY',None,None
        yield dict(season=YEAR,mlbam_id=pid,prior_role=r['prior_role'],status=state,
                   frozen_actual_g=old_g,frozen_actual_outs=old_outs,evaluation_g=g,evaluation_outs=o,
                   added_zero_pair=state=='VERIFIED_NO_APPEARANCE' and (old_g is None or old_outs is None),
                   accepted_ip=r['accepted_ip'],two_part_ip=r['two_part_ip'],
                   role_hybrid_ip=r['accepted_ip'] if r['prior_role']=='STARTER' else r['two_part_ip'])


def score(records):
    groups=defaultdict(list)
    for r in records:
        if r['evaluation_outs'] is None:
            continue
        for key in [('ALL','ALL'),('APPEARANCE',r['status']),('PRIOR_ROLE',r['prior_role']),
                    ('ROLE_AND_APPEARANCE',r['prior_role']+'/'+r['status'])]:
            groups[key].append(r)
    result=[]
    for (dimension,cohort), group in sorted(groups.items()):
        n=len(group)
        sig=member([str(r['mlbam_id']) for r in group])
        for method in METHODS:
            es=[r[method]-r['evaluation_outs']/3 for r in group]
            sse=math.fsum(e*e for e in es)
            result.append(dict(season=YEAR,dimension=dimension,cohort=cohort,method=method,n=n,
                               sse=sse,mse=sse/n,rmse=math.sqrt(sse/n),
                               mae=math.fsum(map(abs,es))/n,bias=math.fsum(es)/n,membership_sha256=sig))
    return result


def run(a):
    src, lab, cache = (Path(x).resolve() for x in (a.run,a.labels,a.cache))
    if any(cache==p or cache in p.parents or p in cache.parents for p in (src,lab)):
        raise ValueError('Cache overlaps frozen inputs')
    w={}
    freeze=load(checked(src,'forecast_freeze.json',w))
    r=load(registered(src,'report.json',w,freeze))
    lr=checked(lab,'label_build_report.json',w)
    if (r['version']!='1.27.0' or r['evaluation_outcomes_read'] is not False
            or r['label_report_sha256']!=w[str(lr)]):
        raise ValueError('Require the matching frozen v1.27 run and labels')
    p=registered(src,'frozen_2026_workload.csv',w,freeze)
    frozen={}
    for row in rows(p):
        pid=mlbid(row['mlbam_id'])
        if row['season']!='2026' or pid in frozen or row['prior_role'] not in ROLES:
            raise ValueError('Invalid frozen pitcher membership or role')
        vals={m:float(row[m]) for m in METHODS[:2]}
        if any(not math.isfinite(x) or x<0 for x in vals.values()):
            raise ValueError('Invalid frozen workload')
        frozen[pid]=dict(prior_role=row['prior_role'],**vals)
    if not frozen:
        raise ValueError('Empty frozen pitcher pool')
    actual=labels(checked(lab,'holdout_labels.parquet',w),YEAR)
    output,bak,stage=start(a.output,a.backup_root,[src,lab,cache])
    try:
        api=Cache(cache,a.download,a.delay,w)
        issues=[]
        def note(scope,key,e):
            issues.append(dict(scope=scope,key=key,detail=str(e)))
        games, expected, counts, schedule_ok = {}, {}, {}, False
        try:
            expected=standings(api.get('2026/standings.json','standings',leagueId='103,104',season=YEAR,
                                       standingsTypes='regularSeason'),YEAR)
            games,schedule_ok,pending,counts=schedule(api.get('2026/schedule.json','schedule',sportId=1,
                                                             season=YEAR,gameTypes='R'),YEAR,expected)
            if not schedule_ok:
                note('schedule',YEAR,f'Team totals differ or unfinished games: {pending}')
        except (OSError, ValueError, KeyError, TypeError) as e:
            note('schedule',YEAR,e)
        gs, outs, verified=Counter(),Counter(),0
        for pk,teams in sorted(games.items()):
            try:
                lines=verified_box(api.get(f'2026/game_{pk}.json',f'game/{pk}/boxscore'),teams)
                gs.update(lines.keys())
                outs.update(lines)
                verified+=1
                if verified%200==0:
                    print(f'{verified}/{len(games)} boxscores verified',flush=True)
            except (OSError, ValueError, KeyError, TypeError) as e:
                note('boxscore',pk,e)
        complete=bool(schedule_ok and games and verified==len(games))
        conflicts=set()
        if complete:
            for (y,typ,pid,metric),value in actual.items():
                if y!=YEAR or typ!='pitcher' or metric not in COUNTS:
                    continue
                observed=(gs if metric=='G' else outs)[mlbid(pid)]
                if observed!=value:
                    conflicts.add(pid)
                    note('label_conflict',pid,f'{metric}: frozen={value}; boxscore={observed}')
        certified=complete and not conflicts
        people=set()
        if certified:
            missing=sorted(frozen.keys()-gs.keys())
            for i in range(0,len(missing),50):
                batch=missing[i:i+50]
                ids=','.join(map(str,batch))
                tag=hashlib.sha256(ids.encode()).hexdigest()[:20]
                try:
                    received=[mlbid(x['id']) for x in api.get(f'2026/people_{tag}.json','people',
                                                             personIds=ids)['people']]
                    if len(received)!=len(set(received)) or set(received)-set(batch):
                        raise ValueError('Unexpected identity results')
                    people.update(received)
                    for pid in set(batch)-people:
                        note('identity_unresolved',pid,'No exact MLBAM match returned')
                except (OSError, ValueError, KeyError, TypeError) as e:
                    note('identity_batch',tag,e)
        records=list(outcomes(frozen,actual,gs,outs,people,certified))
        scored=score(records)
        emit(stage/'evaluation_label_overlay_2026.csv',records)
        emit(stage/'evaluation_2026_scores.csv',scored)
        emit(stage/'coverage_issues.csv',issues)
        report=dict(version='1.29.0',scope='2026 regular season, reporting only',season_certified=certified,
                    source_complete=complete,expected_team_games=expected,observed_team_games=counts,
                    expected_boxscores=len(games),verified_boxscores=verified,label_conflicts=len(conflicts),
                    preseason_pool=len(frozen),statuses=dict(Counter(x['status'] for x in records)),
                    added_zero_pairs=sum(x['added_zero_pair'] for x in records),
                    complete_pool_scored=certified and all(x['evaluation_outs'] is not None for x in records),
                    frozen_forecast_sha256=w[str(p)],selection_uses_2026=False,
                    default_method='accepted_ip',default_changed=False,models_refitted=False,
                    overall_scores=[x for x in scored if x['dimension']=='ALL'])
        dump(stage/'report.json',report)
        return dict(report,output=str(output),backup=finish(output,bak,stage,w))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',default='outputs/pitcher_workload_v1_27')
    p.add_argument('--labels',default='outputs/training_labels_v1_0')
    p.add_argument('--cache',default='cache/pitcher_appearance_mlb')
    p.add_argument('--output',default='outputs/pitcher_evaluation_v1_29')
    p.add_argument('--backup-root',default='backups')
    p.add_argument('--download',action='store_true')
    p.add_argument('--delay',type=float,default=.35)
    a=p.parse_args()
    if not .25<=a.delay<=10:
        p.error('--delay must be .25–10 seconds')
    print(json.dumps(run(a),indent=2))
