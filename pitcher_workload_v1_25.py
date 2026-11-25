"""Research only: preseason pitcher participation and conditional innings."""
import argparse
from datetime import date
import json
from collections import Counter, defaultdict
from pathlib import Path
import shutil

import numpy as np

from contact_workload_audit_v1_24 import BASE, exposure, registered, role, rows, vectors
from recent_skill_core_v1_23 import checked, emit, member
from recent_skill_inputs_v1_23 import labels
from standalone_io_v1_0 import dump, finish, load, sha, start

VERSION = '1.25.0'
YEARS = range(2019, 2026)
ARMS = ('direct_ip', 'two_part_ip')
ANCHORS = ('ERA', 'SV', 'HLD')
ROLES = ('STARTER', 'SWING', 'RELIEVER')
AVAIL = ('AVAILABLE', 'LIMITED', 'UNAVAILABLE')


def observed(actual, k):
    outs, games, starts = (actual.get(k+(m,)) for m in ('OUTS','G','GS'))
    if outs is None and games == 0:
        outs = 0.
    if outs is not None and outs > 0 and games == 0:
        raise ValueError(f'Positive outs with zero appearances: {k}')
    pitched = 1 if (outs or 0) > 0 or (games or 0) > 0 else 0 if games == 0 else None
    return (None if outs is None else outs/3, pitched, role(games,starts))


def availability(path, w):
    if not path:
        return {}
    p = Path(path).resolve()
    w[str(p)] = sha(p)
    result = {}
    for r in rows(p):
        year, pid = int(r['season']), r['mlbam_id']
        key = year,'pitcher',pid
        timestamp, cutoff = map(date.fromisoformat,(r['published_on'],r['preseason_cutoff']))
        if (year not in range(2019,2027) or not pid.isdigit() or int(pid)<=0 or
                not date(year-1,10,1) <= timestamp < cutoff or
                not date(year,1,1) <= cutoff <= date(year,3,1) or
                r['availability'] not in AVAIL or not r['source'].strip() or key in result):
            raise ValueError(f'Invalid dated preseason availability: {key}')
        result[key] = r['availability']
    return result


def features(k, v, actual, documented):
    y, _, pid = k
    prior = [observed(actual, (y-i,'pitcher',pid)) for i in (1,2,3)]
    previous_role = prior[0][2]
    status = documented.get(k,'UNKNOWN')
    x = [v['OUTS']/3]
    for ip, pitched, _ in prior:
        x.extend((0. if ip is None else ip, float(ip is None),
                  float(pitched == 1), float(pitched is None)))
    x.extend(float(previous_role==r) for r in (*ROLES,'UNKNOWN'))
    x.extend(float(status==r) for r in (*AVAIL,'UNKNOWN'))
    return x, previous_role, status


def fit(train):
    known_ip = [(x,ip) for x,ip,p in train if ip is not None]
    positive = [(x,ip) for x,ip,p in train if p==1 and ip is not None]
    participation = [(x,p) for x,_,p in train if p is not None]
    classes = Counter(p for _,p in participation)
    if not train:
        return None
    matrix = np.array([x for x,_,_ in train],dtype=float)
    mu, sd = matrix.mean(axis=0), matrix.std(axis=0)
    sd = np.where(sd>1e-8,sd,1.)
    def design(x):
        z = np.clip((np.asarray(x)-mu)/sd,-8,8)
        return np.column_stack((np.ones(len(z)),z))
    def ridge(data):
        z = design([x for x,_ in data])
        return np.linalg.solve(z.T@z + penalty,z.T@np.array([y for _,y in data]))
    penalty = 10*np.eye(matrix.shape[1]+1)
    penalty[0,0] = 0
    b = None
    if min(classes[0],classes[1])>=10 and len(participation)>=40:
        z = design([x for x,_ in participation])
        y = np.array([p for _,p in participation])
        b = np.zeros(z.shape[1])
        for _ in range(60):
            pr = 1/(1+np.exp(-np.clip(z@b,-30,30)))
            step = np.linalg.solve(z.T@((pr*(1-pr))[:,None]*z)+penalty,z.T@(y-pr)-penalty@b)
            b += step
            if np.max(np.abs(step))<1e-8:
                break
        else:
            raise ValueError('Participation fit did not converge')
    return {key:(val.tolist() if isinstance(val,np.ndarray) else val) for key,val in
            dict(mu=mu,sd=sd,logistic=b,conditional=ridge(positive) if len(positive)>=30 else None,
                 direct=ridge(known_ip) if len(known_ip)>=40 else None,
                 prior=classes[1]/len(participation) if b is not None else None,
                 participation_n=len(participation),zero_appearance_n=classes[0],conditional_n=len(positive),
                 direct_n=len(known_ip)).items()}


