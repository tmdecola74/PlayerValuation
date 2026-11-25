"""Fixed returner workload diagnostic using v1.32 forecasts and prior MLB history."""
import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import shutil

from pitcher_three_way_v1_32 import METHODS, num, read

ARMS = (*METHODS, 'returner_guard')
RETURNER = 'ESTABLISHED_RETURNER'
WINDOW = 4
ESTABLISHED_IP = 100
LIGHT_IP = 50
RESTORE = 0.5


def cohort(year, pid, role, history):
    # Use the same four-year observation window at every origin. The most
    # recent year supplies the role, not the earlier workload threshold.
    k = lambda y: (y, 'pitcher', pid, 'OUTS')
    recent = history.get(k(year-1))
    earlier = [history.get(k(y)) for y in range(year-WINDOW, year-1)]
    known = sum(x is not None for x in earlier)
    ip = sum(x for x in earlier if x is not None) / 3
    if role == 'STARTER':
        group = 'PRIOR_STARTER'
    elif role != 'UNKNOWN':
        group = 'OTHER_KNOWN_ROLE'
    elif (recent is None or recent == 0) and ip >= ESTABLISHED_IP:
        group = RETURNER
    elif recent is not None and recent > 0:
        group = 'UNKNOWN_ROLE_WITH_RECENT_IP'
    elif known == len(earlier) and ip < LIGHT_IP:
        group = 'LOW_RECORDED_HISTORY'
    elif known != len(earlier):
        group = 'INCOMPLETE_HISTORY'
    else:
        group = 'INTERMEDIATE_HISTORY'
    return group, ip, known, None if recent is None else recent / 3


def analyze(rows, history, years):
    bins = defaultdict(list)
    details = []
    seen = set()
    for r in rows:
        year, pid, metric = int(r['season']), r['mlbam_id'], r['metric']
        key = (year, pid, metric)
        if (year not in years or metric not in {'IP','SO','W'} or key in seen
                or r['reporting_only'] != str(year == 2026) or r['hybrid_qs']):
            raise ValueError(f'Invalid v1.32 audit row: {key}')
        seen.add(key)
        if r['status'] != 'SCORED':
            continue
        role = r['prior_role']
        group, early_ip, known, recent = cohort(year, pid, role, history)
        a,b,h = (num(r[m]) for m in METHODS)
        truth = num(r['actual'])
        guarded = h + RESTORE * (b-h) if group == RETURNER and h < b else h
        # Counts use the same player rate and identical scored membership across methods.
        vals = (a,b,h,guarded)
        details.append(dict(r, history_cohort=group, earlier_ip=early_ip, earlier_years_known=known,
                            recent_ip=recent, returner_guard=guarded, guard_changed=guarded != h))
        # Appearance is a retrospective slice only; it cannot affect the forecast.
        for season in (year, '2023-2025') if year != 2026 else (year,):
            for g in ('ALL',group):
                for appearance in ('ALL',r['appearance']):
                    bins[season,metric,g,appearance].append((year,pid,truth,vals))
    summary = []
    for (season,metric,group,appearance), members in sorted(bins.items(), key=lambda item: str(item[0])):
        n = len(members)
        signature = hashlib.sha256(json.dumps(sorted((y,p) for y,p,_,_ in members)).encode()).hexdigest()
        for i,m in enumerate(ARMS):
            e = [v[i]-a for _,_,a,v in members]
            summary.append(dict(season=season, metric=metric, cohort=group, appearance=appearance,
                method=m, n=n, membership_sha256=signature, reporting_only=season==2026,
                rmse=math.sqrt(math.fsum(x*x for x in e)/n), mae=math.fsum(map(abs,e))/n,
                bias=math.fsum(e)/n,
                delta_sse_vs_hybrid=math.fsum(x*x-(v[2]-a)**2 for x,(_,_,a,v) in zip(e,members))))
    return summary,details


def run(args):
    from recent_skill_core_v1_23 import checked, emit
    from recent_skill_inputs_v1_23 import labels
    from participation_label_overlay_v1_27 import apply_overlay
    from standalone_io_v1_0 import dump, finish, load, start
    src,lab,res,overlay = roots = [Path(getattr(args,x)).resolve() for x in ('source','labels','research','overlay')]
    w = {}
    provenance = load(checked(src,'input_hashes.json',w))
    report = load(checked(src,'report.json',w))
    if report['version'] != '1.32.0' or report['default_changed'] or report['selection_uses_2026']:
        raise ValueError('Expected unchanged v1.32 research run')
    lp = checked(lab,'training_labels.parquet',w)
    hp = checked(res,'historical_forecasts.csv',w)
    history, _ = apply_overlay(overlay,labels(lp),lp,hp,w)
    # Audit and history must trace to the same source bytes used in v1.32.
    for p in (lp,hp,overlay/'report.json',overlay/'participation_label_overlay.csv'):
        if w[str(p)] not in {h for name,h in provenance.items()
                                 if name.replace(chr(92),'/').rsplit('/',1)[-1]==p.name}:
            raise ValueError(f'History provenance differs from v1.32: {p}')
    out,bak,stage = start(args.output,args.backup_root,roots)
    try:
        result = dict(version='1.33.0',status='RESEARCH_ONLY',default_method='accepted_ip',
            valuation_enabled=False,hybrid_qs=None,selection_uses_2026=False,models_refitted=False,
            earlier_ip_min=ESTABLISHED_IP,low_history_below_ip=LIGHT_IP,restored_fraction=RESTORE,
            notes=['Known earlier IP is a lower bound; missing history is not zero.',
                   'Low history requires three known earlier seasons; recent zero and missing are shown separately in player audit.',
                   'Raw hybrid and legacy stay frozen. The guard restores half of a downward hybrid cut only for established returners.',
                   'This is a sensitivity chosen after inspecting prior errors, not independent validation.'])
        for prefix,years in [('historical',{2023,2024,2025}),('evaluation_2026',{2026})]:
            summary, details = analyze(read(checked(src,f'{prefix}_player_audit.csv',w)),history,years)
            if {int(r['season']) for r in details} != years:
                raise ValueError(f'Incomplete {prefix} audit')
            emit(stage/f'{prefix}_cohort_scores.csv',summary)
            emit(stage/f'{prefix}_returner_audit.csv',details)
            result[prefix+'_returner_ip'] = [
                {k:r[k] for k in ('method','n','rmse','mae','bias')}
                for r in summary if r['cohort']==RETURNER and r['appearance']=='ALL'
                and r['metric']=='IP' and r['season'] in ('2023-2025',2026)]
            result[prefix+'_adjusted_pitcher_seasons'] = sum(r['metric']=='IP' and r['guard_changed'] for r in details)
        dump(stage/'report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for k,d in dict(source='outputs/pitcher_three_way_v1_32', labels='outputs/training_labels_v1_0',
                    research='outputs/recent_history_skills_v1_23', overlay='outputs/participation_label_overlay_v1_27',
                    output='outputs/pitcher_returners_v1_33', backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=d)
    print(json.dumps(run(p.parse_args()),indent=2))
