"""Freeze choices, generate an actuals-only 2027 prototype, and audit benchmarks."""
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil

YEARS=(2023,2024,2025,2026)
WEIGHTS=(1,2,3,4)
FIELDS={
    'hitter': ('PA','AB','H','1B','2B','3B','HR','R','RBI','SB','BB','HBP','SF','SH','AVG','OBP','SLG','OPS'),
    'pitcher': ('OUTS','IP','H','ER','BB','SO','HR','W','SV','HLD','QS','ERA','WHIP','GS','G','SV_plus_HLD'),
}
FILES={
    (s,r):f'2027{f}{r}s111326.csv' for s,f in [('steamer','steamer'),('depth_charts','fgdepthcharts')]
    for r in FIELDS
}
LARGE={'PA':100,'HR':8,'SB':8,'AVG':.025,'OPS':.08,'IP':35,'SO':35,'W':4,'QS':5,'ERA':.75,'WHIP':.15}


def read(path):
    with path.open(encoding='utf-8-sig',newline='') as f:
        return list(csv.DictReader(f))


def num(value):
    if value in (None,''):
        return None
    x=float(value)
    if not math.isfinite(x) or x<0:
        raise ValueError(f'Invalid nonnegative number: {value}')
    return x


def divide(a,b):
    return a/b if a is not None and b else None


def product(a,b):
    return a*b if a is not None and b is not None else None


def total(*v):
    return sum(v) if None not in v else None


def project(actual,role,pid,target=2027):
    years=range(target-4,target)
    get=lambda y,m: actual.get((y,role,pid,m))
    exposure='PA' if role=='hitter' else 'OUTS'
    history=[(y,w,get(y,exposure)) for y,w in zip(years,WEIGHTS)]
    known=[(y,w,e) for y,w,e in history if e is not None]
    if not any(e>0 for _,_,e in known):
        return None
    volume=sum(w*e for _,w,e in known)/sum(w for _,w,_ in known)
    def rate(m,denom=exposure):
        pairs=[(w,get(y,m),get(y,denom)) for y,w in zip(years,WEIGHTS)]
        pairs=[(w,n,d) for w,n,d in pairs if n is not None and d is not None and d>0]
        return divide(sum(w*n for w,n,d in pairs),sum(w*d for w,n,d in pairs))
    out=dict(season=target,player_type=role,mlbam_id=pid,
             exposure_history_years='|'.join(str(y) for y,_,_ in known),
             confirmed_zero_exposure_years='|'.join(str(y) for y,_,e in known if not e))
    if role=='hitter':
        v={m:product(volume,rate(m)) for m in ('AB','BB','HBP','SF','SH','R','RBI','SB')}
        pa_parts=('AB','BB','HBP','SF','SH')
        s=total(*(v[m] for m in pa_parts))
        if s is not None and s>volume:
            for m in pa_parts:
                v[m]*=volume/s
        for m in ('1B','2B','3B','HR'):
            v[m]=product(v['AB'],rate(m,'AB'))
        h=total(*(v[m] for m in ('1B','2B','3B','HR')))
        if h is not None and h>v['AB']:
            for m in ('1B','2B','3B','HR'):
                v[m]*=v['AB']/h
            h=v['AB']
        tb=total(*(product(v[m],i) for i,m in enumerate(('1B','2B','3B','HR'),1)))
        obp=divide(total(h,v['BB'],v['HBP']),total(v['AB'],v['BB'],v['HBP'],v['SF']))
        slg=divide(tb,v['AB'])
        return dict(out,**v,PA=volume,H=h,AVG=divide(h,v['AB']),OBP=obp,SLG=slg,OPS=total(obp,slg))
    v={m:product(volume,rate(m)) for m in ('H','ER','BB','SO','HR','W','SV','HLD','GS','G')}
    if v['H'] is not None and v['HR'] is not None:
        v['H']=max(v['H'],v['HR'])
    if v['G'] is not None and v['GS'] is not None:
        v['GS']=min(v['GS'],v['G'])
    qs=product(v['GS'],rate('QS','GS'))
    ip=volume/3
    return dict(out,**v,OUTS=volume,IP=ip,accepted_ip=ip,
                QS=0.0 if v['GS']==0 else min(qs,v['GS'],ip/6) if qs is not None else None,
                ERA=divide(product(v['ER'],9),ip),WHIP=divide(total(v['H'],v['BB']),ip),
                SV_plus_HLD=total(v['SV'],v['HLD']))


