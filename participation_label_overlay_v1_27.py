"""Build and verify a separate historical pitcher label overlay."""
import argparse
from collections import Counter
import json
from pathlib import Path
import shutil

from contact_workload_audit_v1_24 import BASE, registered, rows
from recent_skill_core_v1_23 import checked, emit
from recent_skill_inputs_v1_23 import labels
from standalone_io_v1_0 import dump, finish, load, start

YEARS = range(2019, 2026)
WALKER = (2023, 'pitcher', '677020', 'G')
COUNTS = dict(zip(YEARS, (534, 625, 516, 583, 619, 714, 639)))
SOURCE = 'https://statsapi.mlb.com/api/v1/people/677020/stats?stats=gameLog&group=pitching&season=2023&gameType=R'


def audit_changes(year, report, records, pool, actual):
    (s,) = report['seasons']
    if (report['version'] != '1.26.1' or report['labels_modified'] is not False
            or report['models_refitted'] is not False or s['season'] != year
            or s['season_certified'] is not True or s['source_complete'] is not True
            or s['conflicting_pitchers'] != 0 or s['pool'] != len(pool)
            or not 0 < s['schedule_final_games'] == s['boxscores_verified']
            or len(s['standings_team_counts']) != 30
            or s['standings_team_counts'] != s['schedule_team_counts']
            or sum(s['standings_team_counts'].values()) != 2*s['boxscores_verified']):
        raise ValueError(f'{year}: audit not certified or coverage does not reconcile')
    corrections = report.get('applied_label_corrections', [])
    if year == 2023:
        (c,) = corrections
        if ((c['season'],c['player_type'],c['mlbam_id'],c['metric']) != WALKER
                or c['old_value'] != 13 or c['new_value'] != 14
                or c['source'] != SOURCE or not c['reason'].strip()
                or actual.get(WALKER) != 13):
            raise ValueError('Unexpected Walker correction')
    elif corrections:
        raise ValueError(f'{year}: unexpected correction')
    seen = set()
    totals = Counter()
    out = {}
    for r in records:
        pid = r['mlbam_id']
        if r['season'] != str(year) or pid in seen or pid not in pool:
            raise ValueError(f'{year}: incorrect audit membership')
        seen.add(pid)
        if r['season_certified'] != 'True' or r['appearance_identity_verified'] != 'True':
            raise ValueError(f'{year}/{pid}: no row certification')
        k = year, 'pitcher', pid
        for metric in ('G','OUTS'):
            prior = 14 if k+(metric,) == WALKER else actual.get(k+(metric,))
            supplied = r['existing_'+metric]
            if prior != (float(supplied) if supplied else None):
                raise ValueError(f'{year}/{pid}: audit does not match frozen {metric}')
        state = r['status']
        totals[state] += 1
        n = int(r['observed_boxscore_G'])
        if state == 'VERIFIED_APPEARED':
            if (n <= 0 or int(r['proposed_G']) != n or r['proposed_OUTS']
                    or r['existing_G'] and float(r['existing_G']) != n):
                raise ValueError(f'{year}/{pid}: invalid appearance record')
            continue
        if (state != 'VERIFIED_NO_APPEARANCE' or n != 0
                or r['proposed_G'] != '0' or r['proposed_OUTS'] != '0'
                or any(actual.get(k+(m,)) not in (None,0) for m in ('G','OUTS'))):
            raise ValueError(f'{year}/{pid}: invalid non-appearance record')
        for m in ('G','OUTS'):
            out[k+(m,)] = 0
    if (seen != pool or dict(totals) != s['statuses']
            or totals['VERIFIED_NO_APPEARANCE'] != COUNTS[year]):
        raise ValueError(f'{year}: counts differ from certified run')
    if year == 2023:
        out[WALKER] = 14
    return out


