"""Unscored player-anchored residual candidate. Pure import; no files or model fit."""
import math
from collections import Counter
VERSION='PLAYER_ANCHORED_WORKLOAD_0.1'
STATES={'hitter':('NO_PA','LIMITED_OR_BENCH','PART_TIME_STARTER','REGULAR_STARTER'),
        'pitcher':('NO_PITCHING_APPEARANCE','RELIEF','SWING_OR_LIMITED','ROTATION')}
FIELDS={'hitter':('MLB_G','BATTING_G','STARTS','PA'),
        'pitcher':('G','GS','GR','START_OUTS','RELIEF_OUTS')}
SETTINGS=dict(minimum_known=200,minimum_positive=20,minimum_zero=20,
 minimum_each_active_state=20,minimum_pure_start_seasons=50,
 minimum_pure_relief_seasons=100,parent_prior_rows=50)

def valid_vector(role,v):
    if not isinstance(v,list) or len(v)!=len(FIELDS[role]) or any(not isinstance(x,(int,float)) or not math.isfinite(x) or x<0 for x in v):return False
    if role=='hitter':return v[2]<=v[1]+1e-10<=v[0]+2e-10 and not (v[3]>0 and v[1]<=0)
    return math.isclose(v[0],v[1]+v[2],rel_tol=1e-10,abs_tol=1e-10) and not (v[3]>0 and v[1]<=0) and not (v[4]>0 and v[2]<=0)

def support(rows,role):
    counts=Counter(r['target_state'] for r in rows);zero=counts[STATES[role][0]];positive=len(rows)-zero
    reasons=[]
    if len(rows)<200:reasons.append('FEWER_THAN_200_KNOWN_LABELS')
    if positive<20 or zero<20:reasons.append('FEWER_THAN_20_POSITIVE_OR_ZERO_LABELS')
    if any(counts[s]<20 for s in STATES[role][1:]):reasons.append('ACTIVE_STATE_BELOW_20_ROWS')
    ps=sum(r.get('pure_start',False) for r in rows);pr=sum(r.get('pure_relief',False) for r in rows)
    if role=='pitcher' and (ps<50 or pr<100):reasons.append('LEGACY_PURE_ROLE_SUPPORT_FLOOR')
    return dict(n=len(rows),positive=positive,zero=zero,state_counts=dict(counts),pure_start=ps,pure_relief=pr,supported=not reasons,reasons=reasons)

def cell_supported(rows,role):
    zero=sum(r['target_state']==STATES[role][0] for r in rows)
    return len(rows)>=200 and zero>=20 and len(rows)-zero>=20

def node(rows,role,parent=None):
    n=len(rows);sums=[sum(r['residual_vector'][i] for r in rows) for i in range(len(FIELDS[role]))]
    values=[s/n for s in sums] if parent is None else [(s+50*parent['mean_residual'][i])/(n+50) for i,s in enumerate(sums)]
    return dict(n=n,mean_residual=values,parent_weight=0 if parent is None else 50/(n+50))

