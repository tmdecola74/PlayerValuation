"""Bounded historical skill/workload experiments and a frozen-baseline 2027 release."""
import argparse
from collections import defaultdict,Counter
import hashlib,json,math
from pathlib import Path
import shutil
from project_2027_v1_31 import project,FIELDS,WEIGHTS,read,num

HISTORICAL=tuple(range(2019,2026))
SKILL={'hitter':('1B','2B','3B','HR'),'pitcher':('H','ER','BB','SO','HR')}
RATES={'hitter':('AVG','OPS'),'pitcher':('ERA','WHIP','SO_PER_OUTS','HR_PER_OUTS')}
METHODS=('weighted_actuals','skill_regression','freshness_workload')
CONTRACT=dict(version='1.42.0',origins=list(HISTORICAL),weights=list(WEIGHTS),
    skill_prior_exposure=dict(hitter_AB=200,pitcher_OUTS=300),
    minimum_population_exposure=10000,workload_group_prior_players=50,
    minimum_selection_folds=3,minimum_rows_per_fold=30,minimum_improvement=.01,
    maximum_individual_metric_degradation=.02,maximum_recent_degradation=.02,
    maximum_low_history_degradation=.02,minimum_cohort_rows=15,
    final_selection_max_season=2025,include_2020_2021=True,
    default_skill='weighted_actuals',default_workload='accepted_ip',
    automatic_promotion=False,valuation_enabled=False)

def exposure(role):return 'PA' if role=='hitter' else 'OUTS'
def finite(x):return isinstance(x,(float,int)) and math.isfinite(x)
def keyhash(ids):return hashlib.sha256(json.dumps(sorted(ids)).encode()).hexdigest()
def ids_before(actual,role,target):
    e=exposure(role)
    return sorted({p for (y,r,p,m),v in actual.items() if target-4<=y<target and r==role and m==e and v>0},key=int)
def context(actual,role,pid,target):
    e=exposure(role)
    vals=[actual.get((y,role,pid,e)) for y in range(target-4,target)]
    pos=sum(v is not None and v>0 for v in vals)
    prior=vals[-1]
    gs=actual.get((target-1,role,pid,'GS'));g=actual.get((target-1,role,pid,'G'))
    rolelabel=('STARTER' if g and gs is not None and gs/g>=.5 else
               'RELIEVER' if g and gs==0 else 'SWING' if g and gs is not None else 'UNKNOWN') if role=='pitcher' else 'HITTER'
    state='RECENT_POSITIVE' if prior is not None and prior>0 else 'KNOWN_ZERO_RECENT' if prior==0 else 'UNKNOWN_RECENT'
    recorded=sum(v for v in vals if v is not None)
    # Returner-like is an observable history cohort, not a future participation label.
    earlier=sum(v for v in vals[:-1] if v is not None)
    return dict(freshness=state,history='LOW_HISTORY' if pos<2 else 'ESTABLISHED',
        prior_role=rolelabel,returner='EARLIER_SUBSTANTIAL_NO_RECENT_POSITIVE' if state!='RECENT_POSITIVE' and earlier>=(300 if role=='pitcher' else 400) else 'OTHER',
        group=state+'|'+rolelabel,recorded_exposure=recorded)
def population(actual,target):
    if target>2026:raise ValueError('Population coefficients freeze through 2025 outcomes')
    bank={}
    for role in FIELDS:
        den='AB' if role=='hitter' else 'OUTS';out={}
        for m in SKILL[role]:
            pairs=[(v,actual.get((y,r,p,den))) for (y,r,p,k),v in actual.items()
                   if target-4<=y<target and r==role and k==m]
            pairs=[(n,d) for n,d in pairs if d is not None and d>0]
            n=sum(n for n,d in pairs);d=sum(d for n,d in pairs)
            out[m]=dict(numerator=n,denominator=d,rate=n/d if d>=CONTRACT['minimum_population_exposure'] else None)
        bank[role]=out
    return bank
