"""Frozen-reference label decisions. No source counts are changed or substituted."""
from decimal import Decimal
import hashlib,json

COUNTS={'hitter':{'G','PA','AB','H','1B','2B','3B','HR','R','RBI','BB','IBB','SO','HBP','SF','SH','SB','CS'},'pitcher':{'G','GS','W','L','SV','HLD','QS','OUTS','H','ER','R','BB','IBB','SO','HR','HBP','TBF'}}
DEPS={'hitter':{'AVG':{'H','AB'},'OBP':{'H','BB','HBP','AB','SF'},'SLG':{'1B','2B','3B','HR','AB'},'OPS':{'OBP','SLG'},'ISO':{'SLG','AVG'},'BABIP':{'H','HR','AB','SO','SF'},'K%':{'SO','PA'},'BB%':{'BB','PA'},'HR_per_PA':{'HR','PA'},'SB_per_PA':{'SB','PA'}},'pitcher':{'IP':{'OUTS'},'ERA':{'ER','OUTS'},'WHIP':{'H','BB','OUTS'},'K/9':{'SO','OUTS'},'BB/9':{'BB','OUTS'},'HR/9':{'HR','OUTS'},'K%':{'SO','TBF'},'BB%':{'BB','TBF'},'K-BB%':{'K%','BB%'},'SV_plus_HLD':{'SV','HLD'}}}
ALIAS={'K':'SO'}
def primitives(role,metric):
 metric=ALIAS.get(metric,metric)
 if role not in COUNTS:raise ValueError('Unknown player role')
 if role=='hitter' and metric=='1B':return {'1B','H','2B','3B','HR'}
 if metric in COUNTS[role]:return {metric}
 if metric not in DEPS[role]:raise ValueError('Unsupported metric: '+metric)
 return set().union(*(primitives(role,m) for m in DEPS[role][metric]))
def key(season,role,pid):return (int(season),role,str(pid))
def decision(season,role,pid,metric,register,policy,purpose='training'):
 if purpose not in ('training','holdout_evaluation'):raise ValueError('Explicit training/evaluation purpose required')
 y=int(season);reasons=[]
 if purpose=='training' and y>policy['training_max_season']:reasons.append('HOLDOUT_OR_FUTURE_SEASON')
 if purpose=='holdout_evaluation' and y!=policy['holdout_season']:reasons.append('NOT_CONFIGURED_HOLDOUT')
 try:deps=primitives(role,metric)
 except ValueError:deps=set();reasons.append('UNSUPPORTED_METRIC_OR_ROLE')
 cases=[r['case_id'] for r in register if key(r['season'],r['player_type'],r['mlbam_id'])==key(y,role,pid) and r['metric'] in deps]
 if cases:reasons.append('DISPUTED_LABEL_COMPONENT')
 return dict(eligible=not reasons,source=policy['primary_season_label_source'],metric=metric,dependencies=sorted(deps),case_ids=sorted(cases),reasons=reasons,policy_version=policy['version'],purpose=purpose)
def value_of(role,metric,counts):
 m=ALIAS.get(metric,metric)
 if m in COUNTS[role]:
  if m not in counts or counts[m] is None:raise ValueError('Missing component '+m)
  n=Decimal(str(counts[m]))
  if not n.is_finite() or n<0 or n!=int(n):raise ValueError('Counts must be nonnegative integers')
  return n
 v=lambda x:value_of(role,x,counts)
 div=lambda a,b:a/b if b>0 else None
 if m in ('OPS','ISO','K-BB%'):
  a,b={'OPS':('OBP','SLG'),'ISO':('SLG','AVG'),'K-BB%':('K%','BB%')}[m];a,b=v(a),v(b)
  return None if a is None or b is None else a+b if m=='OPS' else a-b
 if m=='AVG':return div(v('H'),v('AB'))
 if m=='OBP':return div(v('H')+v('BB')+v('HBP'),v('AB')+v('BB')+v('HBP')+v('SF'))
 if m=='SLG':return div(v('1B')+2*v('2B')+3*v('3B')+4*v('HR'),v('AB'))
 if m=='BABIP':return div(v('H')-v('HR'),v('AB')-v('SO')-v('HR')+v('SF'))
 if m=='IP':return v('OUTS')/3
 if m=='ERA':return div(27*v('ER'),v('OUTS'))
 if m=='WHIP':return div(3*(v('H')+v('BB')),v('OUTS'))
 if m in ('K/9','BB/9','HR/9'):return div(27*v({'K/9':'SO','BB/9':'BB','HR/9':'HR'}[m]),v('OUTS'))
 if m in ('K%','BB%'):return div(v('SO' if m=='K%' else 'BB'),v('PA' if role=='hitter' else 'TBF'))
 if m in ('HR_per_PA','SB_per_PA'):return div(v('HR' if m=='HR_per_PA' else 'SB'),v('PA'))
 if m=='SV_plus_HLD':return v('SV')+v('HLD')
 raise ValueError('Unsupported metric')
def resolve_label(season,role,pid,metric,counts,register,policy,reference_sha256,purpose='training'):
 if reference_sha256!=policy['expected_reference_hashes']['actual_counts.parquet']:raise ValueError('Wrong frozen actuals reference hash')
 d=decision(season,role,pid,metric,register,policy,purpose);d['value']=None;d['reference_sha256']=reference_sha256
 if d['eligible']:
  try:
   if role=='hitter' and all(counts.get(m) is not None for m in ['H','AB']) and Decimal(str(counts['H']))>Decimal(str(counts['AB'])):raise ValueError('H exceeds AB')
   if role=='hitter' and all(counts.get(m) is not None for m in ['H','1B','2B','3B','HR']) and Decimal(str(counts['H']))!=sum(Decimal(str(counts[m])) for m in ['1B','2B','3B','HR']):raise ValueError('Incoherent hit components')
   n=value_of(role,metric,counts)
   if n is None:d['eligible']=False;d['reasons'].append('ZERO_OR_INVALID_DENOMINATOR')
   else:d['value']=float(n)
  except (ValueError,KeyError,ArithmeticError):d['eligible']=False;d['reasons'].append('MISSING_OR_INVALID_COMPONENT')
 return d
def resolve_bundle(season,role,pid,metrics,counts,register,policy,reference_sha256,purpose='training'):
 rows=[resolve_label(season,role,pid,m,counts,register,policy,reference_sha256,purpose) for m in metrics]
 eligible=all(r['eligible'] for r in rows)
 return dict(eligible=eligible,labels=rows,values={r['metric']:r['value'] for r in rows} if eligible else None)

def verified_reference_sha256(path,policy):
 from pathlib import Path
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 value=h.hexdigest()
 if value!=policy['expected_reference_hashes']['actual_counts.parquet']:raise ValueError('Actuals file does not match frozen reference')
 return value
