"""Paired preseason DC draft experiments. Not an outcomes backtest or weekly optimizer."""
import argparse,bisect,csv,hashlib,json,math,random,shutil,statistics,tempfile
from concurrent.futures import ProcessPoolExecutor
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from scipy.optimize import linear_sum_assignment, milp, LinearConstraint, Bounds
from scipy.sparse import csr_matrix

CATS=['R','HR','RBI','SB','AVG','W','SV','K','ERA','WHIP']
SLOTS=['C','C','1B','2B','3B','SS','CI','MI']+['OF']*5+['UT']+['P']*9
COUNTS=['R','HR','RBI','SB','W','SV','SO','AB','H_hit','IP','ER','H_allowed','BB_allowed']

def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def write(p,rows):
 if not rows:return
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def num(v):
 try:
  x=float(v);return x if math.isfinite(x) else None
 except (ValueError,TypeError):return None

def eligible(positions,typ):
 p=set(positions.split(';'))
 if typ=='pitcher':return {'P'}
 return (p&{'C','1B','2B','3B','SS','OF'})|{'UT'}|({'CI'} if p&{'1B','3B'} else set())|({'MI'} if p&{'2B','SS'} else set())

def load_players(rankings,watch,eligibility_file,review_file=None):
 players=[]
 for r in read(rankings):
  p=dict(r);p['id']=r['nfbc_player_id'];p['adp']=float(r['market_ADP']);p['value']=float(r['sgp_above_replacement']);p['raw']=float(r['raw_sgp']);p['known']=True
  p['slots']=eligible(r['positions'],r['player_type']);players.append(p)
 # Market-only assets may fill an eligibility slot, but get no fabricated metrics.
 for r in read(watch):
  if r['nfbc_player_id'] in {p['id'] for p in players}:raise ValueError('Valued/watchlist overlap')
  players.append(dict(r,id=r['nfbc_player_id'],adp=float(r['market_ADP']),value=None,raw=None,known=False,slots=set()))
 eligibility={r['nfbc_player_id']:r for r in (read(review_file) if review_file else [])}
 eligibility.update({r['nfbc_player_id']:r for r in read(eligibility_file)})
 for p in players:
  if not p['known']:
   e=eligibility.get(p['id']);p['slots']=eligible(e['positions'],p['player_type']) if e else set()
 if len({p['id'] for p in players})!=len(players):raise ValueError('Duplicate NFBC asset')
 # Canonical valuations contain one role per two-way asset. Never synthesize second role.
 return sorted(players,key=lambda p:(p['adp'],p['id']))

def lineup(roster):
 # Distinct roster identities are columns. Dummy columns expose actual shortfalls.
 a=np.full((23,len(roster)+23),-1e9,dtype=float)
 a[:,len(roster):]=0
 for j,p in enumerate(roster):
  if p['known']:
   for i,s in enumerate(SLOTS):
    if s in p['slots']:a[i,j]=10000+p['raw']
 rows,cols=linear_sum_assignment(a,maximize=True)
 chosen=[(SLOTS[i],roster[j]) for i,j in zip(rows,cols) if j<len(roster) and a[i,j]>0]
 return chosen,23-len(chosen)

def totals(chosen):
 sums={k:0.0 for k in COUNTS}
 for slot,p in chosen:
  if not p['known']:raise ValueError('Unknown projection included in totals')
  metrics=['R','HR','RBI','SB','AB'] if p['player_type']=='hitter' else ['W','SV','SO','IP','ER']
  for k in metrics:
   v=num(p.get(k))
   if v is None:raise ValueError('Missing active component '+p['name']+' '+k)
   sums[k]+=v
  if p['player_type']=='hitter':sums['H_hit']+=float(p['H'])
  else:sums['H_allowed']+=float(p['H']);sums['BB_allowed']+=float(p['BB'])
 sums['K']=sums['SO'];sums['AVG']=sums['H_hit']/sums['AB'] if sums['AB'] else None
 sums['ERA']=9*sums['ER']/sums['IP'] if sums['IP'] else None
 sums['WHIP']=(sums['H_allowed']+sums['BB_allowed'])/sums['IP'] if sums['IP'] else None
 return sums

