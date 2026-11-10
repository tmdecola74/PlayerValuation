"""Fixed arithmetic research candidate. Never modifies a frozen source."""
import json,math,copy
from projection_release_v1_11_1 import METRICS,finite,consensus_vector
from projection_release_audit_v1_12 import decompose,EQUATIONS

POLICY=dict(version='1.13.0',candidate_only=True,max_absolute_single_change=1.0,max_PA_increase=1.0,numerical_epsilon=1e-9,singles_rule='H_MINUS_2B_3B_HR',PA_rule='RAISE_TO_COMPONENT_SUM_ONLY_WHEN_BELOW',provenance_rule='REQUIRE_REPLAY_AND_COMMON_POOL_WEIGHTS_FOR_MATERIAL_COUNT_REPAIRS',selection='FIXED_ARITHMETIC_NO_OUTCOME_SELECTION')
CANDIDATE='CONSENSUS_RECONCILED_CANDIDATE_V1_13'

def checked(policy):
 if policy!=POLICY:raise ValueError('Unsupported policy: preserve v1.13.0 and use a new version to revise its rules')
 return policy

def reconcile(record,provenance,policy):
 policy=checked(policy);original=record['metrics'];role=record['player_type'];v=copy.deepcopy(original);reasons={};decisions=[];eps=policy['numerical_epsilon']
 def reject(reason):return None,[],dict(status='QUARANTINED',reason=reason,provenance_checks_json=json.dumps(decisions,sort_keys=True))
 def guard(equation):
  d,_=decompose(original,provenance,EQUATIONS['hitter'][equation]);decisions.append(dict(equation=equation,**d))
  return d['status']=='DECOMPOSED' and not d.get('source_pools_differ') and not d.get('common_pool_weights_differ')
 if any(value is not None and (not finite(value) or value<0) for m,value in v.items() if m in METRICS[role]):return reject('INVALID_PRIMITIVE_OR_RELEASED_VALUE')
 if role=='hitter':
  names=['H','1B','2B','3B','HR']
  if all(finite(v.get(n)) for n in names):
   single=v['H']-v['2B']-v['3B']-v['HR'];delta=single-v['1B']
   if single<0 and abs(delta)>eps:return reject('NEGATIVE_DERIVED_SINGLE_NO_CLIPPING')
   if abs(delta)>policy['max_absolute_single_change']+eps:return reject('SINGLE_ADJUSTMENT_EXCEEDS_POLICY_CAP')
   if abs(delta)>eps and not guard('H_MINUS_HIT_TYPES'):return reject('HIT_COMPONENT_PROVENANCE_REQUIRES_REVIEW')
   if abs(delta)>eps:v['1B']=single;reasons['1B']='DERIVED_SINGLES_KEEP_PUBLISHED_H_2B_3B_HR'
  parts=['AB','BB','HBP','SF','SH']
  if finite(v.get('PA')) and all(finite(v.get(n)) for n in parts):
   total=sum(v[n] for n in parts);increase=total-v['PA']
   if increase>policy['max_PA_increase']+eps:return reject('PA_INCREASE_EXCEEDS_POLICY_CAP')
   if increase>eps:
    if increase>eps and not guard('PA_MINUS_COMPONENTS'):return reject('PA_COMPONENT_PROVENANCE_REQUIRES_REVIEW')
    v['PA']=total;reasons['PA']='RAISED_PA_TO_PUBLISHED_COMPONENT_BUDGET'
  # Positive PA remainder is retained; missing counts are not imputed.
 try:result=consensus_vector(role,v)
 except ValueError as error:return reject('UNRESOLVED_COMPONENT_CONSTRAINT: '+str(error))
 # Preserve anchors exactly, including any floating-point difference from a sum.
 if role=='hitter' and finite(original.get('H')):
  result['H']=original['H'];result['AVG']=result['H']/result['AB'] if finite(result.get('AB')) and result['AB']>0 else None
  if all(finite(result.get(n)) for n in ['H','BB','HBP','AB','SF']):
   den=result['AB']+result['BB']+result['HBP']+result['SF'];result['OBP']=(result['H']+result['BB']+result['HBP'])/den if den>0 else None
  result['OPS']=result['OBP']+result['SLG'] if finite(result.get('OBP')) and finite(result.get('SLG')) else None
 if role=='pitcher' and finite(original.get('IP')):
  result['IP']=original['IP'];result['ERA']=9*result['ER']/result['IP'] if finite(result.get('ER')) and result['IP']>0 else None;result['WHIP']=(result['H']+result['BB'])/result['IP'] if all(finite(result.get(n)) for n in ['H','BB']) and result['IP']>0 else None
 for m in ['H','AB','HR','2B','3B','BB','HBP','SF','SH','R','RBI','SB'] if role=='hitter' else ['IP','OUTS','H','ER','BB','SO','HR','W','SV','HLD','QS']:
  if m in original and original[m] is not None and result.get(m)!=original[m]:return reject('PUBLISHED_ANCHOR_CHANGED: '+m)
 ledger=[]
 for m in METRICS[role]:
  before=original.get(m);after=result.get(m);changed=before!=after
  ledger.append(dict(metric=m,original_present=m in original,original_value=before,candidate_value=after,delta=after-before if finite(before) and finite(after) else None,changed=changed,reason=reasons.get(m,'DERIVED_FROM_CANDIDATE_COMPONENTS_OR_ALIAS' if changed else 'UNCHANGED'),policy_version=policy['version']))
 return result,ledger,dict(status='CANDIDATE_AVAILABLE',reason='FIXED_ARITHMETIC_POLICY_NOT_ADOPTED',provenance_checks_json=json.dumps(decisions,sort_keys=True))
