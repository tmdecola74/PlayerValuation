"""Coherent rates, linear full-roster SGP, exact multi-position roster margins."""
from __future__ import annotations
import heapq,math,collections

def finite(x):return isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x)

def coherent(typ,metrics):
 m=dict(metrics)
 def ratio(keys,den,scale=1):
  vals=[m.get(k) for k in keys];d=m.get(den)
  return scale*sum(vals)/d if all(finite(v) and v>=0 for v in vals) and finite(d) and d>0 else None
 if typ=='hitter':
  m['AVG']=ratio(['H'],'AB')
  den=[m.get(k) for k in ['AB','BB','HBP','SF']];num=[m.get(k) for k in ['H','BB','HBP']]
  m['OBP']=sum(num)/sum(den) if all(finite(v) and v>=0 for v in den+num) and sum(den)>0 else None
  tb=[m.get(k) for k in ['1B','2B','3B','HR']]
  m['SLG']=sum(v*c for v,c in zip(tb,[1,2,3,4]))/m['AB'] if all(finite(v) and v>=0 for v in tb) and finite(m.get('AB')) and m['AB']>0 else None
  m['OPS']=m['OBP']+m['SLG'] if finite(m['OBP']) and finite(m['SLG']) else None
 else:
  m['ERA']=ratio(['ER'],'IP',9);m['WHIP']=ratio(['H','BB'],'IP')
  m['SV_plus_HLD']=m['SV']+m['HLD'] if finite(m.get('SV')) and finite(m.get('HLD')) else None
 return m

def sgp(typ,m,slopes,reference,category_definitions):
 out={}
 for cat,rule in category_definitions.items():
  if rule['kind']=='count':value=m.get(rule['metric']);contribution=value/slopes[cat] if finite(value) else None
  elif cat=='AVG':contribution=(m['H']-reference['AVG']*m['AB'])/(reference['team_AB']*slopes[cat])
  elif cat=='ERA':contribution=(reference['ERA']*m['IP']-9*m['ER'])/(reference['team_IP']*slopes[cat])
  elif cat=='WHIP':contribution=(reference['WHIP']*m['IP']-m['H']-m['BB'])/(reference['team_IP']*slopes[cat])
  else:raise ValueError('Unsupported rate category: '+cat)
  if not finite(contribution):raise ValueError('Unavailable category contribution: '+cat)
  out[cat]=contribution
 return out

def reference_from_pool(records,teams):
 h=[r['metrics'] for r in records if r['player_type']=='hitter'];p=[r['metrics'] for r in records if r['player_type']=='pitcher']
 ab=sum(r['AB'] for r in h);ip=sum(r['IP'] for r in p)
 if ab<=0 or ip<=0:raise ValueError('Rate-reference pool needs positive hitter AB and pitcher IP')
 return dict(AVG=sum(r['H'] for r in h)/ab,ERA=9*sum(r['ER'] for r in p)/ip,WHIP=sum(r['H']+r['BB'] for r in p)/ip,team_AB=ab/teams,team_IP=ip/teams)

