"""Replay one fixed preseason role rule on matched v1.27 score cohorts."""
import argparse
from collections import defaultdict
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import shutil
import tempfile

BASE, TWO, HYBRID = 'accepted_ip', 'two_part_ip', 'role_hybrid_ip'
ROLES = ('STARTER', 'RELIEVER', 'SWING', 'UNKNOWN')
METRICS = ('mse', 'mae', 'bias', 'mean_forecast', 'mean_actual')
YEARS = range(2020, 2026)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(root, filename, verified=True):
    data = (root / filename).read_bytes()
    if verified:
        manifest = json.loads((root / 'output_sha256.json').read_bytes())
        if manifest.get(filename) != sha(data):
            raise ValueError(f'Checksum mismatch: {root / filename}')
    return data


def source(root, path=None, evaluation=False):
    if path is not None:
        data = path.read_bytes()
        return data, dict(csv=str(path.resolve()), csv_sha256=sha(data), verification='SUPPLIED_CSV')
    name = 'evaluation_scores.csv' if evaluation else 'historical_scores.csv'
    report_bytes = read(root,'report.json')
    report = json.loads(report_bytes)
    if report['version'] != '1.27.0':
        raise ValueError('Require the v1.27 source')
    if evaluation and (report['status'] != 'PREVIOUSLY_REVIEWED_2026_REPORTING_ONLY'
                       or report['selection_uses_2026'] is not False or report['models_refitted'] is not False):
        raise ValueError('Require a reporting-only evaluation')
    if not evaluation and report['evaluation_outcomes_read'] is not False:
        raise ValueError('Require a historical run that did not read holdout outcomes')
    data = read(root,name)
    if not evaluation:
        freeze = json.loads(read(root,'forecast_freeze.json'))
        if freeze.get(name) != sha(data) or freeze.get('report.json') != sha(report_bytes):
            raise ValueError('Historical scores not bound to the forecast freeze')
    return data, dict(csv=str((root/name).resolve()),csv_sha256=sha(data),
                      report_sha256=sha(report_bytes),verification='V1_27_MANIFEST',
                      overlay=report['participation_label_overlay'],
                      confirmed_non_appearances=report.get('holdout_confirmed_non_appearances'),
                      unlabeled_participation=report.get('holdout_unlabelled_participation'))


def aggregate(data, years):
    index = defaultdict(dict)
    for r in csv.DictReader(io.StringIO(data.decode('utf-8-sig'),newline='')):
        year = int(r['season'])
        if year not in years:
            if year == 2019 and 2020 in years:
                continue
            raise ValueError(f'Unexpected year {year}')
        if r['task'] != 'EXPECTED_IP' or r['method'] not in (BASE,TWO):
            continue
        if r['dimension']=='ALL' and r['cohort']=='ALL':
            cohort = 'ALL'
        elif r['dimension']=='PRIOR_ROLE' and r['cohort'] in ROLES:
            cohort = r['cohort']
        else:
            continue
        key = cohort,r['method']
        if key in index[year]:
            raise ValueError(f'Duplicate score: {year}/{key}')
        v = dict(n=int(r['n']), membership_sha256=r['membership_sha256'],
                 **{k:float(r[k]) for k in METRICS})
        if (v['n'] <= 0 or len(v['membership_sha256']) != 64
                or not all(math.isfinite(v[k]) for k in METRICS)
                or v['mse'] < 0 or v['mae'] < 0):
            raise ValueError(f'Invalid score: {year}/{key}')
        index[year][key] = v

    result = []
    for year in years:
        scores = index[year]
        for cohort in ('ALL',*ROLES):
            a,b = scores[cohort,BASE],scores[cohort,TWO]
            if (a['n'],a['membership_sha256'],a['mean_actual']) != (b['n'],b['membership_sha256'],b['mean_actual']):
                raise ValueError(f'Unmatched rows: {year}/{cohort}')
        def combine(arm):
            parts = [scores[c,arm(c)] for c in ROLES]
            n = sum(v['n'] for v in parts)
            return dict(n=n,**{k:math.fsum(v['n']*v[k] for v in parts)/n for k in METRICS})
        for method in (BASE,TWO):
            rolled, original = combine(lambda _:method), scores['ALL',method]
            if rolled['n'] != original['n'] or any(
                not math.isclose(rolled[k],original[k],rel_tol=1e-10,abs_tol=1e-10) for k in METRICS
            ):
                raise ValueError(f'Role groups do not reproduce the overall score: {year}/{method}')
        def rule(role):
            return BASE if role=='STARTER' else TWO
        h = combine(rule)
        for c in ('ALL',*ROLES):
            for m in (BASE,TWO,HYBRID):
                v = (h if c=='ALL' else scores[c,rule(c)]) if m==HYBRID else scores[c,m]
                result.append(dict(season=year,cohort=c,method=m,n=v['n'],
                                   **{k:v[k] for k in METRICS},rmse=math.sqrt(v['mse']),
                                   source_membership_sha256=scores[c,BASE]['membership_sha256']))
    return result