def skill_candidate(b,actual,role,pid,target,bank):
    out=dict(b);den='AB' if role=='hitter' else 'OUTS';strength=200 if role=='hitter' else 300
    trace=[];supported=True
    for m in SKILL[role]:
        pairs=[(w,actual.get((y,role,pid,m)),actual.get((y,role,pid,den)))
               for y,w in zip(range(target-4,target),WEIGHTS)]
        pairs=[(w,n,d) for w,n,d in pairs if n is not None and d is not None and d>0]
        d=sum(w*d for w,n,d in pairs);n=sum(w*n for w,n,d in pairs)
        # Divide by the mean of available season weights so one observation is
        # not counted as four independent observations just because it is recent.
        meanw=sum(w for w,_,_ in pairs)/len(pairs) if pairs else None
        adjusted_d=d/meanw if meanw else None
        prior=bank[role][m]['rate']
        if not pairs or prior is None or b.get(m) is None or not b.get(den):
            supported=False
        rate=(n/meanw+strength*prior)/(adjusted_d+strength) if pairs and prior is not None else None
        if rate is not None and b.get(den) is not None:out[m]=b[den]*rate
        trace.append(dict(metric=m,denominator=den,weighted_numerator=n,weighted_denominator=d,
            raw_denominator=sum(d for _,_,d in pairs),normalized_weighted_exposure=adjusted_d,
            prior_rate=prior,prior_exposure=strength,shrunk_rate=rate))
    # Common complete-group support, never substitute a population-only estimate.
    if not supported:return dict(b),False,trace
    if role=='hitter':
        hit=sum(out[m] for m in SKILL[role])
        if hit>out['AB']:
            for m in SKILL[role]:out[m]*=out['AB']/hit
        out['H']=sum(out[m] for m in SKILL[role]);out['AVG']=out['H']/out['AB']
        out['SLG']=sum(i*out[m] for i,m in enumerate(SKILL[role],1))/out['AB']
        dd=sum(out[m] for m in ('AB','BB','HBP','SF')) if all(out.get(m) is not None for m in ('AB','BB','HBP','SF')) else None
        out['OBP']=(out['H']+out['BB']+out['HBP'])/dd if dd else None
        out['OPS']=out['OBP']+out['SLG'] if out['OBP'] is not None else None
    else:
        out['H']=max(out['H'],out['HR'])
        out['ERA']=27*out['ER']/out['OUTS'];out['WHIP']=3*(out['H']+out['BB'])/out['OUTS']
    return out,True,trace
def fit_freshness(records,origin):
    # Only earlier, eligible observed exposure outcomes enter this fit.
    if origin>2026:raise ValueError('Freeze workload coefficients through 2025')
    out={}
    for role in FIELDS:
        rr=[r for r in records if r['season']<origin and r['role']==role and r['actual_exposure'] is not None]
        sums=defaultdict(lambda:[0.,0.,0])
        for r in rr:
            s=sums[r['context']['group']];s[0]+=r['actual_exposure'];s[1]+=r['baseline'][exposure(role)];s[2]+=1
        out[role]={}
        for group,(y,b,n) in sums.items():
            # Shrink toward unchanged workload, avoiding an all-pool discount.
            prior=50*(b/n)
            out[role][group]=dict(multiplier=min(1.,max(0.,(y+prior)/(b+prior))) if b else 1.,
                n=n,origin=origin,max_label_year=max(r['season'] for r in rr))
    return out
def workload_candidate(b,ctx,role,model):
    fit=model.get(role,{}).get(ctx['group']);factor=fit['multiplier'] if fit else 1.
    c=dict(b)
    if role=='hitter':
        for m in FIELDS[role]:
            if m not in ('AVG','OBP','SLG','OPS') and c.get(m) is not None:c[m]*=factor
    else:
        for m in ('OUTS','IP','H','ER','BB','SO','HR','W','GS','G'):
            if c.get(m) is not None:c[m]*=factor
        # Saves/holds are frozen anchors; a new starts/QS relationship is not inferred.
        c['QS']=None
    return c,bool(fit),factor