def forecast(k,v,x,prior_role,status,model):
    row = dict(season=k[0],mlbam_id=k[2],prior_role=prior_role,
               availability=status,accepted_ip=v['OUTS']/3,**{m:v[m] for m in ANCHORS})
    if model is None:
        return dict(row,probability=None,prior_probability=None,conditional_ip=None,
                    direct_ip=None,two_part_ip=None)
    z = np.r_[1.,np.clip((np.array(x)-model['mu'])/model['sd'],-8,8)]
    p = float(1/(1+np.exp(-np.clip(z@model['logistic'],-30,30)))) if model['logistic'] is not None else None
    def innings(name):
        return float(np.clip(z@model[name],0,250)) if model[name] is not None else None
    conditional, direct = innings('conditional'), innings('direct')
    return dict(row,probability=p,prior_probability=model['prior'],conditional_ip=conditional,
                direct_ip=direct,two_part_ip=p*conditional if p is not None and conditional is not None else None)


def score(preds,actual):
    bins = defaultdict(list)
    audit = []
    for r in preds:
        year,pid = int(r['season']),r['mlbam_id']
        k = year,'pitcher',pid
        ip,pitched,actual_role = observed(actual,k)
        prior = r['prior_role']
        transition = f'{prior}->{actual_role}'
        role_group = ('UNKNOWN' if 'UNKNOWN' in (prior,actual_role) else
                      'STABLE_STARTER' if prior==actual_role=='STARTER' else
                      'STABLE_OTHER' if prior==actual_role else 'ROLE_CHANGED')
        outcomes = [('ROLE_GROUP',role_group),('ALL','ALL'),('PRIOR_ROLE',prior),('AVAILABILITY',r['availability']),
                    ('ACTUAL_ROLE_TRANSITION',transition),
                    ('ACTUAL_EXPOSURE',exposure(None if ip is None else ip*3))]
        audit.append(dict(r,actual_ip=ip,pitched=pitched,actual_role=actual_role,
                          transition=transition,actual_exposure=outcomes[-1][1]))
        def add(task,truth,methods):
            if truth is None or any(r.get(m) is None for m in methods):
                return
            for m in methods:
                for dim,cohort in outcomes:
                    bins[year,task,dim,cohort,m].append((pid,r[m]-truth,r[m],truth))
        add('PARTICIPATION',pitched,('prior_probability','probability'))
        if pitched==1:
            add('CONDITIONAL_IP',ip,('accepted_ip',)+tuple(m for m in ('direct_ip','conditional_ip') if r[m] is not None))
        add('EXPECTED_IP',ip,('accepted_ip',)+tuple(m for m in ARMS if r[m] is not None))
        if r.get('historically_selected_ip') is not None:
            add('SELECTED_EXPECTED_IP',ip,('accepted_ip','historically_selected_ip'))
    scores = []
    for (y,task,dim,cohort,m), vals in sorted(bins.items()):
        e = np.array([v[1] for v in vals])
        mse = float(np.mean(e**2))
        scores.append(dict(season=y,task=task,dimension=dim,cohort=cohort,method=m,
                           n=len(vals),mse=mse,rmse=mse**.5,mae=float(np.mean(abs(e))),
                           bias=float(np.mean(e)),brier=mse if task=='PARTICIPATION' else None,
                           mean_forecast=sum(v[2] for v in vals)/len(vals),
                           mean_actual=sum(v[3] for v in vals)/len(vals),
                           membership_sha256=member([v[0] for v in vals])))
    return scores,audit


