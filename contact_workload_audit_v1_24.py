"""Frozen contact-only replay and pitcher workload diagnostics; no refitting."""
import argparse
import csv
import json
import math
import shutil
from collections import defaultdict
from pathlib import Path

from standalone_io_v1_0 import dump, finish, load, sha, start
from recent_skill_core_v1_23 import checked, coherent, emit, finite, member, number
from recent_skill_inputs_v1_23 import labels

VERSION = '1.24.0'
BASE = 'accepted_frozen'
ARMS = ('standard_recent', 'expanded_recent')
HITS = ('1B', '2B', '3B')
CONTACT = HITS + ('H', 'AVG', 'OBP', 'SLG', 'OPS')
GATE = ('AVG', 'OPS')
ROLES = ('STARTER', 'RELIEVER', 'SWING')


def rows(path):
    with path.open(encoding='utf-8-sig', newline='') as f:
        yield from csv.DictReader(f)


def registered(root, name, watched, freeze):
    p = checked(root, name, watched)
    if freeze.get(name) != watched[str(p)]:
        raise ValueError(f'Forecast freeze mismatch: {name}')
    return p


def key(row):
    k = int(row['season']), row['player_type'], row['mlbam_id']
    if k[1] not in ('hitter', 'pitcher') or not k[2].isdigit() or int(k[2]) <= 0:
        raise ValueError(f'Invalid forecast identity: {k}')
    return k


def vectors(path, years, methods):
    bank = defaultdict(dict)
    for r in rows(path):
        if r['method'] not in methods:
            continue
        k = key(r)
        d = bank[k, r['method']]
        if k[0] not in years or r['metric'] in d:
            raise ValueError('Invalid season or duplicate forecast metric')
        d[r['metric']] = number(r['prediction'])
    for (k, _), v in bank.items():
        coherent(k[1], v)
    if not bank:
        raise ValueError('Empty forecast pool')
    return dict(bank)


def contact_only(base, rates):
    """Allocate only the remaining AB budget after reserving frozen HR."""
    v = dict(base)
    if not all(finite(base.get(m)) for m in ('AB', 'HR', 'BB', 'HBP', 'SF')):
        return v, 'MISSING_ANCHOR'
    ab, hr = base['AB'], base['HR']
    if ab <= 0 or hr > ab:
        return v, 'NO_VALID_AB_BUDGET'
    if not all(finite(rates.get(m)) and rates[m] >= 0 for m in HITS):
        return v, 'UNSUPPORTED_CONTACT_RATE'
    raw = [ab * rates[m] for m in HITS]
    total = sum(raw)
    scale = min(1., (ab - hr) / total) if total > 0 else 1.
    v.update({m: x * scale for m, x in zip(HITS, raw)})
    v['H'] = hr + sum(v[m] for m in HITS)
    v['AVG'] = v['H'] / ab
    v['OBP'] = (v['H'] + v['BB'] + v['HBP']) / (ab + v['BB'] + v['HBP'] + v['SF'])
    v['SLG'] = (v['1B'] + 2 * v['2B'] + 3 * v['3B'] + 4 * hr) / ab
    v['OPS'] = v['OBP'] + v['SLG']
    coherent('hitter', v)
    return v, 'CAPPED_CONTACT' if scale < 1 else 'FITTED_CONTACT'


def replay(base, rate_file, years):
    rates = defaultdict(dict)
    for r in rows(rate_file):
        if r['player_type'] != 'hitter' or r['method'] not in ARMS or r['metric'] not in HITS:
            continue
        k = key(r)
        d = rates[k, r['method']]
        if k[0] not in years or (k, BASE) not in base or r['metric'] in d or r['denominator'] != 'AB':
            raise ValueError('Invalid contact-rate binding or duplicate')
        d[r['metric']] = number(r['prediction']) if r['model_status'] == 'FITTED' else None
    result = dict(base)
    support = []
    for (k, _), v in sorted(base.items()):
        if k[1] != 'hitter':
            continue
        for arm in ARMS:
            adjusted, status = contact_only(v, rates[k, arm])
            result[k, arm] = adjusted
            support.append(dict(season=k[0], player_type=k[1], mlbam_id=k[2], method=arm, status=status))
    return result, support


