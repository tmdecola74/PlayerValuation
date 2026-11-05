"""Independent playing-time and rate baselines; training-only preprocessing."""
import math,json
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class Target:
 role:str
 name:str
 numerator:str
 denominator:str|None
 minimum:float
 cap:float
 prior:float
 @property
 def id(self):return self.role+'_'+self.name
 @property
 def playing_time(self):return self.denominator is None
TARGETS=[Target('hitter','PA','PA',None,0,800,0),Target('pitcher','OUTS','OUTS',None,0,900,0)]
for name,num,den,minimum,cap,prior in [
 ('AB_per_PA','AB','PA',50,1,150),('1B_per_AB','1B','AB',30,1,100),('2B_per_AB','2B','AB',30,1,100),('3B_per_AB','3B','AB',30,1,100),('HR_per_AB','HR','AB',30,1,100),
 ('BB_per_PA','BB','PA',50,1,150),('HBP_per_PA','HBP','PA',50,1,150),('SF_per_PA','SF','PA',50,1,150),('SH_per_PA','SH','PA',50,1,150),('R_per_PA','R','PA',50,1,150),('RBI_per_PA','RBI','PA',50,4,150),('SB_per_PA','SB','PA',50,1,150)]:TARGETS.append(Target('hitter',name,num,den,minimum,cap,prior))
for num,cap in [('H',5),('ER',5),('BB',5),('SO',2),('HR',2),('W',1),('SV',1),('HLD',1),('QS',1)]:TARGETS.append(Target('pitcher',num+'_per_OUTS',num,'OUTS',90,cap,300))

def finite(x):return isinstance(x,(int,float,np.number)) and not isinstance(x,bool) and math.isfinite(float(x))
def number(row,col):
 v=row.get(col)
 return float(v) if finite(v) else None

def outcome(row,t):
 a=number(row,'y_'+t.numerator)
 if a is None or a<0 or not row.get('y_eligible_'+t.numerator):return None
 if t.denominator:
  b=number(row,'y_'+t.denominator)
  if b is None or b<t.minimum or b<=0 or not row.get('y_eligible_'+t.denominator):return None
  return a/b,b
 return a,1.

def prior_value(row,metric,lag,c):
 v=number(row,f'x_actual_lag{lag}_{metric}')
 if v is not None and metric in c['volume_metrics'] and row.get(f'source_season_lag{lag}')==2020:v*=c['source_2020_volume_multiplier']
 return v

def historical(row,t,pop,c):
 if pop is None:return None
 weights=c['lag_weights'];values=[]
 if t.playing_time:
  for lag,w in enumerate(weights,1):
   v=prior_value(row,t.numerator,lag,c)
   if v is not None and v>=0:values.append((w,v))
  value=sum(w*v for w,v in values)/sum(w for w,v in values) if values else pop
 else:
  a=b=0.
  for lag,w in enumerate(weights,1):
   n=number(row,f'x_actual_lag{lag}_{t.numerator}');d=number(row,f'x_actual_lag{lag}_{t.denominator}')
   if n is not None and d is not None and d>0:a+=w*n;b+=w*d
  value=(a+t.prior*pop)/(b+t.prior)
  if t.role=='pitcher' and t.numerator in c['structural_zero_baseline_counts'] and b>0 and a==0:value=0.
 return min(t.cap,max(0.,value))

def feature_names(allow,t,c):
 actual=set(c['actual_features'][t.role])|{t.numerator,t.denominator}
 names=[]
 for name in allow:
  if name in c['context_features'] or name.startswith(('tracking_era_lag','short_season_lag')):names.append(name)
  elif name.startswith('x_statcast_lag'):names.append(name)
  elif name.startswith('x_actual_lag'):
   metric=name.split('_',3)[-1]
   if metric in actual:names.append(name)
 return sorted(names)

def get_feature(row,name,c):
 if name.startswith('x_actual_lag'):
  lag=int(name.split('_')[2][3:]);metric=name.split('_',3)[-1]
  return prior_value(row,metric,lag,c)
 return number(row,name)

def fit_transform(rows,names,c):
 state={'numeric':{},'categorical':{},'dropped':[],'clip_z':c['clip_z']}
 for name in names:
  values=[get_feature(r,name,c) for r in rows]
  finite_values=[v for v in values if v is not None]
  if not finite_values:state['dropped'].append(name);continue
  if name.startswith('tracking_era_lag'):
   state['categorical'][name]=sorted(set(finite_values));continue
  med=float(np.median(finite_values));filled=np.array([med if v is None else v for v in values]);mean=float(filled.mean());scale=float(filled.std())
  state['numeric'][name]={'median':med,'mean':mean,'scale':scale if scale>1e-12 else 1.}
 return state

def transform(rows,state,c):
 columns=[]
 for name,s in state['numeric'].items():
  v=[get_feature(r,name,c) for r in rows];missing=np.array([x is None for x in v],dtype=float);filled=np.array([s['median'] if x is None else x for x in v],dtype=float)
  columns.extend([np.clip((filled-s['mean'])/s['scale'],-state['clip_z'],state['clip_z']),missing])
 for name,categories in state['categorical'].items():
  v=[get_feature(r,name,c) for r in rows]
  columns.extend([np.array([float(x==cat) for x in v]) for cat in categories]);columns.append(np.array([float(x not in categories) for x in v]))
 return np.column_stack([np.ones(len(rows))]+columns)

