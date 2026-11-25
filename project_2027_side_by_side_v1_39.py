"""2027 frozen-recipe research export; no fitting, evaluation or promotion."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import shutil
import math
from project_2027_v1_31 import FIELDS, read, num, WEIGHTS
from statcast_pull_air_v1_37 import FEATURES, TARGETS, ARMS, EXPOSURE, features, ready, adjust
METHODS=('weighted_actuals','residual_only','pull_air_only')
MUTABLE={'hitter':{'2B','3B','H','AVG','OBP','SLG','OPS'},'pitcher':{'SO'}}

def assemble(raws,role,board,model,model_sha):
    wide=[];changes=[];support=[];seen=set()
    for raw in raws:
        pid=raw['mlbam_id']
        if raw['season']!='2027' or raw['player_type']!=role or pid in seen or not pid.isascii() or not pid.isdigit() or int(pid)<=0:
            raise ValueError('Invalid or duplicate forecast identity')
        seen.add(pid)
        b=dict(raw,**{m:num(raw[m]) for m in FIELDS[role]})
        x,ys=features(board,2027,role,pid)
        supported=x is not None and ready(b,role) and all(m in model['arms'] for m in METHODS[1:])
        reason=('SUPPORTED' if supported else 'MISSING_ELIGIBLE_FEATURES' if x is None else
                'MISSING_BASELINE_COMPONENTS' if not ready(b,role) else 'MISSING_FROZEN_MODEL')
        row={k:v for k,v in raw.items() if k not in FIELDS[role]}
        row.update(season=2027,player_type=role,mlbam_id=pid,status=reason,
            default_method='weighted_actuals',workload_default='accepted_ip',hybrid_qs=None,
            model_sha256=model_sha,statcast_years=';'.join(map(str,ys)),
            recipe='V1_37_FROZEN_FIT_TARGETS_2024_2025',valuation_enabled=False)
        for arm in METHODS:
            c=adjust(b,x,model,arm) if supported and arm!='weighted_actuals' else dict(b)
            for m in FIELDS[role]:
                if m not in MUTABLE[role] and c[m]!=b[m]:
                    raise ValueError('Frozen category changed: '+m)
                if c[m] is not None and (not math.isfinite(c[m]) or c[m]<0):
                    raise ValueError('Invalid projected value')
                row[f'{arm}__{m}']=c[m]
                if arm!='weighted_actuals':
                    changes.append(dict(season=2027,player_type=role,mlbam_id=pid,
                        name=raw.get('name',raw.get('Name','')),method=arm,metric=m,
                        baseline=b[m],candidate=c[m],
                        delta=c[m]-b[m] if c[m] is not None and b[m] is not None else None,
                        adjustable=m in MUTABLE[role],status=reason,model_sha256=model_sha))
        wide.append(row)
        for j,metric in enumerate(FEATURES):
            obs=[(y,w,board[y,role,pid,metric]) for y,w in zip(range(2023,2027),WEIGHTS)
                 if (y,role,pid,metric) in board]
            if not obs:
                support.append(dict(player_type=role,mlbam_id=pid,metric=metric,
                    source_season=None,eligible=False,value=None,bbe=None,recency_weight=None,
                    exposure_weight=None,weighted_feature=None,status=reason))
            for y,w,(v,n) in obs:
                support.append(dict(player_type=role,mlbam_id=pid,metric=metric,
                    source_season=y,eligible=True,value=v,bbe=n,recency_weight=w,
                    exposure_weight=w*n,
                    weighted_feature=sum(ww*vv*nn for _,ww,(vv,nn) in obs)/sum(ww*nn for _,ww,(_,nn) in obs),
                    status=reason))
    return wide,changes,support

def validate_models(f):
    if (f['development_targets']!=[2024] or f['reporting_fit_targets']!=[2024,2025]
        or tuple(f['features'])!=FEATURES or f['targets']!={k:list(v) for k,v in TARGETS.items()}
        or f['arm_indices']!={k:list(v) if v is not None else None for k,v in ARMS.items()}):
        raise ValueError('Unexpected v1.37 frozen recipe')
    for role in FIELDS:
        m=f['frozen'][role]
        for arm,cols in ARMS.items():
            if cols is None or arm not in m['arms']:continue
            beta=m['arms'][arm]
            if len(beta)!=len(cols)+1 or any(len(r)!=len(TARGETS[role]) for r in beta):
                raise ValueError('Invalid coefficient shape')
            if any(not math.isfinite(z) for r in beta for z in r):
                raise ValueError('Nonfinite coefficients')
        if m['arms']:
            if len(m['mean'])!=len(FEATURES) or len(m['scale'])!=len(FEATURES) or any(not math.isfinite(v) or v<=0 for v in m['scale']) or any(not math.isfinite(v) for v in m['mean']):
                raise ValueError('Invalid preprocessing')

def run(a):
    from standalone_io_v1_0 import dump,load,start,finish
    from recent_skill_core_v1_23 import checked,emit
    from recent_skill_inputs_v1_23 import parquet_rows
    from project_2027_statcast_v1_35 import board_index
    roots=[Path(getattr(a,k)).resolve() for k in ('baseline','leaderboards','experiment')]
    base,lb,exp=roots;watch={}
    take=lambda root,n:checked(root,n,watch)
    br=load(take(base,'report.json'));freeze=load(take(base,'model_choice_freeze.json'))
    if (br['version']!='1.31.0' or br['valuation_enabled'] is not False
        or br['actual_input_years']!=[2023,2024,2025,2026]
        or br['model_selection_uses_2026'] is not False or freeze['pitcher_default']!='accepted_ip'):
        raise ValueError('Unexpected frozen weighted baseline')
    er=load(take(exp,'report.json'))
    if er['version']!='1.37.0' or er['selection_uses_2026'] is not False or er['promotion_performed'] is not False:
        raise ValueError('Unexpected research experiment')
    mp=take(exp,'frozen_models.json');models=load(mp);validate_models(models)
    # Verify that the recipe was fitted against this same baseline/leaderboard release.
    bindings=load(take(exp,'input_hashes.json'))
    def bound(path):
        hashes={v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==path.name}
        if watch[str(path)] not in hashes:raise ValueError('Experiment input binding differs: '+path.name)
    bound(base/'report.json')
    bound(take(base,'model_choice_freeze.json'))
    irp=take(lb,'leaderboard_build_report.json');ir=load(irp);bound(irp)
    if ir['version']!='1.21.0' or ir['training_uses_2026_data'] is not False:
        raise ValueError('Unexpected leaderboard release')
    counts=Counter()
    hp=take(lb,'historical/leaderboard_features.parquet');bound(hp)
    board=board_index(parquet_rows(hp),{2023,2024,2025},counts)
    qp=take(lb,'quarantine_2026/leaderboard_features.parquet')
    board.update(board_index(parquet_rows(qp),{2026},counts))
    if {k[0] for k in board}!={2023,2024,2025,2026}:
        raise ValueError('Missing eligible source season')
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        all_changes=[];all_support=[];n={};statuses=Counter()
        shutil.copyfile(mp,stage/'frozen_models.json')
        for role in FIELDS:
            src=take(base,f'homegrown_2027_{role}s.csv')
            rows,changes,support=assemble(read(src),role,board,models['frozen'][role],watch[str(mp)])
            if len(rows)!=br['forecast_counts'][role]:raise ValueError('Baseline population differs')
            shutil.copyfile(src,stage/f'baseline_2027_{role}s.csv')
            emit(stage/f'side_by_side_2027_{role}s.csv',rows)
            all_changes.extend(changes);all_support.extend(support);n[role]=len(rows)
            statuses.update((role,r['status']) for r in rows)
        emit(stage/'player_adjustments.csv',all_changes)
        emit(stage/'player_feature_provenance.csv',all_support)
        emit(stage/'statcast_input_audit.csv',[dict(source_season=y,role=r,family=f,metric=m,
            treatment=t,source_reason=s,rows=n) for (y,r,f,m,t,s),n in sorted(counts.items())])
        ranked=[]
        for role in FIELDS:
            for metric in sorted(MUTABLE[role]):
                for arm in METHODS[1:]:
                    pool=[r for r in all_changes if r['player_type']==role and r['metric']==metric and r['method']==arm and r['delta']]
                    ranked.extend(dict(r,rank=i) for i,r in enumerate(sorted(pool,key=lambda r:(-abs(r['delta']),r['mlbam_id']))[:30],1))
        emit(stage/'largest_changes.csv',ranked or [dict(status='NO_NONZERO_CHANGES')])
        result=dict(version='1.39.0',status='RESEARCH_SIDE_BY_SIDE_EXPORT',forecast_counts=n,
            source_seasons=[2023,2024,2025,2026],fit_target_seasons=[2024,2025],
            models_refitted=False,model_selection_performed=False,additional_validation=False,
            model_selection_uses_2026=False,evaluation_outcomes_read=False,
            source_2026_measurements_used_for_2027_only=True,
            source_2026_scope='V1_21_NORMALIZATION_ONLY_NOT_EVENT_RECONCILED',
            skill_default='weighted_actuals',workload_default='accepted_ip',
            hybrid_qs=None,valuation_enabled=False,published_default_changed=False,
            player_status=[dict(role=r,status=s,n=n) for (r,s),n in sorted(statuses.items())],
            limitations=['Frozen v1.37 models fit on 2024–2025 targets, not refitted on 2026 outcomes.',
                '2026 actuals are inherited through the frozen 2027 weighted baseline.',
                'All arms share full-vector support; unsupported rows retain baseline.',
                'Only hitter 2B/3B and pitcher SO change; hitter H and ratios are recomputed.',
                'Retrospective sources and one inspected 2025 development fold; no new validation or promotion.',
                'No prospect population expansion or valuation wiring.'])
        dump(stage/'report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in dict(baseline='outputs/homegrown_2027_v1_31',
        leaderboards='outputs/statcast_leaderboards_v1_21',
        experiment='outputs/2027_statcast_pull_air_v1_37',
        output='outputs/2027_side_by_side_v1_39',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(json.dumps(run(p.parse_args()),indent=2))