class History:
 def __init__(self,path):
  data=read(path);self.seasons=sorted({r['season'] for r in data});self.dist={}
  if any(int(s)>=2026 for s in self.seasons):raise ValueError('Historical target leakage')
  for s in self.seasons:
   for c in CATS:
    vals=[float(r[c]) for r in data if r['season']==s and (c not in ['ERA','WHIP'] or float(r['IP'])>=950)]
    if not vals:raise ValueError('Missing historical category')
    self.dist[s,c]=sorted(vals)
  self.reference_AB=statistics.mean(statistics.mean(float(r['AB']) for r in data if r['season']==s) for s in self.seasons)
  self.targets={c:statistics.mean(self.quantile(self.dist[s,c],.2 if c in ['ERA','WHIP'] else .8) for s in self.seasons) for c in CATS}
 @staticmethod
 def quantile(v,q):
  pos=q*(len(v)-1);lo=int(pos);return v[lo]+(v[min(lo+1,len(v)-1)]-v[lo])*(pos-lo)
 def percentiles(self,t):
  result={}
  for c in CATS:
   v=t[c]
   if v is None:result[c]=None;continue
   ranks=[]
   for s in self.seasons:
    d=self.dist[s,c];f=(bisect.bisect_left(d,v)+bisect.bisect_right(d,v))/(2*len(d))
    ranks.append(1-f if c in ['ERA','WHIP'] else f)
   result[c]=statistics.mean(ranks)
  return result

MIN_IP=950.0

def pitching_choice(roster):
 pitchers=[p for p in roster if p['known'] and p['player_type']=='pitcher']
 if len(pitchers)<9:return None
 ranked=sorted(pitchers,key=lambda p:p['raw'],reverse=True)[:9]
 if sum(float(p['IP']) for p in ranked)>=MIN_IP-1e-7:return ranked
 if sum(sorted((float(p['IP']) for p in pitchers),reverse=True)[:9])<MIN_IP-1e-7:return None
 n=len(pitchers)
 a=np.array([[1.0]*n,[float(p['IP']) for p in pitchers]])
 result=milp(-np.array([p['raw'] for p in pitchers]),integrality=np.ones(n),bounds=Bounds(np.zeros(n),np.ones(n)),constraints=LinearConstraint(a,[9,MIN_IP],[9,np.inf]),options={'time_limit':10})
 if not result.success:raise ValueError('Active pitching solver did not certify optimality')
 picked=[p for p,v in zip(pitchers,result.x) if v>.5]
 if len(picked)!=9 or sum(float(p['IP']) for p in picked)<MIN_IP-1e-6:raise ValueError('Invalid constrained pitching witness')
 return picked

def constrained_lineup(roster):
 original,short=lineup(roster);pitchers=pitching_choice(roster)
 if pitchers is None:return original,short,False
 hitters=[(slot,p) for slot,p in original if slot!='P']
 chosen=hitters+[('P',p) for p in pitchers]
 return chosen,23-len(chosen),len(chosen)==23

def robust_coverage(roster):
 active,missing=lineup(roster)
 if missing:return False
 return all(lineup([p for p in roster if p['id']!=removed['id']])[1]==0 for slot,removed in active)