def fit(rows,t,allow,c):
 eligible=[];ys=[];weights=[]
 for r in rows:
  if r['player_type']!=t.role:continue
  if t.playing_time and r['target_season'] in c['exclude_playing_time_target_seasons']:continue
  o=outcome(r,t)
  if o is not None:eligible.append(r);ys.append(o[0]);weights.append(min(o[1],c['maximum_exposure_weight']))
 pop=(sum(y*w for y,w in zip(ys,weights))/sum(weights)) if weights else None
 model={'target':t.id,'n_fit':len(eligible),'fit_target_seasons':sorted({r['target_season'] for r in eligible}),'population_value':pop,'preprocessing':None,'coefficients':None,'ridge_status':'INSUFFICIENT_TRAINING_ROWS'}
 if len(eligible)<c['minimum_fit_rows']:return model
 state=fit_transform(eligible,feature_names(allow,t,c),c);x=transform(eligible,state,c);w=np.array(weights,dtype=float);w/=w.sum()
 base=np.array([historical(r,t,pop,c) for r in eligible]);residual=np.array(ys)-base
 penalty=np.eye(x.shape[1])*c['ridge_alpha'];penalty[0,0]=1e-10
 coef=np.linalg.solve(x.T@(x*w[:,None])+penalty,x.T@(w*residual))
 if not np.isfinite(coef).all():raise ValueError('Nonfinite ridge solution')
 model.update(preprocessing=state,coefficients=coef.tolist(),ridge_status='FITTED');return model

def predict(model,rows,t,c):
 base=[historical(r,t,model['population_value'],c) for r in rows]
 if model['coefficients'] is None:return base,list(base)
 adjustment=transform(rows,model['preprocessing'],c)@np.array(model['coefficients'])
 ridge=[None if v is None else min(t.cap,max(0.,v+float(d))) for v,d in zip(base,adjustment)]
 return base,ridge

def choose(history,t,c):
 valid=[h for h in history if h['target']==t.id and h['n']>=c['minimum_validation_rows'] and not(t.playing_time and h['season'] in c['exclude_playing_time_target_seasons']) and h['ridge_fitted']]
 result={'candidate':'historical_baseline','validation_seasons':[h['season'] for h in valid],'reason':'INSUFFICIENT_PRIOR_VALIDATION_FOLDS'}
 if len(valid)<c['minimum_selection_folds']:return result
 bm=float(np.mean([h['baseline_mse'] for h in valid]));rm=float(np.mean([h['ridge_mse'] for h in valid]));ba=float(np.mean([h['baseline_mae'] for h in valid]));ra=float(np.mean([h['ridge_mae'] for h in valid]))
 adopt=bm>0 and rm<=bm*(1-c['minimum_mse_improvement']) and ra<=ba*(1+c['maximum_mae_degradation'])
 result.update(candidate='ridge' if adopt else 'historical_baseline',reason='PRIOR_FOLDS_GATE_PASSED' if adopt else 'PRIOR_FOLDS_GATE_REJECTED',baseline_mse=bm,ridge_mse=rm,baseline_mae=ba,ridge_mae=ra)
 return result

def compose(role,components):
 g=lambda n:components.get(role+'_'+n)
 mul=lambda a,b:None if a is None or b is None else a*b
 div=lambda a,b:None if a is None or b is None or b<=0 else a/b
 if role=='hitter':
  pa=g('PA');fractions=[g(m) for m in ['AB_per_PA','BB_per_PA','HBP_per_PA','SF_per_PA','SH_per_PA']]
  if any(v is None for v in fractions):ab=bb=hbp=sf=sh=None
  else:
   scale=max(1.,sum(fractions));ab,bb,hbp,sf,sh=[mul(pa,v/scale) for v in fractions]
  hits=[g(m+'_per_AB') for m in ['1B','2B','3B','HR']]
  if any(v is None for v in hits):one=two=three=hr=h=None
  else:
   scale=max(1.,sum(hits));one,two,three,hr=[mul(ab,v/scale) for v in hits];h=None if one is None else one+two+three+hr
  avg=div(h,ab);obp=div(None if h is None or bb is None or hbp is None else h+bb+hbp,None if ab is None or bb is None or hbp is None or sf is None else ab+bb+hbp+sf)
  slg=div(None if one is None else one+2*two+3*three+4*hr,ab)
  return dict(PA=pa,AB=ab,H=h,**{'1B':one,'2B':two,'3B':three,'HR':hr},BB=bb,HBP=hbp,SF=sf,SH=sh,R=mul(pa,g('R_per_PA')),RBI=mul(pa,g('RBI_per_PA')),SB=mul(pa,g('SB_per_PA')),AVG=avg,OBP=obp,SLG=slg,OPS=None if obp is None or slg is None else obp+slg)
 outs=g('OUTS');v={m:mul(outs,g(m+'_per_OUTS')) for m in ['H','ER','BB','SO','HR','W','SV','HLD','QS']}
 if v['HR'] is not None and v['H'] is not None:v['HR']=min(v['HR'],v['H'])
 return dict(OUTS=outs,IP=None if outs is None else outs/3,**v,ERA=div(None if v['ER'] is None else 27*v['ER'],outs),WHIP=div(None if v['H'] is None or v['BB'] is None else 3*(v['H']+v['BB']),outs))
