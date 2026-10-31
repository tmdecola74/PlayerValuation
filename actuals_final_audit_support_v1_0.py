"""Shared import, scoring rules and immutable MLB evidence helpers."""
from __future__ import annotations
import csv
import hashlib
import json
import math
import os
import shutil
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

VERSION='1.0.1'
HITTER_COUNTS=['G','PA','AB','H','1B','2B','3B','HR','R','RBI','SB','CS','BB','IBB','SO','HBP','SF','SH']
PITCHER_COUNTS=['W','L','SV','G','GS','TBF','H','R','ER','HR','BB','IBB','HBP','SO','HLD','QS']
PA_EVENTS={'single','double','triple','home_run','walk','intent_walk','hit_by_pitch','strikeout','strikeout_double_play','field_out','force_out','grounded_into_double_play','fielders_choice','fielders_choice_out','field_error','double_play','triple_play','sac_fly','sac_bunt','sac_fly_double_play','sac_bunt_double_play','catcher_interf'}
NON_PA_EVENTS={'truncated_pa','pickoff_1b','pickoff_2b','pickoff_3b','caught_stealing_2b','caught_stealing_3b','caught_stealing_home','pickoff_caught_stealing_2b','pickoff_caught_stealing_3b','pickoff_caught_stealing_home','stolen_base_2b','stolen_base_3b','stolen_base_home','other_advance','wild_pitch','passed_ball','balk','pickoff_error_1b','pickoff_error_2b','pickoff_error_3b','other_out','runner_double_play','cs_double_play','defensive_indiff'}
KS={'strikeout','strikeout_double_play'}
BBS={'walk','intent_walk'}
ADVANTAGE={(2,0),(2,1),(3,0),(3,1),(3,2)}
H_METRICS=['PA','AB','H','1B','2B','3B','HR','BB','IBB','SO','HBP','SF','SH']
P_METRICS=['TBF','H','HR','BB','IBB','SO','HBP']
SUPPORTED={'hitter':H_METRICS,'pitcher':P_METRICS}
ALL_METRICS={'hitter':HITTER_COUNTS,'pitcher':PITCHER_COUNTS+['OUTS']}


def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def now():return datetime.now(timezone.utc).isoformat()
def lit(v):return "'"+str(v).replace("'","''")+"'"
def ident(v):return '"'+str(v).replace('"','""')+'"'
def dump(path,obj):Path(path).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')
def csv_out(path,rows,fields):
 with Path(path).open('w',newline='',encoding='utf-8') as f:
  writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)

def integer(value,label):
 try:v=Decimal(str(value).strip())
 except InvalidOperation:raise ValueError(f'{label}: invalid integer {value!r}') from None
 if not v.is_finite() or v<0 or v!=v.to_integral_value():raise ValueError(f'{label}: invalid nonnegative integer {value!r}')
 return int(v)

def innings_outs(value):
 text=str(value).strip()
 # Baseball notation, not decimal innings. Reject fractional representations.
 parts=text.split('.')
 if len(parts)>2 or not parts[0].isdigit() or (len(parts)==2 and parts[1] not in ('0','1','2')):
  raise ValueError('Invalid baseball innings notation: '+text)
 return 3*int(parts[0])+(int(parts[1]) if len(parts)==2 else 0)

def checked_rows(path):
 """Preserve duplicate columns only if their values agree on every row."""
 with Path(path).open(encoding='utf-8-sig',newline='') as f:
  reader=csv.reader(f);head=next(reader,None)
  if not head:raise ValueError('Empty CSV: '+str(path))
  head=[s.strip() for s in head]
  if any(not s for s in head):raise ValueError('Empty CSV heading')
  for line,values in enumerate(reader,2):
   if not values:continue
   if len(values)!=len(head):raise ValueError(f'{path}:{line}: field count mismatch')
   row={}
   for name,value in zip(head,values):
    if name in row and row[name]!=value:raise ValueError(f'{path}:{line}: conflicting duplicate heading {name}')
    row[name]=value
   yield line,row