def build(a):
    parent, lab, audits = (Path(x).resolve() for x in (a.parent,a.labels,a.audits_root))
    w = {}
    lp = checked(lab,'training_labels.parquet',w)
    freeze = load(checked(parent,'forecast_freeze.json',w))
    hp = registered(parent,'historical_forecasts.csv',w,freeze)
    if load(checked(parent,'input_hashes.json',w)).get(str(lp)) != w[str(lp)]:
        raise ValueError('Frozen labels are not bound to historical forecasts')
    pool = {y:set() for y in YEARS}
    for r in rows(hp):
        if (r['method'],r['player_type'],r['metric']) == (BASE,'pitcher','OUTS'):
            members = pool[int(r['season'])]
            if r['mlbam_id'] in members:
                raise ValueError('Duplicate frozen forecast pitcher-season')
            members.add(r['mlbam_id'])
    actual = labels(lp)
    records, sources = [], {}
    for y in YEARS:
        path = audits / (f'pitcher_label_coverage_{y}_'+('corrected' if y==2023 else 'v1_26_1'))
        rp, cp, ip = (checked(path,f,w) for f in ('report.json','pitcher_label_coverage.csv','input_hashes.json'))
        upstream = load(ip)
        if any(upstream.get(str(p)) != w[str(p)] for p in (hp,lp)):
            raise ValueError(f'{y}: audit inputs differ from current frozen inputs')
        report = load(rp)
        edits = audit_changes(y,report,rows(cp),pool[y],actual)
        records.extend(dict(season=y,player_type=typ,mlbam_id=pid,metric=metric,
                            old_value=actual.get((y,typ,pid,metric)),new_value=v,
                            reason='DOCUMENTED_WALKER_CORRECTION' if (y,typ,pid,metric)==WALKER else 'CERTIFIED_NON_APPEARANCE',
                            source_report=str(rp),source_report_sha256=w[str(rp)],
                            source_coverage=str(cp),source_coverage_sha256=w[str(cp)])
                       for (y,typ,pid,metric),v in sorted(edits.items()))
        sources[y] = dict(report=str(rp),report_sha256=w[str(rp)],
                          coverage=str(cp),coverage_sha256=w[str(cp)],
                          audit_inputs=str(ip),audit_inputs_sha256=w[str(ip)],
                          certified_zeros=COUNTS[y],applied_label_corrections=report.get('applied_label_corrections',[]))
    o,b,s = start(a.output,a.backup_root,[parent,lab]+[Path(x['report']).parent for x in sources.values()])
    try:
        emit(s/'participation_label_overlay.csv',records)
        summary = dict(version='1.27.0',training_labels_sha256=w[str(lp)],
                       historical_forecasts_sha256=w[str(hp)],certified_zero_players=sum(COUNTS.values()),
                       metric_rows=len(records),sources=sources,holdout_labels_read=False)
        dump(s/'report.json',summary)
        return dict(summary,output=str(o),backup=finish(o,b,s,w))
    finally:
        if s.exists():
            shutil.rmtree(s)


def apply_overlay(root, actual, lp, hp, w):
    cp = checked(root,'participation_label_overlay.csv',w)
    rp = checked(root,'report.json',w)
    r = load(rp)
    if (r['version']!='1.27.0' or r['holdout_labels_read'] is not False
            or r['training_labels_sha256']!=w[str(lp)] or r['historical_forecasts_sha256']!=w[str(hp)]
            or set(r['sources'])!={str(y) for y in YEARS}):
        raise ValueError('Overlay not bound to current frozen inputs')
    edits = {}
    grouped = Counter()
    for v in rows(cp):
        k = int(v['season']),v['player_type'],v['mlbam_id'],v['metric']
        y,typ,pid,m = k
        if y not in YEARS or typ!='pitcher' or not pid.isascii() or not pid.isdigit() or int(pid)<=0 or k in edits:
            raise ValueError(f'Invalid overlay key {k}')
        source = r['sources'][str(y)]
        if any(v['source_'+key] != source[key] for key in ('report','report_sha256','coverage','coverage_sha256')):
            raise ValueError('Overlay provenance mismatch')
        old = float(v['old_value']) if v['old_value'] else None
        new = int(v['new_value'])
        if old != actual.get(k):
            raise ValueError(f'Overlay old value mismatch {k}')
        if k == WALKER:
            if (old,new,v['reason']) != (13,14,'DOCUMENTED_WALKER_CORRECTION'):
                raise ValueError('Invalid Walker correction')
        else:
            if m not in ('G','OUTS') or old not in (0,None) or new != 0 or v['reason']!='CERTIFIED_NON_APPEARANCE':
                raise ValueError(f'Invalid zero label {k}')
            grouped[k[:3]] += 1
        edits[k] = new
    if (WALKER not in edits or any(n!=2 for n in grouped.values())
            or Counter(k[0] for k in grouped)!=COUNTS or len(edits)!=r['metric_rows']):
        raise ValueError('Incomplete overlay')
    return {**actual,**edits}, dict(path=str(root),report_sha256=w[str(rp)],csv_sha256=w[str(cp)],
                                   certified_zero_players=len(grouped),walker_correction=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--parent',default='outputs/recent_history_skills_v1_23')
    p.add_argument('--labels',default='outputs/training_labels_v1_0')
    p.add_argument('--audits-root',default='outputs')
    p.add_argument('--output',default='outputs/participation_label_overlay_v1_27')
    p.add_argument('--backup-root',default='backups')
    result=build(p.parse_args())
    print(json.dumps({k:v for k,v in result.items() if k!='sources'},indent=2))
