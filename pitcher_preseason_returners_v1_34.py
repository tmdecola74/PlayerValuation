"""Read-only research replay. See --help for the evidence CSV schema."""
import argparse
import csv
from collections import Counter, defaultdict
from datetime import date
import hashlib
import json
import math
from pathlib import Path

LEGACY = 'accepted_ip'
HYBRID = 'weighted_actuals_hybrid_ip'
HALF = 'returner_guard'
RULE = 'preseason_selective'
ARMS = (LEGACY, HYBRID, HALF, RULE)
YEARS = {2023, 2024, 2025, 2026}
POSITIVE = {'ROTATION_CONFIRMED', 'ACTIVE_MLB_ROSTER'}
NEGATIVE = {'INJURED_LIST', 'OPTIONED', 'NOT_ON_ACTIVE_ROSTER', 'UNAVAILABLE', 'UNCERTAIN'}
FIELDS = ('season', 'mlbam_id', 'published_on', 'known_on',
          'forecast_as_of', 'opening_day', 'status', 'source')


def read(path, fields=()):
    with path.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        if not set(fields).issubset(reader.fieldnames or []):
            raise ValueError(f'Missing required columns in {path}')
        return list(reader)


def evidence(rows):
    latest, cutoffs, rejected = {}, {}, Counter()
    for r in rows:
        year, pid = int(r['season']), r['mlbam_id']
        status = r['status'].strip().upper()
        if (year not in YEARS or not pid.isascii() or not pid.isdigit()
                or not int(pid) or pid != str(int(pid))
                or status not in POSITIVE | NEGATIVE or not r['source'].strip()):
            raise ValueError(f'Invalid evidence identity, status, or source: {year}/{pid}')
        published, known, cutoff, opening = (
            date.fromisoformat(r[k]) for k in
            ('published_on','known_on','forecast_as_of','opening_day'))
        if cutoff.year != year or opening.year != year or cutoff > opening or published > known:
            raise ValueError(f'Invalid date order: {year}/{pid}')
        if cutoffs.setdefault(year,(cutoff,opening)) != (cutoff,opening):
            raise ValueError(f'Inconsistent forecast/Opening Day dates for {year}')
        if known >= cutoff:
            rejected[year,'ON_OR_AFTER_FORECAST_DATE'] += 1
            continue
        if published < date(year-1,10,1):
            rejected[year,'OLDER_THAN_PRESEASON_WINDOW'] += 1
            continue
        key = year,pid
        # Use publication chronology so a newly found old article cannot
        # override a newer statement. Same-day conflicts block restoration.
        prev = latest.get(key)
        if prev is None or published > prev[0]:
            latest[key] = published,[r]
        elif published == prev[0]:
            prev[1].append(r)
    return latest, rejected