def role(g, gs):
    if not finite(g) or not finite(gs) or g <= 0 or not 0 <= gs <= g:
        return 'UNKNOWN'
    return 'STARTER' if gs/g >= .5 else 'RELIEVER' if gs/g <= .1 else 'SWING'


def contexts(bank, actual, role_dir, w, training):
    predicted = {}
    if role_dir is not None:
        freeze = load(checked(role_dir, 'freeze_manifest.json', w))
        p = checked(role_dir, 'role_predictions.csv', w)
        model = checked(role_dir, 'frozen_models.json', w)
        if (freeze['role_predictions_sha256'] != w[str(p)] or
                freeze['models_sha256'] != w[str(model)] or freeze['evaluation_outcomes_read'] or
                load(model)['training_labels_sha256'] != sha(training)):
            raise ValueError('v1.2 role reference does not match the frozen labels')
        for r in rows(p):
            if r['method'] != 'selected_role':
                continue
            k = int(r['season']), 'pitcher', r['mlbam_id']
            if k in predicted or r['predicted_role'] not in ROLES or r['latest_fit_year'] and int(r['latest_fit_year']) >= k[0]:
                raise ValueError('Invalid historical role forecast')
            predicted[k] = r['predicted_role']
    out = {}
    for k, method in bank:
        if method != BASE:
            continue
        y, player_type, pid = k
        lag = lambda year, m: actual.get((year, player_type, pid, m))
        history = sum((lag(t, 'AB') or 0) > 0 for t in range(y-3, y))
        out[k] = dict(history_cohort='ESTABLISHED_HISTORY' if history >= 2 else 'LOW_HISTORY',
                      prior_role=role(lag(y-1, 'G'), lag(y-1, 'GS')),
                      v1_2_selected_role=predicted.get(k, 'UNKNOWN'))
    return out


def exposure(outs):
    if outs is None:
        return 'UNKNOWN'
    return 'ZERO' if outs == 0 else 'LT20_IP' if outs < 60 else '20_99_IP' if outs < 300 else 'GE100_IP'


def score(groups):
    return [dict(**dict(zip(('season', 'metric', 'dimension', 'cohort', 'comparison', 'method'), k)),
                 n=len(es), mse=sum(e*e for _, e in es)/len(es),
                 rmse=math.sqrt(sum(e*e for _, e in es)/len(es)),
                 mae=sum(abs(e) for _, e in es)/len(es), bias=sum(e for _, e in es)/len(es),
                 membership_sha256=member([pid for pid, _ in es]))
            for k, es in sorted(groups.items()) if es]


def hitter_scores(bank, actual, context, support, fitted):
    good = {(key(r), r['method']) for r in support if r['status'] in ('FITTED_CONTACT', 'CAPPED_CONTACT')}
    groups = defaultdict(list)
    for (k, method), v in bank.items():
        if k[1] != 'hitter' or method != BASE:
            continue
        ab = actual.get(k+('AB',))
        if not finite(ab) or ab <= 0:
            continue
        if fitted and (ab < 30 or not all((k, arm) in good for arm in ARMS) or
                       not all(finite(actual.get(k+(m,))) and all(finite(bank[k, a].get(m)) for a in (BASE, *ARMS)) for m in GATE)):
            continue
        pa = actual.get(k+('PA',))
        exp = 'UNKNOWN' if pa is None else 'LT100_PA' if pa < 100 else '100_299_PA' if pa < 300 else 'GE300_PA'
        methods = (BASE, *ARMS) if fitted else tuple(m for m in (BASE, *ARMS, 'historical_selected') if (k, m) in bank)
        for m in (*CONTACT, 'HR', 'AB'):
            truth = actual.get(k+(m,))
            if not finite(truth) or not all(finite(bank[k, a].get(m)) for a in methods):
                continue
            for dim, cohort in [('ALL','ALL'), ('HISTORY',context[k]['history_cohort']), ('ACTUAL_EXPOSURE',exp)]:
                for arm in methods:
                    groups[k[0], m, dim, cohort, 'all_contact_arms', arm].append((k[2], bank[k, arm][m]-truth))
    return score(groups)


