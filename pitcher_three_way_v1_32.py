"""Compare frozen legacy and weighted pitcher workloads; 2026 reporting only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import shutil

from project_2027_v1_31 import project, with_hybrid, read, num

METHODS = ('accepted_ip', 'weighted_actuals_ip', 'weighted_actuals_hybrid_ip')
METRICS = ('IP', 'SO', 'W')
HISTORY = (2023, 2024, 2025)


def legacy_rows(path, allowed):
    result = {}
    for row in read(path):
        season, pid = int(row['season']), row['mlbam_id']
        key = season, 'pitcher', pid
        if season not in allowed or key in result or not pid.isascii() or not pid.isdigit() or pid != str(int(pid)) or int(pid) <= 0:
            raise ValueError(f'Invalid or duplicate frozen pitcher identity: {key}')
        result[key] = num(row['accepted_ip'])
    return result


def overlay_2026(rows, actual, legacy, report):
    statuses, seen = Counter(), set()
    for row in rows:
        pid, status = row['mlbam_id'], row['status']
        k = (2026, 'pitcher', pid)
        if row['season'] != '2026' or k not in legacy or k in seen:
            raise ValueError(f'Unexpected 2026 overlay identity: {k}')
        seen.add(k)
        g, outs = int(row['evaluation_g']), int(row['evaluation_outs'])
        if not ((status == 'VERIFIED_APPEARED' and g > 0 and outs >= 0) or
                (status == 'VERIFIED_NO_APPEARANCE' and g == outs == 0)):
            raise ValueError(f'Invalid 2026 appearance evidence: {k}')
        for m, value in (('G', g), ('OUTS', outs)):
            if actual.get(k + (m,), value) != value:
                raise ValueError(f'Overlay conflicts with eligible label: {k}, {m}')
            actual[k + (m,)] = value
        statuses[status] += 1
    if seen != set(legacy) or len(seen) != report['preseason_pool'] or dict(statuses) != report['statuses']:
        raise ValueError('2026 evaluation overlay does not cover the frozen universe')


def replay(year, actual, legacy, model, features, forecast):
    before = {k: v for k, v in actual.items() if year-4 <= k[0] < year and k[1] == 'pitcher'}
    prior_ids = {k[2] for k in before}
    legacy_ids = {k[2] for k in legacy if k[0] == year}
    groups = defaultdict(list)
    audit = []
    coverage = Counter()
    for pid in sorted(prior_ids | legacy_ids, key=int):
        k = (year, 'pitcher', pid)
        baseline = project(before, 'pitcher', pid, year)
        old = legacy.get(k)
        # Neither model receives target-season actuals, nor a target-derived role.
        if baseline is not None and old is not None:
            baseline = with_hybrid(baseline, before, model, features, forecast)
        g, outs = (actual.get(k + (m,)) for m in ('G', 'OUTS'))
        no_appearance = g == outs == 0
        state = ('NON_APPEARANCE' if no_appearance else 'APPEARED'
                 if (g is not None and g > 0) or (outs is not None and outs > 0)
                 else 'UNKNOWN')
        prior = (baseline or {}).get('prior_role', 'UNKNOWN')
        ip = (baseline or {}).get('IP')
        hybrid = (baseline or {}).get('hybrid_ip')
        for metric in METRICS:
            truth = (None if outs is None else outs / 3) if metric == 'IP' else actual.get(k + (metric,))
            source = 'ELIGIBLE_LABEL_OR_CERTIFIED_OUTS' if truth is not None else 'UNKNOWN'
            if metric != 'IP' and no_appearance:
                if truth not in (0, None):
                    raise ValueError(f'Counting label conflicts with non-appearance: {k}, {metric}')
                if truth is None:
                    truth, source = 0, 'CERTIFIED_NON_APPEARANCE'
            rate = None
            if metric == 'IP':
                values = (old, ip, hybrid)
            else:
                count = (baseline or {}).get(metric)
                if count is not None and ip:
                    rate = count / ip
                values = tuple(None if x is None or rate is None else x * rate for x in (old, ip, hybrid))
            status = ('NO_WEIGHTED_HISTORY' if baseline is None else
                      'NO_FROZEN_ACCEPTED_IP' if old is None else
                      'ACTUAL_UNKNOWN' if truth is None else
                      'SHARED_RATE_UNAVAILABLE' if any(x is None for x in values) else 'SCORED')
            coverage[metric, status] += 1
            # QS is deliberately unmodeled for the challenger.
            audit.append(dict(season=year, mlbam_id=pid, metric=metric, prior_role=prior,
                              appearance=state, actual=truth, actual_source=source, status=status,
                              shared_rate_per_ip=rate, **dict(zip(METHODS, values)), hybrid_qs=None,
                              reporting_only=year==2026))
            if status == 'SCORED':
                for dim, cohort in (('ALL','ALL'), ('PRIOR_ROLE',prior), ('APPEARANCE',state)):
                    groups[metric, dim, cohort].append((pid, truth, values))
    scores = []
    for (metric, dim, cohort), entries in sorted(groups.items()):
        n = len(entries)
        membership = hashlib.sha256(json.dumps(sorted(p for p, _, _ in entries)).encode()).hexdigest()
        for i, method in enumerate(METHODS):
            errors = [v[i] - truth for _, truth, v in entries]
            mse = math.fsum(e*e for e in errors) / n
            scores.append(dict(season=year, metric=metric, dimension=dim, cohort=cohort, method=method,
                               reporting_only=year==2026, n=n, membership_sha256=membership,
                               mse=mse, rmse=math.sqrt(mse), mae=math.fsum(map(abs, errors))/n,
                               bias=math.fsum(errors)/n))
    status_rows = [dict(season=year, metric=m, status=s, n=n, reporting_only=year==2026)
                   for (m,s),n in sorted(coverage.items())]
    return scores, status_rows, audit


def historical_summary(scores):
    groups = defaultdict(list)
    for r in scores:
        if r['season'] in HISTORY and not r['reporting_only']:
            groups[r['metric'], r['method']].append(r)
    result = []
    for (metric, method), rows in sorted(groups.items()):
        n = sum(r['n'] for r in rows)
        averages = {k: math.fsum(r[k]*r['n'] for r in rows)/n for k in ('mse','mae','bias')}
        result.append(dict(metric=metric, method=method, n=n, seasons=len(rows),
                           rmse=math.sqrt(averages['mse']), **averages))
    return result


def run(args):
    from recent_skill_core_v1_23 import checked, emit
    from recent_skill_inputs_v1_23 import labels
    from standalone_io_v1_0 import dump, finish, load, start
    from pitcher_workload_v1_27 import features, forecast, registered
    from participation_label_overlay_v1_27 import apply_overlay

    lab, research, workload, evaluation, overlay = roots = [
        Path(getattr(args, name)).resolve() for name in ('labels','research','workload','evaluation','overlay')]
    watched = {}
    def take(root, name):
        return checked(root, name, watched)

    freeze = load(take(workload, 'forecast_freeze.json'))
    wp = load(registered(workload, 'report.json', watched, freeze))
    if (wp['version'] != '1.27.0' or wp['selected_method'] != 'accepted_ip'
            or wp['evaluation_outcomes_read'] is not False):
        raise ValueError('Require original frozen v1.27 workload run')
    def work(name):
        return registered(workload, name, watched, freeze)
    hist = work('historical_player_audit.csv')
    models = load(work('models.json'))
    lp = take(lab, 'training_labels.parquet')
    lr = take(lab, 'label_build_report.json')
    hp = take(research, 'historical_forecasts.csv')
    historical, info = apply_overlay(overlay, labels(lp), lp, hp, watched)
    bindings = wp['participation_label_overlay']
    if (wp['label_report_sha256'] != watched[str(lr)]
            or any(bindings[k] != info[k] for k in ('report_sha256','csv_sha256'))):
        raise ValueError('Historical label provenance differs from the frozen workload run')

    history_legacy = legacy_rows(hist, set(range(2019,2026)))
    output, backups, stage = start(args.output, args.backup_root, roots)
    try:
        def report_set(prefix, years, actual, legacy):
            scores, coverage, audit = [], [], []
            for year in years:
                s,c,a = replay(year, actual, legacy, models[str(year)], features, forecast)
                if {r['metric'] for r in s} != set(METRICS):
                    raise ValueError(f'No matched comparison pool for one or more metrics in {year}')
                scores.extend(s)
                coverage.extend(c)
                audit.extend(a)
            for kind, rows in (('scores',scores),('coverage',coverage),('player_audit',audit)):
                emit(stage/f'{prefix}_{kind}.csv', rows)
            return [r for r in scores if r['dimension']=='ALL']

        history_scores = report_set('historical', HISTORY, historical, history_legacy)
        pooled = historical_summary(history_scores)
        emit(stage/'historical_pooled_scores.csv', pooled)
        # Historical scores are constructed and staged before opening 2026 labels.
        ep = load(take(evaluation, 'report.json'))
        cold = work('frozen_2026_workload.csv')
        if (ep['version'] != '1.29.0' or ep['season_certified'] is not True
                or ep['complete_pool_scored'] is not True or ep['selection_uses_2026'] is not False
                or ep['models_refitted'] is not False or ep['default_method'] != 'accepted_ip'
                or ep['frozen_forecast_sha256'] != watched[str(cold)]):
            raise ValueError('Require complete certified v1.29 evaluation bound to v1.27 forecasts')
        evaluation_legacy = legacy_rows(cold, {2026})
        actual = historical | labels(take(lab,'holdout_labels.parquet'), 2026)
        overlay_2026(read(take(evaluation,'evaluation_label_overlay_2026.csv')), actual, evaluation_legacy, ep)
        eval_scores = report_set('evaluation_2026', (2026,), actual, evaluation_legacy)
        result = dict(version='1.32.0', status='RESEARCH_ONLY', default_method='accepted_ip',
                      default_changed=False, valuation_enabled=False, models_refitted=False,
                      selection_uses_2026=False, historical_years=list(HISTORY), evaluation_year=2026,
                      rates='Same four-year weighted SO/IP and W/IP across arms; workload-only sensitivity.',
                      hybrid_qs=None, historical_pooled=pooled, historical_overall=history_scores, evaluation_2026_overall=eval_scores)
        dump(stage/'report.json', result)
        return dict(result, output=str(output), backup=finish(output, backups, stage, watched))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    for k,d in dict(labels='outputs/training_labels_v1_0', research='outputs/recent_history_skills_v1_23',
                    workload='outputs/pitcher_workload_v1_27', evaluation='outputs/pitcher_evaluation_v1_29',
                    overlay='outputs/participation_label_overlay_v1_27', output='outputs/pitcher_three_way_v1_32',
                    backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'), default=d)
    return p


if __name__ == '__main__':
    print(json.dumps(run(parser().parse_args()), indent=2))