def rate(role,m,v):
    if m.endswith('_PER_OUTS'):
        n=v.get(m.removesuffix('_PER_OUTS'));d=v.get('OUTS')
        return n/d if n is not None and d and d>0 else None
    return v.get(m)
def observe(actual,target,role,pid,metrics):
    v={m:actual.get((target,role,pid,m)) for m in FIELDS[role]}
    return {m:rate(role,m,v) for m in metrics}
def score_records(records):
    bins=defaultdict(list)
    for r in records:
        role=r['role'];ctx=r['context'];target=r['season']
        metrics=RATES[role]+(('H','HR','R','RBI','SB') if role=='hitter' else ('SO','ER','BB','H','HR','W'))
        for m in metrics:
            y=r['truth'].get(m)
            pred=[rate(role,m,r[a]) for a in ('baseline','skill')]
            if y is None or any(v is None for v in pred):continue
            for cohort in ('ALL',ctx['history'],r.get('sample_cohort','UNKNOWN_SAMPLE'),r.get('actual_band','UNKNOWN_ACTUAL_EXPOSURE')):
                bins[target,role,'SKILL',m,cohort,'SUPPORTED' if r['skill_supported'] else 'FALLBACK'].append((r['pid'],tuple(p-y for p in pred)))
        y=r['actual_exposure']
        if y is None:continue
        scale=3 if role=='pitcher' else 1
        errors=tuple((r[a][exposure(role)]-y)/scale for a in ('baseline','workload'))
        state='APPEARED' if r['target_g'] is not None and r['target_g']>0 or y>0 else 'CONFIRMED_NO_APPEARANCE' if r['target_g']==0 and y==0 else 'ZERO_EXPOSURE_STATUS_UNKNOWN'
        for cohort in ('ALL',ctx['history'],ctx['freshness'],ctx['prior_role'],ctx['returner'],state):
            bins[target,role,'WORKLOAD','IP' if role=='pitcher' else 'PA',cohort,'SUPPORTED' if r['workload_supported'] else 'FALLBACK'].append((r['pid'],errors))
        # Counting-category diagnostics use eligible targets only. Certified zero
        # OUTS does not manufacture missing SO/W/etc labels.
        for m in (('HR','R','RBI','SB') if role=='hitter' else ('SO','W')):
            y=r['truth'].get(m)
            pp=[r[a].get(m) for a in ('baseline','workload')]
            if y is None or any(v is None for v in pp):continue
            ee=tuple(v-y for v in pp)
            for cohort in ('ALL',ctx['history'],ctx['freshness'],ctx['prior_role'],ctx['returner'],state):
                bins[target,role,'WORKLOAD',m,cohort,'SUPPORTED' if r['workload_supported'] else 'FALLBACK'].append((r['pid'],ee))
    rows=[]
    for (year,role,experiment,m,cohort,pool),rr in sorted(bins.items()):
        for i,method in enumerate(('weighted_actuals','skill_regression' if experiment=='SKILL' else 'freshness_workload')):
            errors=[v[i] for _,v in rr];n=len(rr)
            rows.append(dict(season=year,role=role,experiment=experiment,metric=m,cohort=cohort,pool=pool,
                method=method,n=n,membership_sha256=keyhash([pid for pid,_ in rr]),
                mse=sum(e*e for e in errors)/n,rmse=math.sqrt(sum(e*e for e in errors)/n),
                mae=sum(abs(e) for e in errors)/n,bias=sum(errors)/n))
    return rows