def benchmarks(root):
    sources, exceptions={},[]
    for (source,role),name in FILES.items():
        found={}
        for i,r in enumerate(read(root/name),2):
            pid=(r.get('MLBAMID') or '').strip()
            if not pid.isascii() or not pid.isdigit() or int(pid)<=0:
                exceptions.append(dict(source=source,player_type=role,row=i,name=r.get('Name'),issue='NO_VALID_MLBAM'))
                continue
            pid=str(int(pid))
            if pid in found:
                raise ValueError(f'Duplicate MLBAM ID in {name}: {pid}')
            found[pid]={'name':r['Name'],**{m:num(r.get(m)) for m in FIELDS[role] if m not in ('OUTS','SV_plus_HLD')}}
        if not found:
            raise ValueError(f'Empty benchmark {name}')
        sources[source,role]=found
    return sources,exceptions


def compare(home,sources):
    coverage,large=[],[]
    for (source,role),external in sources.items():
        local={pid:v for (r,pid),v in home.items() if r==role}
        for pid in sorted(local.keys()|external.keys(),key=int):
            b,e=local.get(pid),external.get(pid)
            coverage.append(dict(source=source,player_type=role,mlbam_id=pid,
                                 name=e['name'] if e else None,
                                 status='MATCHED' if b and e else 'HOMEGROWN_ONLY' if b else 'BENCHMARK_ONLY'))
            if b and e:
                arms=[('baseline',b)]
                if role=='pitcher':
                    arms.append(('hybrid_ip_only',{'IP':b['hybrid_ip']}))
                for arm,vec in arms:
                    for m,t in LARGE.items():
                        x,y=vec.get(m),e.get(m)
                        if x is not None and y is not None and abs(x-y)>=t:
                            large.append(dict(source=source,player_type=role,mlbam_id=pid,
                                name=e['name'],arm=arm,metric=m,homegrown=x,benchmark=y,delta=x-y))
    return coverage,sorted(large,key=lambda r:abs(r['delta']),reverse=True)


def sensitivity(r):
    ip,alt=r['IP'],r['hybrid_ip']
    return dict(mlbam_id=r['mlbam_id'],prior_role=r['prior_role'],accepted_ip=ip,hybrid_ip=alt,
                delta_ip=None if alt is None else alt-ip,accepted_so=r['SO'],accepted_w=r['W'],
                accepted_qs=r['QS'],accepted_gs=r['GS'],
                so_at_fixed_rate=product(divide(r['SO'],ip),alt),
                w_at_fixed_rate=product(divide(r['W'],ip),alt),
                hybrid_gs=None,hybrid_qs=None,qs_ip_ceiling=divide(alt,6))


def with_hybrid(r,actual,model,features,forecast):
    k=r['season'],'pitcher',r['mlbam_id']
    v={m:r[m] for m in ('OUTS','ERA','SV','HLD')}
    c=forecast(k,v,*features(k,v,actual,{}),model)
    if c['two_part_ip'] is None:
        raise ValueError('Frozen two-part forecast unavailable')
    r.update(prior_role=c['prior_role'],two_part_ip=c['two_part_ip'],
             appearance_probability=c['probability'],conditional_ip=c['conditional_ip'],
             hybrid_ip=r['IP'] if c['prior_role']=='STARTER' else c['two_part_ip'])
    return r


