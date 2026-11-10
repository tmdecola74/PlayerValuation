"""Independent semantic audit of v1.13 originals, candidate and full ledger."""
import csv,json,math
from collections import Counter,defaultdict
from projection_release_v1_11_1 import METRICS,finite
from consensus_policy_v1_13 import POLICY,CANDIDATE
from projection_release_audit_v1_12 import primitive_provenance

SUPPORTED='SUPPORTED_RECONCILED_CONSENSUS_V1_14'
EPS=POLICY['numerical_epsilon']
ANCHORS={'hitter':['H','AB','2B','3B','HR','BB','HBP','SF','SH','R','RBI','SB'],'pitcher':['IP','OUTS','H','ER','BB','SO','HR','W','SV','HLD','QS']}

def near(x,y):return x is None and y is None or finite(x) and finite(y) and abs(x-y)<=EPS*max(1,abs(x),abs(y))
def num(v):
 if v in ['',None]:return None
 x=float(v)
 if not finite(x):raise ValueError('Nonfinite ledger value')
 return x

def independent_expected(role,old):
 v={m:old.get(m) for m in METRICS[role]}
 if role=='hitter':
  if all(finite(old.get(m)) for m in ['H','1B','2B','3B','HR']):
   single=old['H']-old['2B']-old['3B']-old['HR']
   if abs(single-old['1B'])>EPS:v['1B']=single
  parts=['AB','BB','HBP','SF','SH']
  if finite(old.get('PA')) and all(finite(old.get(m)) for m in parts):
   total=sum(old[m] for m in parts)
   if total-old['PA']>EPS:v['PA']=total
  if v['H'] is None and all(finite(v.get(m)) for m in ['1B','2B','3B','HR']):v['H']=sum(v[m] for m in ['1B','2B','3B','HR'])
  v['AVG']=v['H']/v['AB'] if finite(v['H']) and finite(v['AB']) and v['AB']>0 else None
  parts=['H','BB','HBP','AB','SF']
  den=sum(v[m] for m in ['AB','BB','HBP','SF']) if all(finite(v.get(m)) for m in parts) else None
  v['OBP']=(v['H']+v['BB']+v['HBP'])/den if den is not None and den>0 else None
  v['SLG']=(v['1B']+2*v['2B']+3*v['3B']+4*v['HR'])/v['AB'] if all(finite(v.get(m)) for m in ['1B','2B','3B','HR','AB']) and v['AB']>0 else None
  v['OPS']=v['OBP']+v['SLG'] if finite(v['OBP']) and finite(v['SLG']) else None
 else:
  if v['SO'] is None and finite(old.get('K')):v['SO']=old['K']
  if v['OUTS'] is None and finite(v['IP']):v['OUTS']=3*v['IP']
  if v['IP'] is None and finite(v['OUTS']):v['IP']=v['OUTS']/3
  v['ERA']=9*v['ER']/v['IP'] if finite(v['ER']) and finite(v['IP']) and v['IP']>0 else None
  v['WHIP']=(v['H']+v['BB'])/v['IP'] if all(finite(v.get(m)) for m in ['H','BB','IP']) and v['IP']>0 else None
  v['SV_plus_HLD']=v['SV']+v['HLD'] if finite(v['SV']) and finite(v['HLD']) else None
 return v