def gate(scores,role,experiment,origin):
    if origin>2026:raise ValueError('Selection may not use 2026 outcomes')
    metrics=RATES[role] if experiment=='SKILL' else ('IP' if role=='pitcher' else 'PA',)
    selected=[r for r in scores if r['season']<origin and r['role']==role and r['experiment']==experiment and r['pool']=='SUPPORTED']
    bank={(r['season'],r['metric'],r['cohort'],r['method']):r for r in selected}
    candidate='skill_regression' if experiment=='SKILL' else 'freshness_workload'
    years=sorted({r['season'] for r in selected if r['cohort']=='ALL'})
    reason=[];ratios=[]
    if len(years)<3:reason.append('INSUFFICIENT_EARLIER_FOLDS')
    for year in years:
        for m in metrics:
            a=bank.get((year,m,'ALL',candidate));b=bank.get((year,m,'ALL','weighted_actuals'))
            if not a or not b or a['n']<30 or b['mse']<=0:reason.append('UNSUPPORTED_FOLD');continue
            if a['membership_sha256']!=b['membership_sha256']:raise ValueError('Pool mismatch')
            ratios.append((year,m,a['mse']/b['mse']))
    if not ratios or sum(z for _,_,z in ratios)/len(ratios)>.99:reason.append('NO_ONE_PERCENT_MSE_IMPROVEMENT')
    for m in metrics:
        z=[v for _,metric,v in ratios if metric==m]
        if not z or sum(z)/len(z)>1.02:reason.append('METRIC_REGRESSION_'+m)
    # Coherent-count safeguards use the same supported memberships.
    if experiment=='SKILL':
        counts=('H','HR') if role=='hitter' else ('SO','ER','BB','H','HR')
        for m in counts:
            z=[]
            for y in years:
                a=bank.get((y,m,'ALL',candidate));b=bank.get((y,m,'ALL','weighted_actuals'))
                if a and b and a['n']>=30 and b['mse']>0:z.append(a['mse']/b['mse'])
            if not z or sum(z)/len(z)>1.02:reason.append('COUNT_GUARD_'+m)
    recent=years[-2:]
    z=[v for y,_,v in ratios if y in recent]
    if len(recent)<2 or not z:reason.append('RECENT_GUARD')
    for year in recent:
        yy=[v for y,_,v in ratios if y==year]
        if not yy or sum(yy)/len(yy)>1.02:reason.append('RECENT_GUARD_'+str(year))
    # A low-history guard must have support; it is never silently waived.
    low=[]
    for y in years:
        for m in metrics:
            a=bank.get((y,m,'LOW_HISTORY',candidate));b=bank.get((y,m,'LOW_HISTORY','weighted_actuals'))
            if a and b and a['n']>=15 and b['mse']>0:low.append(a['mse']/b['mse'])
    if not low or sum(low)/len(low)>1.02:reason.append('LOW_HISTORY_GUARD')
    return dict(origin=origin,role=role,experiment=experiment,eligible=not reason,reasons=sorted(set(reason)),
        selected_for_research=candidate if not reason else 'weighted_actuals',years=years,
        mean_mse_ratio=sum(z for _,_,z in ratios)/len(ratios) if ratios else None,
        default_changed=False)
