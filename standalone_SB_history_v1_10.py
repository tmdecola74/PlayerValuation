"""A fixed, exposure-aware multiyear SB propensity baseline. No complex model."""
from collections import defaultdict
from standalone_models_v1_0 import finite
from standalone_growth_sb_v1_6 import opportunity
from standalone_refinements_v1_8 import selection as select18,add_history as add18

DISCLOSURE='2026 was previously reviewed and is disclosed evaluation only. Historical-only fitting/selection retains 2021; 2020 target is stress-only.'
METHODS=['frozen_v1_5','last_season_rate','multiyear_candidate','selected_SB_experiment']

def settings_checked(s):
 if s.get('version')!='1.10.0' or len(s.get('lag_weights',[]))!=3 or any(not finite(x) or x<=0 for x in s['lag_weights']):raise ValueError('Wrong configuration/lag weights')
 for n,v in s.items():
  if n not in ['version','lag_weights'] and (not finite(v) or v<=0):raise ValueError('Invalid control: '+n)
 if s['minimum_selection_folds']<2 or s['minimum_candidate_fraction']>1 or s['minimum_mse_improvement']>=1 or s['diagnostic_reduction_fraction']>=1 or s['diagnostic_return_fraction']>1:raise ValueError('Invalid selection/diagnostic controls')
 return s

def population(actual,origin,s):
 members=[]
 keys=sorted({k[:3] for k in actual if k[1]=='hitter' and k[0]<origin and k[0]!=2020})
 for k in keys:
  sb=actual.get(k+('SB',));opp=opportunity({m:actual.get(k+(m,)) for m in ['H','HR','BB','HBP']})
  if not finite(sb) or not finite(opp) or opp<=0:continue
  members.append(dict(origin=origin,season=k[0],mlbam_id=k[2],SB=sb,proxy=opp))
 n=len(members);den=sum(d['proxy'] for d in members);num=sum(d['SB'] for d in members);supported=n>=s['minimum_population_rows'] and den>0
 return dict(origin=origin,fit_years=sorted({d['season'] for d in members}),n=n,SB_sum=num,proxy_sum=den,population_rate=num/den if supported else None,supported=supported),members

def lag_history(r,s):
 rows=[]
 for lag,w in enumerate(s['lag_weights'],1):
  p=f'x_actual_lag{lag}_';sb=r.get(p+'SB');opp=opportunity({m:r.get(p+m) for m in ['H','HR','BB','HBP']})
  known=finite(sb) and sb>=0 and finite(opp) and opp>0;rows.append(dict(lag=lag,source_season=r.get('source_season_lag'+str(lag)),weight=w,SB=sb,proxy=opp,usable=known))
 return rows

def prediction(k,r,base,model,s):
 history=lag_history(r,s);usable=[d for d in history if d['usable']];num=sum(d['weight']*d['SB'] for d in usable);den=sum(d['weight']*d['proxy'] for d in usable);opp=opportunity(base);last=history[0];rawlast=last['SB']/last['proxy'] if last['usable'] else None;lastrate=min(s['maximum_SB_rate'],rawlast) if finite(rawlast) else None
 rawmulti=(num+s['prior_opportunities']*model['population_rate'])/(den+s['prior_opportunities']) if model['supported'] else None;rate=min(s['maximum_SB_rate'],max(0.,rawmulti)) if finite(rawmulti) else None;supported=finite(opp) and finite(rate);lastsupported=finite(opp) and finite(lastrate)
 return dict(metric='SB',baseline=base.get('SB'),candidate=min(s['maximum_SB'],opp*rate) if supported else base.get('SB'),last_season=min(s['maximum_SB'],opp*lastrate) if lastsupported else base.get('SB'),supported=bool(supported),last_supported=bool(lastsupported),support_status='AVAILABLE_WITH_HISTORY' if supported and usable else 'POPULATION_ONLY_NO_USABLE_HISTORY' if supported else 'MISSING_PROXY_OR_POPULATION',projected_proxy=opp,population_rate=model['population_rate'],multiyear_rate=rate,raw_multiyear_rate=rawmulti,last_rate=lastrate,raw_last_rate=rawlast,weighted_SB=num,weighted_proxy=den,usable_lags=len(usable),population_only=bool(supported and not usable))

def selection(history,origin,s):
 a=select18(history['accepted'],origin,'hitter',s);b=select18(history['last_season'],origin,'hitter',s);return dict(adopt=a['adopt'] and b['adopt'],accepted_gates=a['gates'],last_season_gates=b['gates'])
def add_history(year,items,rows,actual,history,s):
 for name in ['accepted','last_season']:
  pp={k:dict(d,baseline=d['baseline'] if name=='accepted' else d['last_season']) for k,d in items.items() if k[1]=='hitter'};h=defaultdict(list);add18(year,pp,rows,actual,h,s);history[name].extend(h['hitter'])