def choose(scores, origin):
    """Prespecified matched AVG/OPS gate, applied only to earlier seasons."""
    if not 2019 <= origin <= 2026:
        raise ValueError('Invalid selection origin')
    index = {(r['season'], r['metric'], r['cohort'], r['method']):r
             for r in scores if r['season'] < origin and r['dimension'] in ('ALL','HISTORY')}
    decisions = {}
    for arm in ARMS:
        checks = []
        for ref in (BASE,) if arm == ARMS[0] else (BASE, ARMS[0]):
            for cohort in ('ALL', 'RECENT', 'LOW_HISTORY', 'ESTABLISHED_HISTORY'):
                source = 'ALL' if cohort == 'RECENT' else cohort
                window = list(range(origin-2, origin)) if cohort == 'RECENT' else list(range(2019, origin))
                floor = 30 if source == 'ALL' else 20
                years = [y for y in window if all(index.get((y,m,source,a),{}).get('n',0) >= floor for m in GATE for a in (arm,ref))]
                support = len(years) >= (3 if cohort == 'ALL' else 2)
                per_metric = {}
                for m in GATE:
                    for loss in ('mse','mae'):
                        ratios = [index[y,m,source,arm][loss]/index[y,m,source,ref][loss]
                                  for y in years if index[y,m,source,ref][loss] > 0]
                        per_metric[m+'_'+loss] = sum(ratios)/len(ratios) if ratios and len(ratios)==len(years) else None
                values = [per_metric[m+'_mse'] for m in GATE]
                objective = sum(values)/len(values) if all(finite(v) for v in values) else None
                threshold = .99 if cohort == 'ALL' else 1.01
                guard = 1.01 if cohort == 'ALL' else 1.02
                checks.append(dict(reference=ref, cohort=cohort, years=years, sufficient_support=support,
                                   objective=objective, ratios=per_metric, passed=bool(support and objective is not None and
                                   objective <= threshold and all(finite(v) and v <= guard for v in per_metric.values()))))
        decisions[arm] = dict(passed=all(r['passed'] for r in checks), checks=checks)
    passing = [a for a in ARMS if decisions[a]['passed']]
    return dict(origin=origin, selected=min(passing,key=lambda a:decisions[a]['checks'][0]['objective']) if passing else BASE,
                selection_max_season=origin-1, candidates=decisions)