def load_fangraphs(path,role):
 counts=HITTER_COUNTS if role=='hitter' else PITCHER_COUNTS
 required=set(counts+['Season','Age','PlayerId','MLBAMID','Name','Team']+(['IP'] if role=='pitcher' else []))
 result=[];seen=set();fg_seen=set();issues=[]
 for line,raw in checked_rows(path):
  if not required<=raw.keys():raise ValueError('Missing headings: '+str(sorted(required-raw.keys())))
  year=integer(raw['Season'],'Season');mid=integer(raw['MLBAMID'],'MLBAMID');age=integer(raw['Age'],'Age');fg=raw['PlayerId'].strip()
  if not 1876<=year<=2100 or mid<=0 or not fg or not raw['Name'].strip() or not 10<=age<=80:raise ValueError('Invalid season, player identity or age at source row '+str(line))
  key=(year,mid);fgkey=(year,fg)
  if key in seen or fgkey in fg_seen:raise ValueError(f'Duplicate player-season; combine team splits before import: {key}')
  seen.add(key);fg_seen.add(fgkey)
  values={m:integer(raw[m],f'{line}:{m}') for m in counts}
  if role=='pitcher':values['OUTS']=innings_outs(raw['IP'])
  if role=='hitter':
   if values['H']!=sum(values[m] for m in ['1B','2B','3B','HR']):raise ValueError(f'Hit components disagree at row {line}')
   if values['H']>values['AB'] or values['AB']>values['PA'] or values['IBB']>values['BB']:raise ValueError(f'Impossible batting counts at row {line}')
   residual=values['PA']-sum(values[m] for m in ['AB','BB','HBP','SF','SH'])
   if residual<0:raise ValueError(f'Negative PA residual at row {line}')
   if residual:issues.append(dict(season=year,player_type=role,mlbam_id=mid,check='PA_RESIDUAL',detail=f'{residual}; may include interference/obstruction; not automatically an error'))
  else:
   if values['ER']>values['R'] or values['IBB']>values['BB'] or values['HR']>values['H']:raise ValueError(f'Impossible pitching counts at row {line}')
  derived=derive_rates(role,values)
  for name,calculated in derived.items():
   if name in raw and raw[name].strip() and calculated is not None:
    try:published=float(raw[name])
    except ValueError:continue
    if math.isfinite(published) and abs(published-calculated)>0.00051:
     issues.append(dict(season=year,player_type=role,mlbam_id=mid,check='PUBLISHED_RATE_DIFFERENCE',detail=f'{name}: published={published}, components={calculated}'))
  result.append(dict(season=year,player_type=role,mlbam_id=mid,fangraphs_id=fg,name=raw['Name'],team=raw['Team'],age=age,source_row=line,counts=values,derived_rates=derived,raw=raw))
 if not result:raise ValueError('No player rows: '+str(path))
 return result,issues

def derive_rates(role,v):
 if role=='hitter':
  obden=sum(v[m] for m in ['AB','BB','HBP','SF'])
  return {'AVG':v['H']/v['AB'] if v['AB'] else None,'OBP':(v['H']+v['BB']+v['HBP'])/obden if obden else None,'SLG':(v['1B']+2*v['2B']+3*v['3B']+4*v['HR'])/v['AB'] if v['AB'] else None}
 return {'ERA':27*v['ER']/v['OUTS'] if v['OUTS'] else None,'WHIP':3*(v['H']+v['BB'])/v['OUTS'] if v['OUTS'] else None,'K/9':27*v['SO']/v['OUTS'] if v['OUTS'] else None,'BB/9':27*v['BB']/v['OUTS'] if v['OUTS'] else None}