def analyze(rows, latest, years):
    bins, trace, seen = defaultdict(list), [], set()
    for r in rows:
        year,pid,metric = int(r['season']),r['mlbam_id'],r['metric']
        key = year,pid,metric
        if (year not in years or metric not in {'IP','SO','W'} or key in seen
                or r['hybrid_qs'] or r['reporting_only'] != str(year==2026)
                or r['status'] != 'SCORED' or r['appearance'] not in
                {'APPEARED','NON_APPEARANCE','UNKNOWN'}):
            raise ValueError(f'Unexpected audit row: {key}')
        seen.add(key)
        actual,a,h,b = (float(r[k]) for k in ('actual',LEGACY,HYBRID,HALF))
        if any(not math.isfinite(x) or x < 0 for x in (actual,a,h,b)):
            raise ValueError(f'Invalid forecast or actual: {key}')
        eligible = r['history_cohort'] == 'ESTABLISHED_RETURNER'
        records = latest.get((year,pid),(None,[]))[1]
        states = {x['status'].strip().upper() for x in records}
        signal = ('NO_TIMELY_EVIDENCE' if not states else
                  'SUPPORTS_RETURN' if states <= POSITIVE else
                  'CONFLICT' if states & POSITIVE else 'DOES_NOT_SUPPORT_RETURN')
        selected = b if eligible and signal == 'SUPPORTS_RETURN' else h
        trace.append(dict(r, preseason_signal=signal, preseason_selective=selected,
                          evidence_status='|'.join(sorted(states)),
                          evidence_published_on=records[0]['published_on'] if records else '',
                          evidence_known_on='|'.join(sorted({x['known_on'] for x in records})),
                          forecast_as_of=records[0]['forecast_as_of'] if records else '',
                          evidence_sources=' | '.join(sorted({x['source'] for x in records}))))
        # Actual appearance is applied only after the projection is fixed.
        for cohort in ('ALL',r['history_cohort']):
            for appearance in ('ALL',r['appearance']):
                bins[year,metric,cohort,appearance].append((pid,actual,(a,h,b,selected),signal))
    if {r[0] for r in seen} != years:
        raise ValueError('Unexpected or incomplete set of seasons')
    out = []
    for (y,m,c,s), members in sorted(bins.items()):
        n = len(members)
        signature = hashlib.sha256(json.dumps(sorted(x[0] for x in members)).encode()).hexdigest()
        counts = Counter(x[3] for x in members)
        for i,arm in enumerate(ARMS):
            errors = [v[i]-a for _,a,v,_ in members]
            sse = math.fsum(e*e for e in errors)
            out.append(dict(season=y, metric=m, cohort=c, appearance=s, method=arm,
                            reporting_only=y==2026, n=n, membership_sha256=signature,
                            timely_evidence=n-counts['NO_TIMELY_EVIDENCE'],
                            positive_evidence=counts['SUPPORTS_RETURN'],
                            selective_changes=sum(v[3]!=v[1] for _,_,v,_ in members),
                            rmse=math.sqrt(sse/n),mae=math.fsum(map(abs,errors))/n,
                            bias=math.fsum(errors)/n, sse=sse,
                            delta_sse_vs_hybrid=math.fsum(
                                e*e-(v[1]-a)**2 for e,(_,a,v,_) in zip(errors,members))))
    return out, trace


def write(path, rows):
    with path.open('x', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f,fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(args):
    source = Path(args.source)
    latest, rejected = evidence(read(Path(args.evidence),FIELDS))
    out = Path(args.output)
    paths = [('historical',{2023,2024,2025}),('evaluation_2026',{2026})]
    manifest = json.loads((source/'output_sha256.json').read_text(encoding='utf-8-sig'))
    def frozen(name):
        path = source/name
        if hashlib.sha256(path.read_bytes()).hexdigest() != manifest.get(name):
            raise ValueError(f'Frozen audit checksum failed: {path}')
        return path
    ref = json.loads(frozen('report.json').read_text(encoding='utf-8-sig'))
    if ref['version'] != '1.33.0' or ref['valuation_enabled'] or ref['selection_uses_2026']:
        raise ValueError('Expected the frozen v1.33 research output')
    historical, evaluation = [
        analyze(read(frozen(f'{prefix}_returner_audit.csv')),latest,years)
        for prefix,years in paths]
    summary = dict(version='1.34.0', status='RESEARCH_ONLY',
        default_method=LEGACY, valuation_enabled=False, hybrid_qs=None,
        selection_uses_2026=False, models_refitted=False,
        excluded_evidence=[dict(season=y, reason=s, n=n) for (y,s),n in sorted(rejected.items())],
        coverage=[{k:r[k] for k in ('season','n','timely_evidence','positive_evidence','selective_changes')}
                  for scores,_ in (historical,evaluation) for r in scores
                  if r['method']==RULE and r['metric']=='IP'
                  and r['cohort']=='ESTABLISHED_RETURNER' and r['appearance']=='ALL'])
    summary['status'] = ('RESEARCH_ONLY' if any(r['selective_changes'] and r['season'] != 2026
                                              for r in summary['coverage'])
                         else 'NO_HISTORICAL_SELECTIVE_CHANGES')
    out.mkdir(parents=True,exist_ok=False)
    for (prefix,_),(scores,trace) in zip(paths,(historical,evaluation)):
        write(out/f'{prefix}_scores.csv', scores)
        write(out/f'{prefix}_player_audit.csv', trace)
    (out/'report.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(summary,indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',default='outputs/pitcher_returners_v1_33')
    p.add_argument('--output',default='outputs/pitcher_preseason_returners_v1_34')
    p.add_argument('--evidence',required=True,help='CSV columns: '+','.join(FIELDS))
    run(p.parse_args())