def select(scores,year):
    index = {(r['season'],r['task'],r['dimension'],r['cohort'],r['method']):r
             for r in scores if r['season']<year}
    def compare(task,dim,c,arm,ref,floor,limit):
        ratios = {}
        for y in range(2019,year):
            a,b = (index.get((y,task,dim,c,m)) for m in (arm,ref))
            if a and b and a['n']>=floor and a['membership_sha256']==b['membership_sha256'] and b['mse']>0:
                ratios[y] = a['mse']/b['mse']
        mean = sum(ratios.values())/len(ratios) if ratios else None
        return dict(ratios=ratios,mean=mean,passed=len(ratios)>=3 and mean<=limit)
    pc = compare('PARTICIPATION','ALL','ALL','probability','prior_probability',50,.99)
    cc = compare('CONDITIONAL_IP','ALL','ALL','conditional_ip','direct_ip',50,1.)
    gates = {}
    for arm in ARMS:
        gates[arm] = dict(all=compare('EXPECTED_IP','ALL','ALL',arm,'accepted_ip',50,.99),
                          prior_starters=compare('EXPECTED_IP','PRIOR_ROLE','STARTER',arm,'accepted_ip',20,1.01))
    gates['two_part_ip'].update(participation=pc,conditional_ip=cc,
         beats_direct=compare('EXPECTED_IP','ALL','ALL','two_part_ip','direct_ip',50,.99))
    passing = [a for a in ARMS if all(c['passed'] for c in gates[a].values())]
    chosen = min(passing,key=lambda a:gates[a]['all']['mean']) if passing else 'accepted_ip'
    return dict(method=chosen,gates=gates)


def report_coverage(audit):
    counts = Counter((r['season'],r['availability'],r['pitched'],r['actual_exposure'],
                      r['probability'] is not None) for r in audit)
    return [dict(season=y,availability=s,pitched=p,actual_exposure=e,model_supported=m,n=n)
            for (y,s,p,e,m),n in sorted(counts.items(),key=lambda kv:str(kv[0]))]


def publish(a, roots, w, tables, payload, report):
    out,bak,stage = start(a.output,a.backup_root,roots)
    try:
        for name,data in tables.items():
            emit(stage/(name+'.csv'),data)
        for name,data in payload.items():
            dump(stage/(name+'.json'),data)
        dump(stage/'report.json',report)
        dump(stage/'forecast_freeze.json',{p.name:sha(p) for p in stage.iterdir()})
        return dict(report,output=str(out),backup=finish(out,bak,stage,w))
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def build(a):
    ref, lab = Path(a.reference).resolve(), Path(a.labels).resolve()
    w = {}
    freeze = load(checked(ref,'forecast_freeze.json',w))
    report = load(registered(ref,'build_report.json',w,freeze))
    lr = checked(lab,'label_build_report.json',w)
    lp = checked(lab,'training_labels.parquet',w)
    if (report['version']!='1.24.0' or report['evaluation_outcomes_read'] or
            w[str(lr)]!=report['label_report_sha256'] or load(checked(ref,'input_hashes.json',w)).get(str(lp))!=w[str(lp)]):
        raise ValueError('Require the v1.24 freeze and its original historical labels')
    documented = availability(a.availability,w)
    actual = labels(lp)
    # Historical accepted forecasts come directly from the same v1.23 parent
    # registered by v1.24; do not reconstruct them from error reports.
    parent = Path(a.parent).resolve()
    pf = load(checked(parent,'forecast_freeze.json',w))
    hp = registered(parent,'historical_forecasts.csv',w,pf)
    binding = load(ref/'input_hashes.json')
    if binding.get(str(hp))!=w[str(hp)]:
        raise ValueError('Historical forecasts differ from the v1.24 parent binding')
    hist = vectors(hp,YEARS,{BASE})
    def cases(bank):
        for (k,_),v in sorted(bank.items()):
            if k[1]=='pitcher' and v['OUTS'] is not None:
                yield k,v,features(k,v,actual,documented)
    prepared = list(cases(hist))
    models = {}
    historical = []
    for y in YEARS:
        train = [(f[0],*observed(actual,k)[:2]) for k,v,f in prepared if k[0]<y]
        model = models[y] = fit(train)
        print(f'{y}: {len(train)} earlier forecast rows; fitted={model is not None}',flush=True)
        historical.extend(forecast(k,v,*f,model) for k,v,f in prepared if k[0]==y)
    scores,audit = score(historical,actual)
    choices = {y:select(scores,y) for y in range(2019,2027)}
    for r in audit:
        chosen = choices[r['season']]['method']
        r['historically_selected_ip'] = r[chosen] if r[chosen] is not None else r['accepted_ip']
    models[2026] = fit([(f[0],*observed(actual,k)[:2]) for k,v,f in prepared])
    hold = vectors(registered(ref,'frozen_2026_forecasts.csv',w,freeze),{2026},{BASE})
    preds = [forecast(k,v,*f,models[2026]) for k,v,f in cases(hold)]
    chosen = choices[2026]['method']
    for r in preds:
        r['historically_selected_ip'] = r[chosen] if r[chosen] is not None else r['accepted_ip']
    for r in preds+historical:
        k = int(r['season']),'pitcher',r['mlbam_id']
        src = (hold if k[0]==2026 else hist)[k,BASE]
        if any(r[m]!=src[m] for m in ANCHORS):
            raise ValueError('Frozen pitcher anchor changed')
    selected_scores,_ = score(audit,actual)
    scores.extend(r for r in selected_scores if r['task']=='SELECTED_EXPECTED_IP')
    return publish(a,[ref,lab,parent]+([Path(a.availability)] if a.availability else []),w,
                   dict(historical_scores=scores,historical_player_audit=audit,historical_coverage=report_coverage(audit),
                        frozen_2026_workload=preds),
                   dict(rolling_choices=choices,models=models),
                   dict(version=VERSION,status='RESEARCH_ONLY',selected_method=chosen,
                        participation_fit_origins=[y for y,m in models.items() if m is not None and m['logistic'] is not None],
                        historical_documented_forecast_rows=sum(r['availability']!='UNKNOWN' for r in historical),
                        evaluation_documented_forecast_rows=sum(r['availability']!='UNKNOWN' for r in preds),
                        evaluation_outcomes_read=False,missing_accepted_ip_historical=sum(k[1]=='pitcher' and v['OUTS'] is None for (k,_),v in hist.items()),
                        missing_accepted_ip_evaluation=sum(k[1]=='pitcher' and v['OUTS'] is None for (k,_),v in hold.items()),
                        anchors_frozen=list(ANCHORS),
                        label_report_sha256=w[str(lr)],source_forecasts_modified=False))


