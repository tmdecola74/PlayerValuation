"""Research-only 2027 skill overlay: frozen v1.31 workload, fixed Statcast recipe."""
from argparse import ArgumentParser
from collections import Counter, defaultdict
import json
import hashlib
import math
from pathlib import Path
import shutil

from project_2027_v1_31 import FIELDS, WEIGHTS, project, read, num
import numpy as np

VERSION = '1.35.0'
FEATURES = ('gb_rate', 'ld_rate', 'fb_rate', 'pull_air_rate')
YEARS = {2023, 2024, 2025, 2026}
TARGETS = {'hitter': ('1B', '2B', '3B'), 'pitcher': ('SO', 'BB')}
EXPOSURE = {'hitter': 'AB', 'pitcher': 'OUTS'}
MIN_TRAIN = 100
RIDGE = 20.0


def board_index(rows, years, audit):
    """Respect the v1.21 row-level eligibility mask, including relationship flags."""
    values, identities = {}, set()
    for r in rows:
        y, role, pid, family, metric = (int(r['source_season']), r['player_type'],
            str(r['mlbam_id']), r['family'], r['metric'])
        k = (y, role, pid, family, metric)
        if y not in years or role not in TARGETS or not pid.isascii() or not pid.isdigit() or int(pid)<=0 or k in identities:
            raise ValueError(f'Invalid leaderboard split or duplicate: {k}')
        identities.add(k)
        visible = r['eligible'] is True
        selected = family == 'batted_ball' and metric in FEATURES
        if visible and selected:
            x, count = r['value'], r['denominator']
            if (r['sample_eligible'] is not True or r['definition_supported'] is not True
                    or r['sample_basis'] != 'EXPORTED_BBE'
                    or r['definition'] != 'EXPORTED_FRACTION_OF_ALL_BBE' or r['unit'] != 'fraction'
                    or count is None or count < max(30, r['minimum_observations'])
                    or x is None or not math.isfinite(x) or not 0 <= x <= 1):
                raise ValueError(f'Inconsistent eligible batted-ball row: {k}')
            values[y,role,pid,metric] = float(x), float(count)
        treatment = ('ADMITTED_RESEARCH_FEATURE' if selected and visible else
                     'MASKED_RESEARCH_FEATURE' if selected else
                     'BAT_TRACKING_AUDIT_ONLY' if family == 'bat_tracking' else 'AUDIT_ONLY')
        audit[y,role,family,metric,treatment,r['reason']] += 1
    return values


def features(board, year, role, pid):
    vals, sources = [], set()
    for metric in FEATURES:
        obs = [(s, w, board[s,role,pid,metric]) for s,w in zip(range(year-4,year), WEIGHTS)
               if (s,role,pid,metric) in board]
        if not obs:
            return None, ()
        vals.append(sum(w*x*n for _,w,(x,n) in obs)/sum(w*n for _,w,(_,n) in obs))
        sources.update(s for s,_,_ in obs)
    return vals, tuple(sorted(sources))


def training_cases(actual, board, year, role):
    # Baselines for retrospective origins use prior eligible actuals only.
    ids = sorted({pid for (s,r,pid,m),x in actual.items()
                  if r == role and m == ('PA' if role=='hitter' else 'OUTS')
                  and year-4 <= s < year and x > 0})
    for pid in ids:
        b = project(actual, role, pid, year)
        x, _ = features(board,year,role,pid)
        exp = EXPOSURE[role]
        den = actual.get((year,role,pid,exp))
        truth = [actual.get((year,role,pid,m)) for m in TARGETS[role]]
        if (x is None or not den or not b[exp] or None in truth
                or any(b[m] is None for m in TARGETS[role])):
            continue
        residual = [v/den-b[m]/b[exp] for m,v in zip(TARGETS[role],truth)]
        yield x, residual, min(den, 600.0)


