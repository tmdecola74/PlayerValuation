"""Read-only baseline reliability: exposure freshness, source samples and benchmark scope."""
import argparse
from collections import Counter
import csv
import math
from pathlib import Path
import shutil
from project_2027_v1_31 import FIELDS,FILES,WEIGHTS,read,num

YEARS=(2023,2024,2025,2026)
RATE_PARTS={'hitter':{'AVG':('AB',('1B','2B','3B','HR')),
                    'OPS':('AB',('1B','2B','3B','HR'))},
            'pitcher':{'ERA':('OUTS',('ER',)),'WHIP':('OUTS',('H','BB'))}}
EXTREME={'AVG':(0.15,.35),'OPS':(.4,1.1),'ERA':(1.5,7.),'WHIP':(.8,1.8)}

def sample(actual,role,pid,metric,denom):
    obs=[(y,w,actual.get((y,role,pid,metric)),actual.get((y,role,pid,denom)))
         for y,w in zip(YEARS,WEIGHTS)]
    valid=[(y,w,n,d) for y,w,n,d in obs if n is not None and d is not None and d>0]
    wn=sum(w*n for y,w,n,d in valid);wd=sum(w*d for y,w,n,d in valid)
    return dict(metric=metric,denominator_metric=denom,paired_years='|'.join(str(y) for y,w,n,d in valid),
        paired_seasons=len(valid),raw_numerator=sum(n for y,w,n,d in valid),
        raw_denominator=sum(d for y,w,n,d in valid),weighted_numerator=wn,
        weighted_denominator=wd,weighted_component_rate=wn/wd if wd else None,
        sample_status='PAIRED_POSITIVE_DENOMINATOR' if valid else 'UNKNOWN_NO_VALID_PAIR',
        **{f'source_{y}_{field}':value for y,w,n,d in obs for field,value in (('numerator',n),('denominator',d),('weight',w))})

def audit_players(home,actual):
    histories=[];samples=[];exceptions=[]
    for role,rows in home.items():
        exposure='PA' if role=='hitter' else 'OUTS';unit='PA' if role=='hitter' else 'IP'
        seen=set()
        for r in rows:
            pid=r['mlbam_id']
            if r['season']!='2027' or r['player_type']!=role or pid in seen:raise ValueError('Invalid forecast identity')
            seen.add(pid)
            values={y:actual.get((y,role,pid,exposure)) for y in YEARS}
            if any(v is not None and (not math.isfinite(v) or v<0) for v in values.values()):raise ValueError('Invalid actual exposure')
            positive=[y for y,v in values.items() if v is not None and v>0]
            latest=max(positive) if positive else None
            state='UNKNOWN' if values[2026] is None else 'KNOWN_ZERO_EXPOSURE' if values[2026]==0 else 'POSITIVE_EXPOSURE'
            # Zero OUTS is not necessarily no appearance; G establishes that distinction.
            g=actual.get((2026,role,pid,'G')) if role=='pitcher' else None
            participation=('KNOWN_APPEARED' if g is not None and g>0 else
                'CERTIFIED_NO_APPEARANCE' if g==0 and values[2026]==0 else
                'POSITIVE_EXPOSURE' if values[2026] and values[2026]>0 else 'UNKNOWN')
            projected=num(r['weighted_actuals__'+unit])
            flags=[]
            if latest is None or latest<2026:flags.append('STALE_POSITIVE_EXPOSURE_HISTORY')
            if len(positive)<2:flags.append('LIMITED_POSITIVE_HISTORY')
            total=sum(v for v in values.values() if v is not None)
            if total<(200 if role=='hitter' else 150):flags.append('LOW_RECORDED_EXPOSURE')
            if state=='UNKNOWN':flags.append('LATEST_EXPOSURE_UNKNOWN')
            if state=='KNOWN_ZERO_EXPOSURE':flags.append('LATEST_EXPOSURE_ZERO')
            if projected and state!='POSITIVE_EXPOSURE':flags.append('POSITIVE_FORECAST_WITHOUT_RECENT_POSITIVE_EXPOSURE')
            context=dict(player_type=role,mlbam_id=pid,name=r.get('name',''),projected_exposure=projected,
                exposure_unit=unit,latest_positive_season=latest,positive_history_seasons=len(positive),
                known_history_seasons=sum(v is not None for v in values.values()),
                known_zero_years='|'.join(str(y) for y,v in values.items() if v==0),
                unknown_years='|'.join(str(y) for y,v in values.items() if v is None),
                raw_recorded_exposure=total,raw_exposure_unit=exposure,
                latest_exposure_status=state,latest_participation_status=participation,
                preseason_participation_evidence='NOT_SUPPLIED_NO_2027_STATUS_INFERRED',
                flags=';'.join(flags))
            context.update({f'exposure_{y}':v for y,v in values.items()})
            histories.append(context)
            for flag in flags:exceptions.append(dict(context,issue=flag,metric=unit))
            for rate,(den,parts) in RATE_PARTS[role].items():
                value=num(r['weighted_actuals__'+rate]);lo,hi=EXTREME[rate]
                extreme=value is not None and (value<lo or value>hi)
                metrics=list(parts)
                # OPS depends also on BB/HBP/SF rates estimated against PA.
                if rate=='OPS':metrics+=['BB','HBP','SF','AB']
                for m in metrics:
                    dd='PA' if rate=='OPS' and m in ('BB','HBP','SF','AB') else den
                    ss=sample(actual,role,pid,m,dd)
                    samples.append(dict(player_type=role,mlbam_id=pid,name=r.get('name',''),
                        projected_rate=rate,projected_value=value,extreme=extreme,
                        **ss,formula_scope='COMPONENT_SAMPLE_NOT_ONE_COMMON_COMPOSITE_DENOMINATOR'))
                if extreme:
                    exceptions.append(dict(context,issue='EXTREME_RATE_REQUIRES_SAMPLE_REVIEW',metric=rate,projected_value=value))
    exceptions.sort(key=lambda r:(r['player_type'],-(r['projected_exposure'] or 0),r['mlbam_id'],r['issue'],r['metric']))
    return histories,samples,[dict(r,rank_within_role=i) for role in FIELDS for i,r in enumerate([x for x in exceptions if x['player_type']==role],1)]