def evaluate(a):
    ref,lab = Path(a.run).resolve(),Path(a.labels).resolve()
    w = {}
    freeze = load(checked(ref,'forecast_freeze.json',w))
    report = load(registered(ref,'report.json',w,freeze))
    lr = checked(lab,'label_build_report.json',w)
    if report['version']!=VERSION or report['evaluation_outcomes_read'] or w[str(lr)]!=report['label_report_sha256']:
        raise ValueError('Evaluation requires the matching v1.25 research freeze')
    p = registered(ref,'frozen_2026_workload.csv',w,freeze)
    preds = list(rows(p))
    for r in preds:
        if r['season']!='2026':
            raise ValueError('Non-2026 forecast in evaluation file')
        for m in (*ANCHORS,'accepted_ip','probability','prior_probability','conditional_ip',*ARMS,'historically_selected_ip'):
            r[m] = float(r[m]) if r[m] else None
    actual = labels(checked(lab,'holdout_labels.parquet',w),2026)
    scores,audit = score(preds,actual)
    return publish(a,[ref,lab],w,dict(evaluation_scores=scores,evaluation_player_audit=audit,
                    evaluation_coverage=report_coverage(audit)),{},
                    dict(version=VERSION,status='PREVIOUSLY_REVIEWED_2026_REPORTING_ONLY',
                         selected_method=report['selected_method'],selection_uses_2026=False,
                         forecasts_modified=False,models_refitted=False))


if __name__=='__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--evaluate',action='store_true')
    p.add_argument('--reference',default='outputs/contact_workload_audit_v1_24')
    p.add_argument('--parent',default='outputs/recent_history_skills_v1_23')
    p.add_argument('--labels',default='outputs/training_labels_v1_0')
    p.add_argument('--run',default='outputs/pitcher_workload_v1_25')
    p.add_argument('--availability')
    p.add_argument('--output')
    p.add_argument('--backup-root',default='backups')
    a=p.parse_args()
    a.output=a.output or ('outputs/pitcher_workload_v1_25_evaluation' if a.evaluate else a.run)
    print(json.dumps((evaluate if a.evaluate else build)(a),indent=2))
