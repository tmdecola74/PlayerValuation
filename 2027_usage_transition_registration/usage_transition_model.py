"""Registered empirical usage-transition candidate. Import has no I/O or fitting."""
from collections import Counter
import math

VERSION='USAGE_TRANSITION_0.1'
STATES={'hitter':('NO_PA','LIMITED_OR_BENCH','PART_TIME_STARTER','REGULAR_STARTER'),
        'pitcher':('NO_PITCHING_APPEARANCE','RELIEF','SWING_OR_LIMITED','ROTATION')}
FIELDS={'hitter':('MLB_G','BATTING_G','STARTS','PA'),
        'pitcher':('G','GS','GR','START_OUTS','RELIEF_OUTS')}
SETTINGS=dict(minimum_known=200,minimum_positive=20,minimum_zero=20,
              minimum_each_active_state=20,minimum_conditional_rows=20,
              minimum_pure_start_seasons=50,minimum_pure_relief_seasons=100,
              transition_prior_rows=50,conditional_prior_rows=50,
              global_probability_pseudocount=1,last60_minimum_games=10,
              hitter_role_minimum_batting_games=20,hitter_regular_share=.75,
              hitter_partial_share=.25,pitcher_rotation_share=.8,
              pitcher_role_minimum_outings=5,secondary_pitcher_minimum_G=5,
              secondary_pitcher_maximum_PA_exclusive=100)

def usage_state(role,row,certified_zero=False):
    if row is None:
        return STATES[role][0] if certified_zero else 'UNKNOWN'
    if row.get('source_reconciliation_status')!='SOURCE_RECONCILED':return 'UNKNOWN'
    if role=='hitter':
        pa=float(row.get('PA') or 0);g=float(row.get('BATTING_G') or 0);starts=float(row.get('STARTS') or 0)
        if pa==0:return 'NO_PA'
        if g<SETTINGS['hitter_role_minimum_batting_games']:return 'LIMITED_OR_BENCH'
        share=starts/g
        return 'REGULAR_STARTER' if share>=SETTINGS['hitter_regular_share'] else 'PART_TIME_STARTER' if share>=SETTINGS['hitter_partial_share'] else 'LIMITED_OR_BENCH'
    g=float(row.get('G') or 0);gs=float(row.get('GS') or 0)
    if g==0:return 'NO_PITCHING_APPEARANCE'
    if g<SETTINGS['pitcher_role_minimum_outings']:return 'SWING_OR_LIMITED'
    return 'ROTATION' if gs/g>=SETTINGS['pitcher_rotation_share'] else 'RELIEF' if gs==0 else 'SWING_OR_LIMITED'

def recent_state(role,row):
    if row is None or row.get('source_reconciliation_status')!='SOURCE_RECONCILED':return 'UNKNOWN'
    g=float(row.get('BATTING_G' if role=='hitter' else 'G') or 0)
    if g<SETTINGS['last60_minimum_games']:return 'UNKNOWN'
    # Same share thresholds, but require only the registered recent-window support.
    if role=='hitter':
        share=float(row.get('STARTS') or 0)/g
        return 'REGULAR_STARTER' if share>=.75 else 'PART_TIME_STARTER' if share>=.25 else 'LIMITED_OR_BENCH'
    gs=float(row.get('GS') or 0)
    return 'ROTATION' if gs/g>=.8 else 'RELIEF' if gs==0 else 'SWING_OR_LIMITED'

def vector(role,row,calendar):
    if not calendar or calendar<=0:raise ValueError('Positive observed calendar required')
    if row is None:return [0.]*len(FIELDS[role])
    values=[float(row.get('G' if f=='MLB_G' else f) or 0)/calendar for f in FIELDS[role]]
    if any(not math.isfinite(x) or x<0 for x in values):raise ValueError('Invalid workload vector')
    return values

def global_support(rows,role):
    state=Counter(r['target_state'] for r in rows);positive=sum(state[s] for s in STATES[role][1:]);zero=state[STATES[role][0]]
    reasons=[]
    if len(rows)<SETTINGS['minimum_known']:reasons.append('FEWER_THAN_200_KNOWN_LABELS')
    if positive<20 or zero<20:reasons.append('FEWER_THAN_20_POSITIVE_OR_ZERO_LABELS')
    if any(state[s]<20 for s in STATES[role][1:]):reasons.append('ACTIVE_STATE_BELOW_20_ROWS')
    pure_start=sum(r.get('pure_start',False) for r in rows);pure_relief=sum(r.get('pure_relief',False) for r in rows)
    if role=='pitcher' and (pure_start<50 or pure_relief<100):reasons.append('LEGACY_PURE_ROLE_SUPPORT_FLOOR')
    return dict(n=len(rows),state_counts=dict(state),positive=positive,zero=zero,pure_start=pure_start,pure_relief=pure_relief,supported=not reasons,reasons=reasons)