def audit_benchmarks(root):
    details=[];summaries=[]
    for (source,role),filename in FILES.items():
        if role!='pitcher':continue
        p=root/filename
        with p.open(encoding='utf-8-sig',newline='') as f:
            reader=csv.DictReader(f);header=reader.fieldnames or []
            if len(header)!=len(set(header)):raise ValueError('Duplicate benchmark header')
            for line,r in enumerate(reader,2):
                for m in ('SV','HLD'):
                    raw=r.get(m)
                    if m not in header:status='COLUMN_ABSENT';v=None
                    elif raw is None or not raw.strip():status='BLANK_MISSING';v=None
                    else:
                        v=num(raw);status='EXPLICIT_ZERO' if v==0 else 'POSITIVE_VALUE'
                    details.append(dict(source=source,source_file=filename,source_row=line,
                        mlbam_id=r.get('MLBAMID',''),name=r.get('Name',''),metric=m,
                        raw_text=raw,value=v,status=status,semantic_status='SOURCE_INTENT_NOT_CERTIFIED'))
        for m in ('SV','HLD'):
            rr=[r for r in details if r['source']==source and r['metric']==m]
            counts=Counter(r['status'] for r in rr);present=[r['value'] for r in rr if r['value'] is not None]
            summaries.append(dict(source=source,metric=m,rows=len(rr),
                column_absent=counts['COLUMN_ABSENT'],missing=counts['BLANK_MISSING'],
                explicit_zero=counts['EXPLICIT_ZERO'],positive=counts['POSITIVE_VALUE'],
                exported_total=sum(present) if present else None,
                scope_status='ALL_RECORDED_VALUES_ZERO_REQUIRES_SOURCE_SCOPE_REVIEW' if present and all(v==0 for v in present)
                    else 'NO_NUMERIC_VALUES' if not present else 'MIXED_VALUES_NOT_INDEPENDENTLY_CERTIFIED'))
    return details,summaries

def verify_baseline(home,actual):
    from project_2027_v1_31 import project
    for role,rows in home.items():
        for r in rows:
            expected=project(actual,role,r['mlbam_id'])
            if expected is None:raise ValueError('No reconstructible baseline')
            for m in FIELDS[role]:
                x=num(r['weighted_actuals__'+m]);y=expected[m]
                if (x is None)!=(y is None) or x is not None and not math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-9):
                    raise ValueError('Baseline sample replay mismatch: '+role+'/'+r['mlbam_id']+'/'+m)