class Assignment:
 """Min-cost fixed-demand flow. One capacity per canonical player across all roles."""
 def __init__(self,records,demands):
  self.records=records;self.demands=demands
  ids=sorted({r['player_id'] for r in records});groups=sorted(demands)
  self.source=0;self.player_nodes={pid:i+1 for i,pid in enumerate(ids)}
  self.group_nodes={g:len(ids)+i+1 for i,g in enumerate(groups)};self.sink=len(ids)+len(groups)+1
  self.graph=[[] for _ in range(self.sink+1)];self.potential=[0.0]*len(self.graph);self.profit_offset=max([r['raw_sgp'] for r in records]+[0.0]);self.option_edges=[]
  def add(u,v,cap,cost):
   f=[v,len(self.graph[v]),cap,cost];b=[u,len(self.graph[u]),0,-cost]
   self.graph[u].append(f);self.graph[v].append(b);return f
  for pid,node in self.player_nodes.items():add(self.source,node,1,0)
  for i,r in enumerate(records):
   for group in sorted(r['eligible_slots']):
    if group in self.group_nodes:
     edge=add(self.player_nodes[r['player_id']],self.group_nodes[group],1,self.profit_offset-r['raw_sgp'])
     self.option_edges.append((i,group,edge))
  for group,cap in demands.items():add(self.group_nodes[group],self.sink,cap,0)
  flow=0;needed=sum(demands.values())
  while flow<needed:
   dist,prev=self.shortest(self.source)
   if not math.isfinite(dist[self.sink]):raise ValueError(f'Insufficient eligible roster depth: filled {flow}/{needed} slots')
   limit=dist[self.sink]
   for i,d in enumerate(dist):self.potential[i]+=min(d,limit)
   node=self.sink
   while node!=self.source:
    u,k=prev[node];edge=self.graph[u][k];edge[2]-=1;self.graph[node][edge[1]][2]+=1;node=u
   flow+=1
  self.selected=[]
  for i,group,edge in self.option_edges:
   if edge[2]==0:self.selected.append(dict(records[i],assigned_slot=group))
  if len(self.selected)!=needed or len({r['player_id'] for r in self.selected})!=needed:raise ValueError('Assignment uniqueness/slot reconciliation failed')
  self.objective=sum(r['raw_sgp'] for r in self.selected)
 def shortest(self,start,banned=None,no_sink=False):
  n=len(self.graph);dist=[float('inf')]*n;prev=[None]*n;dist[start]=0;heap=[(0,start)]
  while heap:
   d,u=heapq.heappop(heap)
   if d>dist[u]+1e-10:continue
   for k,edge in enumerate(self.graph[u]):
    v,_,cap,cost=edge
    if not cap or v==banned or u==banned or (no_sink and (u==self.sink or v==self.sink)):continue
    reduced=cost+self.potential[u]-self.potential[v]
    if reduced<-1e-7:raise ValueError('Invalid residual potential; assignment optimality cannot be certified')
    nd=d+max(0,reduced)
    if nd<dist[v]-1e-10:dist[v]=nd;prev[v]=(u,k);heapq.heappush(heap,(nd,v))
  return dist,prev
 def original_distance(self,start,end,banned=None):
  distances,_=self.shortest(start,banned=banned,no_sink=True)
  return distances[end]-self.potential[start]+self.potential[end]
 def margins(self):
  selected={r['player_id']:r for r in self.selected};margins={};thresholds={}
  for g,node in self.group_nodes.items():thresholds[g]=self.profit_offset+self.original_distance(node,self.source)
  for pid,r in selected.items():
   cost=self.original_distance(self.source,self.group_nodes[r['assigned_slot']],banned=self.player_nodes[pid])
   if not math.isfinite(cost):raise ValueError('No replacement path for '+pid+'; supply deeper position eligibility')
   loss=r['raw_sgp']+cost-self.profit_offset
   if loss<-1e-6:raise ValueError('Negative drafted marginal value; optimizer failed')
   margins[pid]=dict(sgp_above_replacement=max(0.0,loss),effective_replacement_sgp=r['raw_sgp']-max(0.0,loss),assigned_slot=r['assigned_slot'],player_type=r['player_type'],selected=True)
  alternatives=[]
  for r in self.records:
   if r['player_id'] in selected:continue
   choices=[(r['raw_sgp']-thresholds[g],g,thresholds[g]) for g in r['eligible_slots'] if g in thresholds]
   vor,g,floor=max(choices,key=lambda x:(x[0],x[1]))
   if vor>1e-6:raise ValueError('Positive undrafted inclusion gain; optimizer failed')
   alternatives.append(dict(r,sgp_above_replacement=min(0.0,vor),effective_replacement_sgp=floor,assigned_slot=g,selected=False))
  return margins,alternatives,thresholds

def allocate_cents(selected,teams,budget_per_team,minimum_bid,hitter_share):
 total=round(teams*budget_per_team*100);minimum=round(minimum_bid*100);hbudget=round(total*hitter_share)
 budgets={'hitter':hbudget,'pitcher':total-hbudget};values={};factors={}
 for typ,budget in budgets.items():
  pool=[r for r in selected if r['player_type']==typ];discretionary=budget-minimum*len(pool)
  if discretionary<0:raise ValueError('Budget split cannot cover minimum bids')
  weights=[max(0,r['sgp_above_replacement']) for r in pool];wsum=sum(weights)
  if not pool:raise ValueError('Empty auction group')
  if wsum<=1e-10:weights=[1.0]*len(pool);wsum=len(pool);factor=0.0
  else:factor=(discretionary/100)/wsum
  exact=[minimum+discretionary*w/wsum for w in weights];rounded=[math.floor(v+1e-9) for v in exact]
  remainder=budget-sum(rounded)
  order=sorted(range(len(pool)),key=lambda i:(-(exact[i]-rounded[i]),pool[i]['player_id']))
  for i in order[:remainder]:rounded[i]+=1
  for r,cents in zip(pool,rounded):values[r['player_id']]=cents
  factors[typ]=factor
 if sum(values.values())!=total:raise ValueError('Auction budget does not reconcile')
 return values,factors,budgets