def replay(actual, models, features, forecast):
    """Four trailing years for the baseline; same per-origin frozen hybrid policy."""
    from collections import defaultdict
    groups=defaultdict(list)
    coverage=[]
    for target in (2023,2024,2025,2026):
        before={k:v for k,v in actual.items() if target-4<=k[0]<target}
        ids=sorted({k[2] for k in before if k[1]=='pitcher'})
        model=models[str(target)]
        c=Counter()
        for pid in ids:
            row=project(before,'pitcher',pid,target)
            if row is None:
                c['no_positive_history']+=1
                continue
            row=with_hybrid(row,before,model,features,forecast)
            outs=actual.get((target,'pitcher',pid,'OUTS'))
            if outs is None:
                c['unknown_outcome']+=1
                continue
            g=actual.get((target,'pitcher',pid,'G'))
            state='APPEARED' if outs>0 or (g is not None and g>0) else 'NON_APPEARANCE' if g==0 else 'ZERO_OUTS_UNKNOWN_G'
            c['scored']+=1
            for dim,cohort in [('ALL','ALL'),('PRIOR_ROLE',row['prior_role']),('APPEARANCE',state)]:
                groups[target,dim,cohort].append((pid,row['IP'],row['hybrid_ip'],outs/3))
        coverage.append(dict(season=target,history_start=target-4,history_end=target-1,
            reporting_only=target==2026,prior_history_ids=len(ids),
            **{k:c[k] for k in ('no_positive_history','unknown_outcome','scored')}))
    scores=[]
    for (year,dim,cohort),rows in sorted(groups.items()):
        n=len(rows)
        membership=hashlib.sha256(json.dumps(sorted(r[0] for r in rows)).encode()).hexdigest()
        for i,method in [(1,'weighted_actuals_ip'),(2,'weighted_actuals_hybrid_ip')]:
            e=[r[i]-r[3] for r in rows]
            mse=math.fsum(x*x for x in e)/n
            scores.append(dict(season=year,dimension=dim,cohort=cohort,method=method,n=n,membership_sha256=membership,
                reporting_only=year==2026,mse=mse,rmse=math.sqrt(mse),
                mae=math.fsum(map(abs,e))/n,bias=math.fsum(e)/n))
    return scores,coverage


def ranked_gaps(coverage,sources):
    result=[]
    for (source,role),players in sources.items():
        metric='PA' if role=='hitter' else 'IP'
        gaps=[r for r in coverage if (r['source'],r['player_type'],r['status'])==(source,role,'BENCHMARK_ONLY')]
        def exposure(row):
            return players[row['mlbam_id']].get(metric)
        gaps.sort(key=lambda r: (exposure(r) is None,-(exposure(r) or 0),int(r['mlbam_id'])))
        result.extend(dict(r,rank=i,playing_time_metric=metric,projected_playing_time=exposure(r))
                      for i,r in enumerate(gaps,1))
    return result


def cuts(home,actual,sources):
    result=[]
    for (role,pid),r in home.items():
        if role!='pitcher' or r['hybrid_ip']>=r['IP']:
            continue
        names=[(s,sources[s,role].get(pid,{}).get('name')) for s in ('depth_charts','steamer')]
        source,name=next(((s,n) for s,n in names if n),('unmatched',None))
        out=actual.get((2026,role,pid,'OUTS'))
        result.append(dict(player_name=name,name_source=source,
            prior_year_ip=divide(out,3),prior_year_g=actual.get((2026,role,pid,'G')),
            prior_year_gs=actual.get((2026,role,pid,'GS')),**sensitivity(r)))
    result.sort(key=lambda r:(r['delta_ip'],int(r['mlbam_id'])))
    return [dict(rank=i,**r) for i,r in enumerate(result,1)]