def audit(originals,candidates,ledger_path,provenance,policy_hash):
 originals_by={};by={};failures=[];summary=defaultdict(lambda:dict(rows=0,changed=0,derived_without_original=0,maximum_absolute_delta=0.,worst_player=None,worst_player_id=None,worst_original_value=None,worst_candidate_value=None));anchor_rows=0;cap_checks=0;prov_checks=0
 def issue(key,metric,reason):failures.append(dict(player_type=key[0],player_id=key[1],metric=metric,reason=reason))
 for r in originals:
  k=r['player_type'],r['player_id']
  if k in originals_by:raise ValueError('Duplicate original consensus')
  originals_by[k]=r
 for r in candidates:
  k=r['player_type'],r['player_id']
  if k in by or k not in originals_by:raise ValueError('Duplicate/orphan candidate')
  by[k]=r;role=k[0];old=originals_by[k]['metrics']
  if r.get('projection_key')!=f'{CANDIDATE}:2026:{role}:{k[1]}':issue(k,'','CANDIDATE_PROJECTION_KEY_MISMATCH')
  mids={str(x).strip() for x in originals_by[k].get('mlbam_ids',[])}
  if r.get('mlbam_id') and mids and r['mlbam_id'] not in mids:issue(k,'','CANDIDATE_MLBAM_CONFLICTS_WITH_ORIGINAL')
  expected=independent_expected(role,old)
  if r['projection_source']!=CANDIDATE or r['season']!=2026:issue(k,'','CANDIDATE_SOURCE_OR_SEASON_MISMATCH')
  for m in METRICS[role]:
   value=r.get(m)
   if value is not None and (not finite(value) or value<0):issue(k,m,'INVALID_CANDIDATE_COMPONENT')
   if not near(value,expected.get(m)):issue(k,m,'INDEPENDENT_ARITHMETIC_REPLAY_MISMATCH')
  for m in ANCHORS[role]:
   if old.get(m) is not None:
    anchor_rows+=1
    if r.get(m)!=old[m]:issue(k,m,'PUBLISHED_ANCHOR_NOT_PRESERVED_EXACTLY')
  if role=='hitter':
   for metric,cap,parts in [('1B',POLICY['max_absolute_single_change'],['H','1B','2B','3B','HR']),('PA',POLICY['max_PA_increase'],['PA','AB','BB','HBP','SF','SH'])]:
    if finite(old.get(metric)) and finite(r.get(metric)):
     delta=r[metric]-old[metric];cap_checks+=1
     if abs(delta)>cap+EPS or metric=='PA' and delta < -EPS:issue(k,metric,'COUNT_CHANGE_OUTSIDE_FIXED_POLICY')
     if abs(delta)>EPS:
      prov_checks+=1;parsed=[]
      for m in parts:
       p,status=primitive_provenance(provenance.get((role,k[1],m)))
       if p is None:issue(k,metric,'MATERIAL_REPAIR_WITHOUT_PRIMITIVE_PROVENANCE');break
       w,v=p
       if not near(sum(w[s]*v[s] for s in w),old.get(m)):issue(k,m,'PROVENANCE_MEAN_DOES_NOT_REPLAY_ORIGINAL')
       parsed.append(w)
      if len(parsed)==len(parts):
       first=parsed[0]
       if any(set(w)!=set(first) or any(abs(w[s]-first[s])>1e-8 for s in first) for w in parsed[1:]):issue(k,metric,'MATERIAL_REPAIR_CHANGED_SOURCE_POOL_OR_WEIGHTS')
   if finite(r.get('H')) and finite(r.get('AB')) and r['H']>r['AB']+1e-8:issue(k,'H','H_EXCEEDS_AB')
   if all(finite(r.get(m)) for m in ['PA','AB','BB','HBP','SF','SH']) and sum(r[m] for m in ['AB','BB','HBP','SF','SH'])>r['PA']+1e-8:issue(k,'PA','PA_COMPONENT_BUDGET_INVALID')
  else:
   if finite(r.get('H')) and finite(r.get('HR')) and r['HR']>r['H']+1e-8:issue(k,'HR','HR_EXCEEDS_H')
   if finite(r.get('OUTS')) and finite(r.get('IP')) and not near(r['OUTS'],3*r['IP']):issue(k,'IP','OUTS_IP_IDENTITY_INVALID')
 expected_keys={(role,pid,m) for role,pid in by for m in METRICS[role]};seen=set()
 with open(ledger_path,encoding='utf-8-sig',newline='') as stream:
  for row in csv.DictReader(stream):
   key=row['player_type'],row['player_id'];metric=row['metric'];token=key+(metric,)
   if token in seen or token not in expected_keys:issue(key,metric,'DUPLICATE_OR_ORPHAN_LEDGER_ROW');continue
   seen.add(token);old=originals_by[key]['metrics'];candidate=by[key];before=old.get(metric);after=candidate.get(metric)
   try:
    ob,cv,delta=map(num,[row['original_value'],row['candidate_value'],row['delta']])
    if row['changed'] not in ['True','False'] or row['original_present'] not in ['True','False']:raise ValueError('Invalid flag')
   except (ValueError,KeyError):issue(key,metric,'INVALID_LEDGER_VALUE_OR_FLAG');continue
   changed=before!=after
   if not near(ob,before) or not near(cv,after) or not near(delta,after-before if finite(before) and finite(after) else None):issue(key,metric,'LEDGER_VALUES_OR_DELTA_DO_NOT_MATCH_SNAPSHOTS')
   if (row['changed']=='True')!=changed or (row['original_present']=='True')!=(metric in old):issue(key,metric,'LEDGER_CHANGE_OR_PRESENCE_FLAG_MISMATCH')
   if row.get('policy_version')!=POLICY['version'] or row.get('policy_sha256')!=policy_hash:issue(key,metric,'LEDGER_POLICY_BINDING_MISMATCH')
   s=summary[key[0],metric];s['rows']+=1;s['changed']+=changed;s['derived_without_original']+=changed and before is None and after is not None
   if finite(before) and finite(after) and abs(after-before)>s['maximum_absolute_delta']:s['maximum_absolute_delta']=abs(after-before);s['worst_player']=originals_by[key]['name'];s['worst_player_id']=key[1];s['worst_original_value']=before;s['worst_candidate_value']=after
 for role,pid,m in expected_keys-seen:issue((role,pid),m,'MISSING_LEDGER_ROW')
 rows=[dict(player_type=k[0],metric=k[1],**v) for k,v in sorted(summary.items())]
 report=dict(audit_pass=not failures,candidate_rows=len(by),ledger_expected_rows=len(expected_keys),ledger_observed_unique_rows=len(seen),published_anchor_checks=anchor_rows,count_cap_checks=cap_checks,material_repair_provenance_checks=prov_checks,failure_rows=len(failures),failure_reasons=dict(Counter(r['reason'] for r in failures)))
 return report,rows,failures