def pitcher_diagnostics(bank, actual, context, external):
    groups = defaultdict(list)
    detail = []
    confusion = defaultdict(int)
    benchmarks = defaultdict(dict)
    sources_by_year = defaultdict(set)
    for r in external:
        if r['player_type'] != 'pitcher' or r['metric'] not in ('IP','ERA'):
            continue
        k = key(r), r['metric']
        if r['source'] in benchmarks[k]:
            raise ValueError('Duplicate benchmark metric')
        benchmarks[k][r['source']] = number(r['prediction'])
        sources_by_year[k[0][0]].add(r['source'])
    for (k, method), v in sorted(bank.items()):
        if k[1] != 'pitcher' or method != BASE:
            continue
        outs = actual.get(k+('OUTS',))
        ip = outs/3 if finite(outs) else None
        era = actual.get(k+('ERA',)) if finite(outs) and outs > 0 else None
        g, gs = (actual.get(k+(m,)) for m in ('G','GS'))
        ar = role(g, gs)
        pr = context[k]['prior_role']
        pred = context[k]['v1_2_selected_role']
        exp = exposure(outs)
        detail.append(dict(season=k[0], mlbam_id=k[2], prior_role=pr, actual_role=ar, v1_2_selected_role=pred,
                           actual_G=g, actual_GS=gs, exposure=exp, predicted_IP=v['IP'], actual_IP=ip,
                           IP_error=v['IP']-ip if finite(v['IP']) and finite(ip) else None,
                           predicted_ERA=v['ERA'], actual_ERA=era, frozen_SV=v['SV'], frozen_HLD=v['HLD']))
        if ar in ROLES and pr in ROLES and pred in ROLES:
            for name, predicted in [('prior_role',pr),('v1_2_selected_role',pred)]:
                confusion[k[0],name,ar,predicted] += 1
        for m, truth in [('IP',ip),('ERA',era)]:
            if not finite(truth) or not finite(v[m]):
                continue
            available = benchmarks[k,m]
            expected = sorted(sources_by_year[k[0]])
            comparisons = [('accepted_only',{BASE:v[m]})]
            comparisons += [('paired_'+a,{BASE:v[m],a:p}) for a,p in available.items() if finite(p)]
            if expected and all(finite(available.get(a)) for a in expected):
                comparisons.append(('all_available_benchmarks',{BASE:v[m],**{a:available[a] for a in expected}}))
            for group, methods in comparisons:
                for dim, cohort in [('ALL','ALL'),('ACTUAL_EXPOSURE',exp),('PRIOR_ROLE',pr),
                                    ('ACTUAL_ROLE',ar),('ROLE_TRANSITION',pr+'->'+ar),
                                    ('V1_2_PREDICTED_ROLE',pred),
                                    ('V1_2_ROLE_MATCH','UNKNOWN' if ar not in ROLES or pred not in ROLES
                                     else 'MATCH' if ar==pred else 'MISMATCH')]:
                    for a,p in methods.items():
                        groups[k[0],m,dim,cohort,group,a].append((k[2],p-truth))
    cm = [dict(season=y, method=m, actual_role=a, predicted_role=p, n=n)
          for (y,m,a,p),n in sorted(confusion.items())]
    return score(groups), detail, cm


def flatten(bank):
    return [dict(season=k[0], player_type=k[1], mlbam_id=k[2], method=method, metric=m, prediction=p)
            for (k,method),v in sorted(bank.items()) for m,p in v.items()]


