"""Prior-history opportunity models; missing outcomes never imply nonappearance."""
import copy
import numpy as np
from standalone_models_v1_0 import Target,fit,predict,finite

DERIVED=['RECENT_MAX_VOLUME','LATEST_VOLUME','VOLUME_TREND','START_SHARE','RELIEF_G','SV_PER_G','HLD_PER_G','OBSERVED_LAGS']
DISCLOSURE='2026 was reviewed during v1.0 development. It is a disclosed evaluation set, not an untouched holdout; no 2026 outcomes enter v1.1 fitting or selection.'

def role_of(g,gs):
 if not finite(g) or not finite(gs) or g<=0 or not 0<=gs<=g:return 'UNKNOWN'
 return 'STARTER' if gs/g>=.5 else 'RELIEVER' if gs/g<=.1 else 'SWING'

def labels(rows):
 out=copy.deepcopy(rows)
 for r in out:
  value=lambda m:r.get('y_'+m) if r.get('y_eligible_'+m) else None
  g,gs,sv=value('G'),value('GS'),value('SV');exp=value('PA' if r['player_type']=='hitter' else 'OUTS')
  active=1 if (finite(g) and g>0) or (finite(exp) and exp>0) else 0 if finite(g) and g==0 and finite(exp) and exp==0 else None
  for name,v in [('ACTIVE',active),('ANY_SAVE',int(sv>0) if finite(sv) and finite(g) and g>0 else None),('POS_SV',sv if finite(sv) and sv>0 and finite(g) and g>0 else None)]:r['y_'+name]=v;r['y_eligible_'+name]=int(v is not None)
  r['observed_role']=role_of(g,gs)
 return out

def enrich(rows,role):
 out=copy.deepcopy(rows);metric='PA' if role=='hitter' else 'OUTS'
 for r in out:
  vol=[]
  for lag in [1,2,3]:
   v=r.get(f'x_actual_lag{lag}_{metric}')
   if finite(v):vol.append(v*(2.7 if r.get(f'source_season_lag{lag}')==2020 else 1))
  g,gs,sv,hld=(r.get('x_actual_lag1_'+m) for m in ['G','GS','SV','HLD'])
  values=[max(vol) if vol else None,vol[0] if vol else None,vol[0]-vol[1] if len(vol)>1 else None,gs/g if finite(gs) and finite(g) and g>0 and 0<=gs<=g else None,g-gs if finite(gs) and finite(g) and 0<=gs<=g else None,sv/g if finite(sv) and finite(g) and g>0 else None,hld/g if finite(hld) and finite(g) and g>0 else None,len(vol)]
  for name,v in zip(DERIVED,values):r['x_actual_lag1_'+name]=v
 return out

def train(rows,allow,base):
 c=copy.deepcopy(base)
 for role in ['hitter','pitcher']:c['actual_features'][role]+=DERIVED+['G','GS','SV','HLD']
 bundle={'models':{},'config':c};audit=[]
 for role in ['hitter','pitcher']:
  rr=enrich([r for r in labels(rows) if r['player_type']==role and r['target_season']!=2020],role);aa=allow+['x_actual_lag1_'+m for m in DERIVED];volume='PA' if role=='hitter' else 'OUTS'
  targets=[Target(role,volume,volume,None,0,800 if role=='hitter' else 900,0),Target(role,'ACTIVE','ACTIVE',None,0,1,0)]
  if role=='pitcher':targets += [Target(role,'G','G',None,0,90,0),Target(role,'START_SHARE','GS','G',1,1,20),Target(role,'ANY_SAVE','ANY_SAVE',None,0,1,0),Target(role,'POS_SV_RATE','POS_SV','G',1,1,20)]
  for t in targets:
   fitting=[r for r in rr if r['y_ACTIVE']==1] if t.name in [volume,'G'] else rr
   known=[r['y_ACTIVE'] for r in rr if r['y_eligible_ACTIVE']];supported=t.name!='ACTIVE' or (known.count(0)>=c['participation_minimum_each_class'] and known.count(1)>=c['participation_minimum_each_class'])
   m=fit(fitting,t,aa,c)
   if not supported:m['coefficients']=None;m['ridge_status']='PARTICIPATION_BLOCKED_NO_VERIFIED_CLASS_SUPPORT'
   bundle['models'][t.id]={'target':t.__dict__,'model':m,'supported':supported};audit.append(dict(target=t.id,n_fit=m['n_fit'],fit_years=m['fit_target_seasons'],status=m['ridge_status']))
 return bundle,audit