def credit_pa(rows):
 """Cautious OBR 9.15(b)/9.16(h) credit. Never rewrite physical pitches.
 Multi-change and incomplete sequences remain unresolved for affected roles.
 """
 rows=sorted(rows,key=lambda r:r['pitch_number'])
 terminal=[r for r in rows if r.get('events') in PA_EVENTS]
 if len(terminal)!=1 or terminal[0]!=rows[-1]:return dict(status='INVALID_TERMINAL_SEQUENCE',owners={},transitions=[],reasons=['Expected one terminal PA event on last row'])
 last=terminal[0];event=last['events'];owners={'hitter':last['batter'],'pitcher':last['pitcher']};reasons=[];transitions=[];unresolved=set()
 for role,col,relevant in [('hitter','batter',event in KS),('pitcher','pitcher',event in BBS)]:
  pairs=[(a,b) for a,b in zip(rows,rows[1:]) if a[col]!=b[col]]
  for a,b in pairs:
   transitions.append(dict(player_type=role,from_mlbam_id=a[col],to_mlbam_id=b[col],incoming_balls=b.get('balls'),incoming_strikes=b.get('strikes')))
  if not pairs or not relevant:continue
  if len(pairs)>1:
   unresolved.add(role);reasons.append(role+': multiple within-PA substitutions require game-feed evidence');continue
  a,b=pairs[0];balls=b.get('balls');strikes=b.get('strikes')
  # Count is pre-pitch. A gap may conceal pitches that altered the count.
  if balls not in range(4) or strikes not in range(3) or b['pitch_number']!=a['pitch_number']+1:
   unresolved.add(role);reasons.append(role+': missing count or pitch gap at substitution');continue
  if role=='hitter' and strikes==2:owners[role]=rows[0][col]
  if role=='pitcher' and (balls,strikes) in ADVANTAGE:owners[role]=rows[0][col]
 # A non-zero starting count may conceal an owner who never appears in pitches.
 first=rows[0]
 if (first.get('balls'),first.get('strikes'))!=(0,0) or first['pitch_number']!=1:
  if event in KS:unresolved.add('hitter');reasons.append('Incomplete PA start: strikeout batter credit needs review')
  if event in BBS:unresolved.add('pitcher');reasons.append('Incomplete PA start: walk pitcher credit needs review')
 return dict(status='REVIEW_REQUIRED' if unresolved else 'RULE_ATTRIBUTED',owners=owners,unresolved_roles=sorted(unresolved),transitions=transitions,reasons=reasons)


def event_vector(event,role):
 if event not in PA_EVENTS:return {}
 common={'H':int(event in {'single','double','triple','home_run'}),'HR':int(event=='home_run'),'BB':int(event in BBS),'IBB':int(event=='intent_walk'),'SO':int(event in KS),'HBP':int(event=='hit_by_pitch')}
 if role=='pitcher':return {'TBF':1,**common}
 return {'PA':1,'AB':int(event not in BBS|{'hit_by_pitch','sac_fly','sac_fly_double_play','sac_bunt','sac_bunt_double_play','catcher_interf'}),**common,'1B':int(event=='single'),'2B':int(event=='double'),'3B':int(event=='triple'),'SF':int(event in {'sac_fly','sac_fly_double_play'}),'SH':int(event in {'sac_bunt','sac_bunt_double_play'})}


def stage_output(output,inputs,backup_root=None):
 out=Path(output).resolve()
 if out.exists():raise FileExistsError('Use a new output directory: '+str(out))
 for source in inputs:
  source=Path(source).resolve()
  if out==source or out in source.parents or source in out.parents:raise ValueError('Output must be separate from inputs: '+str(source))
  if backup_root is not None:
   backup=Path(backup_root).resolve()
   if backup==source or source in backup.parents:raise ValueError('Backup must be outside protected inputs: '+str(source))
 out.parent.mkdir(parents=True,exist_ok=True)
 return out,Path(tempfile.mkdtemp(prefix=out.name+'.staging-',dir=out.parent))

def finish_output(stage,out,backup_root):
 backup_root=Path(backup_root).resolve()
 if backup_root==out or out in backup_root.parents or backup_root==stage or stage in backup_root.parents:raise ValueError('Backup must be outside output')
 backup_root.mkdir(parents=True,exist_ok=True)
 backup=backup_root/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
 shutil.copytree(stage,backup)
 expected={str(p.relative_to(stage)):sha(p) for p in stage.rglob('*') if p.is_file()}
 copied={str(p.relative_to(backup)):sha(p) for p in backup.rglob('*') if p.is_file()}
 if expected!=copied:raise ValueError('Complete backup verification failed')
 os.replace(stage,out)
 return str(backup)

