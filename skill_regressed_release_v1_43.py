"""Publish the frozen v1.42 skill arm; workload and opportunity anchors unchanged."""
import argparse
from collections import Counter,defaultdict
import hashlib,json,math
from pathlib import Path
import shutil
from project_2027_v1_31 import FIELDS,project,read,num
from projection_phase_v1_42 import CONTRACT,SKILL,RATES,ids_before,context,skill_candidate,verify_vector,rate
VERSION='1.43.0'
MUTABLE={'hitter':{'1B','2B','3B','HR','H','AVG','OBP','SLG','OPS'},
         'pitcher':{'H','ER','BB','SO','HR','ERA','WHIP'}}
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def same(x,y):
    return (x is None and y is None) or (x is not None and y is not None and math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-10))
def decision(report,frozen,contract):
    if report['version']!='1.42.0' or report['selection_uses_2026'] is not False or report['defaults_changed'] is not False or contract!=CONTRACT:
        raise ValueError('Unexpected research contract')
    if frozen['selection_max_year']!=2025 or frozen['skill_population_origin']!=2026:
        raise ValueError('Frozen coefficients exceed approved history')
    if report['final_historical_gates']!=frozen['final_historical_gates']:
        raise ValueError('Gate evidence differs')
    for role in FIELDS:
        rr=[g for g in frozen['final_historical_gates'] if g['role']==role and g['experiment']=='SKILL']
        if len(rr)!=1 or rr[0]['eligible'] is not True or rr[0]['selected_for_research']!='skill_regression' or rr[0]['origin']!=2026:
            raise ValueError('Both skill bundles must pass historical gates')
    bank=frozen['skill_population']
    for role in FIELDS:
        for m in SKILL[role]:
            d=bank[role][m]
            if d['rate'] is not None and (not math.isfinite(d['rate']) or d['rate']<0 or d['denominator']<10000 or not same(d['rate'],d['numerator']/d['denominator'])):
                raise ValueError('Invalid frozen prior')
    return bank
def publish_rows(baselines,candidates,role):
    found={};exceptions=[];changes=[];anchors=[];out=[]
    for r in candidates:
        pid=r['mlbam_id']
        if pid in found:raise ValueError('Duplicate candidate')
        found[pid]=r
    seen=set()
    for r in baselines:
        pid=r['mlbam_id']
        if pid in seen or r['season']!='2027' or r['player_type']!=role or pid not in found:
            raise ValueError('Invalid baseline population')
        seen.add(pid);c=found[pid]
        if c['season']!='2027' or c['player_type']!=role or c['skill_supported'] not in ('True','False'):
            raise ValueError('Invalid candidate population')
        supported=c['skill_supported']=='True'
        b={m:num(r[m]) for m in FIELDS[role]}
        v={m:num(c['skill_regression__'+m]) for m in FIELDS[role]}
        for m in FIELDS[role]:
            if not same(num(c['baseline__'+m]),b[m]):raise ValueError('Candidate baseline mismatch')
            if (m not in MUTABLE[role] or not supported) and v[m]!=b[m]:
                raise ValueError('Frozen anchor/fallback changed: '+m)
            changes.append(dict(player_type=role,mlbam_id=pid,name=r.get('name',''),metric=m,
                baseline=b[m],released=v[m],delta=v[m]-b[m] if None not in (v[m],b[m]) else None,
                skill_supported=supported))
        issues=verify_vector(v,role)
        inherited=[x for x in r.get('exceptions','').split(';') if x and not x.startswith(('MISSING_','EXTREME_BASELINE_')) and x not in ('UNSUPPORTED_SKILL_CANDIDATE','UNSUPPORTED_FRESHNESS_CANDIDATE')]
        issues+=inherited
        if not supported:issues.append('BASELINE_FALLBACK_UNSUPPORTED_SKILL')
        for m,lo,hi in (('AVG',.15,.35),('OPS',.4,1.1)) if role=='hitter' else (('ERA',1.5,7.),('WHIP',.8,1.8)):
            if v.get(m) is not None and not lo<=v[m]<=hi:issues.append('EXTREME_RELEASE_'+m)
        issues=sorted(set(issues))
        metadata={k:val for k,val in r.items() if k not in FIELDS[role]}
        metadata.update(projection_source='HOMEGROWN_SKILL_REGRESSED_V1_43',
            skill_method='skill_regression' if supported else 'weighted_actuals_fallback',
            workload_method='accepted_ip',hybrid_qs=None,valuation_enabled=False,
            release_status='RELEASE_WITH_EXCEPTIONS' if issues else 'COHERENCE_CHECK_PASSED',
            exceptions=';'.join(issues),source_release='v1.42.0')
        out.append(dict(metadata,**v))
        exceptions.extend(dict(player_type=role,mlbam_id=pid,name=r.get('name',''),issue=i,
            projected_exposure=v['PA'] if role=='hitter' else v['IP']) for i in issues)
        if role=='pitcher':
            anchors.append(dict(mlbam_id=pid,name=r.get('name',''),
                **{m:b[m] for m in ('IP','OUTS','W','SV','HLD','SV_plus_HLD','G','GS','QS')}))
    if set(found)!=seen:raise ValueError('Candidate population differs')
    return out,exceptions,changes,anchors