def completion_plan(roster,available):
 # Exact Hall constraints enforce a legal matching after ANY one known player's
 # removal. Pitcher variables separately witness nine active pitchers >=950 IP.
 owned={p['id'] for p in roster};known=[p for p in roster if p['known']]
 if robust_coverage(known) and pitching_choice(known) is not None:return []
 # All currently available assets are considered: no future opponent picks or
 # post-draft trades enter the feasibility calculation.
 candidates=[p for p in sorted(available,key=lambda p:(p['adp'],p['id'])) if p['known'] and p['id'] not in owned]
 pool=known+candidates;n=len(pool);pi=[i for i,p in enumerate(pool) if p['player_type']=='pitcher'];size=n+len(pi)
 if not size:return None
 rows=[];lower=[];upper=[]
 def add(indices,values,lo,hi=np.inf):
  rows.append(dict(zip(indices,values)));lower.append(lo);upper.append(hi)
 demands=Counter(SLOTS);types=sorted(set(SLOTS)-{'P'});dedup={}
 for mask in range(1,1<<len(types)):
  subset={types[j] for j in range(len(types)) if mask>>j&1}
  neighbors=tuple(i for i,p in enumerate(pool) if p['slots']&subset)
  required=sum(demands[t] for t in subset)+1
  dedup[neighbors]=max(dedup.get(neighbors,0),required)
 for indices,required in dedup.items():
  if len(indices)<required:return None
  add(indices,[1]*len(indices),required)
 if len(pi)<10:return None
 add(pi,[1]*len(pi),10)
 add(list(range(n,size)),[1]*len(pi),9,9)
 add(list(range(n,size)),[float(pool[i]['IP']) for i in pi],MIN_IP)
 for j,i in enumerate(pi):add([n+j,i],[1,-1],-np.inf,0)
 rr=[];cc=[];vv=[]
 for j,row in enumerate(rows):
  for i,v in row.items():rr.append(j);cc.append(i);vv.append(v)
 mat=csr_matrix((vv,(rr,cc)),shape=(len(rows),size))
 costs=np.array([0 if p['id'] in owned else 10000+p['adp']/1000 for p in pool]+[0]*len(pi))
 lb=np.zeros(size);ub=np.ones(size)
 for i,p in enumerate(pool):
  if p['id'] in owned:lb[i]=1
 result=milp(costs,integrality=np.ones(size),bounds=Bounds(lb,ub),constraints=LinearConstraint(mat,lower,upper),options={'time_limit':20})
 if result.status==2:return None
 if not result.success:raise ValueError('Completion solver did not certify minimum picks: '+result.message)
 plan=[p for i,p in enumerate(pool) if result.x[i]>.5 and p['id'] not in owned]
 witness=known+plan
 if not robust_coverage(witness) or pitching_choice(witness) is None:raise ValueError('Completion witness failed independent checks')
 return plan

