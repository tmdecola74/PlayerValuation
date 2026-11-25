"""Read-only named 2027 projection review; benchmark disagreements are not accuracy."""
import argparse
from collections import Counter,defaultdict
import math
from pathlib import Path
import shutil
from project_2027_v1_31 import FIELDS, FILES, LARGE, read, num
METRICS={'hitter':('PA','AB','H','2B','3B','HR','R','RBI','SB','AVG','OPS'),
         'pitcher':('IP','GS','G','SO','W','QS','ERA','WHIP','SV','HLD')}
def identity(sources,role,pid):
    candidates=[(s,rows[pid]['name']) for (s,r),rows in sorted(sources.items()) if r==role and pid in rows and rows[pid]['name'].strip()]
    # Names are display labels only. Membership is always role + MLBAM ID.
    if not candidates:return '', 'UNRESOLVED_NO_ID_NAME', ''
    variants=sorted(set(n for _,n in candidates))
    # Explicit stable display priority; spelling differences do not merge identities.
    chosen=next((n for s,n in candidates if s=='steamer'),candidates[0][1])
    return chosen,'ID_LINKED_NAME_VARIANTS' if len(variants)>1 else 'ID_LINKED_NAME','; '.join(s+': '+n for s,n in candidates)

def support(rows):
    by=defaultdict(set);allmetrics=defaultdict(set)
    for r in rows:
        k=r['player_type'],r['mlbam_id']
        if r['eligible']=='True' and r['source_season']:
            y=int(r['source_season'])
            if not 2023<=y<=2026:raise ValueError('Unexpected feature source year')
            allmetrics[k].add(r['metric'])
            if y==2026:by[k].add(r['metric'])
    return by,allmetrics

def review(home,provenance,sources):
    current,ever=support(provenance)
    named={};exceptions=[];comparisons=[];coverage=[];components=[]
    for role,rows in home.items():
        seen=set();out=[]
        for r in rows:
            pid=r['mlbam_id']
            if r['season']!='2027' or r['player_type']!=role or pid in seen:raise ValueError('Duplicate/future review identity')
            seen.add(pid)
            name,status,evidence=identity(sources,role,pid)
            n=len(current[role,pid])
            vintage='CURRENT_2026_ALL_FOUR' if n==4 else 'CURRENT_2026_PARTIAL' if n else 'OLDER_ONLY' if ever[role,pid] else 'NO_ELIGIBLE_FEATURES'
            out.append(dict(r,name=name,name_status=status,name_evidence=evidence,
                feature_vintage=vintage,eligible_2026_metrics=n))
            if status!='ID_LINKED_NAME':exceptions.append(dict(player_type=role,mlbam_id=pid,name=name,status=status,evidence=evidence))
        named[role]=out
    for (source,role),external in sorted(sources.items()):
        local={r['mlbam_id']:r for r in named[role]}
        exp='PA' if role=='hitter' else 'IP'
        for pid in sorted(local.keys()|external.keys(),key=int):
            r,b=local.get(pid),external.get(pid)
            h={m:num(r.get('weighted_actuals__'+m)) for m in FIELDS[role]} if r else {}
            name=r['name'] if r else b['name']
            coverage.append(dict(source=source,player_type=role,mlbam_id=pid,name=name,
                status='MATCHED' if r and b else 'HOMEGROWN_ONLY' if r else 'BENCHMARK_ONLY',
                exposure_metric=exp,homegrown_exposure=h.get(exp),benchmark_exposure=b.get(exp) if b else None,
                priority_exposure=max(h.get(exp) or 0,b.get(exp) or 0) if b else h.get(exp),
                feature_vintage=r['feature_vintage'] if r else 'NO_HOMEGROWN_FORECAST'))
            if not (r and b):continue
            for m in METRICS[role]:
                x,y=h.get(m),b.get(m)
                if x is None or y is None:continue
                comparisons.append(dict(source=source,player_type=role,mlbam_id=pid,name=name,metric=m,
                    homegrown=x,benchmark=y,delta=x-y,
                    common_both_benchmarks=all(pid in sources.get((s,role),{}) and sources[s,role][pid].get(m) is not None for s in ('steamer','depth_charts')),
                    feature_vintage=r['feature_vintage'],
                    large_difference=abs(x-y)>=LARGE[m] if m in LARGE else False))
            for m in (('HR','R','RBI','SB') if role=='hitter' else ('SO','W')):
                he,be=h.get(exp),b.get(exp);hc,bc=h.get(m),b.get(m)
                if None in (he,be,hc,bc) or he<=0 or be<=0:continue
                workload=(he-be)*(bc/be)
                rate=he*(hc/he-bc/be)
                components.append(dict(source=source,player_type=role,mlbam_id=pid,name=name,metric=m,
                    exposure_metric=exp,homegrown_exposure=he,benchmark_exposure=be,
                    homegrown_rate=hc/he,benchmark_rate=bc/be,delta=hc-bc,
                    exposure_component=workload,rate_component=rate,
                    accounting_residual=hc-bc-workload-rate,
                    interpretation='FORECAST_DISAGREEMENT_NOT_ERROR_ATTRIBUTION'))
    groups=defaultdict(list)
    for r in comparisons:
        groups[r['source'],r['player_type'],r['metric'],'PAIRWISE'].append(r)
        if r['common_both_benchmarks']:groups[r['source'],r['player_type'],r['metric'],'COMMON_BOTH'].append(r)
    summary=[]
    import hashlib,json
    for (s,role,m,pool),rows in sorted(groups.items()):
        ds=[r['delta'] for r in rows];n=len(ds)
        summary.append(dict(source=s,player_type=role,metric=m,pool=pool,n=n,
            membership_sha256=hashlib.sha256(json.dumps(sorted(r['mlbam_id'] for r in rows)).encode()).hexdigest(),
            mean_signed_difference=sum(ds)/n,mean_absolute_difference=sum(map(abs,ds))/n,
            maximum_absolute_difference=max(map(abs,ds)),interpretation='NOT_ACCURACY'))
    return named,exceptions,comparisons,coverage,components,summary

