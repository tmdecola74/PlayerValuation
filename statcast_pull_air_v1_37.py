"""Matched pull-air-only test for hitter extra-base hits and pitcher strikeouts."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import shutil

import numpy as np
from project_2027_statcast_v1_35 import (
    EXPOSURE, FEATURES, MIN_TRAIN, RIDGE, board_index, features, project,
)

TARGETS = {'hitter': ('2B', '3B'), 'pitcher': ('SO',)}
ARMS = {'weighted_actuals': None, 'residual_only': (),
        'pull_air_only': (FEATURES.index('pull_air_rate'),),
        'statcast_full': tuple(range(len(FEATURES)))}
PAIRS = (('residual_only', 'weighted_actuals'),
         ('pull_air_only', 'weighted_actuals'),
         ('pull_air_only', 'residual_only'),
         ('statcast_full', 'pull_air_only'),
         ('statcast_full', 'residual_only'))


def history_ids(actual, year, role):
    exp = 'PA' if role == 'hitter' else 'OUTS'
    return sorted({p for (s,r,p,m),v in actual.items()
                   if year-4 <= s < year and r == role and m == exp and v > 0})


def ready(b, role):
    needed = TARGETS[role] + (('1B','HR','BB','HBP','SF') if role=='hitter' else ())
    return b is not None and b.get(EXPOSURE[role],0) and all(b[m] is not None for m in needed)


def fit(actual, board, years, origin):
    if not years or any(y>=origin or y>=2026 for y in years):
        raise ValueError('Training requires earlier target seasons through 2025 only')
    models = {}
    for role, metrics in TARGETS.items():
        e = EXPOSURE[role]
        cases = []
        for year in years:
            for pid in history_ids(actual,year,role):
                b = project(actual,role,pid,year)
                x,_ = features(board,year,role,pid)
                n = actual.get((year,role,pid,e))
                y = [actual.get((year,role,pid,m)) for m in metrics]
                if x is None or not ready(b,role) or not n or None in y:
                    continue
                cases.append((x,[z/n-b[m]/b[e] for m,z in zip(metrics,y)],min(n,600.)))
        arms = {}
        if len(cases)>=MIN_TRAIN:
            x,y,w = map(lambda a:np.asarray(a,dtype=float),zip(*cases))
            mu=np.average(x,axis=0,weights=w)
            sd=np.sqrt(np.average((x-mu)**2,axis=0,weights=w))
            sd=np.where(sd<1e-8,1.,sd)
            xs=np.clip((x-mu)/sd,-4,4)
            w=w/w.mean()
            for arm, cols in ARMS.items():
                if cols is None:
                    continue
                z=np.column_stack((np.ones(len(x)),xs[:,list(cols)]))
                penalty=RIDGE*np.eye(z.shape[1]); penalty[0,0]=0.
                beta=np.linalg.solve(z.T@(z*w[:,None])+penalty,z.T@(y*w[:,None]))
                arms[arm]=beta.tolist()
            models[role]=dict(n=len(cases),mean=mu.tolist(),scale=sd.tolist(),arms=arms)
        else:
            models[role]=dict(n=len(cases),arms=arms)
    return models


def adjust(b, x, model, arm):
    c=dict(b)
    role=b['player_type']
    if x is None or arm not in model['arms'] or not ready(b,role):
        return c
    cols=list(ARMS[arm])
    z=np.clip((np.asarray(x)-model['mean'])/model['scale'],-4,4)
    delta=np.r_[1.,z[cols]]@np.asarray(model['arms'][arm])
    for m,d in zip(TARGETS[role],delta):
        c[m]=float(b[m]+np.clip(.5*b[EXPOSURE[role]]*d,-.5*b[m],.5*b[m]))
    if role=='hitter':
        room=max(0.,b['AB']-b['1B']-b['HR'])
        xb=c['2B']+c['3B']
        if xb>room:
            for m in TARGETS[role]:
                c[m]*=room/xb
        c['H']=math.fsum(c[m] for m in ('1B','2B','3B','HR'))
        c['AVG']=c['H']/c['AB']
        c['SLG']=math.fsum(i*c[m] for i,m in enumerate(('1B','2B','3B','HR'),1))/c['AB']
        c['OBP']=(c['H']+c['BB']+c['HBP'])/sum(c[m] for m in ('AB','BB','HBP','SF'))
        c['OPS']=c['OBP']+c['SLG']
    return c


def workload(role,b):
    e, thresholds = ('PA',(200,450)) if role=='hitter' else ('IP',(30,100))
    v=b[e]
    if v is None:
        return f'{e}_UNKNOWN'
    lo,hi=thresholds
    return f'{e}_LT_{lo}' if v<lo else f'{e}_{lo}_LT_{hi}' if v<hi else f'{e}_GE_{hi}'


def score(actual,board,year,models):
    bins=defaultdict(list)
    for role in TARGETS:
        exp=EXPOSURE[role]
        extra=('XBH','AVG','OPS') if role=='hitter' else ()
        for pid in history_ids(actual,year,role):
            b=project(actual,role,pid,year)
            x,_=features(board,year,role,pid)
            model=models[role]
            yden=actual.get((year,role,pid,exp))
            if not yden or not b[exp]:
                continue
            supported=x is not None and bool(model['arms']) and ready(b,role)
            preds={arm:adjust(b,x,model,arm) for arm in ARMS}
            y=lambda m: actual.get((year,role,pid,m))
            for metric in TARGETS[role]+extra:
                if metric=='XBH':
                    # Here XBH is doubles + triples + HR; HR is fixed.
                    fields=('2B','3B','HR')
                    if any(y(m) is None or b[m] is None for m in fields):
                        continue
                    truth=sum(y(m) for m in fields)
                    values=[sum(v[m] for m in fields) for v in preds.values()]
                else:
                    truth=y(metric)
                    if truth is None or b[metric] is None:
                        continue
                    values=[v[metric] for v in preds.values()]
                metrics=[(metric,tuple(v-truth for v in values))]
                if metric in (*TARGETS[role],'XBH'):
                    metrics.append((metric+'_PER_'+exp,tuple(v/b[exp]-truth/yden for v in values)))
                for m,errors in metrics:
                    for pool in ('MATCHED_ALL','FEATURE_SUPPORTED' if supported else 'BASELINE_FALLBACK'):
                        for band in ('ALL',workload(role,b)):
                            bins[role,m,pool,band].append((pid,errors))
    rows=[]
    for (role,m,pool,band),v in sorted(bins.items()):
        n=len(v)
        sig=hashlib.sha256(json.dumps(sorted(pid for pid,_ in v)).encode()).hexdigest()
        for i,arm in enumerate(ARMS):
            errors=[ee[i] for _,ee in v]
            rows.append(dict(target_season=year,reporting_only=year==2026,role=role,metric=m,
                     pool=pool,projected_workload_band=band,method=arm,n=n,membership_sha256=sig,
                     rmse=math.sqrt(math.fsum(z*z for z in errors)/n),
                     mae=math.fsum(map(abs,errors))/n,bias=math.fsum(errors)/n))
    return rows


def run(a):
    from recent_skill_core_v1_23 import checked, emit
    from recent_skill_inputs_v1_23 import labels, parquet_rows
    from participation_label_overlay_v1_27 import apply_overlay
    from standalone_io_v1_0 import dump, finish, load, start

    base,boards,lab,overlay,research = roots = [Path(getattr(a,k)).resolve() for k in
                                              ('baseline','leaderboards','labels','overlay','research')]
    watch = {}
    def take(root,n):
        return checked(root,n,watch)
    report = load(take(base,'report.json'))
    if (report['version']!='1.31.0' or report['valuation_enabled'] is not False
            or report['actual_input_years']!=[2023,2024,2025,2026]
            or report['model_selection_uses_2026'] is not False):
        raise ValueError('Expected provisional frozen v1.31 run')
    freeze = load(take(base,'model_choice_freeze.json'))
    if freeze['pitcher_default']!='accepted_ip':
        raise ValueError('Workload default differs from v1.31')
    bindings = load(take(base,'input_hashes.json'))
    train = take(lab,'training_labels.parquet')
    hp = take(research,'historical_forecasts.csv')
    historical, _ = apply_overlay(overlay,labels(train),train,hp,watch)
    def verify_binding(path):
        hashes = {v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==path.name}
        if watch[str(path)] not in hashes:
            raise ValueError(f'Frozen v1.31 input differs: {path}')
    for path in (train,hp,overlay/'report.json',overlay/'participation_label_overlay.csv'):
        verify_binding(path)
    imports = load(take(boards,'leaderboard_build_report.json'))
    if imports['version']!='1.21.0' or imports['training_uses_2026_data'] is not False:
        raise ValueError('Unexpected leaderboard input')
    counts = Counter()
    board = board_index(parquet_rows(take(boards,'historical/leaderboard_features.parquet')),
                        {2023,2024,2025},counts)
    development=fit(historical,board,(2024,),2025)
    frozen=fit(historical,board,(2024,2025),2026)
    historical_scores=score(historical,board,2025,development)
    if not historical_scores or any(not m['arms'] for m in development.values()):
        raise ValueError('Both roles require a fitted 2025 development fold')
    if not all(any(r['role']==role and r['pool']=='FEATURE_SUPPORTED' for r in historical_scores)
               for role in TARGETS):
        raise ValueError('Both roles require supported 2025 scoring rows')
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        emit(stage/'historical_2025_scores.csv',historical_scores)
        dump(stage/'frozen_models.json',dict(development_targets=[2024],reporting_fit_targets=[2024,2025],
             features=FEATURES,targets=TARGETS,arm_indices=ARMS,development=development,frozen=frozen))
        dump(stage/'development_fold_audit.json',dict(
             feature_source_seasons=sorted({k[0] for k in board}),
             required_definition='EXPORTED_FRACTION_OF_ALL_BBE',
             earliest_trainable_target=2024, development_folds=[2025],
             blocked_origins={'2023':'No earlier compatible leaderboard history.',
                              '2024':'No earlier trainable target with prior compatible leaderboard history.'},
             evaluation_only=[2026], extra_development_fold_available=False,
             required_for_2024_fold='Compatible eligible 2022 batted-ball export for both roles, or separately validated comparable features, with sufficient overlap and samples.',
             archive_coordinate_proxy_used=False))
        # No 2026 outcomes read or hashed until the models and historical scores are staged.
        hold = take(lab,'holdout_labels.parquet')
        verify_binding(hold)
        evaluation=score(historical | labels(hold,2026),board,2026,frozen)
        if not evaluation:
            raise ValueError('Missing 2026 reporting scores')
        emit(stage/'reporting_only_2026_scores.csv',evaluation)
        gaps=[]
        columns=('target_season','role','metric','pool','projected_workload_band')
        for scores in (historical_scores,evaluation):
            matched=defaultdict(dict)
            for r in scores:
                matched[tuple(r[k] for k in columns)][r['method']]=r
            for key,arms in sorted(matched.items()):
                for arm,comparator in PAIRS:
                    row,ref=arms[arm],arms[comparator]
                    if (row['n'],row['membership_sha256']) != (ref['n'],ref['membership_sha256']):
                        raise ValueError(f'Comparison membership mismatch: {key}')
                    gaps.append(dict(zip(columns,key),reporting_only=key[0]==2026,
                         method=arm,comparator=comparator,n=row['n'],
                         membership_sha256=row['membership_sha256'],
                         delta_rmse=row['rmse']-ref['rmse'],
                         delta_mae=row['mae']-ref['mae'],delta_bias=row['bias']-ref['bias']))
        emit(stage/'pull_air_comparison_deltas.csv',gaps)
        result=dict(version='1.37.0',status='RESEARCH_ONLY',workload_default='accepted_ip',
                    skill_default='weighted_actuals',valuation_enabled=False,hybrid_qs=None,
                    published_default_changed=False,fit_uses_2026_outcomes=False,
                    selection_uses_2026=False,promotion_performed=False,
                    historical_development_folds=[2025],reporting_only_folds=[2026],
                    training_rows={str(y):{r:m['n'] for r,m in bank.items()}
                        for y,bank in ((2025,development),(2026,frozen))},
                    baseline_frozen_fields=['PA','AB','1B','HR','IP','OUTS','BB','WHIP','QS'],
                    limitations=['Only one development fold; pull-air was nominated after inspecting it.',
                      'All arms use the full feature-supported cohort for the primary comparison; fallback rows are reported separately.',
                      'Full overlay reference is the v1.36 full arm for these targets, not the original multi-category v1.35 export.',
                      'Historical weighted baselines are reconstructed, not archived preseason releases.',
                      'No 2027 projections or valuations overwritten.'])
        dump(stage/'report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__=='__main__':
    p=ArgumentParser(description=__doc__)
    for k,v in dict(baseline='outputs/homegrown_2027_v1_31',
                    leaderboards='outputs/statcast_leaderboards_v1_21',
                    labels='outputs/training_labels_v1_0',overlay='outputs/participation_label_overlay_v1_27',
                    research='outputs/recent_history_skills_v1_23',output='outputs/2027_statcast_pull_air_v1_37',
                    backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(json.dumps(run(p.parse_args()),indent=2))