def develop(actual):
    records=[];gates=[];priors={};models={}
    for target in HISTORICAL:
        print(f'{target}: earlier-only population rates and workload fit; experiments separate',flush=True)
        bank=population(actual,target);wm=fit_freshness(records,target)
        priors[str(target)]=bank;models[str(target)]=wm
        # Choices are evaluated on completed earlier origins only.
        earlier_scores=score_records(records)
        gates.extend(gate(earlier_scores,role,exp,target) for role in FIELDS for exp in ('SKILL','WORKLOAD'))
        for role in FIELDS:
            for pid in ids_before(actual,role,target):
                b=project(actual,role,pid,target)
                if b is None:continue
                ctx=context(actual,role,pid,target);c,supported,trace=skill_candidate(b,actual,role,pid,target,bank)
                wc,ws,factor=workload_candidate(b,ctx,role,wm)
                metrics=RATES[role]+(('H','HR','R','RBI','SB') if role=='hitter' else ('SO','ER','BB','H','HR','W'))
                minimum_sample=min((r['raw_denominator'] for r in trace),default=0)
                sample_cohort='LOW_SAMPLE' if minimum_sample<(200 if role=='hitter' else 300) else 'ESTABLISHED_SAMPLE'
                observed=actual.get((target,role,pid,exposure(role)))
                actual_band=('UNKNOWN_ACTUAL_EXPOSURE' if observed is None else
                    'ACTUAL_LOW_EXPOSURE' if observed<(200 if role=='hitter' else 60) else
                    'ACTUAL_MID_EXPOSURE' if observed<(450 if role=='hitter' else 300) else 'ACTUAL_HIGH_EXPOSURE')
                records.append(dict(season=target,role=role,pid=pid,context=ctx,baseline=b,skill=c,workload=wc,
                    skill_supported=supported,sample_cohort=sample_cohort,actual_band=actual_band,workload_supported=ws,workload_factor=factor,
                    truth=observe(actual,target,role,pid,metrics),
                    actual_exposure=actual.get((target,role,pid,exposure(role))),
                    target_g=actual.get((target,role,pid,'G'))))
    scores=score_records(records)
    final=[gate(scores,role,exp,2026) for role in FIELDS for exp in ('SKILL','WORKLOAD')]
    return records,scores,gates,final,population(actual,2026),fit_freshness(records,2026),priors,models

def verify_vector(v,role):
    issues=[]
    for m in FIELDS[role]:
        x=v.get(m)
        if x is None:issues.append('MISSING_'+m)
        elif not finite(x) or x<0:raise ValueError('Invalid projection '+m)
    def eq(m,deps,fn):
        expected=fn() if all(v.get(d) is not None for d in deps) else None
        x=v.get(m)
        if (x is None)!=(expected is None) or x is not None and not math.isclose(x,expected,rel_tol=1e-8,abs_tol=1e-8):
            raise ValueError('Coherence failure '+m)
    if role=='hitter':
        eq('H',('1B','2B','3B','HR'),lambda:sum(v[m] for m in ('1B','2B','3B','HR')))
        eq('AVG',('H','AB'),lambda:v['H']/v['AB'] if v['AB'] else None)
        eq('SLG',('1B','2B','3B','HR','AB'),lambda:sum(i*v[m] for i,m in enumerate(('1B','2B','3B','HR'),1))/v['AB'] if v['AB'] else None)
        eq('OBP',('H','BB','HBP','AB','SF'),lambda:(v['H']+v['BB']+v['HBP'])/(v['AB']+v['BB']+v['HBP']+v['SF']) if v['AB']+v['BB']+v['HBP']+v['SF'] else None)
        eq('OPS',('OBP','SLG'),lambda:v['OBP']+v['SLG'])
        if v.get('H') is not None and v.get('AB') is not None and v['H']>v['AB']+1e-8:raise ValueError('Hits exceed AB')
        if all(v.get(m) is not None for m in ('PA','AB','BB','HBP','SF','SH')) and sum(v[m] for m in ('AB','BB','HBP','SF','SH'))>v['PA']+1e-8:raise ValueError('PA bound')
    else:
        eq('OUTS',('IP',),lambda:v['IP']*3)
        eq('ERA',('ER','IP'),lambda:9*v['ER']/v['IP'] if v['IP'] else None)
        eq('WHIP',('H','BB','IP'),lambda:(v['H']+v['BB'])/v['IP'] if v['IP'] else None)
        eq('SV_plus_HLD',('SV','HLD'),lambda:v['SV']+v['HLD'])
        if v.get('GS') is not None and v.get('G') is not None and v['GS']>v['G']+1e-8:raise ValueError('GS exceeds G')
        if v.get('QS') is not None and v.get('GS') is not None and v['QS']>v['GS']+1e-8:raise ValueError('QS exceeds GS')
    return issues