def gates(scores, year):
    ix = {(r['season'],r['cohort'],r['method']):r['mse'] for r in scores if r['season']<year}
    out = {}
    for c,limit in [('ALL',.99),('STARTER',1.01)]:
        ratios = {y:ix[y,c,HYBRID]/ix[y,c,BASE] for y in YEARS
                  if (y,c,HYBRID) in ix and ix[y,c,BASE]>0}
        mean = math.fsum(ratios.values())/len(ratios) if ratios else None
        out[c] = dict(ratios=ratios,mean=mean,limit=limit,passed=len(ratios)>=3 and mean<=limit)
    return dict(eligible_under_innings_gates=all(v['passed'] for v in out.values()), gates=out)


def run(a):
    h, hs = source(a.run,a.historical_scores)
    scores = aggregate(h,YEARS)
    report = dict(version='1.28.0',status='RESEARCH_ONLY',default_method=BASE,
                  default_changed=False,models_refitted=False,history=hs,
                  historical_rule='STARTER uses accepted_ip; RELIEVER, SWING and UNKNOWN use two_part_ip',
                  historical_scored_years=list(YEARS),unscored_origin_2019='NO_EARLIER_TRAINING_FOLD',
                  retrospective_rule_chosen_after_reviewing_2020_2025=True,
                  rolling_checks={y:gates(scores,y) for y in range(2020,2027)})
    evaluation = None
    if a.evaluation_run is not None:
        e, es = source(a.evaluation_run,evaluation=True)
        if hs.get('overlay') is not None and hs['overlay'] != es['overlay']:
            raise ValueError('2026 evaluation uses a different label overlay')
        evaluation = aggregate(e,(2026,))
        report['evaluation'] = dict(es,status='REPORTING_ONLY_KNOWN_OUTCOMES',
                                    participation_scored_by_hybrid=False,selection_uses_2026=False)
    else:
        report['evaluation'] = dict(status='NOT_RUN',selection_uses_2026=False)
    output = a.output.resolve()
    if output.exists():
        raise FileExistsError(f'Choose a new output directory: {output}')
    output.parent.mkdir(parents=True,exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=output.name+'.',dir=output.parent))
    try:
        for name,records in [('historical_hybrid_scores.csv',scores),('evaluation_2026_hybrid_scores.csv',evaluation)]:
            if records is not None:
                with (stage/name).open('w',encoding='utf-8',newline='') as f:
                    w=csv.DictWriter(f,fieldnames=list(records[0]))
                    w.writeheader()
                    w.writerows(records)
        (stage/'report.json').write_text(json.dumps(report,indent=2,allow_nan=False)+'\n',encoding='utf-8')
        stage.rename(output)
    finally:
        if stage.exists():
            shutil.rmtree(stage)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,default=Path('outputs/pitcher_workload_v1_27'))
    p.add_argument('--historical-scores',type=Path,help='Explicit standalone historical CSV, with recorded SHA-256')
    p.add_argument('--evaluation-run',type=Path,help='Optional verified v1.27 reporting-only evaluation directory')
    p.add_argument('--output',type=Path,default=Path('outputs/pitcher_role_hybrid_v1_28'))
    report=run(p.parse_args())
    print(json.dumps({k:v for k,v in report.items() if k!='rolling_checks'} |
                     {'final_historical_check':report['rolling_checks'][2026]},indent=2))