def fit(actual, board, targets, year):
    if not targets or max(targets) >= year or max(targets)>2025:
        raise ValueError('Invalid fit chronology; 2026 outcomes cannot fit this recipe')
    output = {}
    for role in TARGETS:
        cases = [v for y in targets for v in training_cases(actual,board,y,role)]
        if len(cases)<MIN_TRAIN:
            output[role] = dict(n=len(cases), model=None)
            continue
        x,y,w = map(lambda v:np.asarray(v,dtype=float),zip(*cases))
        mu = np.average(x,axis=0,weights=w)
        sd = np.sqrt(np.average((x-mu)**2,axis=0,weights=w))
        sd = np.where(sd<1e-8,1.,sd)
        z = np.column_stack([np.ones(len(x)), np.clip((x-mu)/sd,-4,4)])
        w = w/w.mean()
        penalty = RIDGE*np.eye(z.shape[1])
        penalty[0,0] = 0
        beta = np.linalg.solve(z.T@(z*w[:,None])+penalty,z.T@(y*w[:,None]))
        output[role] = dict(n=len(cases),model=dict(mean=mu.tolist(),scale=sd.tolist(),beta=beta.tolist()))
    return output


def apply(base, x, model):
    r = dict(base)
    role = r['player_type']
    den = r[EXPOSURE[role]]
    if x is None:
        return r, 'MISSING_ELIGIBLE_STATCAST'
    if model is None:
        return r, 'INSUFFICIENT_TRAINING'
    needed = TARGETS[role]+(('HR','BB','HBP','SF') if role=='hitter' else ('IP','H'))
    if not den or any(r.get(m) is None for m in needed) or (role=='pitcher' and not r['IP']):
        return r, 'MISSING_BASELINE_COMPONENT'
    z = np.r_[1.,np.clip((np.asarray(x)-model['mean'])/model['scale'],-4,4)]
    # Fixed, conservative half-strength residual overlay, with a 50% relative cap.
    for m, delta in zip(TARGETS[role], z @ np.asarray(model['beta'])):
        r[m] = float(base[m]+np.clip(.5*den*delta, -.5*base[m], .5*base[m]))
    if role=='hitter':
        capacity = max(0.,r['AB']-r['HR'])
        non_hr = math.fsum(r[m] for m in TARGETS[role])
        if non_hr>capacity:
            for m in TARGETS[role]:
                r[m] *= capacity/non_hr
        r['H'] = math.fsum(r[m] for m in (*TARGETS[role],'HR'))
        r['AVG'] = r['H']/r['AB']
        r['SLG'] = math.fsum(i*r[m] for i,m in enumerate((*TARGETS[role],'HR'),1))/r['AB']
        obp_den = math.fsum(r[m] for m in ('AB','BB','HBP','SF'))
        r['OBP'] = math.fsum(r[m] for m in ('H','BB','HBP'))/obp_den
        r['OPS'] = r['OBP']+r['SLG']
    else:
        r['WHIP'] = (r['BB']+r['H'])/r['IP']
    return r, 'STATCAST_CHALLENGER'