def draft(players,hist,seed,seat,strategy,jitter=12.0):
 rng=random.Random(seed)
 # Same per-team/per-asset market draws for paired strategies and seats.
 prices={(team,p['id']):max(1,p['adp']+rng.gauss(0,jitter)) for team in range(15) for p in players}
 rosters=[[] for _ in range(15)];available={p['id']:p for p in players};log=[];guard_events=[]
 for roundno in range(1,51):
  for team in (range(15) if roundno%2 else range(14,-1,-1)):
   own=rosters[team];chosen,missing=lineup(own);remaining=51-roundno
   if team==seat:
    pool=sorted(available.values(),key=lambda p:(-(p['value'] if p['known'] else -1e6),p['adp'],p['id']))[:16]
    # Include affordable coverage alternatives beyond the pure-value shortlist.
    needed=Counter(SLOTS);needed.subtract(s for s,p in chosen)
    for slot,n in needed.items():
     if n>0:
      q=next((p for p in sorted(available.values(),key=lambda p:p['adp']) if p['known'] and slot in p['slots']),None)
      if q and q not in pool:pool.append(q)
    base=totals(chosen);basepct=hist.percentiles(base)
    def score(p):
     active,short=lineup(own+[p]);gain=missing-short
     urgency=100000 if missing>=remaining else 0
     if strategy=='value':return (urgency*gain+(p['value'] if p['known'] else -1e6),-p['adp'])
     t=totals(active);pct=hist.percentiles(t)
     # Partial-roster scarcity pressure uses deficits; fixed scales prevent re-tuning on results.
     utility=0.0
     for c in CATS:
      # Ratio effects are deferred until both pitching and hitting have exposure.
      if t[c] is None:continue
      before=base[c]
      if before is None:continue
      target=hist.targets[c]
      if c in ['AVG','ERA','WHIP']:
       change=(pct[c] or 0)-(basepct[c] or 0)
       exposure=min(1,t['AB']/hist.reference_AB) if c=='AVG' else min(1,t['IP']/950)
       utility+=change*exposure
      else:
       # Concave progress rewards breadth and diminishes surplus above the target.
       utility+=math.log1p(max(0,t[c])/target)-math.log1p(max(0,before)/target)
     return (urgency*gain+utility*100+0.15*(p['value'] if p['known'] else -1e6)+gain*2,-p['adp'])
    plan=completion_plan(own,list(available.values())) if roundno>=24 else []
    guard=False
    if plan is None:
     guard_events.append(dict(round=roundno,status='NO_AVAILABLE_COMPLETION',remaining_picks=remaining))
    elif len(plan)>remaining:
     guard_events.append(dict(round=roundno,status='INSUFFICIENT_REMAINING_PICKS',minimum_completion_picks=len(plan),remaining_picks=remaining))
    elif plan:
     # Mandatory completion picks take precedence over either category or value
     # utility. They are actual current picks, never post-draft repairs.
     pool=plan;guard=True
     guard_events.append(dict(round=roundno,status='MANDATORY_FEASIBILITY_PICK',minimum_completion_picks=len(plan),remaining_picks=remaining))
    pick=max(pool,key=score)
   else:
    market=sorted(available.values(),key=lambda p:(prices[team,p['id']],p['id']))
    pool=market[:20]
    if missing>=remaining:
     feasible=[p for p in market if p['known'] and lineup(own+[p])[1]<missing]
     if feasible:pool=feasible[:20]
    # Soft roster awareness in the market model, with mandatory late coverage when possible.
    pick=min(pool,key=lambda p:prices[team,p['id']]-10*(missing-lineup(own+[p])[1]))
   own.append(pick);del available[pick['id']]
   log.append(dict(seed=seed,seat=seat+1,strategy=strategy,overall_pick=(roundno-1)*15+(team+1 if roundno%2 else 15-team),round=roundno,team=team+1,nfbc_player_id=pick['id'],name=pick['name'],ADP=pick['adp'],has_projection=pick['known'],feasibility_pick=guard if team==seat else False))
 # Explicit checks: 750 distinct assets, 50 per team, target known-production lineup only.
 assert all(len(r)==50 for r in rosters)
 assert len({p['id'] for r in rosters for p in r})==750
 active,short,ip_feasible=constrained_lineup(rosters[seat]);t=totals(active);pct=hist.percentiles(t)
 active_ids={p['id'] for s,p in active};reserves=[p for p in rosters[seat] if p['id'] not in active_ids]
 league_incomplete=sum(lineup(r)[1]>0 for r in rosters)
 summary=dict(feasibility_picks=sum(e['status']=='MANDATORY_FEASIBILITY_PICK' for e in guard_events),completion_failures=sum(e['status']!='MANDATORY_FEASIBILITY_PICK' for e in guard_events),single_absence_coverage=robust_coverage(rosters[seat]),all_constraints_pass=ip_feasible and robust_coverage(rosters[seat]),guard_events=json.dumps(guard_events),league_incomplete_teams=league_incomplete,seed=seed,seat=seat+1,strategy=strategy,players=50,active=len(active),active_shortfall=short,reserves=len(reserves),market_only=sum(not p['known'] for p in rosters[seat]),projected_IP=t['IP'],below_950_IP=t['IP']<950,passes_roster_and_IP_gate=short==0 and t['IP']>=950,historical_mean_percentile=statistics.mean(v for v in pct.values() if v is not None),categories_at_80th=sum(v is not None and v>=.8 for v in pct.values()),weakest_category=min((c for c in CATS if pct[c] is not None),key=lambda c:pct[c]))
 for c in CATS:summary[c]=t[c];summary[c+'_historical_percentile']=pct[c]
 coverage=[]
 for s in ['C','1B','2B','3B','SS','OF','P']:
  alternatives=[p for p in reserves if s in p['slots']]
  coverage.append(dict(seed=seed,seat=seat+1,strategy=strategy,position=s,eligible_reserves=len(alternatives),projected_reserves=sum(p['known'] for p in alternatives),market_only_reserves=sum(not p['known'] for p in alternatives),note='Multi-eligible reserves overlap; no weekly substitution production assumed'))
 assignments=[dict(seed=seed,seat=seat+1,strategy=strategy,slot=s,nfbc_player_id=p['id'],name=p['name']) for s,p in active]
 return summary,log,coverage,assignments