def build(a):
    ref, lab = Path(a.reference).resolve(), Path(a.labels).resolve()
    w = {}
    freeze = load(checked(ref,'forecast_freeze.json',w))
    report = load(registered(ref,'recent_history_build_report.json',w,freeze))
    if report['version'] != '1.23.0' or report['evaluation_outcomes_read'] or report['accepted_forecasts_modified']:
        raise ValueError('Require an unchanged v1.23 research freeze')
    binding = load(checked(ref,'input_hashes.json',w))
    lp = checked(lab,'training_labels.parquet',w)
    lr = checked(lab,'label_build_report.json',w)
    if any(binding.get(str(p)) != w[str(p)] for p in (lp,lr)):
        raise ValueError('Label source differs from the v1.23 binding')
    actual = labels(lp)
    years = range(2019,2026)
    hist, hs = replay(vectors(registered(ref,'historical_forecasts.csv',w,freeze),years,{BASE}),
                      registered(ref,'historical_skill_rates.csv',w,freeze),years)
    hold, fs = replay(vectors(registered(ref,'frozen_2026_forecasts.csv',w,freeze),{2026},{BASE}),
                      registered(ref,'frozen_2026_skill_rates.csv',w,freeze),{2026})
    role_dir = None if a.skip_roles or not Path(a.roles).exists() else Path(a.roles).resolve()
    context = contexts(hist|hold,actual,role_dir,w,lp)
    print('Scoring historical contact folds; pitcher forecasts are unchanged.',flush=True)
    fitted = hitter_scores(hist,actual,context,hs,True)
    choices = {y:choose(fitted,y) for y in range(2019,2027)}
    for bank in (hist,hold):
        for k,method in list(bank):
            if method == BASE and k[1]=='hitter':
                bank[k,'historical_selected'] = bank[k,choices[k[0]]['selected']]
    external = [r for r in rows(registered(ref,'frozen_benchmark_predictions.csv',w,freeze))
                if r.get('player_type')=='pitcher' and r['metric'] in ('IP','ERA')]
    ps,pd,cm = pitcher_diagnostics(hist,actual,context,external)
    out,bak,stage = start(a.output,a.backup_root,[ref,lab]+([role_dir] if role_dir else []))
    try:
        for name,data in [('historical_contact_scores',hitter_scores(hist,actual,context,hs,False)),
                          ('historical_fitted_contact_scores',fitted),('historical_pitcher_scores',ps),
                          ('historical_pitcher_player_errors',pd),('historical_role_confusion',cm),
                          ('frozen_2026_forecasts',flatten(hold)),('frozen_2026_contact_support',fs),
                          ('frozen_pitcher_benchmarks',[r for r in external if r['season']=='2026']),
                          ('frozen_2026_context',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],**c)
                                                 for k,c in sorted(context.items()) if k[0]==2026])]:
            emit(stage/(name+'.csv'),data)
        dump(stage/'rolling_contact_choices.json',choices)
        rep=dict(version=VERSION,selected_contact=choices[2026]['selected'],role_reference_available=role_dir is not None,
                 models_refitted=False,new_source_promoted=False,pitcher_forecasts_modified=False,
                 evaluation_outcomes_read=False,label_report_sha256=w[str(lr)])
        dump(stage/'build_report.json',rep)
        dump(stage/'forecast_freeze.json',{p.name:sha(p) for p in stage.iterdir()})
        return dict(rep,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def evaluate(a):
    ref,lab = Path(a.run).resolve(),Path(a.labels).resolve()
    w = {}
    freeze = load(checked(ref,'forecast_freeze.json',w))
    report = load(registered(ref,'build_report.json',w,freeze))
    if report['version'] != VERSION or report['evaluation_outcomes_read']:
        raise ValueError('Invalid v1.24 freeze')
    lr = checked(lab,'label_build_report.json',w)
    if w[str(lr)] != report['label_report_sha256']:
        raise ValueError('Label reference differs from build')
    bank = vectors(registered(ref,'frozen_2026_forecasts.csv',w,freeze),{2026},{BASE,*ARMS,'historical_selected'})
    context = {key(r):r for r in rows(registered(ref,'frozen_2026_context.csv',w,freeze))}
    support = list(rows(registered(ref,'frozen_2026_contact_support.csv',w,freeze)))
    external = list(rows(registered(ref,'frozen_pitcher_benchmarks.csv',w,freeze)))
    actual = labels(checked(lab,'holdout_labels.parquet',w),2026)
    ps,pd,cm = pitcher_diagnostics(bank,actual,context,external)
    out,bak,stage = start(a.output,a.backup_root,[ref,lab])
    try:
        for name,data in [('evaluation_contact_scores',hitter_scores(bank,actual,context,support,False)),
                          ('evaluation_fitted_contact_scores',hitter_scores(bank,actual,context,support,True)),
                          ('evaluation_pitcher_scores',ps),('evaluation_pitcher_player_errors',pd),
                          ('evaluation_role_confusion',cm)]:
            emit(stage/(name+'.csv'),data)
        rep=dict(version=VERSION,status='PREVIOUSLY_REVIEWED_2026_REPORTING_ONLY',
                 selected_contact=report['selected_contact'],selection_uses_2026=False,
                 models_refitted=False,forecasts_modified=False,role_reference_available=report['role_reference_available'])
        dump(stage/'evaluation_report.json',rep)
        return dict(rep,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluate',action='store_true')
    p.add_argument('--reference',default='outputs/recent_history_skills_v1_23')
    p.add_argument('--run',default='outputs/contact_workload_audit_v1_24')
    p.add_argument('--labels',default='outputs/training_labels_v1_0')
    p.add_argument('--roles',default='outputs/standalone_role_workload_v1_2')
    p.add_argument('--skip-roles',action='store_true')
    p.add_argument('--output')
    p.add_argument('--backup-root',default='backups')
    a = p.parse_args()
    a.output = a.output or ('outputs/contact_workload_audit_v1_24_evaluation' if a.evaluate else a.run)
    print(json.dumps((evaluate if a.evaluate else build)(a),indent=2))