# Boxscore field names. Missing fields remain unsupported, not zero.
BOX_FIELDS={'hitter':{'PA':'plateAppearances','AB':'atBats','H':'hits','2B':'doubles','3B':'triples','HR':'homeRuns','R':'runs','RBI':'rbi','SB':'stolenBases','CS':'caughtStealing','BB':'baseOnBalls','IBB':'intentionalWalks','SO':'strikeOuts','HBP':'hitByPitch','SF':'sacFlies','SH':'sacBunts'},'pitcher':{'TBF':'battersFaced','H':'hits','R':'runs','ER':'earnedRuns','HR':'homeRuns','BB':'baseOnBalls','IBB':'intentionalWalks','HBP':'hitBatsmen','SO':'strikeOuts'}}

def validate_feed(payload,game_pk,year):
 data=payload.get('gameData',{})
 if int(payload.get('gamePk',0))!=int(game_pk) or data.get('game',{}).get('type')!='R':raise ValueError('MLB feed game ID/type mismatch')
 if int(data.get('game',{}).get('season',0))!=int(year):raise ValueError('MLB feed season mismatch')
 status=data.get('status',{});detail=status.get('detailedState','').lower()
 if status.get('abstractGameState')!='Final' or any(v in detail for v in ['postpon','cancel','suspend','forfeit']):raise ValueError('MLB feed is not a completed played game')
 if not payload.get('liveData',{}).get('boxscore',{}).get('teams'):raise ValueError('MLB feed lacks boxscore')
 return payload

def boxscore_counts(payload):
 """Only metrics whose player sum agrees with supplied team total are admitted.
 Returns complete game/role/metric blocks; absence inside such a block is zero.
 """
 result={};admitted=set();notes=[]
 for role,group in [('hitter','batting'),('pitcher','pitching')]:
  sides=[]
  for side in ('home','away'):
   team=payload['liveData']['boxscore']['teams'].get(side,{})
   stats=team.get('teamStats',{}).get(group,{})
   players={}
   for player in team.get('players',{}).values():
    pstats=player.get('stats',{}).get(group,{})
    if not pstats:continue
    pid=integer(player.get('person',{}).get('id'),'MLB person ID')
    if pid<=0 or pid in players:raise ValueError('Invalid/duplicate boxscore person ID')
    players[pid]=pstats
   sides.append((stats,players))
  fields=dict(BOX_FIELDS[role])
  if role=='pitcher':fields['OUTS']='inningsPitched'
  if role=='hitter':fields['1B']='__singles'
  for metric,field in fields.items():
   block={};ok=True
   def value(s):
    if metric=='OUTS':return innings_outs(s[field])
    if metric=='1B':return integer(s['hits'],'hits')-sum(integer(s[k],k) for k in ('doubles','triples','homeRuns'))
    return integer(s[field],field)
   try:
    for stats,players in sides:
     team_total=value(stats)
     if not players:raise ValueError('Missing player boxscore stats')
     values={p:value(s) for p,s in players.items()}
     if team_total<0 or min(values.values())<0 or sum(values.values())!=team_total:raise ValueError('Player/team sum mismatch')
     for p,v in values.items():
      if p in block:raise ValueError('Player appears for both teams')
      block[p]=v
   except (KeyError,ValueError,TypeError):ok=False
   if ok:
    admitted.add((role,metric));result.update({(role,p,metric):v for p,v in block.items()})
   else:notes.append(dict(player_type=role,metric=metric,status='NOT_ADMITTED_MISSING_OR_INCONSISTENT'))
 return result,admitted,notes

def read_cached_feed(cache,game,year):
 directory=Path(cache)/str(game);raw=directory/'feed.json';meta=directory/'source.json'
 if not raw.is_file() or not meta.is_file():return None
 m=json.loads(meta.read_text(encoding='utf-8'))
 if m.get('sha256')!=sha(raw) or int(m.get('game_pk',0))!=int(game):raise ValueError('Cached feed hash/ID mismatch: '+str(game))
 return validate_feed(json.loads(raw.read_text(encoding='utf-8')),game,year)


