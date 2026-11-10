"""Preseason-source population and coverage; no target-season labels accepted."""
import csv,json,datetime
from collections import defaultdict
from pathlib import Path
from projection_release_v1_11_1 import HOME,CONS,finite,mid,sha,csvrows

CUTOFF='2026-03-24'
EVIDENCE_FIELDS=['season','player_type','player_id','mlbam_id','name','preseason_class','effective_date','evidence_as_of','date_basis','source','source_record_id','evidence_reference','notes']
CLASSES={'prospect','international_arrival','returner','established_mlb','unknown'}

def dated_evidence(path,catalog,names):
 if path is None:return [],{}
 path=Path(path).resolve();rows=csvrows(path);result=[];seen=set();reverse={m:p for p,m in catalog.items()}
 with path.open(encoding='utf-8-sig',newline='') as stream:
  if set(csv.DictReader(stream).fieldnames or [])!=set(EVIDENCE_FIELDS):raise ValueError('Preseason evidence must use the exact versioned schema; no target outcome columns')
 for r in rows:
  if r['season']!='2026' or r['player_type'] not in ['hitter','pitcher'] or r['preseason_class'] not in CLASSES:raise ValueError('Invalid preseason evidence season, role or class')
  for n in ['effective_date','evidence_as_of']:
   try:date=datetime.date.fromisoformat(r[n])
   except (ValueError,TypeError):raise ValueError('Invalid evidence date: '+n)
   if date.isoformat()>CUTOFF:raise ValueError('Evidence postdates preseason cutoff; cannot determine inclusion')
  if r['date_basis'] not in ['ARCHIVED_AS_OF_CLAIM','USER_CONFIRMED_PRESEASON_EFFECTIVE']:raise ValueError('Explicit evidence date basis required')
  if not all(r[n].strip() for n in ['source','source_record_id','evidence_reference']):raise ValueError('Evidence source, record and reference required')
  pid=r['player_id'].strip() or None;mlbam=mid(r['mlbam_id']) if r['mlbam_id'].strip() else None
  if r['mlbam_id'].strip() and mlbam is None:raise ValueError('Invalid MLBAM evidence ID')
  if pid and pid not in names:raise ValueError('Evidence canonical ID not in frozen warehouse')
  if pid in catalog and mlbam and catalog[pid]!=mlbam:raise ValueError('Evidence identity conflicts with canonical mapping')
  if mlbam in reverse and pid and reverse[mlbam]!=pid:raise ValueError('Evidence MLBAM ownership conflicts')
  pid=pid or reverse.get(mlbam);mlbam=catalog.get(pid) or mlbam
  if not pid and not mlbam:raise ValueError('Evidence needs canonical or MLBAM identity; no name matching')
  key=r['player_type'],pid or 'MLBAM:'+mlbam,r['source'],r['source_record_id']
  if key in seen:raise ValueError('Duplicate preseason evidence record')
  seen.add(key);result.append(dict(r,player_id=pid,mlbam_id=mlbam))
 return result,{str(path):sha(path)}

