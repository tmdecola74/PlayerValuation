"""Export accepted 2027 pitcher projections; isolate workload sensitivity checks."""
import argparse
from hashlib import sha256
import json
import math
from pathlib import Path
import shutil

from pitcher_label_coverage_v1_26 import mlbid
from contact_workload_audit_v1_24 import rows
from recent_skill_core_v1_23 import emit
from standalone_io_v1_0 import dump, finish, start

BASE = ('accepted_ip','accepted_so','accepted_w','accepted_qs','accepted_gs')
DIAGNOSTIC = ('challenger_ip','challenger_gs')


def export(records):
    baseline, checks, seen = [], [], set()
    for r in records:
        pid=mlbid(r['mlbam_id'])
        if r['season']!='2027' or pid in seen:
            raise ValueError('Expected one 2027 preseason pitcher per MLBAM ID')
        seen.add(pid)
        v={k:float(r[k]) for k in BASE}
        v.update({k:float(r[k]) if r.get(k) not in (None,'') else None for k in DIAGNOSTIC})
        if any(x is not None and (not math.isfinite(x) or x<0) for x in v.values()):
            raise ValueError(f'Invalid projected workload/count for {pid}')
        ip,so,w,qs,gs=(v[k] for k in BASE)
        cip,cgs=(v[k] for k in DIAGNOSTIC)
        if qs>gs or 6*qs>ip+1e-8 or (ip==0 and any((so,w,qs,gs))):
            raise ValueError(f'Inconsistent accepted projection for {pid}')
        if cgs is not None and cip is None:
            raise ValueError(f'Challenger starts require challenger innings: {pid}')
        b=dict(season=2027,mlbam_id=pid,player_name=r.get('player_name',''),
               IP=ip,SO=so,W=w,QS=qs,GS=gs)
        baseline.append(b)
        diag=dict(b,challenger_ip=cip,challenger_gs=cgs,
                  accepted_k_per_9=9*so/ip if ip else None,
                  accepted_w_per_9=9*w/ip if ip else None,
                  accepted_qs_per_start=qs/gs if gs else None,
                  ip_delta=cip-ip if cip is not None else None,
                  so_if_k_rate_unchanged=so*cip/ip if ip and cip is not None else None,
                  w_if_w_rate_unchanged=w*cip/ip if ip and cip is not None else None,
                  qs_if_start_rate_unchanged=(min(qs*cgs/gs,cip/6) if gs and cgs is not None else None))
        checks.append(diag)
    if not baseline:
        raise ValueError('No 2027 preseason projections supplied')
    return baseline, checks


def run(a):
    path=Path(a.input).resolve()
    before=sha256(path.read_bytes()).hexdigest()
    base, checks=export(rows(path))
    o,b,s=start(a.output,a.backup_root,[path])
    try:
        emit(s/'pitcher_baseline_2027.csv',base)
        emit(s/'workload_sensitivity_2027.csv',checks)
        report=dict(version='1.29.0',source=str(path),source_sha256=before,
                    pitcher_rows=len(base),challenger_rows=sum(x['challenger_ip'] is not None for x in checks),
                    default_method='accepted_ip',selection_uses_2026=False,
                    valuation_integration_performed=False)
        dump(s/'report.json',report)
        return dict(report,output=str(o),backup=finish(o,b,s,{str(path):before}))
    finally:
        if s.exists():
            shutil.rmtree(s)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',required=True)
    p.add_argument('--output',default='outputs/pitcher_baseline_2027_v1_29')
    p.add_argument('--backup-root',default='backups')
    print(json.dumps(run(p.parse_args()),indent=2))