def _node(rows,role,parent=None):
    states=STATES[role];state=Counter(r['target_state'] for r in rows);n=len(rows)
    if parent is None:
        probs={s:(state[s]+1)/(n+len(states)) for s in states}
    else:
        probs={s:(state[s]+50*parent['probabilities'][s])/(n+50) for s in states}
    means={};support={}
    for s in states:
        rr=[r for r in rows if r['target_state']==s];count=len(rr);support[s]=count
        if parent is not None and count<20:means[s]=parent['means'][s];continue
        sums=[sum(r['target_vector'][i] for r in rr) for i in range(len(FIELDS[role]))]
        if parent is None:
            if not count:raise ValueError('Unsupported root conditional state')
            means[s]=[v/count for v in sums]
        else:means[s]=[(v+50*parent['means'][s][i])/(count+50) for i,v in enumerate(sums)]
    return dict(n=n,probabilities=probs,means=means,conditional_support=support)

def _cell_supported(rows,role):
    counts=Counter(r['target_state'] for r in rows)
    return len(rows)>=200 and counts[STATES[role][0]]>=20 and sum(counts[s] for s in STATES[role][1:])>=20

def fit(panel,origin):
    """Fit only targets before origin, never after 2025. Caller must freeze contract first."""
    if origin not in (2023,2024,2025,2026):raise ValueError('Origin must be 2023..2026; 2026 means coefficient freeze through 2025')
    if any(type(r.get('eligible')) is not bool for r in panel):raise ValueError('Eligibility must be boolean; use the registered JSON panel')
    if any(int(r['target_season'])>2025 for r in panel):raise ValueError('2026+ targets prohibited even if filtered later')
    model=dict(version=VERSION,origin=origin,roles={})
    for role in STATES:
        rows=[r for r in panel if r['role']==role and r['eligible'] and int(r['target_season'])<origin]
        for r in rows:
            if int(r['max_feature_season'])>=int(r['target_season']):raise ValueError('Target-season predictor leakage')
            if r['target_state'] not in STATES[role] or len(r['target_vector'])!=len(FIELDS[role]):raise ValueError('Bad label schema')
            if any(not math.isfinite(x) or x<0 for x in r['target_vector']):raise ValueError('Bad numeric target')
        support=global_support(rows,role)
        out=dict(support=support,max_target_season=max((int(r['target_season']) for r in rows),default=None),root=None,nodes={})
        if support['supported']:
            root=_node(rows,role);out['root']=root
            # Fixed hierarchy: root -> latest state -> latest/recent/experience.
            for state in sorted({r['latest_state'] for r in rows}):
                rr=[r for r in rows if r['latest_state']==state]
                if not _cell_supported(rr,role):continue
                parent=_node(rr,role,root);out['nodes'][state]=parent
                keys=sorted({(r['recent_state'],r['experience']) for r in rr})
                for recent,experience in keys:
                    ss=[r for r in rr if r['recent_state']==recent and r['experience']==experience]
                    if _cell_supported(ss,role):out['nodes']['|'.join((state,recent,experience))]=_node(ss,role,parent)
        model['roles'][role]=out
    return model

def predict(model,features,calendar=162):
    """Return experimental workload only. A fallback never returns replacement values."""
    role=features['role'];entry=model['roles'][role]
    if int(features['max_feature_season'])>=int(features['target_season']):raise ValueError('Feature cutoff violation')
    if entry['max_target_season'] is not None and entry['max_target_season']>=int(features['target_season']):raise ValueError('Model trained on forecast season or later')
    reason=features.get('fallback_reason')
    if reason:return dict(status='FULL_BASELINE_FALLBACK',reason=reason,workload=None)
    if features.get('latest_state') not in STATES[role]:return dict(status='FULL_BASELINE_FALLBACK',reason='UNKNOWN_LATEST_STATE',workload=None)
    if not entry['support']['supported']:return dict(status='FULL_BASELINE_FALLBACK',reason='GLOBAL_SUPPORT_FAILED',workload=None)
    if not math.isfinite(calendar) or not 0<calendar<=200:raise ValueError('Explicit planned team-game calendar required')
    latest=features['latest_state'];specific='|'.join((latest,features['recent_state'],features['experience']))
    node=entry['nodes'].get(specific) or entry['nodes'].get(latest) or entry['root'];level=specific if specific in entry['nodes'] else latest if latest in entry['nodes'] else 'GLOBAL'
    q=node['probabilities'];v={f:calendar*sum(q[s]*node['means'][s][i] for s in STATES[role]) for i,f in enumerate(FIELDS[role])}
    if role=='pitcher':
        v['OUTS']=v['START_OUTS']+v['RELIEF_OUTS'];v['IP']=v['OUTS']/3
        if not math.isclose(v['GS']+v['GR'],v['G'],abs_tol=1e-8):raise ValueError('Pitching partition failure')
    elif not (v['STARTS']<=v['BATTING_G']+1e-8<=v['MLB_G']+2e-8):raise ValueError('Batting opportunity failure')
    return dict(status='EXPERIMENTAL_WORKLOAD_ONLY',reason='',workload=v,state_probabilities=q,probability_label='EXPERIMENTAL_NOT_CALIBRATED',positive_exposure_probability=1-q[STATES[role][0]],positive_exposure_definition='PA>0' if role=='hitter' else 'credited_pitching_G>0',pool=level,pool_rows=node['n'])