def assemble_universe(original,records,candidates,assets,training,features,catalog,names,evidence):
 reverse={m:p for p,m in catalog.items()};universe={};evidence_rows=[]
 def add(role,pid=None,mlbam=None,nfbc=None,name=None,reason=None):
  if mlbam:pid=pid or reverse.get(mlbam)
  mlbam=catalog.get(pid) or mlbam;token=pid or ('MLBAM:'+mlbam if mlbam else 'NFBC:'+str(nfbc))
  key=role,token
  if key not in universe:universe[key]=dict(season=2026,player_type=role,universe_id=role+':'+token,player_id=pid,mlbam_id=mlbam,name=name or names.get(pid) or ('MLBAM '+mlbam if mlbam else 'NFBC '+str(nfbc)),reasons=set(),assets=set(),prior=set(),classes=set(),home=False,home_ready=False,original=False,original_ready=False,candidate=False,candidate_ready=False,features=False,dated=False)
  r=universe[key]
  if reason:r['reasons'].add(reason)
  return r
 # Historical reference rows do not imply 2026 availability or an active roster.
 for x in training:
  y=int(x['season']);role=x['player_type'];mlbam=str(x['mlbam_id'])
  if not 2015<=y<=2025 or role not in ['hitter','pitcher'] or mid(mlbam)!=mlbam:raise ValueError('Future/invalid historical universe input')
  add(role,mlbam=mlbam,reason='PRIOR_MLB_REFERENCE_ROW')['prior'].add(y)
 for x in features:
  if x['player_type'] not in ['hitter','pitcher'] or mid(str(x['mlbam_id']))!=str(x['mlbam_id']) or int(x['target_season'])!=2026 or int(x['max_source_season'])>=2026 or str(x['source_cutoff'])>='2026-01-01' or any(n.startswith('y_') for n in x):raise ValueError('Target outcomes or future history in universe feature input')
  add(x['player_type'],mlbam=str(x['mlbam_id']),reason='FROZEN_PRESEASON_FEATURE_POPULATION')['features']=True
 for x in original:
  if int(x['season'])!=2026:raise ValueError('Wrong preseason projection season')
  add(x['player_type'],pid=x['player_id'],mlbam=catalog.get(x['player_id']),name=x['name'],reason='PUBLISHED_PRESEASON_PROJECTION')['original']=True
 for x in records:
  r=add(x['player_type'],pid=x['player_id'],mlbam=x['mlbam_id'],name=x['name'],reason='FROZEN_HOMEGROWN_FORECAST' if x['projection_source']==HOME else 'ORIGINAL_COHERENT_CONSENSUS_EXPORT')
  if x['projection_source']==HOME:r['home']=True;r['home_ready']=x['valuation_ready']
  elif x['projection_source']==CONS:r['original_ready']=x['valuation_ready']
 for x in candidates:
  r=add(x['player_type'],pid=x['player_id'],mlbam=x['mlbam_id'],name=x['name']);r['candidate']=True;r['candidate_ready']=x['valuation_ready']
 for x in assets:
  r=add(x['player_type'],pid=x['player_id'],mlbam=x['mlbam_id'],nfbc=x['nfbc_player_id'],name=x['name'],reason='REVIEWED_NFBC_PRESEASON_ASSET');r['assets'].add(x['nfbc_player_id'])
 for x in evidence:
  r=add(x['player_type'],pid=x['player_id'],mlbam=x['mlbam_id'],name=x['name'],reason='DATED_PRESEASON_EVIDENCE');r['dated']=True;r['classes'].add(x['preseason_class']);evidence_rows.append(dict(universe_id=r['universe_id'],**x))
 out=[]
 for key,r in sorted(universe.items()):
  role,token=key;other='pitcher' if role=='hitter' else 'hitter';opposite=universe.get((other,token));other_years=sorted(opposite['prior']) if opposite else [];prior=sorted(r['prior']);preseason=r['original'] or r['home'] or bool(r['assets']) or r['dated'];known={x for x in r['classes'] if x!='unknown'}
  if not r['player_id'] and not r['mlbam_id']:stratum='IDENTITY_UNRESOLVED'
  elif len(known)>1:stratum='CONFLICTING_PRESEASON_CLASSES_REVIEW'
  elif known:stratum='DOCUMENTED_'+next(iter(known)).upper()
  elif not preseason:stratum='HISTORICAL_OR_FEATURE_ONLY_NO_CURRENT_PRESEASON_EVIDENCE'
  elif prior and max(prior)<=2022:stratum='RETURNER_CANDIDATE_OLDER_HISTORY'
  elif prior:stratum='PRIOR_MLB_ROLE_HISTORY'
  elif other_years:stratum='OTHER_ROLE_HISTORY_REVIEW'
  else:stratum='COLD_START_UNCLASSIFIED_PRESEASON_SOURCE'
  missing_home=not r['home'];coverage='HOMEGROWN_AVAILABLE' if r['home'] else 'NO_HOMEGROWN_RECONCILED_CONSENSUS_CANDIDATE_AVAILABLE' if r['candidate_ready'] else 'NO_HOMEGROWN_OR_USABLE_RECONCILED_CANDIDATE'
  out.append(dict(season=2026,universe_id=r['universe_id'],player_type=role,player_id=r['player_id'],mlbam_id=r['mlbam_id'],name=r['name'],effective_date=CUTOFF,preseason_evidence_present=preseason,preseason_stratum=stratum,inclusion_reasons_json=json.dumps(sorted(r['reasons'])),nfbc_asset_ids_json=json.dumps(sorted(r['assets'])),prior_role_seasons_json=json.dumps(prior),other_role_seasons_json=json.dumps(other_years),declared_classes_json=json.dumps(sorted(r['classes'])),homegrown_forecast_present=r['home'],homegrown_basic_valuation_ready=r['home_ready'],original_consensus_present=r['original'],original_consensus_basic_valuation_ready=r['original_ready'],reconciled_candidate_present=r['candidate'],reconciled_candidate_basic_valuation_ready=r['candidate_ready'],feature_row_present=r['features'],coverage_status=coverage,prospect_or_international_status='DOCUMENTED_CLASS_CLAIM' if known else 'UNKNOWN_NO_CATEGORY_GUESS',date_basis='USER_CONFIRMED_PRESEASON_SOURCE_DATES_PLUS_PRIOR_EVENT_HISTORY; RETROSPECTIVE_RETRIEVAL'))
 assets_out=[]
 bycanonical={(r['player_type'],r['player_id']):r for r in out if r['player_id']};bymid={(r['player_type'],r['mlbam_id']):r for r in out if r['mlbam_id']}
 for x in assets:
  r=bycanonical.get((x['player_type'],x['player_id'])) if x['player_id'] else bymid.get((x['player_type'],x['mlbam_id'])) if x['mlbam_id'] else next(r for r in out if r['universe_id']==x['player_type']+':NFBC:'+x['nfbc_player_id'])
  assets_out.append(dict(**x,universe_id=r['universe_id'],coverage_status=r['coverage_status'],homegrown_forecast_present=r['homegrown_forecast_present'],reconciled_candidate_basic_valuation_ready=r['reconciled_candidate_basic_valuation_ready']))
 return out,assets_out,evidence_rows