def run(a):
    from standalone_io_v1_0 import load,dump,start,finish
    from recent_skill_core_v1_23 import checked,emit
    from recent_skill_inputs_v1_23 import labels
    from participation_label_overlay_v1_27 import apply_overlay
    roots=[Path(getattr(a,k)).resolve() for k in ('audit','review','baseline','labels','overlay','research','evaluation')]
    audit,review,base,lab,ov,research,ev=roots;watch={}
    take=lambda root,n:checked(root,n,watch)
    ar=load(take(audit,'report.json'));br=load(take(base,'report.json'))
    if ar['version']!='1.41.0' or ar['baseline_numeric_replay_verified'] is not True or br['version']!='1.31.0':
        raise ValueError('Require verified v1.41 and frozen v1.31')
    ab=load(take(audit,'input_hashes.json'));bb=load(take(base,'input_hashes.json'))
    def bound(p,bank):
        if watch[str(p)] not in {v for k,v in bank.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==p.name}:
            raise ValueError('Source binding differs: '+p.name)
    bound(base/'report.json',ab)
    train=take(lab,'training_labels.parquet');hp=take(research,'historical_forecasts.csv')
    historical,_=apply_overlay(ov,labels(train),train,hp,watch)
    for p in (train,hp,ov/'report.json',ov/'participation_label_overlay.csv'):bound(p,bb);bound(p,ab)
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        # Development accesses only historical labels. All coefficients and decisions
        # are written before the first 2026 actual label file is opened.
        dump(stage/'experiment_contract.json',CONTRACT)
        records,scores,gates,final,bank,wm,priors,models=develop(historical)
        emit(stage/'historical_scores.csv',scores)
        emit(stage/'rolling_research_choices.csv',gates)
        frozen=dict(selection_max_year=2025,skill_population_origin=2026,skill_population=bank,
            workload_model=wm,final_historical_gates=final,automatic_promotion=False,
            defaults=dict(skill='weighted_actuals',workload='accepted_ip'))
        dump(stage/'frozen_choices.json',frozen)
        coverage=[]
        for y in HISTORICAL:
            for role in FIELDS:
                rr=[r for r in records if r['season']==y and r['role']==role]
                coverage.append(dict(season=y,role=role,population=len(rr),
                    known_positive=sum(r['actual_exposure'] is not None and r['actual_exposure']>0 for r in rr),
                    known_zero_exposure=sum(r['actual_exposure']==0 for r in rr),
                    unknown_outcome=sum(r['actual_exposure'] is None for r in rr),
                    skill_supported=sum(r['skill_supported'] for r in rr),
                    freshness_supported=sum(r['workload_supported'] for r in rr)))
        emit(stage/'historical_label_coverage.csv',coverage)
        dump(stage/'historical_population_priors.json',priors)
        dump(stage/'historical_workload_models.json',models)
        emit(stage/'historical_player_predictions.csv',[
            dict(season=r['season'],player_type=r['role'],mlbam_id=r['pid'],**r['context'],
                 sample_cohort=r['sample_cohort'],actual_band=r['actual_band'],
                 actual_exposure=r['actual_exposure'],target_G=r['target_g'],
                 baseline_exposure=r['baseline'][exposure(r['role'])],
                 candidate_exposure=r['workload'][exposure(r['role'])],
                 workload_factor=r['workload_factor'],skill_supported=r['skill_supported'],
                 workload_supported=r['workload_supported'],
                 **{arm+'__'+m:v.get(m) for arm,v in [('baseline',r['baseline']),('skill',r['skill'])] for m in FIELDS[r['role']]})
            for r in records])
        # 2026 labels now serve ONLY as 2027 player history, never as scores or fits.
        hold=take(lab,'holdout_labels.parquet');bound(hold,bb);bound(hold,ab)
        actual=historical|labels(hold,2026)
        er=load(take(ev,'report.json'));bound(ev/'report.json',bb);bound(ev/'report.json',ab)
        if er['version']!='1.29.0' or er['season_certified'] is not True or er['complete_pool_scored'] is not True:
            raise ValueError('2026 certification required')
        ep=take(ev,'evaluation_label_overlay_2026.csv');bound(ep,bb);bound(ep,ab)
        seen=set()
        for r in read(ep):
            pid=r['mlbam_id']
            if r['season']!='2026' or pid in seen:raise ValueError('Invalid 2026 overlay')
            seen.add(pid)
            if r['status'] not in ('VERIFIED_APPEARED','VERIFIED_NO_APPEARANCE'):raise ValueError('Unknown certification')
            g,o=int(r['evaluation_g']),int(r['evaluation_outs'])
            if o<0 or g<0 or (r['status']=='VERIFIED_APPEARED' and g<=0) or (r['status']=='VERIFIED_NO_APPEARANCE' and (g or o)):raise ValueError('Invalid certification counts')
            for m,v in [('G',g),('OUTS',o)]:
                k=2026,'pitcher',pid,m
                if actual.get(k,v)!=v:raise ValueError('2026 label conflict')
                actual[k]=v
        if len(seen)!=er['preseason_pool']:raise ValueError('Incomplete certified pool')
        releases={};traces=[];exceptions=[];checks=Counter()
        for role in FIELDS:
            p=take(review,f'named_2027_{role}s.csv');bound(p,ab)
            raw=read(p);released=[];candidates=[]
            seen=set()
            for row in raw:
                pid=row['mlbam_id']
                if row['season']!='2027' or row['player_type']!=role or pid in seen:raise ValueError('Invalid release population')
                seen.add(pid)
                b={m:num(row['weighted_actuals__'+m]) for m in FIELDS[role]}
                replay=project(actual,role,pid,2027)
                if replay is None:raise ValueError('Baseline replay missing')
                for m in FIELDS[role]:
                    x,y=b[m],replay[m]
                    if (x is None)!=(y is None) or x is not None and not math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-9):raise ValueError('Release baseline mismatch')
                b.update(season=2027,player_type=role,mlbam_id=pid)
                ctx=context(actual,role,pid,2027)
                sc,supported,trace=skill_candidate(b,actual,role,pid,2027,bank)
                wc,ws,factor=workload_candidate(b,ctx,role,wm)
                issues=verify_vector(b,role)
                verify_vector(sc,role)
                # Zero-workload rates are undefined; preserve them as null in candidate only.
                if role=='pitcher' and not wc['IP']:wc['ERA']=None;wc['WHIP']=None
                verify_vector(wc,role)
                meta=dict(season=2027,player_type=role,mlbam_id=pid,name=row.get('name',''),
                    projection_source='HOMEGROWN_WEIGHTED_BASELINE_V1_42',skill_method='weighted_actuals',
                    workload_method='accepted_ip',hybrid_qs=None,valuation_enabled=False,
                    feature_vintage=row.get('feature_vintage',''),**ctx)
                if not meta['name']:issues.append('UNRESOLVED_NAME')
                if ctx['freshness']!='RECENT_POSITIVE':issues.append('NO_RECENT_POSITIVE_EXPOSURE')
                if ctx['history']=='LOW_HISTORY':issues.append('LOW_HISTORY')
                if ctx['recorded_exposure']<(200 if role=='hitter' else 150):issues.append('LOW_RECORDED_EXPOSURE')
                if not supported:issues.append('UNSUPPORTED_SKILL_CANDIDATE')
                if not ws:issues.append('UNSUPPORTED_FRESHNESS_CANDIDATE')
                if role=='hitter' and not b.get('AB'):issues.append('NO_POSITIVE_AB')
                if role=='pitcher' and not b.get('IP'):issues.append('NO_POSITIVE_IP')
                if role=='hitter' and b.get('AVG') is not None and (b['AVG']<.15 or b['AVG']>.35):issues.append('EXTREME_BASELINE_AVG')
                if role=='pitcher' and b.get('ERA') is not None and (b['ERA']<1.5 or b['ERA']>7):issues.append('EXTREME_BASELINE_ERA')
                if role=='hitter' and b.get('OPS') is not None and (b['OPS']<.4 or b['OPS']>1.1):issues.append('EXTREME_BASELINE_OPS')
                if role=='pitcher' and b.get('WHIP') is not None and (b['WHIP']<.8 or b['WHIP']>1.8):issues.append('EXTREME_BASELINE_WHIP')
                checks[role,'ROWS_CHECKED']+=1
                if issues:checks[role,'WITH_EXCEPTIONS']+=1
                released.append(dict(meta,**{m:b[m] for m in FIELDS[role]},release_status='BASELINE_WITH_EXCEPTIONS' if issues else 'BASELINE_REVIEW_PASSED',exceptions=';'.join(issues)))
                candidates.append(dict(meta,skill_supported=supported,freshness_supported=ws,freshness_multiplier=factor,
                    **{arm+'__'+m:v.get(m) for arm,v in [('baseline',b),('skill_regression',sc),('freshness_workload',wc)] for m in FIELDS[role]}))
                traces.extend(dict(season=2027,player_type=role,mlbam_id=pid,**r) for r in trace)
                exceptions.extend(dict(meta,issue=i,projected_exposure=b[exposure(role)]/(3 if role=='pitcher' else 1)) for i in issues)
            if len(released)!=br['forecast_counts'][role]:raise ValueError('Release population differs')
            releases[role]=released
            emit(stage/f'default_2027_{role}s.csv',released)
            emit(stage/f'research_candidates_2027_{role}s.csv',candidates)
        emit(stage/'skill_regression_component_trace_2027.csv',traces)
        exceptions.sort(key=lambda r:(r['player_type'],-(r['projected_exposure'] or 0),int(r['mlbam_id']),r['issue']))
        emit(stage/'release_exceptions.csv',exceptions)
        result=dict(version='1.42.0',status='CORE_RESEARCH_RELEASE_WITH_EXCEPTIONS',
            historical_origins=list(HISTORICAL),historical_rows=len(records),models_fitted=True,
            final_historical_gates=final,default_skill='weighted_actuals',default_workload='accepted_ip',
            source_player_history_2027=[2023,2024,2025,2026],
            population_fit_max_year=2025,workload_fit_max_year=2025,
            selection_uses_2026=False,evaluation_scores_read=False,
            source_2026_actuals_read_as_2027_history=True,defaults_changed=False,
            valuation_enabled=False,hybrid_qs=None,
            forecast_counts={r:len(rr) for r,rr in releases.items()},
            release_checks=[dict(role=r,check=c,n=n) for (r,c),n in sorted(checks.items())],
            limitations=['Historical folds were previously inspected; not independent confirmation.',
                'Four trailing actual seasons reconstruct each historical baseline; not archived forecast vintages.',
                'Workload outcomes absent from eligible labels remain unknown; hitter nonparticipation coverage is incomplete.',
                'Research arms are separate; their combination has not been tested or promoted.',
                'Population coefficients freeze through 2025; 2026 enters only 2027 player history.',
                'Default release preserves weighted baseline, including flagged extreme rates; not draft-ready for every player.',
                'No prospect/minor/overseas or dated availability branch; no valuation wiring.',
                'Saves/holds are unchanged; workload-challenger QS is null.'])
        dump(stage/'release_report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in dict(audit='outputs/baseline_reliability_v1_41',review='outputs/projection_review_v1_40',
        baseline='outputs/homegrown_2027_v1_31',labels='outputs/training_labels_v1_0',
        overlay='outputs/participation_label_overlay_v1_27',research='outputs/recent_history_skills_v1_23',
        evaluation='outputs/pitcher_evaluation_v1_29',output='outputs/projection_phase_v1_42',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(json.dumps(run(p.parse_args()),indent=2))
