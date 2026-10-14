"""Retrospective validation of the exact Stage 3 calculation; no weights are fitted."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from warehouse_readonly_v1_0 import open_warehouse
from collections import defaultdict
from contextlib import closing
from pathlib import Path

from build_consensus_projections_duckdb_v1_0 import aggregate, build, derive
from evaluate_historical_projection_accuracy_duckdb_v1_0 import finite, score, write_csv


def leaves(metric, settings):
    formula = settings['derived_metrics'].get(metric)
    if formula is None:
        return {metric}
    terms = formula.get('sum', {}) or {**formula['numerator'], **formula['denominator']}
    return set().union(*(leaves(m, settings) for m in terms))


def value_from_components(metric, values, settings):
    """Recursively derive using components, with no substitution of source rates."""
    if metric not in settings['derived_metrics']:
        return values.get(metric)
    formula = settings['derived_metrics'][metric]
    terms = formula.get('sum', {}) or {**formula['numerator'], **formula['denominator']}
    components = {m: value_from_components(m, values, settings) for m in terms}
    return derive(formula, components)[0]


def source_value(metric, values, settings):
    if finite(values.get(metric)):
        return values[metric]
    # Match prior Stage 2 OPS fallback and the warehouse's additive/rate metrics.
    if metric == 'OPS' and all(finite(values.get(m)) for m in ('OBP', 'SLG')):
        return values['OBP'] + values['SLG']
    return value_from_components(metric, values, settings)


def alternatives(metric, records, settings, weights):
    direct, spread = aggregate({r['source']: source_value(metric, r['metrics'], settings)
                               for r in records}, weights)
    required = leaves(metric, settings)
    eligible = [r for r in records if weights.get(r['source'], 1) > 0 and
                all(finite(r['metrics'].get(m)) and
                    (m not in settings['nonnegative_metrics'] or r['metrics'][m] >= 0)
                    for m in required)]
    components = {}
    for m in required:
        w = dict(weights); w.update(settings.get('metric_weight_overrides', {}).get(m, {}))
        components[m] = aggregate({r['source']: r['metrics'][m] for r in eligible}, w)[0]
    common = value_from_components(metric, components, settings)
    return direct, common, spread, sorted(r['source'] for r in eligible)


def actual_value(metric, values, settings):
    # Published actual rates remain authoritative; OPS is absent in some exports.
    return source_value(metric, values, settings)


def qualifies(actual, projected, records, cohort, exposure):
    a = actual.get(exposure); p = projected.get(exposure)
    if not finite(a) or a <= 0 or a < cohort['minimum_actual']:
        return False
    if cohort.get('minimum_projected', 0) > 0 and (not finite(p) or p < cohort['minimum_projected']):
        return False
    return not cohort.get('projected_any_sv_minimum') or any(
        finite(r['metrics'].get('SV')) and r['metrics']['SV'] >= cohort['projected_any_sv_minimum'] for r in records)


def run(config_path, output=None, database=None):
    config_path = Path(config_path).resolve(); project = config_path.parent.parent
    cfg = json.loads(config_path.read_text(encoding='utf-8'))
    stage = json.loads((project/cfg['consensus_config']).read_text(encoding='utf-8'))
    warehouse = Path(database or project/cfg['warehouse']).resolve()
    out = Path(output or project/cfg['output']).resolve()
    if out.exists() and any(out.iterdir()): raise ValueError('Output must be new or empty')
    if out == warehouse or out in warehouse.parents: raise ValueError('Output cannot contain warehouse')
    if len(set(cfg['seasons'])) != len(cfg['seasons']): raise ValueError('Duplicate seasons')
    fingerprint = hashlib.sha256(warehouse.read_bytes()).hexdigest()
    out.mkdir(parents=True, exist_ok=True)
    generated = out/'season_configs'; generated.mkdir()
    groups = defaultdict(list); actuals = {}; season_sources = defaultdict(set)
    with closing(open_warehouse(warehouse)) as db:
        for r in db.execute('SELECT season,source FROM projection_runs'):
            season_sources[r['season']].add(r['source'])
        for typ in cfg['player_types']:
            for r in db.execute(f'SELECT * FROM analytical_{typ}_projections'):
                if r['season'] not in cfg['seasons']: continue
                groups[(typ,r['season'],r['player_id'])].append(dict(r, metrics=json.loads(r['metrics_json'])))
            for r in db.execute(f'SELECT * FROM {typ}_actuals'):
                if r['season'] not in cfg['seasons']: continue
                key = (typ,r['season'],r['player_id'])
                if key in actuals: raise ValueError('Duplicate actual key')
                actuals[key] = dict(r, metrics=json.loads(r['metrics_json']))
    consensus = {}; coverage = []; build_reports = []
    for season in cfg['seasons']:
        seasonal = json.loads(json.dumps(stage)); seasonal['season'] = season
        seasonal['source_weights'] = {s:w for s,w in stage['source_weights'].items() if s in season_sources[season]}
        for settings in seasonal['player_types'].values():
            settings['metric_weight_overrides'] = {m:{s:w for s,w in ws.items() if s in season_sources[season]}
                                                 for m,ws in settings.get('metric_weight_overrides',{}).items()}
        path = generated/f'consensus_{season}.json'; path.write_text(json.dumps(seasonal,indent=2),encoding='utf-8')
        result = out/f'consensus_{season}'
        build_reports.append(build(path, result, warehouse))
        for typ in cfg['player_types']:
            for row in json.loads((result/f'{typ}_consensus.json').read_text(encoding='utf-8')):
                consensus[(typ,season,row['player_id'])] = row
    predictions = []; exclusions = []; validation = []
    for key, row in sorted(consensus.items()):
        typ, season, pid = key; settings = stage['player_types'][typ]
        records = groups[key]; actual = actuals.get(key)
        # Use the reviewed links only, never independently rematch or zero-fill.
        linked = {r['actual_record_id'] for r in records if r['match_status']=='matched'}
        if linked and (actual is None or linked != {actual['record_id']} or actual['identity_conflict']):
            raise ValueError(f'Invalid reviewed match: {key}')
        matched = bool(linked)
        coverage.append(dict(player_type=typ,season=season,player_id=pid,source_count=row['source_count'],
                             matched=matched,source_records=row['source_record_ids']))
        if not matched:
            exclusions.append(dict(player_type=typ,season=season,player_id=pid,reason='no_reviewed_actual_match'))
            continue
        weights = stage['source_weights']
        for metric in cfg['player_types'][typ]['metrics']:
            observed = actual_value(metric, actual['metrics'], settings)
            exact = row['metrics'].get(metric)
            direct, common, spread, common_sources = alternatives(metric, records, settings, weights)
            # Disagreement must use the same supplied-rate spread as Stage 3,
            # independently of the comparison baseline's missing-rate fallback.
            agreement_weights = dict(weights)
            if metric in settings['base_metrics']:
                agreement_weights.update(settings.get('metric_weight_overrides',{}).get(metric,{}))
            _, spread = aggregate({r['source']:r['metrics'].get(metric) for r in records}, agreement_weights)
            if metric in settings['base_metrics']:
                w = dict(weights);w.update(settings.get('metric_weight_overrides',{}).get(metric,{}))
                check = aggregate({r['source']:r['metrics'].get(metric) for r in records
                                   if not finite(r['metrics'].get(metric)) or r['metrics'][metric]>=0}, w)[0]
                passed = exact == check
                validation.append(dict(player_type=typ,season=season,player_id=pid,metric=metric,
                                       check='base_metric_reproduces_available_source_mean',passed=passed))
                if not passed: raise AssertionError('Counting/opportunity baseline mismatch')
            if not finite(observed) or not finite(exact):
                exclusions.append(dict(player_type=typ,season=season,player_id=pid,metric=metric,
                                       reason='missing_actual_metric' if not finite(observed) else 'missing_consensus_metric'))
                continue
            exposure = row['metrics'].get(cfg['player_types'][typ]['exposure'])
            high = spread['source_count'] >= stage['minimum_sources_for_agreement'] and spread['cv'] is not None and spread['cv'] >= stage['high_disagreement_cv']
            component_sets = []
            for m in leaves(metric,settings):
                w = dict(weights);w.update(settings.get('metric_weight_overrides',{}).get(m,{}))
                component_sets.append(tuple(sorted(aggregate({r['source']:r['metrics'].get(m) for r in records},w)[1]['normalized_weights'].items())))
            prediction = dict(player_type=typ,season=season,player_id=pid,name=row['name'],metric=metric,
                actual_record_id=actual['record_id'],actual=observed,stage3=exact,direct_source_mean=direct,
                common_component_pool=common,common_component_sources=common_sources,
                source_records=row['source_record_ids'],player_source_count=row['source_count'],
                metric_source_count=spread['source_count'],high_disagreement=high,source_cv=spread['cv'],
                mixed_component_pools=len(set(component_sets))>1,projected_exposure=exposure,
                low_projected_exposure=not finite(exposure) or exposure<cfg['player_types'][typ]['projected_exposure_floor'],
                error=exact-observed,absolute_error=abs(exact-observed),
                large_rate_difference=metric in stage['rate_difference_thresholds'] and finite(direct) and abs(exact-direct)>=stage['rate_difference_thresholds'][metric])
            prediction['cohorts'] = [c['name'] for c in cfg['player_types'][typ]['cohorts'] if
                                    (not c.get('metrics') or metric in c['metrics']) and
                                    qualifies(actual['metrics'],row['metrics'],records,c,cfg['player_types'][typ]['exposure'])]
            predictions.append(prediction)
    summary = []; comparisons = []; diagnostics = []; membership = []
    buckets = defaultdict(list)
    for p in predictions:
        for cohort in p['cohorts']: buckets[(p['player_type'],p['season'],p['metric'],cohort)].append(p)
    for (typ,season,metric,cohort), rows in sorted(buckets.items()):
        identity = dict(player_type=typ,season=season,metric=metric,cohort=cohort)
        summary.append(dict(identity,method='stage3',sample='all_available',**score([(r['stage3'],r['actual']) for r in rows],cfg['correlation_min_n'])))
        for method in ('direct_source_mean','common_component_pool'):
            paired = [r for r in rows if finite(r[method])]
            payload = dict(identity,comparator=method,player_ids=sorted(r['player_id'] for r in paired))
            sample_id = hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest()[:24]
            membership.append(dict(sample_id=sample_id,**payload))
            a = score([(r['stage3'],r['actual']) for r in paired],cfg['correlation_min_n'])
            b = score([(r[method],r['actual']) for r in paired],cfg['correlation_min_n'])
            comparisons.append(dict(identity,sample_id=sample_id,comparator=method,n=a['n'],
                stage3_mae=a['mae'],comparator_mae=b['mae'],stage3_rmse=a['rmse'],comparator_rmse=b['rmse'],
                stage3_bias=a['bias'],comparator_bias=b['bias'],
                stage3_mae_gain_pct=100*(b['mae']-a['mae'])/b['mae'] if b['mae'] else None,
                stage3_rmse_gain_pct=100*(b['rmse']-a['rmse'])/b['rmse'] if b['rmse'] else None,
                max_prediction_difference=max((abs(r['stage3']-r[method]) for r in paired),default=None)))
            for name, stats in [('stage3',a),(method,b)]:
                summary.append(dict(identity,method=name,sample=sample_id,**stats))
        strata = [('coverage','one_source',lambda r:r['player_source_count']==1),
                  ('coverage','two_sources',lambda r:r['player_source_count']==2),
                  ('coverage','three_plus_sources',lambda r:r['player_source_count']>=3),
                  ('disagreement','high',lambda r:r['metric_source_count']>=2 and r['high_disagreement']),
                  ('disagreement','not_high',lambda r:r['metric_source_count']>=2 and not r['high_disagreement']),
                  ('projected_exposure','low',lambda r:r['low_projected_exposure']),
                  ('projected_exposure','adequate',lambda r:not r['low_projected_exposure']),
                  ('component_pool','mixed',lambda r:r['mixed_component_pools']),
                  ('component_pool','same',lambda r:not r['mixed_component_pools']),
                  ('rate_difference','large',lambda r:r['large_rate_difference']),
                  ('rate_difference','not_large',lambda r:not r['large_rate_difference'])]
        for dimension,label,predicate in strata:
            selected = [r for r in rows if predicate(r)]
            diagnostics.append(dict(identity,dimension=dimension,stratum=label,
                                    **score([(r['stage3'],r['actual']) for r in selected],cfg['correlation_min_n'])))
    if hashlib.sha256(warehouse.read_bytes()).hexdigest()!=fingerprint: raise RuntimeError('Warehouse changed')
    for name, rows in [('predictions',predictions),('accuracy_summary',summary),('paired_comparisons',comparisons),
                       ('diagnostic_strata',diagnostics),('sample_membership',membership),('coverage',coverage),
                       ('excluded_from_accuracy',exclusions),('baseline_validation',validation)]:
        write_csv(out/f'{name}.csv',rows)
    report = dict(warehouse_sha256=fingerprint,config=cfg,stage3_config_sha256=hashlib.sha256((project/cfg['consensus_config']).read_bytes()).hexdigest(),
                  builds=build_reports,consensus_players=len(consensus),matched_players=sum(r['matched'] for r in coverage),
                  unmatched_players=sum(not r['matched'] for r in coverage),evaluated_player_metrics=len(predictions),
                  base_metric_checks=len(validation),failed_base_metric_checks=sum(not r['passed'] for r in validation))
    (out/'backtest_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    render_report(out, report, comparisons, diagnostics, predictions)
    return report


def render_report(out, report, comparisons, diagnostics, predictions):
    cfg = report['config']
    review = [r for r in predictions if r['metric'] in ('AVG','OPS','ERA','WHIP') and
              r['large_rate_difference'] and cfg['player_types'][r['player_type']]['headline_cohort'] in r['cohorts']]
    write_csv(out/'rate_cases_for_review.csv',review)
    roster_comparisons = [r for r in comparisons if r['cohort']=='projected_roster_pool' and
                          r['comparator']=='direct_source_mean' and r['metric'] in ('AVG','OPS') and r['n']]
    pool_comparisons = [r for r in comparisons if r['cohort']==cfg['player_types'][r['player_type']]['headline_cohort'] and
                        r['comparator']=='common_component_pool' and r['metric'] in ('AVG','OPS','ERA','WHIP') and r['n']]
    lines = ['# Stage 3 historical consensus backtest','',
        '## Findings and next decision','',
        f"All {report['base_metric_checks']:,} counting/opportunity checks reproduce the configured available-source baseline exactly.",
        (f"For hitters projected for at least 300 PA, component-derived AVG/OPS MAE gains versus averaged source rates range from {min(r['stage3_mae_gain_pct'] for r in roster_comparisons):+.2f}% to {max(r['stage3_mae_gain_pct'] for r in roster_comparisons):+.2f}% across the supplied years: essentially unchanged under this roster-relevance proxy." if roster_comparisons else 'No paired hitter roster-cohort rate samples are available.'),
        ('The common-component-pool alternative has identical AVG/OPS/ERA/WHIP forecasts on all headline samples; mixed pools are not the cause of the headline rate differences.' if pool_comparisons and all(r['max_prediction_difference']==0 for r in pool_comparisons) else 'Consult the common-component-pool table and sample sizes before selecting a policy.'),
        f"There are {len(review):,} headline-cohort player/metric cases with large differences from supplied source rates. See rate_cases_for_review.csv for the names, exposures and exact source records. These flag rounded-count or other component/source inconsistencies; they do not identify the sole cause.",
        'Keep equal weights and coherent component rates for now. Before prospect or low-playing-time valuation, explicitly decide how to handle unreliable low-exposure rates; their existing flags should prevent treating them as dependable skill estimates. This test does not change the production consensus or silently suppress records.',
        '', '## Test design','',
        'The unchanged Stage 3 builder generates each season before actual results are scored. No source weights or thresholds are fitted to outcomes. Coverage expands naturally by year.',
        '',f"Generated {report['consensus_players']:,} player/type/seasons; {report['matched_players']:,} have reviewed actual links and {report['unmatched_players']:,} are excluded from accuracy, never treated as zero.",
        f"All {report['base_metric_checks']:,} counting/opportunity baseline checks passed.",
        '', '## Component-derived rates versus source-rate means','',
        'Positive gain means Stage 3 has lower error. Both methods are scored on exactly the same players per row. Each row uses the actual-playing-time headline cohort; the projected roster cohort is also exported. Source means use supplied rates, with OPS = OBP + SLG when missing and component fallback for missing derived skill/additive statistics.',
        '', '|Type|Year|Metric|Players|Stage 3 MAE|Source-mean MAE|MAE gain|RMSE gain|',
        '|---|---:|---|---:|---:|---:|---:|---:|']
    for r in comparisons:
        if r['cohort']!=cfg['player_types'][r['player_type']]['headline_cohort'] or r['comparator']!='direct_source_mean' or r['metric'] not in ('AVG','OPS','ERA','WHIP','K/9','BB/9'):continue
        fmt=lambda v: f'{v:.4f}' if v is not None else '—'
        pct=lambda v: f'{v:+.2f}%' if v is not None else '—'
        lines.append(f"|{r['player_type']}|{r['season']}|{r['metric']}|{r['n']}|{fmt(r['stage3_mae'])}|{fmt(r['comparator_mae'])}|{pct(r['stage3_mae_gain_pct'])}|{pct(r['stage3_rmse_gain_pct'])}|")
    lines.extend(['','## Common component source pools','',
        'The diagnostic alternative restricts every primitive component of a metric to sources supplying all required components, then derives the rate from their averaged counts. OPS recursively requires both its OBP and SLG components. Missing components or nonpositive denominators remain unavailable.',
        '', '|Type|Year|Metric|Players|Stage 3 MAE|Common-pool MAE|Stage 3 MAE gain|',
        '|---|---:|---|---:|---:|---:|---:|'])
    for r in comparisons:
        if r['cohort']!=cfg['player_types'][r['player_type']]['headline_cohort'] or r['comparator']!='common_component_pool' or r['metric'] not in ('AVG','OPS','ERA','WHIP') or not r['n']:continue
        lines.append(f"|{r['player_type']}|{r['season']}|{r['metric']}|{r['n']}|{r['stage3_mae']:.4f}|{r['comparator_mae']:.4f}|{r['stage3_mae_gain_pct']:+.2f}%|")
    lines.extend(['','## Coverage, disagreement and rounded-count diagnostics','',
        'All metrics have source-count, disagreement, projected-exposure, mixed-component-pool and large-rate-difference strata in diagnostic_strata.csv. High/not-high comparisons require at least two rate contributors; they are descriptive associations, not calibrated uncertainty or causal effects. Projected PA/IP floors use preseason consensus only. Actual-playing-time cohorts are retrospective selection, not a draft-time eligibility rule.',
        '', '|Type|Year|Metric|Cohort|Dimension|Stratum|Players|MAE|RMSE|',
        '|---|---:|---|---|---|---|---:|---:|---:|'])
    for r in diagnostics:
        if r['cohort']!='projected_roster_pool' or r['metric'] not in ('AVG','OPS','ERA','WHIP') or r['dimension'] not in ('component_pool','disagreement','rate_difference'):continue
        if r['n']:lines.append(f"|{r['player_type']}|{r['season']}|{r['metric']}|{r['cohort']}|{r['dimension']}|{r['stratum']}|{r['n']}|{r['mae']:.4f}|{r['rmse']:.4f}|")
    lines.extend(['','## Interpretation limits and reproducibility','',
        'This validates the fixed equal-weight consensus retrospectively. 2024 is development-era evidence; 2025/2026 are later-season checks, but the equal-weight choice was already informed by their earlier blend backtests. These are not fresh independent holdouts. No significance or production improvement guarantee is claimed.',
        'Missing and unmatched records are explicitly exported. The same reviewed analytical views retain duplicate decisions and Greg Jones metric exclusions. All original source files and the warehouse remain unchanged.',
        'This comparison uses Stage 3 available-player/statistic pools. It does not claim to reproduce the prior Stage 2B complete-source-pool samples; counting baselines are independently recomputed on the exact current pool.',
        'Forecasts, exact sample membership, component-pool contributors, exclusions, per-season build audits, configuration and input hashes are delivered alongside the scores. Rounded-count impact is proxied by large differences from supplied source rates; the diagnostic does not prove rounding is the sole cause.',
        '', 'Run: python backtest_consensus_projections_v1_0.py. Existing nonempty results are protected; use --output with a new directory for a rerun.'])
    (out/'backtest_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).parent/'config/consensus_backtesting_duckdb.json')
    parser.add_argument('--output',type=Path);parser.add_argument('--warehouse',type=Path)
    args=parser.parse_args();report=run(args.config,args.output,args.warehouse)
    print(json.dumps({k:report[k] for k in ('consensus_players','matched_players','unmatched_players','evaluated_player_metrics','base_metric_checks','failed_base_metric_checks')},indent=2))