def run(a):
    from standalone_io_v1_0 import load,dump,start,finish,sha
    from recent_skill_core_v1_23 import checked,emit
    from recent_skill_inputs_v1_23 import labels
    from participation_label_overlay_v1_27 import apply_overlay
    roots=[Path(getattr(a,k)).resolve() for k in ('review','baseline','labels','overlay','research','evaluation','benchmarks')]
    review,base,lab,overlay,research,ev,bench=roots;w={}
    take=lambda root,n:checked(root,n,w)
    rr=load(take(review,'report.json'));br=load(take(base,'report.json'))
    if rr['version']!='1.40.0' or rr['forecasts_modified'] is not False or br['version']!='1.31.0':
        raise ValueError('Unexpected frozen review/baseline')
    rb=load(take(review,'input_hashes.json'));bb=load(take(base,'input_hashes.json'))
    def bound(p,bindings):
        if w[str(p)] not in {v for k,v in bindings.items() if k.replace(chr(92),'/').rsplit('/',1)[-1]==p.name}:
            raise ValueError('Frozen input differs: '+p.name)
    bound(base/'report.json',rb)
    train=take(lab,'training_labels.parquet');hold=take(lab,'holdout_labels.parquet')
    hp=take(research,'historical_forecasts.csv')
    historical,_=apply_overlay(overlay,labels(train),train,hp,w)
    for p in (train,hold,hp,overlay/'report.json',overlay/'participation_label_overlay.csv'):bound(p,bb)
    actual=historical|labels(hold,2026)
    er=load(take(ev,'report.json'))
    if er['version']!='1.29.0' or er['season_certified'] is not True or er['complete_pool_scored'] is not True or er['selection_uses_2026'] is not False:
        raise ValueError('Require certified historical 2026 source')
    bound(ev/'report.json',bb)
    ep=take(ev,'evaluation_label_overlay_2026.csv');bound(ep,bb)
    seen=set()
    for r in read(ep):
        pid=r['mlbam_id']
        if r['season']!='2026' or pid in seen:raise ValueError('Invalid 2026 overlay identity')
        seen.add(pid)
        if r['status']=='VERIFIED_NO_APPEARANCE':
            if r['evaluation_g']!='0' or r['evaluation_outs']!='0':raise ValueError('Uncertified zero')
            for m in ('G','OUTS'):
                k=2026,'pitcher',pid,m
                if actual.get(k) not in (None,0):raise ValueError('Zero conflicts with source')
                actual[k]=0
        elif r['status']=='VERIFIED_APPEARED':
            if int(r['evaluation_g'])<=0 or int(r['evaluation_outs'])<0:raise ValueError('Invalid appeared record')
            for m,value in [('G',int(r['evaluation_g'])),('OUTS',int(r['evaluation_outs']))]:
                k=2026,'pitcher',pid,m
                if actual.get(k,value)!=value:raise ValueError('Appeared source conflicts')
                actual[k]=value
        else:raise ValueError('Unknown certification status')
    if len(seen)!=er['preseason_pool']:raise ValueError('Incomplete certified overlay')
    for n in FILES.values():
        p=bench/n;w[str(p)]=sha(p);bound(p,bb)
    home={role:read(take(review,f'named_2027_{role}s.csv')) for role in FIELDS}
    verify_baseline(home,actual)
    histories,samples,exceptions=audit_players(home,actual)
    raw,summary=audit_benchmarks(bench)
    out,bak,stage=start(a.output,a.backup_root,roots)
    try:
        emit(stage/'player_history_reliability.csv',histories)
        emit(stage/'rate_component_samples.csv',samples)
        emit(stage/'extreme_rate_samples.csv',[r for r in samples if r['extreme']])
        emit(stage/'prioritized_exceptions.csv',exceptions)
        emit(stage/'benchmark_save_hold_raw_audit.csv',raw)
        emit(stage/'benchmark_save_hold_summary.csv',summary)
        dump(stage/'diagnostic_contract.json',dict(history_years=YEARS,weights=WEIGHTS,
            limited_history_positive_seasons_below=2,low_recorded_hitter_PA_below=200,
            low_recorded_pitcher_OUTS_below=150,extreme_rate_review_bounds=EXTREME,
            thresholds_are_diagnostic_only=True))
        result=dict(version='1.41.0',status='READ_ONLY_BASELINE_RELIABILITY_AUDIT',
            player_rows=len(histories),sample_rows=len(samples),exception_rows=len(exceptions),
            baseline_numeric_replay_verified=True,forecasts_modified=False,
            models_fitted=False,selection_uses_2026=False,
            source_2026_actuals_read_as_2027_history=True,evaluation_scores_read=False,
            skill_default='weighted_actuals',workload_default='accepted_ip',hybrid_qs=None,
            valuation_enabled=False,
            limitations=['Historical records do not establish 2027 participation or roster status.',
              'Missing exposure remains unknown; zero outs alone is not non-appearance.',
              'Composite rates can combine different component samples; all paired denominators are reported separately.',
              'Exported zero is preserved, not automatically declared a forecast or a placeholder.',
              'Diagnostic cutoffs are not stabilization thresholds or chosen model settings.',
              'No regression or freshness candidate fitted; historical experiments are a later step.'])
        dump(stage/'report.json',result)
        return dict(result,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for k,v in dict(review='outputs/projection_review_v1_40',baseline='outputs/homegrown_2027_v1_31',
        labels='outputs/training_labels_v1_0',overlay='outputs/participation_label_overlay_v1_27',
        research='outputs/recent_history_skills_v1_23',evaluation='outputs/pitcher_evaluation_v1_29',
        benchmarks='data/benchmarks_2027',output='outputs/baseline_reliability_v1_41',backup_root='backups').items():
        p.add_argument('--'+k.replace('_','-'),default=v)
    print(__import__('json').dumps(run(p.parse_args()),indent=2))