def reserve_stress(players,logs):
 lookup={p['id']:p for p in players};groups={}
 for row in logs:
  if int(row['team'])==int(row['seat']):
   key=(int(row['seed']),int(row['seat']),row['strategy'])
   groups.setdefault(key,[]).append(lookup[row['nfbc_player_id']])
 result=[]
 for (seed,seat,strategy),roster in groups.items():
  active,short,ip_ok=constrained_lineup(roster);baseline=sum(p['raw'] for slot,p in active)
  for slot,removed in active:
   remaining=[p for p in roster if p['id']!=removed['id']]
   alternative,missing=lineup(remaining)
   result.append(dict(seed=seed,seat=seat,strategy=strategy,removed_nfbc_id=removed['id'],removed_name=removed['name'],removed_slot=slot,remaining_active_shortfall=missing,legal_after_single_loss=missing==0,static_raw_sgp_loss=baseline-sum(p['raw'] for s,p in alternative),note='One simultaneous absence only. Full-season utility stress, not injury probability or lost-season forecast.'))
 return result

def comparison_summary(results):
 rows=[]
 for strategy in ['value','category']:
  q=[r for r in results if r['strategy']==strategy]
  rows.append(dict(strategy=strategy,simulations=len(q),mean_historical_percentile=statistics.mean(float(r['historical_mean_percentile']) for r in q),mean_categories_at_80th=statistics.mean(float(r['categories_at_80th']) for r in q),mean_projected_IP=statistics.mean(float(r['projected_IP']) for r in q),incomplete_lineups=sum(int(r['active_shortfall'])>0 for r in q),below_950_IP=sum(float(r['projected_IP'])<950 for r in q),passes_roster_and_IP_gate=sum(int(r['active_shortfall'])==0 and float(r['projected_IP'])>=950 for r in q),passes_all_constraints=sum(bool(r['all_constraints_pass']) for r in q)))
 return rows

def production_reports(players,logs):
 lookup={p['id']:p for p in players};groups={}
 for row in logs:
  if int(row['team'])==int(row['seat']):groups.setdefault((row['seed'],row['seat'],row['strategy']),[]).append(lookup[row['nfbc_player_id']])
 pitching=[];reserves=[];inventory=[]
 for (seed,seat,strategy),roster in groups.items():
  active,short,ok=constrained_lineup(roster);ids={p['id'] for slot,p in active};bench=[p for p in roster if p['id'] not in ids]
  t=totals(active);pitchers=[p for slot,p in active if slot=='P']
  header=dict(seed=seed,seat=seat,strategy=strategy)
  pitching.append(dict(header,active_pitchers=len(pitchers),active_IP=t['IP'],active_W=t['W'],active_K=t['K'],active_SV=t['SV'],active_ERA=t['ERA'],active_WHIP=t['WHIP'],active_GS=sum(num(p.get('GS')) or 0 for p in pitchers),missing_GS_components=sum(num(p.get('GS')) is None for p in pitchers),pitchers_with_positive_SV=sum(float(p['SV'])>0 for p in pitchers),IP_gate=t['IP']>=MIN_IP,description='Active-only volume and saves; reserve stats excluded'))
  known=[p for p in bench if p['known']];bt=totals([('reserve',p) for p in known])
  reserves.append(dict(header,reserve_count=len(bench),known_projection_reserves=len(known),market_only_reserves=sum(not p['known'] for p in bench),reserve_hitters=sum(p['player_type']=='hitter' for p in known),reserve_pitchers=sum(p['player_type']=='pitcher' for p in known),reserve_PA=sum(float(p['PA']) for p in known if p['player_type']=='hitter'),reserve_IP=bt['IP'],reserve_W=bt['W'],reserve_K=bt['K'],reserve_SV=bt['SV'],reserve_R=bt['R'],reserve_HR=bt['HR'],reserve_RBI=bt['RBI'],reserve_SB=bt['SB'],description='Inventory of full-season published projections, not additional usable team production. No reserve statistics added to active totals.'))
  for player in bench:
   inventory.append(dict(header,nfbc_player_id=player['id'],name=player['name'],player_type=player['player_type'],has_projection=player['known'],eligible_slots=';'.join(sorted(player['slots'])),PA=player.get('PA') if player['known'] else None,IP=player.get('IP') if player['known'] else None,SV=player.get('SV') if player['known'] else None))
 return pitching,reserves,inventory