def compare_origin(actual, board, year, models):
    bins = defaultdict(list)
    for role in TARGETS:
        ids = sorted({pid for (s,r,pid,m),v in actual.items() if s==year and r==role
                      and m==EXPOSURE[role] and v>0})
        for pid in ids:
            b = project(actual,role,pid,year)
            if b is None:
                continue
            x,_ = features(board,year,role,pid)
            c,status = apply(b,x,models[role]['model'])
            for metric in (('1B','2B','3B','AVG','OPS') if role=='hitter' else ('SO','BB','WHIP')):
                y = actual.get((year,role,pid,metric))
                if y is None or b[metric] is None or c[metric] is None:
                    continue
                for group in ('MATCHED_ALL', 'FEATURE_SUPPORTED' if status=='STATCAST_CHALLENGER' else 'BASELINE_FALLBACK'):
                    bins[role,metric,group].append((pid,b[metric]-y,c[metric]-y))
                    den = actual[(year,role,pid,EXPOSURE[role])]
                    if metric in TARGETS[role] and b[EXPOSURE[role]]:
                        bins[role,metric+'_PER_'+EXPOSURE[role],group].append(
                            (pid,b[metric]/b[EXPOSURE[role]]-y/den,c[metric]/b[EXPOSURE[role]]-y/den))
    return [dict(target_season=year,reporting_only=year==2026,role=role,metric=m,group=g,n=len(rows),
                 method=arm, membership_sha256=hashlib.sha256(json.dumps(sorted(r[0] for r in rows)).encode()).hexdigest(),
                 rmse=math.sqrt(math.fsum(r[i+1]**2 for r in rows)/len(rows)),
                 mae=math.fsum(abs(r[i+1]) for r in rows)/len(rows),
                 bias=math.fsum(r[i+1] for r in rows)/len(rows))
            for (role,m,g),rows in sorted(bins.items()) for i,arm in enumerate(('weighted_actuals','statcast'))]


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
    hold = take(lab,'holdout_labels.parquet')
    hp = take(research,'historical_forecasts.csv')
    historical, _ = apply_overlay(overlay,labels(train),train,hp,watch)
    for path in (train,hold,hp,overlay/'report.json',overlay/'participation_label_overlay.csv'):
        hashes = {v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==path.name}
        if watch[str(path)] not in hashes:
            raise ValueError(f'Frozen v1.31 input differs: {path}')
    imports = load(take(boards,'leaderboard_build_report.json'))
    if imports['version']!='1.21.0' or imports['training_uses_2026_data'] is not False:
        raise ValueError('Unexpected leaderboard input')
    counts = Counter()
    board = board_index(parquet_rows(take(boards,'historical/leaderboard_features.parquet')),
                        {2023,2024,2025},counts)
    # Criteria and parameters are fixed. Fit before reading 2026 outcomes or measurements.
    development = fit(historical,board,(2024,),2025)
    frozen = fit(historical,board,(2024,2025),2026)
    scores = compare_origin(historical,board,2025,development)
    actual = historical | labels(hold,2026)
    scores += compare_origin(actual,board,2026,frozen)
    board.update(board_index(parquet_rows(take(boards,'quarantine_2026/leaderboard_features.parquet')),
                             {2026},counts))
    if {k[0] for k in board} != YEARS:
        raise ValueError('One or more source seasons have no admitted batted-ball rows')
    out,bak,stage = start(a.output,a.backup_root,roots)
    try:
        av = [dict(source_season=y,role=r,family=f,metric=m,treatment=t,source_reason=s,rows=n)
              for (y,r,f,m,t,s),n in sorted(counts.items())]
        emit(stage/'statcast_input_audit.csv', av)
        emit(stage/'historical_2025_scores.csv',[r for r in scores if r['target_season']==2025])
        emit(stage/'reporting_only_2026_scores.csv',[r for r in scores if r['target_season']==2026])
        emit(stage/'actual_label_availability.csv',
             [dict(source_season=y,role=r,metric=m,eligible_player_rows=n)
              for (y,r,m),n in sorted(Counter((y,r,m) for y,r,_,m in actual if y in YEARS).items())])
        dump(stage/'frozen_skill_models.json',dict(features=FEATURES,development_fit_target_years=[2024],
              frozen_fit_target_years=[2024,2025],development=development,frozen=frozen))
        changes, support, coverage = [], [], Counter()
        for role,fields in FIELDS.items():
            filename = f'homegrown_2027_{role}s.csv'
            src = take(base,filename)
            shutil.copyfile(src,stage/f'baseline_2027_{role}s.csv')
            seen, challenger, pairs = set(), [], []
            for raw in read(src):
                pid = raw['mlbam_id']
                if (raw['season']!='2027' or raw['player_type']!=role or pid in seen
                        or not pid.isascii() or not pid.isdigit() or int(pid)<=0):
                    raise ValueError(f'Unexpected v1.31 projection key: {role}/{pid}')
                seen.add(pid)
                b = dict(raw,**{m:num(raw[m]) for m in fields})
                x,ys = features(board,2027,role,pid)
                c,status = apply(b,x,frozen[role]['model'])
                mutable = set(TARGETS[role]) | ({'H','AVG','OBP','SLG','OPS'} if role=='hitter' else {'WHIP'})
                if any(c[m]!=b[m] for m in fields if m not in mutable):
                    raise ValueError(f'Frozen category changed: {role}/{pid}')
                coverage[role,status]+=1
                challenger.append(dict(c,statcast_status=status,statcast_source_years=';'.join(map(str,ys)),hybrid_qs=None))
                support.append(dict(player_type=role,mlbam_id=pid,status=status,
                       eligible_2026_batted_ball_metrics=sum((2026,role,pid,m) in board for m in FEATURES),
                       actual_history_years=';'.join(str(y) for y in sorted(YEARS)
                            if (y,role,pid,'PA' if role=='hitter' else 'OUTS') in actual),
                       baseline_exposure_history=raw.get('exposure_history_years',''),
                       statcast_source_years=';'.join(map(str,ys)),
                       **{f'sc_{m}':x[i] if x else None for i,m in enumerate(FEATURES)}))
                for m in fields:
                    d = c[m]-b[m] if c[m] is not None and b[m] is not None else None
                    row = dict(season=2027,player_type=role,mlbam_id=pid,metric=m,baseline=b[m],
                               challenger=c[m],delta=d,statcast_status=status)
                    pairs.append(row)
                    if d:
                        changes.append(row)
            if len(seen)!=report['forecast_counts'][role]:
                raise ValueError('Frozen player count differs')
            emit(stage/f'statcast_2027_{role}s.csv',challenger)
            emit(stage/f'comparison_2027_{role}s.csv',pairs)
        emit(stage/'player_input_coverage.csv',support)
        ranked = defaultdict(list)
        for row in changes:
            ranked[row['player_type'],row['metric']].append(row)
        emit(stage/'largest_changes_by_metric.csv',[
            dict(row,rank=i) for group in sorted(ranked) for i,row in enumerate(
                sorted(ranked[group],key=lambda r:(-abs(r['delta']),r['mlbam_id']))[:30],1)])
        result = dict(version=VERSION,status='RESEARCH_ONLY',valuation_enabled=False,hybrid_qs=None,
                      workload_default='accepted_ip',published_default_changed=False,
                      selection_uses_2026=False,fit_uses_2026_outcomes=False,
                      source_seasons=sorted(YEARS),source_2026_scope='V1_21_NORMALIZATION_ONLY_NOT_EVENT_RECONCILED',
                      player_status=[dict(role=r,status=s,n=n) for (r,s),n in sorted(coverage.items())],
                      limitations=['Only one 2025 development fold; 2026 previously reviewed and reporting only.',
                                   '2026 actuals in the frozen 2027 workload baseline; 2026 leaderboard values for 2027 only.',
                                   'Retrospective origin baselines reconstructed from eligible actuals, not archived 2025 forecasts.',
                                   'Only batted-ball family modeled with v1.21 masks; EV, baserunning and bat tracking audited separately.',
                                   'No new workload, prospects, runs, RBI, wins, ERA, saves, holds, or hybrid QS model.'])
        dump(stage/'report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__=='__main__':
    p = ArgumentParser(description=__doc__)
    for k,v in dict(baseline='outputs/homegrown_2027_v1_31',
                    leaderboards='outputs/statcast_leaderboards_v1_21',
                    labels='outputs/training_labels_v1_0',overlay='outputs/participation_label_overlay_v1_27',
                    research='outputs/recent_history_skills_v1_23',output='outputs/homegrown_2027_statcast_v1_35',
                    backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(json.dumps(run(p.parse_args()),indent=2))
