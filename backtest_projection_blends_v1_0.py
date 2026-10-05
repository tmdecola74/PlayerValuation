"""Chronological, leakage-checked comparison of equal and weighted consensus."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from contextlib import closing

from evaluate_historical_projection_accuracy_v1_0 import finite, score, write_csv


def fit_weights(x, y, observation_weights=None, ridge_strength=.1, max_iterations=10000, tolerance=1e-10):
    """Convex simplex-constrained ridge MSE via exact feasible pair transfers.

    Centers each row on its equal blend to improve numerical stability. Ridge
    scale is the training equal-blend MSE; no held-out values enter fitting.
    """
    if not x or len(x)!=len(y) or not x[0]:
        raise ValueError('Nonempty, aligned training observations required')
    k=len(x[0])
    if any(len(row)!=k or any(not finite(v) for v in row) for row in x) or any(not finite(v) for v in y):
        raise ValueError('Training matrix must be finite and rectangular')
    if ridge_strength<0:
        raise ValueError('Ridge strength must be nonnegative')
    q=observation_weights or [1/len(x)]*len(x)
    if len(q)!=len(y) or any(not finite(v) or v<0 for v in q) or sum(q)<=0:
        raise ValueError('Invalid observation weights')
    q=[v/sum(q) for v in q]
    z,targets=[],[]
    for row,target in zip(x,y):
        base=math.fsum(row)/k
        z.append([v-base for v in row]);targets.append(target-base)
    scale=math.fsum(v*t*t for v,t in zip(q,targets))
    lam=ridge_strength*max(scale,1e-12)
    a=[[math.fsum(v*row[i]*row[j] for v,row in zip(q,z))+(lam if i==j else 0) for j in range(k)] for i in range(k)]
    b=[math.fsum(v*row[i]*target for v,row,target in zip(q,z,targets))+lam/k for i in range(k)]
    weights=[1/k]*k
    converged=False
    for iteration in range(max_iterations):
        gradient=[math.fsum(a[i][j]*weights[j] for j in range(k))-b[i] for i in range(k)]
        best=None
        for i in range(k):
            for j in range(i+1,k):
                curvature=a[i][i]+a[j][j]-2*a[i][j]
                if curvature<=0:
                    continue
                delta=max(-weights[i],min(weights[j],-(gradient[i]-gradient[j])/curvature))
                gain=-(2*delta*(gradient[i]-gradient[j])+delta*delta*curvature)
                if best is None or gain>best[0]:best=(gain,i,j,delta)
        if best is None or best[0]<=tolerance*max(scale,1e-12):
            converged=True;break
        _,i,j,delta=best
        weights[i]+=delta;weights[j]-=delta
    if not converged:
        raise ValueError('Weight optimizer did not converge; no unverified weights emitted')
    weights=[max(0,v) for v in weights]
    weights=[v/sum(weights) for v in weights]
    return weights,dict(converged=converged,iterations=iteration+1,training_equal_mse=scale,ridge_lambda=lam)


def inverse_mae_weights(x,y,q,shrinkage):
    if not 0<=shrinkage<=1:
        raise ValueError('Inverse-MAE shrinkage must be between zero and one')
    k=len(x[0]);q=[v/sum(q) for v in q]
    errors=[math.fsum(v*abs(row[j]-actual) for v,row,actual in zip(q,x,y)) for j in range(k)]
    perfect=[j for j,e in enumerate(errors) if e==0]
    if perfect:
        raw=[1/len(perfect) if j in perfect else 0 for j in range(k)]
    else:
        raw=[1/e for e in errors];raw=[v/sum(raw) for v in raw]
    return [(1-shrinkage)*v+shrinkage/k for v in raw],errors


def expand_weights(known_weights,participants):
    """Assign neutral 1/M to each new source; preserve known relative weights."""
    new=[s for s in participants if s not in known_weights]
    remaining=1-len(new)/len(participants)
    return {s:1/len(participants) if s in new else remaining*known_weights[s] for s in participants}


def load_warehouse(path):
    rows=[]
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro',uri=True)) as db:
        db.row_factory=sqlite3.Row
        for typ in ('hitter','pitcher'):
            seen=set()
            query=f'''SELECT p.*,a.player_id AS actual_player_id,a.season AS actual_season,
                a.identity_conflict AS actual_conflict,a.metrics_json AS actual_metrics_json
                FROM analytical_{typ}_projections p LEFT JOIN {typ}_actuals a
                ON p.actual_record_id=a.record_id'''
            for entry in db.execute(query):
                r=dict(entry);key=(r['season'],r['source'],r['player_id'])
                if key in seen:raise ValueError('Duplicate analytical key')
                seen.add(key)
                if r['match_status']=='matched' and (r['player_id']!=r['actual_player_id'] or r['season']!=r['actual_season'] or r['actual_conflict']):
                    raise ValueError('Invalid analytical actual link')
                rows.append(dict(player_type=typ,season=r['season'],source=r['source'],player_id=r['player_id'],
                    record_id=r['record_id'],actual_record_id=r['actual_record_id'],name=r['name'],
                    projected=json.loads(r['metrics_json']),actual=json.loads(r['actual_metrics_json']) if r['actual_metrics_json'] else {},
                    matched=r['match_status']=='matched'))
    return rows


def eligible_players(index,typ,season,sources,metric,cohort,exposure):
    common=set.intersection(*(set(index.get((typ,season,s),{})) for s in sources)) if sources else set()
    result=[]
    # Closer candidates use preseason predictions only, from the current sample
    # source pool. Actual saves never determine closer eligibility.
    for pid in sorted(common):
        rows=[index[(typ,season,s)][pid] for s in sources]
        if not all(r['matched'] and finite(r['projected'].get(metric)) and finite(r['actual'].get(metric)) for r in rows):continue
        actual=rows[0]['actual'].get(exposure)
        if not finite(actual) or actual<=0 or actual<cohort['minimum_actual']:continue
        if not all(cohort.get('minimum_projected',0)<=0 or finite(r['projected'].get(exposure)) and r['projected'][exposure]>=cohort['minimum_projected'] for r in rows):continue
        if cohort.get('projected_any_sv_minimum') is not None and not any(finite(r['projected'].get('SV')) and r['projected']['SV']>=cohort['projected_any_sv_minimum'] for r in rows):continue
        if len({r['actual_record_id'] for r in rows})!=1:raise ValueError('Sources link to different actual records for common player')
        result.append(dict(season=season,player_id=pid,name=rows[0]['name'],actual=rows[0]['actual'][metric],
                           predictions=[r['projected'][metric] for r in rows],record_ids=[r['record_id'] for r in rows]))
    return result


def backtest(config_path,output=None,database=None):
    config_path=Path(config_path).resolve();project=config_path.parent.parent
    cfg=json.loads(config_path.read_text(encoding='utf-8'))
    path=Path(database or project/cfg['warehouse']).resolve();out=Path(output or project/cfg['output']).resolve()
    if not path.is_file():raise FileNotFoundError(path)
    if out.exists() and any(out.iterdir()):raise ValueError('Output must be new or empty')
    if out in path.parents or out==path:raise ValueError('Output must not contain input warehouse')
    if len({f['name'] for f in cfg['folds']})!=len(cfg['folds']):raise ValueError('Fold names must be unique')
    for fold in cfg['folds']:
        if not fold['train_seasons'] or len(set(fold['train_seasons']))!=len(fold['train_seasons']) or max(fold['train_seasons'])>=fold['test_season']:
            raise ValueError('Every training season must strictly precede test season')
    if len({f['test_season'] for f in cfg['folds'] if f['primary']})!=sum(f['primary'] for f in cfg['folds']):
        raise ValueError('Primary folds must have distinct held-out seasons')
    if cfg['minimum_training_pairs']<2 or cfg['minimum_test_pairs']<2:raise ValueError('Minimum samples must be at least two')
    fingerprint=hashlib.sha256(path.read_bytes()).hexdigest();rows=load_warehouse(path)
    index=defaultdict(dict)
    for row in rows:index[(row['player_type'],row['season'],row['source'])][row['player_id']]=row
    results,weights_audit,predictions,samples,skips=[],[],[],[],[]
    for typ,settings in cfg['player_types'].items():
        for metric in settings['metrics']:
            for cohort in settings['cohorts']:
                if cohort.get('metrics') and metric not in cohort['metrics']:continue
                for fold in cfg['folds']:
                    test=fold['test_season'];years=fold['train_seasons']
                    current=sorted(s for t,y,s in index if t==typ and y==test and any(finite(r['projected'].get(metric)) for r in index[(t,y,s)].values()))
                    known=[s for s in current if all(any(finite(r['projected'].get(metric)) for r in index.get((typ,y,s),{}).values()) for y in years)]
                    if len(known)<2:
                        skips.append(dict(player_type=typ,metric=metric,cohort=cohort['name'],fold=fold['name'],reason='fewer_than_two_complete_history_sources'));continue
                    training={year:eligible_players(index,typ,year,known,metric,cohort,settings['exposure']) for year in years}
                    training_rows=[r for year in years for r in training[year]]
                    trained=len(training_rows)>=cfg['minimum_training_pairs'] and all(len(training[y])>=cfg['minimum_training_pairs_per_season'] for y in years)
                    x=[r['predictions'] for r in training_rows];y=[r['actual'] for r in training_rows]
                    # Every training season has equal total influence regardless
                    # of its player count. All methods share these training rows.
                    q=[1/(len(years)*len(training[year])) for year in years for _ in training[year]]
                    equal=[1/len(known)]*len(known)
                    methods={'equal':equal}
                    optimizer={};individual_errors=[]
                    if trained:
                        inverse,individual_errors=inverse_mae_weights(x,y,q,cfg['inverse_mae_shrinkage'])
                        fitted,optimizer=fit_weights(x,y,q,cfg['ridge_strength'])
                        methods.update(inverse_mae_shrunk=inverse,fitted_rmse_ridge=fitted)
                    else:
                        skips.append(dict(player_type=typ,metric=metric,cohort=cohort['name'],fold=fold['name'],reason='insufficient_training_pairs',training_counts={yr:len(training[yr]) for yr in years}))
                    for pool in ('shared_history','expanding_pool'):
                        participants=known if pool=='shared_history' else current
                        heldout=eligible_players(index,typ,test,participants,metric,cohort,settings['exposure'])
                        sample_data=dict(player_type=typ,metric=metric,cohort=cohort['name'],fold=fold['name'],pool=pool,
                            test_season=test,sources=participants,training_sources=known,train_seasons=years,
                            test_player_ids=[r['player_id'] for r in heldout],
                            training_player_seasons=[{'season':r['season'],'player_id':r['player_id']} for r in training_rows])
                        sample_id=hashlib.sha256(json.dumps(sample_data,sort_keys=True).encode()).hexdigest()[:24]
                        samples.append(dict(sample_id=sample_id,**sample_data))
                        equal_pairs=[(math.fsum(r['predictions'])/len(participants),r['actual']) for r in heldout]
                        baseline=score(equal_pairs,cfg['correlation_min_n'])
                        for method,core_weights in methods.items():
                            source_weights={s:w for s,w in zip(known,core_weights)}
                            full={s:1/len(participants) for s in participants} if method=='equal' else expand_weights(source_weights,participants)
                            pairs=[]
                            for r in heldout:
                                forecast=math.fsum(full[s]*v for s,v in zip(participants,r['predictions']))
                                pairs.append((forecast,r['actual']))
                                predictions.append(dict(sample_id=sample_id,player_type=typ,metric=metric,cohort=cohort['name'],
                                    fold=fold['name'],primary_fold=fold['primary'],pool=pool,test_season=test,method=method,
                                    player_id=r['player_id'],name=r['name'],actual=r['actual'],predicted=forecast,
                                    error=forecast-r['actual'],source_predictions=dict(zip(participants,r['predictions'])),record_ids=r['record_ids']))
                            stats=score(pairs,cfg['correlation_min_n'])
                            pct=lambda current,base:100*(base-current)/base if base is not None and base>0 else None
                            results.append(dict(sample_id=sample_id,player_type=typ,metric=metric,cohort=cohort['name'],pool=pool,
                                fold=fold['name'],primary_fold=fold['primary'],test_season=test,train_seasons=years,method=method,
                                training_n=len(training_rows),test_sources=participants,training_sources=known,
                                new_sources=[s for s in participants if s not in known],
                                mae_improvement_pct=pct(stats['mae'],baseline['mae']),rmse_improvement_pct=pct(stats['rmse'],baseline['rmse']),
                                assessment_eligible=trained and stats['n']>=cfg['minimum_test_pairs'],**stats))
                            for source in participants:
                                weights_audit.append(dict(sample_id=sample_id,player_type=typ,metric=metric,cohort=cohort['name'],pool=pool,
                                    fold=fold['name'],method=method,source=source,weight=full[source],weight_percent=100*full[source],
                                    provenance='equal_baseline' if method=='equal' else 'neutral_share_incomplete_history' if source not in known else 'earlier_seasons_only',
                                    training_counts={yr:len(training[yr]) for yr in years},optimizer=optimizer if method=='fitted_rmse_ridge' else None))
    if hashlib.sha256(path.read_bytes()).hexdigest()!=fingerprint:raise RuntimeError('Warehouse changed during backtest')
    decisions=assess(results,cfg)
    out.mkdir(parents=True,exist_ok=True)
    for name,records in [('fold_accuracy',results),('fold_weights',weights_audit),('heldout_predictions',predictions),('category_assessments',decisions),('skipped_training',skips)]:
        write_csv(out/f'{name}.csv',records)
    with (out/'sample_memberships.jsonl').open('w',encoding='utf-8') as stream:
        for sample in samples:stream.write(json.dumps(sample,ensure_ascii=False)+'\n')
    report=dict(version='1.0',built_at_utc=datetime.now(timezone.utc).isoformat(),warehouse=str(path),warehouse_sha256=fingerprint,
        analytical_projection_rows=len(rows),matched_projection_rows=sum(r['matched'] for r in rows),
        fold_results=len(results),sample_sets=len(samples),heldout_predictions=len(predictions),weight_rows=len(weights_audit),skipped_training=len(skips),
        config=cfg,notes=['Every weight uses earlier-season training data only; held-out actuals are used solely for scoring and retrospective cohort filters.',
                         'Shared-history pools use sources with metric coverage in every training season and the held-out season.',
                         'Expanding pools give each incomplete-history source a neutral 1/M share and allocate the remaining share to trained sources.',
                         'Closer candidates are selected by any source in the sample pool projecting at least the configured saves floor, never by actual saves.',
                         'The rolling 2025-to-2026 fold is sensitivity analysis; it is not an independent third test year.',
                         'Assessments are descriptive. Method choice after inspecting these tests needs confirmation on a new season.'])
    (out/'backtest_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (out/'effective_config.json').write_text(json.dumps(cfg,indent=2),encoding='utf-8')
    render_report(out,report,decisions,results)
    return report


def assess(results,cfg):
    groups=defaultdict(list)
    for r in results:
        if r['primary_fold'] and r['method']!='equal':groups[(r['player_type'],r['metric'],r['cohort'],r['pool'],r['method'])].append(r)
    decisions=[]
    primary=sum(f['primary'] for f in cfg['folds'])
    for (typ,metric,cohort,pool,method),rows in sorted(groups.items()):
        eligible=len(rows)==primary and all(r['assessment_eligible'] and r['mae_improvement_pct'] is not None and r['rmse_improvement_pct'] is not None for r in rows)
        robust=eligible and all(r['mae_improvement_pct']>=cfg['minimum_mae_gain_pct'] and r['rmse_improvement_pct']>=-cfg['maximum_rmse_decline_pct'] for r in rows)
        decisions.append(dict(player_type=typ,metric=metric,cohort=cohort,pool=pool,method=method,
            heldout_years=[r['test_season'] for r in rows],sample_sizes={r['test_season']:r['n'] for r in rows},
            mean_year_mae_gain_pct=sum(r['mae_improvement_pct'] for r in rows)/len(rows) if eligible else None,
            consistent_candidate=robust,assessment='candidate_for_new_season_confirmation' if robust else 'retain_equal_baseline' if eligible else 'insufficient_evidence',
            fold_gains={r['test_season']:dict(mae_pct=r['mae_improvement_pct'],rmse_pct=r['rmse_improvement_pct']) for r in rows}))
    return decisions


def render_report(out,report,decisions,results):
    cfg=report['config']
    lines=['# Stage 2B — held-out weighted blend tests','',
        'Equal weighting is compared with shrinkage toward equal weights using inverse training MAE, and nonnegative sum-to-one weights fitted to regularized training squared error. No test-season outcomes enter weight fitting.',
        '', 'Primary tests: train 2024 → test 2025; train 2024–2025 → test 2026. The additional train 2025 → test 2026 fold assesses broader recent source coverage and is excluded from primary consistency assessments.',
        '', 'Shared-history pools contain sources present in every training year. Expanding pools include all test-season sources; each source lacking complete training history gets an equal neutral share, while earlier-season weights divide the remaining share.',
        '', f"A candidate must reduce held-out MAE by at least {cfg['minimum_mae_gain_pct']}% in both primary years, with RMSE worsening by no more than {cfg['maximum_rmse_decline_pct']}% in either year. This fixed screening rule is descriptive, not a significance test or a production guarantee."]
    for typ,settings in cfg['player_types'].items():
        headline=settings['headline_cohort']
        lines.extend(['',f'## {typ.title()}s — {headline}, expanding source pool','',
            '|Category|Method|2025 MAE gain|2026 MAE gain|Players 2025/2026|Assessment|',
            '|---|---|---:|---:|---|---|'])
        for d in decisions:
            if d['player_type']!=typ or d['cohort']!=headline or d['pool']!='expanding_pool':continue
            fmt=lambda yr:'—' if not d['fold_gains'].get(yr) or d['fold_gains'][yr]['mae_pct'] is None else f"{d['fold_gains'][yr]['mae_pct']:+.2f}%"
            count='/'.join(str(d['sample_sizes'].get(yr,'—')) for yr in (2025,2026))
            label={'retain_equal_baseline':'Retain equal','candidate_for_new_season_confirmation':'Candidate; confirm next season','insufficient_evidence':'Insufficient evidence'}[d['assessment']]
            lines.append(f"|{d['metric']}|{d['method']}|{fmt(2025)}|{fmt(2026)}|{count}|{label}|")
    lines.extend(['','## Saves — preseason closer candidates','',
        'This cohort requires positive actual IP and at least one participating preseason source projecting 5 or more saves. Actual saves do not determine inclusion; projected closers who finished with zero saves remain scored. Unmatched players still cannot be assigned fabricated zero actuals.',
        '', '|Pool|Method|2025 MAE gain|2026 MAE gain|Players 2025/2026|Assessment|',
        '|---|---|---:|---:|---|---|'])
    for d in decisions:
        if d['cohort']!='closer_candidates':continue
        fmt=lambda yr:'—' if not d['fold_gains'].get(yr) or d['fold_gains'][yr]['mae_pct'] is None else f"{d['fold_gains'][yr]['mae_pct']:+.2f}%"
        lines.append(f"|{d['pool']}|{d['method']}|{fmt(2025)}|{fmt(2026)}|{d['sample_sizes'].get(2025,'—')}/{d['sample_sizes'].get(2026,'—')}|{d['assessment']}|")
    lines.extend(['','## Recent-year sensitivity — train 2025, test 2026','',
        'These results learn from the broader 2025 source pool. They use the same 2026 outcomes as the second primary fold and therefore provide sensitivity evidence, not another independent validation season.',
        '', '|Type|Category|Cohort|Method|Players|MAE gain|RMSE gain|',
        '|---|---|---|---|---:|---:|---:|'])
    for r in results:
        typ=r['player_type']
        if r['primary_fold'] or r['pool']!='expanding_pool' or r['method']=='equal' or r['cohort'] not in (cfg['player_types'][typ]['headline_cohort'],'closer_candidates'):continue
        fmt=lambda v:'—' if v is None else f'{v:+.2f}%'
        lines.append(f"|{typ}|{r['metric']}|{r['cohort']}|{r['method']}|{r['n']}|{fmt(r['mae_improvement_pct'])}|{fmt(r['rmse_improvement_pct'])}|")
    lines.extend(['','## Outputs and interpretation','',
        '* `fold_accuracy.csv`: all methods, folds, source pools, cohorts and error/correlation/rank metrics. Positive improvement means lower error than equal weighting on the exact same held-out sample.',
        '* `fold_weights.csv`: exact frozen weights, source provenance, training sample counts and optimizer convergence. These are fold-specific research weights, not current production weights.',
        '* `heldout_predictions.csv`: every consensus forecast, actual value and underlying source forecasts, permitting independent recomputation.',
        '* `sample_memberships.jsonl`: exact training player-seasons and held-out player IDs. Training/test seasons are strictly separated.',
        '* `category_assessments.csv`: primary-fold consistency screens. The rolling fold is never counted as a third independent test.',
        '* `skipped_training.csv`: insufficient historical samples and explicitly unavailable fits.',
        '', 'Models use equal total weight per training season. Inverse-MAE weights are shrunk 50% toward equal. Fitted weights use a fixed ridge strength of 0.1 relative to training equal-blend MSE, preventing tuning on the held-out results. Training cohorts and test cohorts have the same thresholds; actual-playing-time filters condition results on realized opportunity.',
        '', 'Primary folds with longer history restrict trained sources to complete coverage across those years. This conservatively leaves later-introduced sources at neutral shares. The recent-year sensitivity fold learns from OOPSY and RotoWire in 2025, while Depth Charts has no pre-2026 training evidence.',
        '', 'The ten roto categories are evaluated directly. AVG/ERA/WHIP blends are weighted source rates, not separately reconstructed counting components. A later production consensus should reconcile rates with its PA/AB/IP components.',
        '', 'All raw and reviewed Stage 1B rows remain unchanged. No unmatched values are zero-filled, no weights are learned from the held-out season, and Greg Jones\'s unresolved advanced metrics remain outside these ten categories. With only two independent test seasons, small gains are tentative and method selection requires new-season confirmation.'])
    text='\n'.join(lines)+'\n'
    text=text.replace('fitted_rmse_ridge','Fitted weights').replace('inverse_mae_shrunk','Error-weighted').replace('retain_equal_baseline','Retain equal')
    (out/'blend_backtest_report.md').write_text(text,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',type=Path,default=Path(__file__).parent/'config/blend_backtesting.json')
    parser.add_argument('--output',type=Path);parser.add_argument('--warehouse',type=Path)
    args=parser.parse_args();report=backtest(args.config,args.output,args.warehouse)
    print(json.dumps({k:report[k] for k in ['fold_results','sample_sets','heldout_predictions','skipped_training']},indent=2))


if __name__=='__main__':main()