def baseline_comparison(results,path):
 old=read(path);index={(int(r['seed']),int(r['seat']),r['strategy']):r for r in old}
 if len(index)!=len(old):raise ValueError('Duplicate baseline keys')
 result=[]
 for r in results:
  key=(r['seed'],r['seat'],r['strategy'])
  if key not in index:raise ValueError('Missing frozen baseline seed/seat/strategy '+str(key))
  b=index[key]
  result.append(dict(seed=r['seed'],seat=r['seat'],strategy=r['strategy'],v1_0_IP=float(b['projected_IP']),v1_1_IP=r['projected_IP'],IP_change=r['projected_IP']-float(b['projected_IP']),v1_0_mean_percentile=float(b['historical_mean_percentile']),v1_1_mean_percentile=r['historical_mean_percentile'],percentile_change=r['historical_mean_percentile']-float(b['historical_mean_percentile']),v1_1_all_constraints_pass=r['all_constraints_pass'],note='Identical seed/seat/strategy; constraints change target picks and downstream market availability. Synthetic comparison only.'))
 return result

def simulation_job(args):
 return draft(*args)

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--rankings',default='outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix/player_values_with_adp.csv');p.add_argument('--watchlist',default='outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix/unvalued_adp_watchlist.csv');p.add_argument('--eligibility',default='data/valuation_inputs_dc_v1_1/nfbc15_dc_eligibility.csv');p.add_argument('--eligibility-review',default='data/valuation_inputs_dc_v1_1/nfbc15_dc_eligibility_review.csv');p.add_argument('--historical',default='data/valuation_inputs_dc_v1_1/dc_historical_team_stats.csv');p.add_argument('--workers',type=int,default=1);p.add_argument('--baseline-script',default='dc_roster_simulator_v1_0.py');p.add_argument('--baseline-results',default='outputs/dc_roster_simulator_v1_0/team_results.csv');p.add_argument('--output',default='outputs/dc_roster_simulator_v1_1');p.add_argument('--repetitions',type=int,default=5);p.add_argument('--seed',type=int,default=20260324);p.add_argument('--seats',type=int,nargs='+',default=list(range(1,16)));p.add_argument('--backup-root',default='backups');a=p.parse_args()
 if a.workers<1 or a.repetitions<1 or len(set(a.seats))!=len(a.seats) or any(s<1 or s>15 for s in a.seats):raise ValueError('Invalid repetitions or seats')
 out=Path(a.output).resolve()
 if out.exists():raise ValueError('Output already exists')
 files=[a.rankings,a.watchlist,a.eligibility,a.historical,a.eligibility_review,a.baseline_results,a.baseline_script];hashes={str(Path(f).resolve()):sha(f) for f in files}
 players=load_players(a.rankings,a.watchlist,a.eligibility,a.eligibility_review);hist=History(a.historical)
 if len(players)<750:raise ValueError('Insufficient draft pool')
 stage=Path(tempfile.mkdtemp(prefix='dc_sim_',dir=out.parent if out.parent.exists() else None))
 results=[];logs=[];coverage=[];assignments=[]
 try:
  jobs=[(players,hist,a.seed+rep,seat-1,strategy) for rep in range(a.repetitions) for seat in a.seats for strategy in ['value','category']]
  if a.workers==1:
   completed=map(simulation_job,jobs);executor=None
  else:
   executor=ProcessPoolExecutor(max_workers=a.workers);completed=executor.map(simulation_job,jobs)
  try:
   for i,(s,l,c,ass) in enumerate(completed,1):
    results.append(s);logs.extend(l);coverage.extend(c);assignments.extend(ass)
    print(f"Completed {i}/{len(jobs)}: seed {s['seed']}, seat {s['seat']}, {s['strategy']}",flush=True)
  finally:
   if executor:executor.shutdown(wait=True,cancel_futures=True)
  pairs=[]
  for rep in range(a.repetitions):
   for seat in a.seats:
    v=next(r for r in results if r['seed']==a.seed+rep and r['seat']==seat and r['strategy']=='value');c=next(r for r in results if r['seed']==a.seed+rep and r['seat']==seat and r['strategy']=='category')
    pairs.append(dict(seed=a.seed+rep,seat=seat,category_minus_value_mean_percentile=c['historical_mean_percentile']-v['historical_mean_percentile'],category_minus_value_80th_categories=c['categories_at_80th']-v['categories_at_80th'],both_lineups_complete=not(v['active_shortfall'] or c['active_shortfall']),both_pass_roster_and_IP_gate=not(v['active_shortfall'] or c['active_shortfall']) and v['projected_IP']>=950 and c['projected_IP']>=950))
  pitching,reserves,inventory=production_reports(players,logs)
  write(stage/'active_pitching.csv',pitching);write(stage/'reserve_production_inventory.csv',reserves);write(stage/'reserve_players.csv',inventory)
  write(stage/'comparison_to_frozen_v1_0.csv',baseline_comparison(results,a.baseline_results))
  write(stage/'strategy_summary.csv',comparison_summary(results))
  stress=reserve_stress(players,logs)
  write(stage/'single_absence_stress.csv',stress)
  write(stage/'team_results.csv',results);write(stage/'draft_log.csv',logs);write(stage/'reserve_coverage.csv',coverage);write(stage/'active_assignments.csv',assignments);write(stage/'paired_comparison.csv',pairs)
  for f,h in hashes.items():
   if sha(f)!=h:raise ValueError('Input changed')
  backup=Path(a.backup_root).resolve()/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
  audit=dict(version='1.1.0',effective_date='2026-03-24',effective_date_basis='User confirmed for projections and ADP; not independently archived timestamp',ADP_window='Average available on effective date; exact underlying draft interval not verified',all_constraints_pass=sum(r['all_constraints_pass'] for r in results),minimum_active_IP=MIN_IP,baseline_source=a.baseline_results,baseline_frozen=True,single_absence_checks=len(stress),single_absence_failures=sum(not r['legal_after_single_loss'] for r in stress),simulations=len(results),paired_comparisons=len(pairs),draft_pool=len(players),market_only_assets=sum(not p['known'] for p in players),legal_target_lineups=sum(r['active_shortfall']==0 for r in results),input_sha256=hashes,inputs_unchanged=True,backup=str(backup),historical_targets=hist.targets,limitations=['Strategies failing roster/IP gates are research failures and must not drive recommendations.','Synthetic paired experiments, not an outcomes backtest or evidence of real draft improvement.','Historical percentiles compare static projected active season totals with realized DC results including weekly lineup changes.','950 active IP is enforced when a feasible pitching witness exists; failures remain explicit. Single-absence gate guarantees eligibility only, not 950 IP after absence. No weekly lineup coverage production, injury probabilities or prospect call-up model.','Unknown projections are never replaced by zero or included in projected totals.','Opponent ADP jitter is fixed 12 picks, an illustrative assumption not empirically calibrated.','80th percentile targets and category score coefficients are fixed research controls. No tuning on results.','ERA/WHIP historical reference excludes individual teams below 950 IP; reported percentiles do not reconstruct official penalty points.','One role per canonical two-way asset; no dual-role switching option value.'])
  (stage/'simulation_audit.json').write_text(json.dumps(audit,indent=2));backup.parent.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
  for f in stage.iterdir():
   if sha(f)!=sha(backup/f.name):raise ValueError('Backup mismatch')
  out.parent.mkdir(parents=True,exist_ok=True);shutil.move(str(stage),out)
  print(json.dumps(audit,indent=2))
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise
if __name__=='__main__':main()