def fit(panel,origin):
    """Callable for a later registered scoring build. This registration uses synthetic data only."""
    if origin not in (2023,2024,2025,2026):raise ValueError('Allowed origins2023..2026; final origin2026 freezes through2025')
    if any(type(r.get('eligible')) is not bool for r in panel):raise ValueError('Boolean eligibility required')
    if any(int(r['target_season'])>2025 for r in panel):raise ValueError('2026+ targets prohibited even if ineligible')
    result=dict(version=VERSION,origin=origin,roles={})
    for role in STATES:
        rr=[r for r in panel if r['role']==role and r['eligible'] and int(r['target_season'])<origin]
        for r in rr:
            if int(r['max_feature_season'])>=int(r['target_season']) or int(r['anchor_season'])!=int(r['target_season'])-1:raise ValueError('Target-season leakage or nonlatest anchor')
            if r['target_state'] not in STATES[role]:raise ValueError('Unknown target state')
            if not valid_vector(role,r['anchor_vector']) or not valid_vector(role,r['target_vector']):raise ValueError('Invalid joint vector')
            v=r['residual_vector']
            if not isinstance(v,list) or len(v)!=len(FIELDS[role]) or any(not math.isfinite(x) for x in v):raise ValueError('Invalid signed residual')
            if any(not math.isclose(v[i],r['target_vector'][i]-r['anchor_vector'][i],rel_tol=1e-10,abs_tol=1e-10) for i in range(len(v))):raise ValueError('Residual identity failed')
        ss=support(rr,role);e=dict(support=ss,max_target_season=max((int(r['target_season']) for r in rr),default=None),root=None,nodes={})
        if ss['supported']:
            root=node(rr,role);e['root']=root
            for state in sorted({r['latest_state'] for r in rr}):
                state_rows=[r for r in rr if r['latest_state']==state]
                if not cell_supported(state_rows,role):continue
                parent=node(state_rows,role,root);e['nodes'][state]=parent
                for recent,experience in sorted({(r['recent_state'],r['experience']) for r in state_rows}):
                    child=[r for r in state_rows if r['recent_state']==recent and r['experience']==experience]
                    if cell_supported(child,role):e['nodes']['|'.join((state,recent,experience))]=node(child,role,parent)
        result['roles'][role]=e
    return result

def predict(model,features,calendar=162):
    role=features['role'];e=model['roles'][role];target=int(features['target_season'])
    if int(features['max_feature_season'])>=target or int(features['anchor_season'])!=target-1:raise ValueError('Prediction cutoff or latest-anchor violation')
    if e['max_target_season'] is not None and e['max_target_season']>=target:raise ValueError('Future-trained model')
    def fallback(reason):return dict(status='FULL_BASELINE_FALLBACK',reason=reason,workload=None)
    if features.get('fallback_reason'):return fallback(features['fallback_reason'])
    if features.get('latest_state') not in STATES[role]:return fallback('UNKNOWN_LATEST_STATE')
    if not valid_vector(role,features.get('anchor_vector')):return fallback('UNKNOWN_OR_INVALID_ANCHOR')
    if not e['support']['supported']:return fallback('GLOBAL_SUPPORT_FAILED')
    if not isinstance(calendar,(float,int)) or not math.isfinite(calendar) or not 0<calendar<=200:raise ValueError('Explicit planned calendar required')
    specific='|'.join((features['latest_state'],features['recent_state'],features['experience']))
    pool=specific if specific in e['nodes'] else features['latest_state'] if features['latest_state'] in e['nodes'] else 'GLOBAL'
    chosen=e['root'] if pool=='GLOBAL' else e['nodes'][pool]
    raw={f:calendar*(features['anchor_vector'][i]+chosen['mean_residual'][i]) for i,f in enumerate(FIELDS[role])}
    v={f:max(0,x) for f,x in raw.items()}
    if role=='hitter':
        v['BATTING_G']=min(v['BATTING_G'],v['MLB_G']);v['STARTS']=min(v['STARTS'],v['BATTING_G'])
        if v['PA']>0 and v['BATTING_G']<=0:return fallback('INFEASIBLE_POSITIVE_PA_WITH_NO_BATTING_G')
    else:
        v['G']=v['GS']+v['GR'];v['OUTS']=v['START_OUTS']+v['RELIEF_OUTS'];v['IP']=v['OUTS']/3
        if v['START_OUTS']>0 and v['GS']<=0:return fallback('INFEASIBLE_START_OUTS_WITH_NO_STARTS')
        if v['RELIEF_OUTS']>0 and v['GR']<=0:return fallback('INFEASIBLE_RELIEF_OUTS_WITH_NO_RELIEF')
    return dict(status='EXPERIMENTAL_WORKLOAD_ONLY',reason='',workload=v,raw_workload=raw,pool=pool,pool_rows=chosen['n'],mean_residual=chosen['mean_residual'],feasibility_changed=any(abs(v[f]-raw[f])>1e-8 for f in raw),probability_output=None,interpretation='Point estimate, not calibrated role/medical probabilities')
