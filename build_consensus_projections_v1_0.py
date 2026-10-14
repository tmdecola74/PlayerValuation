"""Stage 3: auditable per-statistic consensus and component-derived rates."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from evaluate_historical_projection_accuracy_v1_0 import finite, write_csv


def aggregate(values, weights):
    eligible=[(source,value,weights.get(source,1.0)) for source,value in sorted(values.items())
              if finite(value) and weights.get(source,1.0)>0]
    if not eligible:
        return None,dict(sources=[],normalized_weights={},source_values={},source_count=0,
                         minimum=None,maximum=None,range=None,weighted_std=None,cv=None)
    total=math.fsum(w for _,_,w in eligible)
    norm={s:w/total for s,_,w in eligible}
    mean=math.fsum(norm[s]*v for s,v,_ in eligible)
    std=math.sqrt(math.fsum(norm[s]*(v-mean)**2 for s,v,_ in eligible))
    return mean,dict(sources=[s for s,_,_ in eligible],normalized_weights=norm,
        source_values={s:v for s,v,_ in eligible},source_count=len(eligible),
        minimum=min(v for _,v,_ in eligible),maximum=max(v for _,v,_ in eligible),
        range=max(v for _,v,_ in eligible)-min(v for _,v,_ in eligible),weighted_std=std,
        cv=std/abs(mean) if mean!=0 else None)


def linear(terms,values):
    missing=[metric for metric in terms if not finite(values.get(metric))]
    if missing:return None,missing
    return math.fsum(coefficient*values[metric] for metric,coefficient in terms.items()),[]


def derive(formula,values):
    if 'sum' in formula:
        value,missing=linear(formula['sum'],values)
        return value,missing,'missing_components' if missing else 'derived'
    numerator,missing_n=linear(formula['numerator'],values)
    denominator,missing_d=linear(formula['denominator'],values)
    missing=sorted(set(missing_n+missing_d))
    if missing:return None,missing,'missing_components'
    if denominator<=0:return None,[],'nonpositive_denominator'
    return formula.get('scale',1)*numerator/denominator,[],'derived'


def build(config_path,output=None,database=None):
    config_path=Path(config_path).resolve();project=config_path.parent.parent
    cfg=json.loads(config_path.read_text(encoding='utf-8'))
    path=Path(database or project/cfg['warehouse']).resolve();out=Path(output or project/cfg['output']).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    if out.exists() and any(out.iterdir()):raise ValueError('Output must be new or empty')
    if out==path or out in path.parents:raise ValueError('Output must not contain input warehouse')
    if not isinstance(cfg['season'],int):raise ValueError('Season must be an integer')
    for source,weight in cfg['source_weights'].items():
        if not finite(weight) or weight<0:raise ValueError(f'Invalid source weight: {source}')
    for typ,settings in cfg['player_types'].items():
        if set(settings['base_metrics']) & set(settings['derived_metrics']):raise ValueError('Base and derived metrics overlap')
        for metric,weights in settings.get('metric_weight_overrides',{}).items():
            if metric not in settings['base_metrics']:raise ValueError('Derived-rate weights must be configured on their components')
            if any(not finite(w) or w<0 for w in weights.values()):raise ValueError('Metric weights must be finite and nonnegative')
        known=set(settings['base_metrics'])
        for metric,formula in settings['derived_metrics'].items():
            terms=list(formula['sum']) if 'sum' in formula else list(formula['numerator'])+list(formula['denominator'])
            if not set(terms)<=known:raise ValueError(f'Missing or forward-referenced formula components: {metric}')
            known.add(metric)
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest()
    grouped=defaultdict(list);identity=defaultdict(lambda:defaultdict(list));preferred={}
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        names={r['source'] for r in db.execute('SELECT source FROM projection_runs WHERE season=?',(cfg['season'],))}
        unknown=set(cfg['source_weights'])-names
        unknown.update(source for settings in cfg['player_types'].values() for weights in settings.get('metric_weight_overrides',{}).values() for source in weights if source not in names)
        if unknown:raise ValueError(f'Configured sources absent for this season: {sorted(unknown)}')
        for r in db.execute('SELECT player_id,preferred_name FROM players'):preferred[r['player_id']]=r['preferred_name']
        for r in db.execute('SELECT * FROM player_id_crosswalk'):
            identity[r['player_id']][r['namespace']].append(r['external_id'])
        for typ in cfg['player_types']:
            seen=set()
            for entry in db.execute(f'SELECT * FROM analytical_{typ}_projections WHERE season=? ORDER BY player_id,source',(cfg['season'],)):
                r=dict(entry)
                if (r['player_id'],r['source']) in seen:raise ValueError('Duplicate analytical source/player key')
                seen.add((r['player_id'],r['source']))
                grouped[(typ,r['player_id'])].append(dict(source=r['source'],name=r['name'],team=r['team'],record_id=r['record_id'],
                    metrics=json.loads(r['metrics_json']),identity_method=r['identity_method'],match_status=r['match_status']))
    if not grouped:raise ValueError('No analytical projections for requested season')
    players,provenance,missing,coverage,invalid_values=[],[],[],[],[]
    for (typ,pid),records in sorted(grouped.items()):
        settings=cfg['player_types'][typ];values={};metadata={}
        sources=sorted(r['source'] for r in records);teams=sorted({r['team'] for r in records if r['team']})
        name=preferred.get(pid) or records[0]['name']
        ids={ns:sorted(set(items)) for ns,items in identity[pid].items()}
        row=dict(season=cfg['season'],player_type=typ,player_id=pid,name=name,
                 recorded_names=sorted({r['name'] for r in records}),teams=teams,source_count=len(sources),sources=sources,
                 fangraphs_ids=ids.get('fangraphs',[]),mlbam_ids=ids.get('mlbam',[]),rotowire_ids=ids.get('rotowire',[]),
                 source_record_ids={r['source']:r['record_id'] for r in records},
                 name_bridge_sources=[r['source'] for r in records if r['identity_method']=='unique_name_bridge'])
        for metric in settings['base_metrics']:
            usable={}
            for r in records:
                v=r['metrics'].get(metric)
                if finite(v):
                    if metric in settings['nonnegative_metrics'] and v<0:
                        invalid_values.append(dict(player_type=typ,player_id=pid,source=r['source'],record_id=r['record_id'],metric=metric,value=v,reason='negative_nonnegative_metric'))
                    else:usable[r['source']]=v
            weights=dict(cfg['source_weights']);weights.update(settings.get('metric_weight_overrides',{}).get(metric,{}))
            consensus,info=aggregate(usable,weights)
            values[metric]=consensus
            info.update(method='weighted_available_source_mean',formula=None,missing_components=[],component_sources={},component_weights={},status='available' if consensus is not None else 'no_available_values')
            metadata[metric]=info
        for metric,formula in settings['derived_metrics'].items():
            value,missing_components,status=derive(formula,values)
            values[metric]=value
            terms=list(formula['sum']) if 'sum' in formula else list(formula['numerator'])+list(formula['denominator'])
            component_sources={m:metadata[m]['sources'] for m in dict.fromkeys(terms)}
            component_weights={m:metadata[m]['normalized_weights'] for m in dict.fromkeys(terms)}
            contributing=sorted({s for members in component_sources.values() for s in members})
            # Raw source-rate spread is diagnostic. The consensus rate is always
            # derived from the reported consensus components, never substituted.
            weights=cfg['source_weights']
            rate_mean,spread=aggregate({r['source']:r['metrics'][metric] for r in records if finite(r['metrics'].get(metric))},weights)
            metadata[metric]=dict(spread,method='derived_consensus_components',formula=formula,
                sources=contributing,source_count=len(contributing),normalized_weights={},
                component_sources=component_sources,component_weights=component_weights,
                missing_components=missing_components,status=status,
                mixed_component_pools=len({json.dumps([component_sources[m],component_weights[m]],sort_keys=True) for m in component_sources})>1,
                spread_source_count=spread['source_count'],source_rate_mean=rate_mean,
                difference_from_source_rate_mean=value-rate_mean if value is not None and rate_mean is not None else None,
                large_rate_difference=value is not None and rate_mean is not None and metric in cfg.get('rate_difference_thresholds',{}) and abs(value-rate_mean)>=cfg['rate_difference_thresholds'][metric],
                spread_basis='original_source_rates; not the derived consensus value')
        for metric,info in metadata.items():
            if values[metric] is None:
                missing.append(dict(season=cfg['season'],player_type=typ,player_id=pid,name=name,metric=metric,
                                    reason=info['status'],missing_components=info['missing_components']))
            limited=info['source_count']<cfg['minimum_sources_for_agreement']
            high=not limited and info['cv'] is not None and info['cv']>=cfg['high_disagreement_cv']
            provenance.append(dict(season=cfg['season'],player_type=typ,player_id=pid,name=name,metric=metric,
                consensus=values[metric],limited_coverage=limited,high_disagreement=high,**info))
        coverage.append(dict(player_type=typ,player_id=pid,name=name,source_count=len(sources),sources=sources,
            exposure_metric=settings['exposure'],projected_exposure=values.get(settings['exposure']),
            low_projected_exposure=not finite(values.get(settings['exposure'])) or values[settings['exposure']]<settings.get('rate_interpretation_exposure_floor',0),
            unavailable_metrics=[m for m,v in values.items() if v is None],
            nonpositive_exposure=not finite(values.get(settings['exposure'])) or values[settings['exposure']]<=0,
            mixed_rate_pools=[m for m,info in metadata.items() if info.get('mixed_component_pools')],
            matched_source_rows=sum(r['match_status']=='matched' for r in records),
            unmatched_source_rows=sum(r['match_status']!='matched' for r in records)))
        players.append(dict(row,metrics=values))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=fingerprint:raise RuntimeError('Warehouse changed during consensus build')
    out.mkdir(parents=True,exist_ok=True);audit=out/'audit';audit.mkdir()
    for typ in cfg['player_types']:
        subset=[r for r in players if r['player_type']==typ]
        write_csv(out/f'{typ}_consensus.csv',[{**{k:v for k,v in r.items() if k!='metrics'},**r['metrics']} for r in subset])
        (out/f'{typ}_consensus.json').write_text(json.dumps(subset,ensure_ascii=False,indent=2),encoding='utf-8')
    write_csv(out/'metric_provenance.csv',provenance)
    write_csv(audit/'player_coverage.csv',coverage)
    write_csv(audit/'missing_components.csv',missing)
    write_csv(audit/'invalid_source_values.csv',invalid_values)
    write_csv(audit/'high_disagreement.csv',[r for r in provenance if r['high_disagreement']])
    write_csv(audit/'mixed_component_pools.csv',[r for r in provenance if r.get('mixed_component_pools')])
    write_csv(audit/'derived_vs_source_rates.csv',[r for r in provenance if r.get('large_rate_difference')])
    report=dict(version='1.0',built_at_utc=datetime.now(timezone.utc).isoformat(),season=cfg['season'],warehouse=str(path),warehouse_sha256=fingerprint,
        source_projection_rows=sum(len(rows) for rows in grouped.values()),
        matched_source_rows=sum(r['match_status']=='matched' for rows in grouped.values() for r in rows),
        unmatched_source_rows=sum(r['match_status']!='matched' for rows in grouped.values() for r in rows),
        hitter_players=sum(r['player_type']=='hitter' for r in players),pitcher_players=sum(r['player_type']=='pitcher' for r in players),
        player_source_coverage={typ:{str(n):sum(r['player_type']==typ and r['source_count']==n for r in players) for n in sorted({r['source_count'] for r in players if r['player_type']==typ})} for typ in cfg['player_types']},
        missing_metric_values=len(missing),high_disagreement_values=sum(r['high_disagreement'] for r in provenance),
        mixed_component_rate_values=sum(bool(r.get('mixed_component_pools')) for r in provenance),invalid_source_values=len(invalid_values),
        large_derived_rate_differences=sum(bool(r.get('large_rate_difference')) for r in provenance),
        status='review_required' if invalid_values else 'built_with_coverage_audit',config=cfg,
        notes=[f"All {cfg['season']} analytical projections are included, whether matched to actuals or not.",
               'Weights are renormalized independently for each available base statistic. Zero is a valid projection; missing is not zero.',
               'AVG, OBP, SLG, OPS, ERA and WHIP are derived from the exact reported consensus components.',
               'Component pools may differ when fields are missing; these differences are explicitly audited rather than imputed.',
               'Source disagreement is descriptive dispersion, not calibrated forecast uncertainty.',
               f"This is a retrospective {cfg['season']} preseason consensus, not a live-season update or fantasy valuation."])
    (audit/'consensus_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (out/'effective_config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    render_report(audit,report)
    return report


def render_report(audit,r):
    lines=[f"# Stage 3 — {r['season']} consensus projections",'',
        f"**{r['hitter_players']:,} hitters** and **{r['pitcher_players']:,} pitchers** from {r['source_projection_rows']:,} selected source rows.",
        '',f"Unmatched source projections included: {r['unmatched_source_rows']:,}. No actual results enter the consensus calculations.",
        '', 'Equal source weights are the default. Available source values are averaged independently for each base statistic. Custom source and per-statistic weights can be configured; only contributors with positive weights participate.',
        '', '## Coherent counts and rates','',
        '* AVG = H / AB.',
        '* OBP = (H + BB + HBP) / (AB + BB + HBP + SF).',
        '* SLG = (1B + 2×2B + 3×3B + 4×HR) / AB; OPS = OBP + SLG.',
        '* ERA = 9 × ER / IP; WHIP = (H allowed + BB) / IP.',
        '* Saves plus holds = SV + HLD; QS is included as a counting statistic.',
        '', 'Every rate uses the exact displayed consensus components. Missing components or nonpositive denominators produce unavailable values, never fabricated zeros. Because available sources can differ by component, source-pool differences are audited.',
        '', 'The earlier blend backtest averaged source rates directly. These component-consistent rates are a different aggregation and have not yet had a separate held-out performance test. Formula correctness is verified; improved forecast accuracy is not claimed.',
        '', '## Player source coverage','', '|Type|Sources per player|Players|','|---|---:|---:|']
    for typ,counts in r['player_source_coverage'].items():
        for count,n in counts.items():lines.append(f'|{typ}|{count}|{n:,}|')
    lines.extend(['',f"Unavailable metric values: {r['missing_metric_values']:,}. High-disagreement flags: {r['high_disagreement_values']:,}. Mixed component-pool flags: {r['mixed_component_rate_values']:,}.",
        '', '## Files to review','',
        '* `hitter_consensus.csv` and `pitcher_consensus.csv`: one row per canonical player, IDs, source records, names/teams and consensus statistics.',
        '* `metric_provenance.csv`: each metric\'s contributors, normalized weights, source values, formula, component weights and disagreement statistics.',
        '* `audit/player_coverage.csv`: limited player coverage, missing metrics, nonpositive playing time and underlying matched/unmatched counts.',
        '* `audit/missing_components.csv`: missing-statistic and denominator reasons.',
        '* `audit/high_disagreement.csv`: source dispersion flags; these are not probability or reliability estimates.',
        '* `audit/mixed_component_pools.csv`: derived metrics whose components use different source sets or weights.',
        '* `audit/derived_vs_source_rates.csv`: component-derived rates that differ materially from the available-source mean rate. Rounded low-playing-time counts and mixed source pools can cause these differences.',
        '', 'Zero projected stats participate in averaging. A single source can produce a consensus, but its lack of independent agreement is flagged. No player is removed for having little playing time, no matched actual is required, and identities are inherited from the reviewed warehouse.',
        '', f"All original sources and the warehouse remain unchanged. This build uses {r['season']} preseason data and does not incorporate {r['season']} outcomes into forecast values. The next valuation stage will select the fantasy player pool and convert these projections into format-specific values."])
    (audit/'consensus_report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).parent/'config/consensus_projections.json')
    parser.add_argument('--output',type=Path);parser.add_argument('--warehouse',type=Path)
    args=parser.parse_args();r=build(args.config,args.output,args.warehouse)
    print(json.dumps({k:r[k] for k in ['hitter_players','pitcher_players','source_projection_rows','missing_metric_values','status']},indent=2))
    return 2 if r['status']=='review_required' else 0


if __name__=='__main__':raise SystemExit(main())