def season_comparison_domain(reference_keys, terminal_keys):
 """Full-season comparisons require a season reference or physical pitch baseline.
 Partial boxscore-only keys are retained separately, never promoted by union.
 """
 return set(reference_keys)|set(terminal_keys)


def confirm_terminal_scored_label(trace,play):
 """Confirm a narrow A->B->A inherited-K credit-label pattern from MLB PBP.
 The PA index only nominates a play. IDs, substitution/count, pitcher, full
 pitch numbering and pre/post counts must independently agree. No counts move.
 """
 rows=trace.get('sequence',[])
 if trace.get('event') not in KS or trace.get('unresolved_roles')!=['hitter'] or len(rows)<3:return None
 if trace.get('status')!='REVIEW_REQUIRED':return None
 about=play.get('about',{})
 if not about.get('isComplete') or play.get('result',{}).get('eventType') not in KS:return None
 index=play.get('atBatIndex',about.get('atBatIndex'))
 if index is None or index+1!=trace['at_bat_number']:return None
 first=rows[0]['batter'];last=rows[-1]['batter']
 if first!=last:return None
 ids={r['batter'] for r in rows}
 if len(ids)!=2:return None
 incoming=next(iter(ids-{first}))
 switches=[(a,b) for a,b in zip(rows,rows[1:]) if a['batter']!=b['batter']]
 if len(switches)!=2 or switches[0][0]['batter']!=first or switches[0][1]['batter']!=incoming or switches[1][1]!=rows[-1]:return None
 if switches[0][1].get('strikes')!=2:return None
 matchup=play.get('matchup',{})
 if matchup.get('batter',{}).get('id')!=incoming:return None
 pitchers={r['pitcher'] for r in rows}
 if len(pitchers)!=1 or matchup.get('pitcher',{}).get('id') not in pitchers:return None
 subs=[e for e in play.get('playEvents',[]) if e.get('details',{}).get('eventType')=='offensive_substitution']
 if len(subs)!=1:return None
 sub=subs[0]
 if sub.get('player',{}).get('id')!=incoming or sub.get('replacedPlayer',{}).get('id')!=first:return None
 if sub.get('count',{}).get('strikes')!=2 or sub.get('count',{}).get('balls')!=switches[0][1].get('balls'):return None
 pitches=[e for e in play.get('playEvents',[]) if e.get('isPitch')]
 if len(pitches)!=len(rows):return None
 previous=(0,0)
 for row,e in zip(rows,pitches):
  if row['pitch_number']!=e.get('pitchNumber') or (row.get('balls'),row.get('strikes'))!=previous:return None
  count=e.get('count',{});previous=(count.get('balls'),count.get('strikes'))
 if previous[1]!=3:return None
 return dict(status='MLB_CONFIRMED_INHERITED_TWO_STRIKE_SCORED_LABEL',credited_batter=first,physical_finishing_batter=incoming,pitcher=next(iter(pitchers)),incoming_balls=sub['count']['balls'],incoming_strikes=2,rule='OBR 9.15(b)',count_changes=False,checks=['game selected from validated cache','complete strikeout outcome','matching single explicit pinch-hit substitution','matching two-strike count','matching pitcher','matching pitch sequence/counts','terminal Statcast ID equals outgoing credited batter'])


def confirm_trace_from_feed(trace,payload):
 if payload.get('gamePk')!=trace['game_pk']:return False
 plays=payload.get('liveData',{}).get('plays',{}).get('allPlays',[])
 proofs=[p for p in (confirm_terminal_scored_label(trace,play) for play in plays) if p]
 if len(proofs)!=1:return False
 trace['mlb_scoring_confirmation']=proofs[0]
 trace['original_review_reasons']=list(trace.get('reasons',[]))
 trace['unresolved_roles']=[];trace['reasons']=[];trace['status']='MLB_CONFIRMED_SCORED_TERMINAL_LABEL'
 return True
