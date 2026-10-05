"""Stage 2: retrospective projection evaluation on reproducible player cohorts."""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

VERSION = '1.0'


def finite(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def ranks(values):
    """Ascending average ranks: tied observations receive the same mean rank."""
    result = [0.0] * len(values)
    ordered = sorted(range(len(values)), key=lambda i: values[i])
    start = 0
    while start < len(ordered):
        end = start + 1
        while end < len(ordered) and values[ordered[end]] == values[ordered[start]]:
            end += 1
        rank = (start + 1 + end) / 2
        for i in ordered[start:end]:
            result[i] = rank
        start = end
    return result


def pearson(x, y):
    if len(x) < 2:
        return None
    mx, my = statistics.fmean(x), statistics.fmean(y)
    xx = math.fsum((v-mx)**2 for v in x)
    yy = math.fsum((v-my)**2 for v in y)
    if xx == 0 or yy == 0:
        return None
    return max(-1.0, min(1.0, math.fsum((a-mx)*(b-my) for a,b in zip(x,y)) / math.sqrt(xx*yy)))


def score(pairs, correlation_min_n):
    n = len(pairs)
    blank = dict(n=n, mae=None, rmse=None, bias=None, pearson=None, spearman=None,
                 rank_mae=None, normalized_rank_mae=None, mean_projected=None,
                 mean_actual=None, correlation_status='insufficient_sample')
    if not n:
        return blank
    predicted, actual = zip(*pairs)
    errors = [p-a for p,a in pairs]
    blank.update(mae=statistics.fmean(abs(e) for e in errors),
                 rmse=math.sqrt(statistics.fmean(e*e for e in errors)),
                 bias=statistics.fmean(errors), mean_projected=statistics.fmean(predicted),
                 mean_actual=statistics.fmean(actual))
    if n >= max(2, correlation_min_n):
        pr, ar = ranks(predicted), ranks(actual)
        blank.update(pearson=pearson(predicted,actual), spearman=pearson(pr,ar),
                     rank_mae=statistics.fmean(abs(p-a) for p,a in zip(pr,ar)))
        blank['normalized_rank_mae'] = blank['rank_mae'] / (n-1)
        blank['correlation_status'] = 'ok' if blank['pearson'] is not None else 'constant_series'
    return blank


def write_csv(path, rows, fields=None):
    fields = fields or list(dict.fromkeys(k for row in rows for k in row)) or ['status']
    with path.open('w', encoding='utf-8-sig', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({k:json.dumps(v, ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})


def qualifies(row, cohort, exposure):
    actual = row['actual'].get(exposure)
    projected = row['projected'].get(exposure)
    return (finite(actual) and actual > 0 and actual >= cohort['minimum_actual']
            and (cohort.get('minimum_projected',0) <= 0 or
                 finite(projected) and projected >= cohort['minimum_projected']))


def derive_missing(values, formulas, excluded):
    derived = []
    for metric, formula in formulas.items():
        if metric in excluded or finite(values.get(metric)):
            continue
        operands = [values.get(m) for m in formula['sum']]
        if all(finite(v) for v in operands):
            values[metric] = math.fsum(operands)
            derived.append(metric)
    return derived


def evaluate(config_path, output=None, database=None):
    config_path = Path(config_path).resolve()
    project = config_path.parent.parent
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    db_path = Path(database or project / cfg['warehouse']).resolve()
    destination = Path(output or project / cfg['output']).resolve()
    if destination.exists() and any(destination.iterdir()):
        raise ValueError(f'Output must be new or empty: {destination}')
    if destination == db_path or destination in db_path.parents:
        raise ValueError('Output must not contain the input warehouse')
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    if cfg['correlation_min_n'] < 2 or cfg['ranking_min_n'] < 2:
        raise ValueError('Minimum sample sizes must be at least two')
    for typ in cfg['player_types'].values():
        if len({c['name'] for c in typ['cohorts']}) != len(typ['cohorts']):
            raise ValueError('Cohort names must be unique')
        if any(c['minimum_actual']<0 or c.get('minimum_projected',0)<0 for c in typ['cohorts']):
            raise ValueError('Playing-time thresholds must be nonnegative')
        metric_names=[m for group in typ['metric_groups'].values() for m in group]
        if len(set(metric_names)) != len(metric_names):
            raise ValueError('Each metric must appear in exactly one reporting group per player type')
    fingerprint = hashlib.sha256(db_path.read_bytes()).hexdigest()
    conn = sqlite3.connect(db_path.as_uri() + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    records, coverage, exclusions, derivations = [], [], [], []
    try:
        if conn.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Warehouse integrity check failed')
        registry={r['metric']:json.loads(r['metadata_json']) for r in conn.execute('SELECT * FROM metric_registry')}
        for typ, settings in cfg['player_types'].items():
            metrics=[m for group in settings['metric_groups'].values() for m in group]
            unknown = [m for m in metrics if m not in registry or typ not in registry[m]['player_types']]
            if unknown:
                raise ValueError(f'Metrics absent from warehouse registry for {typ}: {unknown}')
            # Never independently join by name or guess actuals. Consume the
            # reviewed Stage 1B link and verify the exact identity/type/season.
            sql=f'''SELECT p.*,a.record_id AS linked_actual_id,a.season AS actual_season,
                a.player_id AS actual_player_id,a.identity_conflict AS actual_conflict,
                a.metrics_json AS actual_metrics_json
                FROM analytical_{typ}_projections p LEFT JOIN {typ}_actuals a
                ON p.actual_record_id=a.record_id'''
            seen=set()
            for entry in conn.execute(sql):
                r=dict(entry)
                key=(typ,r['season'],r['source'],r['player_id'])
                if key in seen:
                    raise ValueError(f'Duplicate analytical projection key: {key}')
                seen.add(key)
                row=dict(player_type=typ,season=r['season'],source=r['source'],
                         player_id=r['player_id'],name=r['name'],record_id=r['record_id'],
                         actual_record_id=r['linked_actual_id'],projected=json.loads(r['metrics_json']),
                         actual=json.loads(r['actual_metrics_json']) if r['actual_metrics_json'] else {},
                         match_status=r['match_status'],excluded_metrics=json.loads(r['excluded_metrics_json']))
                if row['match_status']=='matched':
                    if not r['linked_actual_id'] or r['season']!=r['actual_season'] or r['player_id']!=r['actual_player_id'] or r['actual_conflict']:
                        raise ValueError(f'Invalid reviewed actual link: {r["record_id"]}')
                for side in ('projected','actual'):
                    derived=derive_missing(row[side],settings.get('derive_if_missing',{}),row['excluded_metrics'] if side=='projected' else [])
                    for metric in derived:
                        derivations.append(dict(player_type=typ,season=row['season'],source=row['source'],
                            player_id=row['player_id'],record_id=row['record_id'],side=side,metric=metric,
                            formula=settings['derive_if_missing'][metric],value=row[side][metric]))
                records.append(row)
            for entry in conn.execute('SELECT * FROM record_selection WHERE player_type=? AND kind=? AND selected=0',(typ,'projection')):
                exclusions.append(dict(player_type=typ,record_id=entry['record_id'],reason=entry['selection_reason']))
    finally:
        conn.close()
    groups=defaultdict(list)
    for row in records:
        groups[(row['player_type'],row['season'],row['source'])].append(row)
    for (typ,season,source),rows in sorted(groups.items()):
        coverage.append(dict(player_type=typ,season=season,source=source,
                             selected_projection_rows=len(rows),matched_rows=sum(r['match_status']=='matched' for r in rows),
                             unmatched_rows=sum(r['match_status']!='matched' for r in rows)))
    metric_availability, evaluation_pairs, missing_metrics = [], [], []
    for (typ,season,source),rows in sorted(groups.items()):
        for category,metrics in cfg['player_types'][typ]['metric_groups'].items():
            for metric in metrics:
                paired=0
                for row in rows:
                    if row['match_status']!='matched':
                        continue
                    p,a=row['projected'].get(metric),row['actual'].get(metric)
                    if finite(p) and finite(a):
                        paired+=1
                        evaluation_pairs.append(dict(player_type=typ,season=season,source=source,
                            player_id=row['player_id'],name=row['name'],record_id=row['record_id'],
                            actual_record_id=row['actual_record_id'],metric=metric,classification=category,
                            projected=p,actual=a,error=p-a,absolute_error=abs(p-a)))
                    else:
                        reason='reviewed_metric_exclusion' if metric in row['excluded_metrics'] else 'missing_projection_metric' if not finite(p) else 'missing_actual_metric'
                        missing_metrics.append(dict(player_type=typ,season=season,source=source,
                            player_id=row['player_id'],record_id=row['record_id'],metric=metric,reason=reason))
                metric_availability.append(dict(player_type=typ,season=season,source=source,metric=metric,
                    classification=category,projection_values=sum(finite(r['projected'].get(metric)) for r in rows),
                    matched_rows=sum(r['match_status']=='matched' for r in rows),paired_metric_rows=paired))
    summary, paired_comparisons, memberships = [], [], []
    index=defaultdict(dict)
    for row in records:
        index[(row['player_type'],row['season'],row['source'])][row['player_id']]=row
    for typ,settings in cfg['player_types'].items():
        seasons=sorted({r['season'] for r in records if r['player_type']==typ})
        for season in seasons:
            sources=sorted(s for t,y,s in index if t==typ and y==season)
            for category,metrics in settings['metric_groups'].items():
                for metric in metrics:
                    # Metric-capable sources are identified before cohort filtering.
                    # A source does not disappear merely because its eligible sample
                    # is empty. Availability and missing metrics are exported.
                    capable=[s for s in sources if any(finite(r['projected'].get(metric)) for r in index[(typ,season,s)].values())]
                    for cohort in settings['cohorts']:
                        eligible={s:{pid:r for pid,r in index[(typ,season,s)].items()
                            if r['match_status']=='matched' and qualifies(r,cohort,settings['exposure'])
                            and finite(r['projected'].get(metric)) and finite(r['actual'].get(metric))} for s in capable}
                        comparisons=[('source_specific',[s]) for s in capable]
                        if len(capable)>=2:
                            comparisons.append(('common_all',capable))
                        comparisons.extend(('pairwise',list(pair)) for pair in itertools.combinations(capable,2))
                        for mode,participants in comparisons:
                            player_ids=sorted(set.intersection(*(set(eligible[s]) for s in participants)))
                            sample_payload=dict(player_type=typ,season=season,cohort=cohort['name'],metric=metric,
                                                comparison=mode,sources=participants,player_ids=player_ids)
                            sample_id=hashlib.sha256(json.dumps(sample_payload,sort_keys=True).encode()).hexdigest()[:24]
                            memberships.append(dict(sample_id=sample_id,**sample_payload))
                            results=[]
                            for source in participants:
                                stats=score([(eligible[source][pid]['projected'][metric],eligible[source][pid]['actual'][metric]) for pid in player_ids],cfg['correlation_min_n'])
                                row=dict(player_type=typ,season=season,metric=metric,classification=category,
                                         cohort=cohort['name'],exposure=settings['exposure'],minimum_actual=cohort['minimum_actual'],
                                         minimum_projected=cohort.get('minimum_projected',0),comparison=mode,
                                         compared_sources=participants,source=source,sample_id=sample_id,
                                         ranking_eligible=stats['n']>=cfg['ranking_min_n'],**stats)
                                summary.append(row)
                                results.append(row)
                            if mode=='pairwise':
                                a,b=results
                                delta=a['mae']-b['mae'] if a['n'] else None
                                paired_comparisons.append(dict(player_type=typ,season=season,metric=metric,classification=category,
                                    cohort=cohort['name'],source_a=a['source'],source_b=b['source'],n=a['n'],
                                    source_a_mae=a['mae'],source_b_mae=b['mae'],mae_delta_a_minus_b=delta,
                                    lower_mae_source=(a['source'] if delta<0 else b['source'] if delta>0 else 'tie') if a['ranking_eligible'] else '',
                                    ranking_eligible=a['ranking_eligible'],sample_id=sample_id))
    if hashlib.sha256(db_path.read_bytes()).hexdigest()!=fingerprint:
        raise RuntimeError('Input warehouse changed during evaluation')
    destination.mkdir(parents=True,exist_ok=True)
    for name,rows in [('accuracy_summary',summary),('pairwise_comparisons',paired_comparisons),
                      ('common_player_accuracy',[r for r in summary if r['comparison']=='common_all']),
                      ('source_specific_accuracy',[r for r in summary if r['comparison']=='source_specific']),
                      ('input_coverage',coverage),('metric_availability',metric_availability),
                      ('evaluation_pairs',evaluation_pairs),('missing_metric_pairs',missing_metrics),
                      ('excluded_projection_records',exclusions),('metric_derivations',derivations)]:
        write_csv(destination/f'{name}.csv',rows)
    with (destination/'cohort_memberships.jsonl').open('w',encoding='utf-8') as f:
        for row in memberships:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    report=dict(version=VERSION,built_at_utc=datetime.now(timezone.utc).isoformat(),
                warehouse=str(db_path),warehouse_sha256=fingerprint,
                selected_projection_rows=len(records),matched_projection_rows=sum(r['match_status']=='matched' for r in records),
                unmatched_projection_rows=sum(r['match_status']!='matched' for r in records),
                excluded_projection_records=len(exclusions),metric_pairs=len(evaluation_pairs),
                missing_metric_pairs=len(missing_metrics),summary_rows=len(summary),
                derived_metric_values=len(derivations),
                pairwise_comparisons=len(paired_comparisons),sample_sets=len(memberships),
                bias_definition='projection minus actual; positive means overprojection',
                weighting='one equal-weight observation per matched player-season within each sample',
                pooled_seasons=False,coverage=coverage,
                config=cfg,notes=['Sources are ranked only within the same season, metric, cohort and common-player sample.',
                                 'Lower MAE is descriptive; it does not establish statistically significant superiority.',
                                 'Source-specific results use different player populations and must not be ranked against one another.',
                                 'Missing/unmatched statistics are never assigned zero. Rate metrics are evaluated unweighted.',
                                 'This is retrospective evaluation of supplied preseason files, not fitted consensus or future out-of-sample evidence.'])
    (destination/'evaluation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (destination/'effective_config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    (destination/'metric_registry_snapshot.json').write_text(json.dumps(registry,indent=2),encoding='utf-8')
    render_report(destination,report,summary,metric_availability)
    return report


def render_report(destination,report,summary,availability):
    cfg=report['config']
    lines=['# Stage 2 — historical projection accuracy','',
           f"Matched analytical projections: **{report['matched_projection_rows']:,}**. Unmatched analytical projections excluded: **{report['unmatched_projection_rows']:,}**.",
           '', 'Errors use projection minus actual: positive bias means overprojection. MAE and RMSE are in each metric\'s original units. Percentage metrics are fractions; multiply errors by 100 for percentage points.',
           '', 'The tables below compare every metric-capable source available that season on exactly the same players. Sources can differ across metrics. No seasons are pooled. These are descriptive lowest-MAE results, not statistically established winners.',
           '', f"Correlations and rank errors require at least {cfg['correlation_min_n']} observations; rankings require {cfg['ranking_min_n']}. Constant-series correlations remain blank. Rate errors are equally weighted by player, with PA/IP thresholds controlling small samples.",
           '', 'All original rows remain in Stage 1B. Only reviewed analytical selections enter Stage 2. Greg Jones\'s WAR, wRC+, Off and Def remain excluded; they are outside this configured metric set.',
           '', '## Common-player comparisons']
    for typ,settings in cfg['player_types'].items():
        headline=settings['headline_cohort']
        cohort=next(c for c in settings['cohorts'] if c['name']==headline)
        lines.extend(['',f"### {typ.title()}s — {headline}",'',
                      f"Actual {settings['exposure']} ≥ {cohort['minimum_actual']}; projected floor {cohort.get('minimum_projected',0)}. Every evaluated player has positive actual {settings['exposure']}."])
        for category in settings['metric_groups']:
            lines.extend(['',f'#### {category.replace("_"," ").title()}','',
                          '|Season|Metric|Sources|Players|Lowest MAE source|MAE|RMSE|Bias|Spearman|',
                          '|---|---|---:|---:|---|---:|---:|---:|---:|'])
            buckets=defaultdict(list)
            for r in summary:
                if r['player_type']==typ and r['cohort']==headline and r['comparison']=='common_all' and r['classification']==category:
                    buckets[(r['season'],r['metric'])].append(r)
            for (season,metric),rows in sorted(buckets.items()):
                eligible=[r for r in rows if r['ranking_eligible']]
                if not eligible:
                    lines.append(f"|{season}|{metric}|{len(rows)}|{rows[0]['n']}|Insufficient sample|—|—|—|—|")
                    continue
                best=min(eligible,key=lambda r:r['mae'])
                names=' / '.join(r['source'] for r in eligible if math.isclose(r['mae'],best['mae'],rel_tol=1e-12,abs_tol=1e-12))
                fmt=lambda v:'—' if v is None else f'{v:.5g}'
                lines.append(f"|{season}|{metric}|{len(rows)}|{best['n']}|{names}|{fmt(best['mae'])}|{fmt(best['rmse'])}|{fmt(best['bias'])}|{fmt(best['spearman'])}|")
    lines.extend(['','## Reading the detailed outputs','',
                  '* `accuracy_summary.csv`: every source/season/metric/cohort, including source-specific, common-all and pairwise samples.',
                  '* `common_player_accuracy.csv`: all-source common-player comparisons only; compare sources within the same sample_id.',
                  '* `source_specific_accuracy.csv`: individual-source diagnostics; player populations differ across sources.',
                  '* `pairwise_comparisons.csv`: two-source comparisons on identical players. Positive MAE delta means source B has lower error.',
                  '* `cohort_memberships.jsonl`: exact player IDs and source sets for each sample_id. Match sample_id across outputs.',
                  '* `evaluation_pairs.csv`: linked projected/actual values and errors before cohort filtering.',
                  '* `input_coverage.csv`: selected, matched and unmatched counts. Unmatched never means assumed zero.',
                  '* `metric_availability.csv`, `missing_metric_pairs.csv`: unavailable fields and explicit missing-value reasons.',
                  '* `excluded_projection_records.csv`: source rows excluded by the reviewed analytical selection policy.',
                  '* `metric_derivations.csv`: missing OPS derived from OBP + SLG, with input side and formula recorded. Original values are never overwritten.',
                  '', 'Only compare rows with the same sample_id when comparing sources. Pairwise and common-all estimates can differ because their player populations differ. Each metric has its own complete-value sample.',
                  '', '## Limits and next use','',
                  'This report evaluates the supplied historical files as preseason snapshots. Their original timing is inherited from source provenance. Future optimized weights must be trained on earlier seasons and validated on a held-out season; this build fits no weights.',
                  '', 'All thresholds are configurable. Source-specific summaries are useful diagnostics; common-player results support fair comparisons. Playing-time and skill are scored separately. Counting-stat errors still combine opportunity and skill, while rates such as HR/PA remove much of the exposure effect.'])
    (destination/'accuracy_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).parent/'config/accuracy_evaluation.json')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--warehouse',type=Path)
    args=parser.parse_args()
    report=evaluate(args.config,args.output,args.warehouse)
    print(json.dumps({k:report[k] for k in ['selected_projection_rows','matched_projection_rows','unmatched_projection_rows','summary_rows','pairwise_comparisons']},indent=2))


if __name__=='__main__':
    main()