def forecast(bundle,rows):
 out={}
 for role in ['hitter','pitcher']:
  rr=enrich([r for r in rows if r['player_type']==role],role);pp={}
  for key,s in bundle['models'].items():
   if key.startswith(role+'_'):t=Target(**s['target']);_,pp[t.name]=predict(s['model'],rr,t,bundle['config'])
  for i,r in enumerate(rr):
   volume='PA' if role=='hitter' else 'OUTS';supported=bundle['models'][role+'_ACTIVE']['supported'];p=pp['ACTIVE'][i] if supported else 1.;v=pp[volume][i]
   d=dict(participation_probability=p,participation_supported=supported,conditional_volume=v,volume=None if v is None or p is None else p*v)
   if role=='pitcher':
    g,s,prob,rate=(pp[k][i] for k in ['G','START_SHARE','ANY_SAVE','POS_SV_RATE']);d.update(G=None if g is None else p*g,GS=None if g is None or s is None else p*g*s,start_share=s,predicted_role=role_of(1,s),save_probability_given_active=prob,save_rate_given_positive=rate,saves=None if any(v is None for v in [p,g,prob,rate]) else p*g*prob*rate)
   out[(r['target_season'],role,r['mlbam_id'])]=d
 return out

def selection(history,role,component,c):
 valid=[h for h in history if h['player_type']==role and h['component']==component and h['season']!=2020 and h['n']>=c['minimum_validation_rows']]
 result=dict(adopt=False,validation_seasons=[h['season'] for h in valid],reason='INSUFFICIENT_PRIOR_FOLDS')
 if len(valid)<c['minimum_selection_folds']:return result
 bm,cm,ba,ca=(float(np.mean([h[n] for h in valid])) for n in ['v1_mse','candidate_mse','v1_mae','candidate_mae']);ok=bm>0 and cm<=bm*(1-c['minimum_mse_improvement']) and ca<=ba*(1+c['maximum_mae_degradation'])
 result.update(adopt=bool(ok),reason='EARLIER_FOLDS_GATE_PASSED' if ok else 'EARLIER_FOLDS_GATE_REJECTED',v1_mse=bm,candidate_mse=cm,v1_mae=ba,candidate_mae=ca)
 if component=='saves':
  cc=dict(c);cc['minimum_validation_rows']=c['minimum_saves_cohort_rows'];gate=selection(history,role,'saves_relevant',cc);result['prior_saves_cohort_gate']=gate;result['adopt']=bool(result['adopt'] and gate['adopt'])
  if not gate['adopt']:result['reason']='PRIOR_SAVES_COHORT_GATE_REJECTED_OR_INSUFFICIENT'
 return result

def apply(old,d,role,choices):
 v=dict(old);volume='PA' if role=='hitter' else 'OUTS';new=d.get('volume');den=old.get(volume)
 counts=['PA','AB','H','1B','2B','3B','HR','BB','HBP','SF','SH','R','RBI','SB'] if role=='hitter' else ['OUTS','IP','H','ER','BB','SO','HR','W','HLD','QS']
 if choices[role+'_volume']['adopt'] and finite(new) and finite(den) and den>0:
  for name in counts:
   if finite(v.get(name)):v[name]*=new/den
 if v.get(volume)==0:
  for name in (['AVG','OBP','SLG','OPS'] if role=='hitter' else ['ERA','WHIP']):v[name]=None
 if role=='pitcher' and choices['pitcher_saves']['adopt'] and finite(d.get('saves')):v['SV']=d['saves']
 return v