def run(a):
    from standalone_io_v1_0 import load,dump,start,finish,sha
    from recent_skill_core_v1_23 import checked,emit
    from project_2027_v1_31 import benchmarks
    roots=[Path(getattr(a,k)).resolve() for k in ('export','baseline','benchmarks')]
    export,base,bench=roots;w={}
    take=lambda r,n:checked(r,n,w)
    report=load(take(export,'report.json'))
    if report['version']!='1.39.0' or report['valuation_enabled'] is not False or report['models_refitted'] is not False:
        raise ValueError('Require frozen v1.39 research export')
    er=load(take(export,'input_hashes.json'));br=load(take(base,'report.json'))
    if br['version']!='1.31.0' or br['benchmark_vintage']!='2026-11-13':
        raise ValueError('Unexpected benchmark baseline vintage')
    def binding(path,bindings):
        hashes={v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==path.name}
        if w[str(path)] not in hashes:raise ValueError('Frozen binding mismatch: '+path.name)
    binding(base/'report.json',er)
    bindings=load(take(base,'input_hashes.json'))
    for name in FILES.values():
        p=bench/name;w[str(p)]=sha(p);binding(p,bindings)
    sources,bad=benchmarks(bench)
    home={role:read(take(export,f'side_by_side_2027_{role}s.csv')) for role in FIELDS}
    provenance=read(take(export,'player_feature_provenance.csv'))
    named,exceptions,pairs,coverage,components,summary=review(home,provenance,sources)
    for role in FIELDS:
        if len(named[role])!=report['forecast_counts'][role]:raise ValueError('Population differs')
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        for role,rows in named.items():emit(stage/f'named_2027_{role}s.csv',rows)
        emit(stage/'matched_baseline_comparisons.csv',pairs)
        emit(stage/'benchmark_disagreement_summary.csv',summary)
        emit(stage/'workload_rate_disagreements.csv',components)
        coverage.sort(key=lambda r:(r['source'],r['player_type'],r['status'],-(r['priority_exposure'] or 0),int(r['mlbam_id'])))
        emit(stage/'ranked_player_coverage.csv',coverage)
        emit(stage/'identity_exceptions.csv',exceptions or [dict(status='NONE')])
        emit(stage/'benchmark_input_exceptions.csv',bad or [dict(status='NONE')])
        groups=defaultdict(list)
        for r in pairs:groups[r['source'],r['player_type'],r['metric']].append(r)
        large=[dict(r,rank=i) for k,rr in sorted(groups.items()) for i,r in enumerate(sorted(rr,key=lambda z:(-abs(z['delta']),int(z['mlbam_id'])))[:30],1)]
        emit(stage/'largest_baseline_benchmark_differences.csv',large)
        names={(r['player_type'],r['mlbam_id']):r for rr in named.values() for r in rr}
        for filename in ('largest_changes.csv','player_adjustments.csv'):
            rows=read(take(export,filename))
            emit(stage/('named_'+filename),[dict(r,name=names[r['player_type'],r['mlbam_id']]['name'],
                name_status=names[r['player_type'],r['mlbam_id']]['name_status'],
                feature_vintage=names[r['player_type'],r['mlbam_id']]['feature_vintage']) for r in rows])
        result=dict(version='1.40.0',status='READ_ONLY_PROJECTION_REVIEW',
            forecast_counts={r:len(rr) for r,rr in named.items()},
            feature_support=[dict(role=r,feature_vintage=s,n=n) for (r,s),n in sorted(Counter((r,v['feature_vintage']) for r,rr in named.items() for v in rr).items())],
            unresolved_names=sum(r['name_status']=='UNRESOLVED_NO_ID_NAME' for rr in named.values() for r in rr),
            benchmark_vintage='2026-11-13',forecasts_modified=False,models_fitted=False,
            model_selection_performed=False,evaluation_outcomes_read=False,
            additional_validation=False,skill_default='weighted_actuals',workload_default='accepted_ip',
            hybrid_qs=None,valuation_enabled=False,
            limitations=['Benchmark disagreements are not forecast errors or accuracy scores.',
                'Names use exact role/MLBAM joins; variants and missing names remain explicit.',
                'Pairwise and common-both benchmark pools are separate; absent metrics remain unscored.',
                '2026 measurement availability is distinct from full-vector model eligibility.',
                'No new validation, model selection, forecast population expansion or valuation wiring.'])
        dump(stage/'report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in dict(export='outputs/2027_side_by_side_v1_39',baseline='outputs/homegrown_2027_v1_31',
        benchmarks='data/benchmarks_2027',output='outputs/projection_review_v1_40',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(__import__('json').dumps(run(p.parse_args()),indent=2))