def run(a):
    from recent_skill_core_v1_23 import checked, emit
    from standalone_io_v1_0 import dump, finish, load, sha, start
    roots=[Path(getattr(a,k)).resolve() for k in ('labels','research','workload','evaluation','benchmarks','overlay')]
    lab,research,workload,evaluation,bench,overlay=roots
    w={}
    def take(root,name):
        return checked(root,name,w)
    evp=take(evaluation,'report.json')
    ev=load(evp)
    evscores=take(evaluation,'evaluation_2026_scores.csv')
    if (ev['version']!='1.29.0' or ev['season_certified'] is not True or ev['complete_pool_scored'] is not True
            or ev['selection_uses_2026'] is not False or ev['models_refitted'] is not False
            or ev['default_method']!='accepted_ip'):
        raise ValueError('Require certified reporting-only v1.29 evaluation')
    rchoices=take(research,'frozen_choices_2026.json')
    hp=take(research,'historical_forecasts.csv')
    ovp=take(overlay,'report.json')
    ovc=take(overlay,'participation_label_overlay.csv')
    wr=load(take(workload,'report.json'))
    models=take(workload,'models.json')
    old_forecast=take(workload,'frozen_2026_workload.csv')
    if (wr['version']!='1.27.0' or wr['selected_method']!='accepted_ip'
            or wr['evaluation_outcomes_read'] is not False or ev['frozen_forecast_sha256']!=w[str(old_forecast)]):
        raise ValueError('Frozen workload provenance mismatch')
    if (wr['participation_label_overlay']['report_sha256']!=w[str(ovp)]
            or wr['participation_label_overlay']['csv_sha256']!=w[str(ovc)]):
        raise ValueError('Historical overlay differs from frozen workload input')
    choices=load(rchoices)
    if any(choices[r]['selected']!='accepted_frozen' for r in FIELDS):
        raise ValueError('Unexpected v1.23 skill choice')
    audit=take(evaluation,'evaluation_label_overlay_2026.csv')
    train=take(lab,'training_labels.parquet')
    hold=take(lab,'holdout_labels.parquet')
    lr=take(lab,'label_build_report.json')
    if wr['label_report_sha256']!=w[str(lr)]:
        raise ValueError('Label report does not match the frozen workload run')
    for path in [bench/n for n in FILES.values()]:
        w[str(path)]=sha(path)
    choice_freeze=dict(historical_choices=choices,pitcher_default='accepted_ip',
         pitcher_hybrid='prior STARTER retains baseline; others use frozen v1.27 two-part model',
         baseline_implementation='NEW_WEIGHTED_ACTUALS_PROTOTYPE_NOT_A_REPLAY_OF_ACCEPTED_2026',
         seasons=YEARS,weights=WEIGHTS,model_selection_on_2026=False,valuation_enabled=False)
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        dump(stage/'model_choice_freeze.json',choice_freeze)
        dump(stage/'evaluation_2026_frozen.json',ev)
        shutil.copyfile(evscores,stage/'evaluation_2026_scores_frozen.csv')
        dump(stage/'freeze_manifest.json',{p.name:sha(p) for p in stage.iterdir()})
        from recent_skill_inputs_v1_23 import labels
        from pitcher_workload_v1_27 import features, forecast
        from participation_label_overlay_v1_27 import apply_overlay
        historical,_=apply_overlay(overlay,labels(train),train,hp,w)
        actual=historical|labels(hold,2026)
        seen=set()
        audit_status=Counter()
        for r in read(audit):
            pid=r['mlbam_id']
            if r['season']!='2026' or pid in seen or not pid.isascii() or not pid.isdigit() or int(pid)<=0:
                raise ValueError('Invalid 2026 overlay membership')
            seen.add(pid)
            audit_status[r['status']]+=1
            if r['status']=='VERIFIED_APPEARED':
                if int(r['evaluation_g'])<=0 or int(r['evaluation_outs'])<0:
                    raise ValueError('Invalid verified appearance')
                for m,value in [('G',int(r['evaluation_g'])),('OUTS',int(r['evaluation_outs']))]:
                    k=2026,'pitcher',pid,m
                    if actual.get(k,value)!=value:
                        raise ValueError('Certified appearance conflicts with actual label')
                    actual[k]=value
            elif r['status']!='VERIFIED_NO_APPEARANCE':
                raise ValueError('Unexpected status in fully certified audit')
            if r['status']=='VERIFIED_NO_APPEARANCE':
                if r['evaluation_g']!='0' or r['evaluation_outs']!='0':
                    raise ValueError('Invalid certified zeros')
                for m in ('G','OUTS'):
                    k=2026,'pitcher',pid,m
                    if actual.get(k) not in (None,0):
                        raise ValueError('Certified zero conflicts with actual label')
                    actual[k]=0
        if len(seen)!=ev['preseason_pool'] or dict(audit_status)!=ev['statuses']:
            raise ValueError('Incomplete audit membership')
        coefficients=load(models)
        scores,replay_coverage=replay(actual,coefficients,features,forecast)
        model=coefficients['2026']
        if model['logistic'] is None or model['conditional'] is None:
            raise ValueError('Frozen two-part model unavailable')
        home={}
        for role,pid in sorted({(k[1],k[2]) for k in actual if k[0] in YEARS}):
            r=project(actual,role,pid)
            if r is None:
                continue
            if role=='pitcher':
                with_hybrid(r,actual,model,features,forecast)
            home[role,pid]=r
        if {r for r,_ in home} != set(FIELDS):
            raise ValueError('Both hitter and pitcher histories are required')
        sources,exceptions=benchmarks(bench)
        coverage,large=compare(home,sources)
        for role in FIELDS:
            emit(stage/f'homegrown_2027_{role}s.csv',[v for (r,_),v in home.items() if r==role])
        emit(stage/'benchmark_coverage.csv',coverage)
        emit(stage/'benchmark_exceptions.csv',exceptions)
        emit(stage/'large_differences.csv',large)
        emit(stage/'pitcher_counting_stat_review.csv',[sensitivity(v) for (r,_),v in home.items() if r=='pitcher'])
        emit(stage/'ranked_coverage_gaps.csv',ranked_gaps(coverage,sources))
        emit(stage/'largest_pitcher_cuts.csv',cuts(home,actual,sources))
        emit(stage/'historical_weighted_ip_scores.csv',scores)
        emit(stage/'historical_weighted_ip_coverage.csv',replay_coverage)
        report=dict(version='1.31.0',replay_years=[2023,2024,2025],diagnostic_year=2026,
                    replay_population='players with positive prior exposure and known target outs',
                    replay_overall_scores=[r for r in scores if r['dimension']=='ALL'],
                    status='PROVISIONAL_RESEARCH_ONLY',models_refitted=False,
                    model_selection_uses_2026=False,actual_input_years=YEARS,
                    historical_replay_equivalent=False,valuation_enabled=False,
                    benchmark_vintage='2026-11-13',benchmark_data_used_in_forecasts=False,
                    forecast_counts=dict(Counter(r for r,_ in home)),
                    missing_components={role:{m:sum(v[m] is None for (rr,_),v in home.items() if rr==role)
                                              for m in FIELDS[role]} for role in FIELDS},
                    coverage_counts=dict(Counter('/'.join((r['source'],r['player_type'],r['status'])) for r in coverage)),
                    large_difference_rows=len(large),benchmark_exceptions=len(exceptions),
                    limitations=['New weighted-actuals baseline is not the frozen accepted 2026 generator.',
                    'Replay tests shifted IP inputs using previously frozen per-origin coefficients; no retuning or promotion.',
                    'No prospect model or unverified non-appearances; missing rate labels stay missing.',
                    'SO/W sensitivities hold rates fixed; QS requires a challenger starts model.'])
        dump(stage/'report.json',report)
        return dict(report,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k,d in dict(labels='outputs/training_labels_v1_0',research='outputs/recent_history_skills_v1_23',
                    workload='outputs/pitcher_workload_v1_27',evaluation='outputs/pitcher_evaluation_v1_29',
                    benchmarks='data/benchmarks_2027',overlay='outputs/participation_label_overlay_v1_27',output='outputs/homegrown_2027_v1_31',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=d)
    print(json.dumps(run(p.parse_args()),indent=2))