def evaluation_forecasts(historical,bank):
    if any(k[0]>=2026 for k in historical):raise ValueError('Future player history in 2026 forecast')
    rows=[]
    for role in FIELDS:
        for pid in ids_before(historical,role,2026):
            b=project(historical,role,pid,2026)
            c,supported,trace=skill_candidate(b,historical,role,pid,2026,bank)
            verify_vector(b,role);verify_vector(c,role)
            for m in FIELDS[role]:
                if m not in MUTABLE[role] and not same(b[m],c[m]):raise ValueError('2026 anchor changed')
            ctx=context(historical,role,pid,2026)
            rows.append(dict(season=2026,player_type=role,mlbam_id=pid,skill_supported=supported,
                sample_cohort='LOW_SAMPLE' if min(t['raw_denominator'] for t in trace)<(200 if role=='hitter' else 300) else 'ESTABLISHED_SAMPLE',
                **ctx,**{'baseline__'+m:b.get(m) for m in FIELDS[role]},
                **{'release__'+m:c.get(m) for m in FIELDS[role]},hybrid_qs=None))
    return rows

def build(a):
    from standalone_io_v1_0 import load,dump,start,finish
    from recent_skill_core_v1_23 import checked,emit
    from recent_skill_inputs_v1_23 import labels
    from participation_label_overlay_v1_27 import apply_overlay
    phase,lab,ov,research=[Path(getattr(a,k)).resolve() for k in ('phase','labels','overlay','research')]
    roots=[phase,lab,ov,research];watch={}
    take=lambda root,n:checked(root,n,watch)
    report=load(take(phase,'release_report.json'))
    frozen=load(take(phase,'frozen_choices.json'));contract=load(take(phase,'experiment_contract.json'))
    bank=decision(report,frozen,contract)
    bindings=load(take(phase,'input_hashes.json'))
    def bound(p):
        if watch[str(p)] not in {v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==p.name}:raise ValueError('Phase source binding differs: '+p.name)
    train=take(lab,'training_labels.parquet');hp=take(research,'historical_forecasts.csv')
    historical,_=apply_overlay(ov,labels(train),train,hp,watch)
    for p in (train,hp,ov/'report.json',ov/'participation_label_overlay.csv'):bound(p)
    evalrows=evaluation_forecasts(historical,bank)
    if not evalrows:raise ValueError('Empty 2026 forecast population')
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        refs=stage/'references';refs.mkdir()
        shutil.copyfile(take(phase,'frozen_choices.json'),refs/'v1_42_frozen_choices.json')
        shutil.copyfile(take(phase,'input_hashes.json'),refs/'v1_42_source_bindings.json')
        exceptions=[];changes=[];counts={};support={}
        for role in FIELDS:
            bp=take(phase,f'default_2027_{role}s.csv')
            cp=take(phase,f'research_candidates_2027_{role}s.csv')
            rows,ee,cc,aa=publish_rows(read(bp),read(cp),role)
            if len(rows)!=report['forecast_counts'][role]:raise ValueError('Release count differs')
            emit(stage/f'projections_2027_{role}s.csv',rows)
            shutil.copyfile(bp,refs/f'original_baseline_2027_{role}s.csv')
            # Keep workload research separate and clearly inactive.
            workload=[dict(player_type=r['player_type'],mlbam_id=r['mlbam_id'],name=r.get('name',''),
                active=False,hybrid_qs=None,**{m:num(r['freshness_workload__'+m]) for m in FIELDS[role]}) for r in read(cp)]
            emit(refs/f'inactive_workload_challenger_2027_{role}s.csv',workload)
            if aa:emit(refs/'unchanged_pitcher_workload_saves_holds.csv',aa)
            exceptions+=ee;changes+=cc;counts[role]=len(rows)
            support[role]=Counter(r['skill_method'] for r in rows)
        exceptions.sort(key=lambda r:(r['player_type'],-(r['projected_exposure'] or 0),int(r['mlbam_id']),r['issue']))
        emit(stage/'release_exceptions.csv',exceptions)
        emit(stage/'baseline_to_release_changes.csv',changes)
        emit(stage/'frozen_2026_forecasts.csv',evalrows)
        freeze=dict(version=VERSION,source_phase_version='1.42.0',skill='skill_regression',
            workload='accepted_ip',saves_holds='FROZEN_BASELINE',hybrid_qs=None,valuation_enabled=False,
            historical_selection_max_year=2025,models_refitted=False,choices_changed_by_2026=False,
            forecast_2026_sha256=digest(stage/'frozen_2026_forecasts.csv'),
            projections_2027_sha256={r:digest(stage/f'projections_2027_{r}s.csv') for r in FIELDS})
        dump(stage/'publication_freeze.json',freeze)
        result=dict(version=VERSION,status='SKILL_REGRESSED_RELEASE_WITH_EXCEPTIONS',
            forecast_counts=counts,skill_support={r:dict(n) for r,n in support.items()},
            exception_rows=len(exceptions),models_refitted=False,feature_search_performed=False,
            source_phase_unchanged=True,workload_unchanged=True,saves_holds_unchanged=True,
            hybrid_qs=None,valuation_enabled=False,evaluation_outcomes_read=False,
            selection_uses_2026=False,forecast_2026_population=len(evalrows),
            limitations=['Historical gates and prior cohorts were previously reviewed; not independent confirmation.',
              '2027 projections are published from frozen v1.42 candidate values, not re-fitted.',
              '2026 forecasts use 2022–2025 player history and the same frozen population priors through 2025.',
              '2027 player history remains 2023–2026; population coefficients still freeze through 2025.',
              'Unsupported skill groups fall back to the entire baseline group; missing values stay missing.',
              'Coherence and source checks do not certify participation, coverage, injuries or draft readiness.',
              'Workload research is inactive; no prospect/minor/overseas branch or valuation wiring.'])
        dump(stage/'release_report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():shutil.rmtree(stage)

def score_evaluation(rows,actual):
    metrics={'hitter':tuple(dict.fromkeys(FIELDS['hitter']+RATES['hitter'])),
             'pitcher':tuple(dict.fromkeys(FIELDS['pitcher']+RATES['pitcher']))}
    bins=defaultdict(list);details=[];coverage=Counter()
    seen=set()
    for r in rows:
        role,pid=r['player_type'],r['mlbam_id'];k=role,pid
        if k in seen or r['season']!='2026':raise ValueError('Invalid frozen evaluation population')
        seen.add(k)
        truth={m:actual.get((2026,role,pid,m)) for m in FIELDS[role]}
        if role=='pitcher' and truth['OUTS'] is not None:truth['IP']=truth['OUTS']/3
        den=truth['PA' if role=='hitter' else 'OUTS']
        positive=den is not None and den>0
        band=('ACTUAL_EXPOSURE_UNKNOWN' if den is None else
            'ACTUAL_PA_LT200' if role=='hitter' and den<200 else
            'ACTUAL_PA_200_LT450' if role=='hitter' and den<450 else
            'ACTUAL_PA_GE450' if role=='hitter' else
            'ACTUAL_IP_LT20' if den<60 else 'ACTUAL_IP_20_LT100' if den<300 else 'ACTUAL_IP_GE100')
        g=truth.get('G')
        appearance='KNOWN_APPEARED' if g is not None and g>0 or positive else 'CONFIRMED_NO_APPEARANCE' if role=='pitcher' and g==0 and den==0 else 'PARTICIPATION_UNKNOWN'
        coverage[role,appearance]+=1
        for m in metrics[role]:
            y=rate(role,m,truth)
            if m in ('AVG','OBP','SLG','OPS','ERA','WHIP','SO_PER_OUTS','HR_PER_OUTS'):
                required=truth.get('AB') if role=='hitter' else truth.get('OUTS')
                if required is None or required<=0:continue
            b=num(r.get('baseline__'+m)) if not m.endswith('_PER_OUTS') else rate(role,m,{d:num(r.get('baseline__'+d)) for d in FIELDS[role]})
            c=num(r.get('release__'+m)) if not m.endswith('_PER_OUTS') else rate(role,m,{d:num(r.get('release__'+d)) for d in FIELDS[role]})
            if y is None or b is None or c is None:continue
            pool='SUPPORTED' if r['skill_supported']=='True' else 'BASELINE_FALLBACK'
            details.append(dict(player_type=role,mlbam_id=pid,metric=m,actual=y,baseline=b,released=c,
                baseline_error=b-y,release_error=c-y,pool=pool,actual_exposure_band=band,
                participation=appearance))
            for cohort in ('ALL',r['history'],r['sample_cohort'],band,appearance):
                for p in ('MATCHED_ALL',pool):
                    bins[role,m,cohort,p].append((pid,b-y,c-y))
    scores=[]
    for (role,m,cohort,pool),rr in sorted(bins.items()):
        h=hashlib.sha256(json.dumps(sorted(pid for pid,_,_ in rr)).encode()).hexdigest();n=len(rr)
        for j,method in ((1,'weighted_actuals'),(2,'skill_regressed_release')):
            errors=[r[j] for r in rr]
            scores.append(dict(season=2026,player_type=role,metric=m,cohort=cohort,pool=pool,
                method=method,n=n,membership_sha256=h,mse=sum(e*e for e in errors)/n,
                rmse=math.sqrt(sum(e*e for e in errors)/n),mae=sum(abs(e) for e in errors)/n,bias=sum(errors)/n))
    return scores,details,[dict(player_type=r,participation=p,n=n) for (r,p),n in sorted(coverage.items())]

def evaluate(a):
    from standalone_io_v1_0 import load,dump,start,finish
    from recent_skill_core_v1_23 import checked,emit
    from recent_skill_inputs_v1_23 import labels
    pub,lab,ev=[Path(getattr(a,k)).resolve() for k in ('release','labels','evaluation')]
    roots=[pub,lab,ev];watch={}
    take=lambda root,n:checked(root,n,watch)
    report=load(take(pub,'release_report.json'));freeze=load(take(pub,'publication_freeze.json'))
    if report['version']!=VERSION or report['models_refitted'] is not False or report['selection_uses_2026'] is not False:
        raise ValueError('Unexpected publication')
    if freeze['historical_selection_max_year']!=2025 or freeze['workload']!='accepted_ip' or freeze['skill']!='skill_regression':
        raise ValueError('Publication choices differ')
    fp=take(pub,'frozen_2026_forecasts.csv')
    if digest(fp)!=freeze['forecast_2026_sha256']:raise ValueError('Frozen forecast changed')
    for role,h in freeze['projections_2027_sha256'].items():
        if digest(take(pub,f'projections_2027_{role}s.csv'))!=h:raise ValueError('2027 export changed')
    bindings=load(take(pub,'references/v1_42_source_bindings.json'))
    def bound(p):
        if watch[str(p)] not in {v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==p.name}:raise ValueError('Evaluation source differs: '+p.name)
    # All publication checks complete before any 2026 outcome file is opened.
    hold=take(lab,'holdout_labels.parquet');bound(hold)
    actual=labels(hold,2026)
    ep=take(ev,'report.json');bound(ep);er=load(ep)
    if er['version']!='1.29.0' or er['season_certified'] is not True or er['complete_pool_scored'] is not True:
        raise ValueError('Certified 2026 source required')
    cp=take(ev,'evaluation_label_overlay_2026.csv');bound(cp)
    seen=set()
    for r in read(cp):
        pid=r['mlbam_id']
        if r['season']!='2026' or pid in seen:raise ValueError('Bad overlay identity')
        seen.add(pid);g,o=int(r['evaluation_g']),int(r['evaluation_outs'])
        if r['status'] not in ('VERIFIED_APPEARED','VERIFIED_NO_APPEARANCE') or g<0 or o<0:
            raise ValueError('Invalid overlay')
        if r['status']=='VERIFIED_APPEARED' and not g:raise ValueError('Invalid positive appearance')
        if r['status']=='VERIFIED_NO_APPEARANCE' and (g or o):raise ValueError('Invalid certified zero')
        for m,v in [('G',g),('OUTS',o)]:
            k=2026,'pitcher',pid,m
            if actual.get(k,v)!=v:raise ValueError('Overlay/label conflict')
            actual[k]=v
    if len(seen)!=er['preseason_pool']:raise ValueError('Incomplete certified source')
    scores,details,coverage=score_evaluation(read(fp),actual)
    if not scores:raise ValueError('No eligible evaluation rows')
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        emit(stage/'evaluation_2026_scores.csv',scores)
        emit(stage/'evaluation_2026_player_comparisons.csv',details)
        emit(stage/'evaluation_2026_participation_coverage.csv',coverage)
        paired=defaultdict(dict)
        for r in scores:paired[r['player_type'],r['metric'],r['cohort'],r['pool']][r['method']]=r
        delta=[]
        for (role,m,cohort,pool),rr in sorted(paired.items()):
            b,c=rr['weighted_actuals'],rr['skill_regressed_release']
            if (b['n'],b['membership_sha256'])!=(c['n'],c['membership_sha256']):raise ValueError('Unequal matched evaluation pools')
            delta.append(dict(player_type=role,metric=m,cohort=cohort,pool=pool,n=b['n'],
                membership_sha256=b['membership_sha256'],delta_rmse=c['rmse']-b['rmse'],
                delta_mae=c['mae']-b['mae'],mse_ratio=c['mse']/b['mse'] if b['mse'] else None))
        emit(stage/'evaluation_2026_deltas.csv',delta)
        result=dict(version=VERSION,status='PREVIOUSLY_REVIEWED_2026_REPORTING_ONLY',
            models_fitted=False,choices_changed=False,forecasts_changed=False,
            selection_uses_2026=False,publication_freeze_sha256=digest(pub/'publication_freeze.json'),
            score_rows=len(scores),player_metric_rows=len(details),valuation_enabled=False,
            limitations=['2026 was repeatedly reviewed; this is not independent confirmation.',
                'No metric, coefficient, prior strength, fallback or source is retuned.',
                'Population priors freeze through 2025; 2026 forecast history is 2022–2025.',
                'Missing eligible outcomes stay unknown; only G/OUTS receive certified pitcher zeros.',
                'Rate comparisons require positive actual AB/OUTS; exposure cohorts are diagnosis only.',
                'Count pools can differ by metric; absent SO/W/etc are not manufactured from non-appearance.',
                'No changes to published 2027 projections or workload research.'])
        dump(stage/'evaluation_report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,watch))
    finally:
        if stage.exists():shutil.rmtree(stage)

def parser():
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in dict(phase='outputs/projection_phase_v1_42',labels='outputs/training_labels_v1_0',
        overlay='outputs/participation_label_overlay_v1_27',research='outputs/recent_history_skills_v1_23',
        output='outputs/skill_regressed_release_v1_43',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
