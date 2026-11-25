"""Frozen, retrospective three-arm skill experiment; no production writes."""
import sys,csv,json,math,hashlib,argparse
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path('D:/JonAPythonClass/pycharm/PlayerValuation')
sys.path.insert(0,str(ROOT))
import projection_phase_v1_42 as phase
from project_2027_v1_31 import project,FIELDS

def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(p,rr):
 if not rr:return
 keys=list(dict.fromkeys(k for r in rr for k in r))
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rr)
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def val(x):
 try:
  v=float(x);return v if math.isfinite(v) and v>=0 else None
 except (ValueError,TypeError):return None
def org(x):return 'ATH' if x in ['OAK','ATH'] else x
ARMS=['MLB_ONLY','MLB_PLUS_MINOR','MLB_PLUS_MINOR_PARK']
CONTRACT={'version':'park_challenger_0.1','status':'RESEARCH_ONLY','origins':[2022,2023,2024,2025],
 'MLB_baseline':'Exact reconstructed v1.43 skill recipe via original project/population/skill_candidate; certified v1.27 historical participation overlay',
 'components':phase.SKILL,'priors':{'hitter_AB':200,'pitcher_OUTS':300},'weights':[1,2,3,4],
 'minor_evidence_weight':0.5,'minor_window':'Same prior four seasons; only mapped 2021-2025 AAA/AA/A+/A stints',
 'calibration':'Previous-season MiLB to next-season eligible MLB; targets strictly before forecast origin; min 30 distinct players and 1000 min(source,target) exposure per level/component',
 'plain_factor':'Sum(w*target_rate)/sum(w*source_rate), w=min(source_den,target_den)',
 'park_context':'Sequential fixed residual model: per-subleague residual mean shrunk with 1000 exposure, then centered log(final run PF) residual slope shrunk with penalty 10. Component-specific coefficients, no uniform division.',
 'context_features':'Source-season PF and supplied source subleague only; no target park, future league constants or target playing time',
 'missing_context':'Missing PF excludes stint from BOTH minor-history arms; missing subleague is explicit UNKNOWN group',
 'fairness':'Same mapped stints, component support, baseline players, target-label eligibility and fixed anchors across all three arms',
 'merge':'MLB and MiLB events are disjoint; sum each source stint once. Recency mean normalized by distinct observed seasons, then add population prior ONCE.',
 'fallback':'If complete minor skill group or park fit unsupported, both minor arms equal MLB_ONLY for whole vector',
 'new_players':'Coverage-only; no population-only baseline or invented PA/IP',
 'gates':phase.CONTRACT,'comparisons':['MINOR_vs_MLB','PARK_vs_MLB','PARK_vs_MINOR'],
 'selection_max_year':2025,'2026_MLB_outcomes_forbidden':True,'production_changes':False,
 'limitations':['Retrospective vintages','Selected MLB movers','No actual home/road exposure','Run PF is context proxy, not component PF','MLB target park not neutralized','No NPB/KBO','Previously reviewed development seasons, no untouched holdout']}

def fitted(pp):
 if len({p['pid'] for p in pp})<30:return None
 weight=sum(p['w'] for p in pp);x=sum(p['w']*p['x'] for p in pp)
 if weight<1000 or x<=0:return None
 factor=sum(p['w']*p['y'] for p in pp)/x
 logmean=sum(p['w']*p['logpf'] for p in pp)/weight
 league=defaultdict(lambda:[0.,0.])
 for p in pp:
  v=league[p['league']];v[0]+=p['w']*(p['y']-factor*p['x']);v[1]+=p['w']
 effects={k:n/(d+1000) for k,(n,d) in league.items()}
 numerator=sum(p['w']*(p['logpf']-logmean)*(p['y']-factor*p['x']-effects[p['league']]) for p in pp)
 denominator=sum(p['w']*(p['logpf']-logmean)**2 for p in pp)+10
 return dict(factor=factor,logpf_mean=logmean,beta=numerator/denominator,league_effects=effects,
             pairs=len(pp),players=len({p['pid'] for p in pp}),paired_exposure=weight,max_target_year=max(p['target'] for p in pp))

def coherent(v,role):
 v=dict(v)
 if role=='hitter':
  h=sum(v[c] for c in phase.SKILL[role])
  if h>v['AB']:
   for c in phase.SKILL[role]:v[c]*=v['AB']/h
  v['H']=sum(v[c] for c in phase.SKILL[role]);v['AVG']=v['H']/v['AB']
  v['SLG']=sum(i*v[c] for i,c in enumerate(phase.SKILL[role],1))/v['AB']
  v['OBP']=(v['H']+v['BB']+v['HBP'])/(v['AB']+v['BB']+v['HBP']+v['SF']);v['OPS']=v['OBP']+v['SLG']
 else:
  v['H']=max(v['H'],v['HR']);v['ERA']=27*v['ER']/v['OUTS'];v['WHIP']=3*(v['H']+v['BB'])/v['OUTS']
 phase.verify_vector(v,role)
 return v

def run(out):
 if out.exists():raise FileExistsError('Fresh output required')
 out.mkdir(parents=True)
 (out/'experiment_contract.json').write_text(json.dumps(CONTRACT,indent=2))
 paths=[ROOT/'outputs/training_labels_v1_0/training_labels.parquet',ROOT/'outputs/participation_label_overlay_v1_27/participation_label_overlay.csv',ROOT/'outputs/participation_label_overlay_v1_27/report.json',ROOT/'outputs/recent_history_skills_v1_23/historical_forecasts.csv',Path('outputs/historical_affiliate_mapping/affiliate_park_crosswalk.csv')]
 paths +=[Path(d)/f'{r}_stints_linkable.csv' for d in ['outputs/minor_league_coverage_2019_2022','outputs/minor_league_coverage_min0'] for r in ['hitters','pitchers']]
 paths+=list((ROOT/'outputs/skill_regressed_release_v1_43').glob('*.csv'))
 paths+=[ROOT/'projection_phase_v1_42.py',ROOT/'project_2027_v1_31.py']
 hashes={str(p):digest(p) for p in paths};(out/'source_manifest.json').write_text(json.dumps(hashes,indent=2))
 from recent_skill_inputs_v1_23 import labels
 actual=labels(paths[0])
 # Verify and apply the original certified overlay using its original validation code.
 from participation_label_overlay_v1_27 import apply_overlay
 actual,ov=apply_overlay(paths[1].parent,actual,paths[0],paths[3],dict(hashes))
 assert max(k[0] for k in actual)<=2025
 maps={(int(r['season']),org(r['organization_code']),r['level']):r for r in read(paths[4])}
 assert len(maps)==720
 attached=[];minor=defaultdict(list);coverage=Counter();newpool=[]
 for role in phase.SKILL:
  for directory in ['outputs/minor_league_coverage_2019_2022','outputs/minor_league_coverage_min0']:
   for rownum,r in enumerate(read(Path(directory)/f'{role}s_stints_linkable.csv'),2):
    year=int(r['Season']);m=maps.get((year,org(r['Team']),r['Level']))
    pf=val(m['park_final']) if m else None
    status='MAPPED_PF' if pf and 2021<=year<=2025 else 'NO_FACTOR_FOR_YEAR_OR_LEVEL'
    coverage[role,status]+=1
    den='AB' if role=='hitter' else 'OUTS';counts={c:val(r.get(c)) for c in [den,*phase.SKILL[role]]}
    eligible=status=='MAPPED_PF' and all(v is not None for v in counts.values()) and counts[den]>0
    attached.append({'role':role,'season':year,'mlbam_id':r['MLBAMID'],'organization':r['Team'],'level':r['Level'],'source_directory':directory,'source_row':rownum,'affiliate':m['affiliate_as_supplied'] if m else '', 'park_team':m['park_team'] if m else '', 'subleague':m['league_as_supplied'] if m else '', 'park_factor':pf,'coverage_status':status,'positive_complete_counts':eligible})
    if eligible:
     minor[role,year,r['MLBAMID']].append({'level':r['Level'],'league':m['league_as_supplied'] or 'UNKNOWN_SUPPLIED_LEAGUE','pf':pf,**counts})
 save(out/'stints_with_park_context.csv',attached)
 # One calibration observation per player/source-year/level, not per duplicate dashboard.
 pairbank=defaultdict(list)
 for (role,s,pid),stints in minor.items():
  target=s+1
  if target>2025:continue
  levels=defaultdict(list)
  for r in stints:levels[r['level']].append(r)
  den='AB' if role=='hitter' else 'OUTS'
  td=actual.get((target,role,pid,den))
  if not td:continue
  for level,rr in levels.items():
   sd=sum(r[den] for r in rr);logpf=sum(r[den]*math.log(r['pf']) for r in rr)/sd
   # Multiple supplied subleagues in a player/level/year are labeled MULTI, not first-match.
   leagues={r['league'] for r in rr};league=next(iter(leagues)) if len(leagues)==1 else 'MULTI_SUBLEAGUE'
   for c in phase.SKILL[role]:
    ty=actual.get((target,role,pid,c))
    if ty is not None:pairbank[role,level,c].append(dict(pid=pid,source=s,target=target,x=sum(r[c] for r in rr)/sd,y=ty/td,w=min(sd,td),logpf=logpf,league=league))
 forecasts=[];traces=[];fitrows=[];coverage_rows=[];scorebin=defaultdict(list)
 for origin in CONTRACT['origins']:
  print('Forecast origin',origin,flush=True)
  fits={}
  for k,pp in pairbank.items():
   f=fitted([p for p in pp if p['target']<origin])
   if f:
    assert f['max_target_year']<origin;fits[k]=f
    fitrows.append(dict(origin=origin,role=k[0],level=k[1],component=k[2],**{a:b for a,b in f.items() if a!='league_effects'},league_effects=json.dumps(f['league_effects'],sort_keys=True)))
  bank=phase.population(actual,origin)
  for role in phase.SKILL:
   ids=phase.ids_before(actual,role,origin);existing=set(ids)
   for pid in {pid for (rr,s,pid) in minor if rr==role and origin-4<=s<origin}-existing:
    newpool.append(dict(origin=origin,role=role,mlbam_id=pid,status='MINOR_HISTORY_NO_MLB_BASELINE_NO_WORKLOAD_FORECAST'))
   den='AB' if role=='hitter' else 'OUTS';strength=200 if role=='hitter' else 300
   for pid in ids:
    baseline=project(actual,role,pid,origin)
    b,base_supported,_=phase.skill_candidate(baseline,actual,role,pid,origin,bank)
    ctx=phase.context(actual,role,pid,origin);usable=[];unfit=0
    for y,w in zip(range(origin-4,origin),(1,2,3,4)):
     for r in minor.get((role,y,pid),[]):
      if all((role,r['level'],c) in fits for c in phase.SKILL[role]):usable.append((y,w,r))
      else:unfit+=1
    supported=bool(base_supported and usable)
    arms={a:dict(b) for a in ARMS}
    if supported:
     for c in phase.SKILL[role]:
      mlb=[(y,w,actual.get((y,role,pid,c)),actual.get((y,role,pid,den))) for y,w in zip(range(origin-4,origin),(1,2,3,4))]
      mlb=[(y,w,n,d) for y,w,n,d in mlb if n is not None and d is not None and d>0]
      # Normalize by DISTINCT seasons, not by number of stints or levels.
      yearweights={y:w for y,w,n,d in mlb}|{y:w for y,w,r in usable};meanw=sum(yearweights.values())/len(yearweights)
      dn=(sum(w*d for y,w,n,d in mlb)+.5*sum(w*r[den] for y,w,r in usable))/meanw
      plain=sum(w*n for y,w,n,d in mlb);park=plain
      for y,w,r in usable:
       f=fits[role,r['level'],c];x=r[c]/r[den];p=f['factor']*x
       q=max(0,p+f['league_effects'].get(r['league'],0)+f['beta']*(math.log(r['pf'])-f['logpf_mean']))
       if den=='AB':p=min(1,max(0,p));q=min(1,q)
       plain+=.5*w*r[den]*p;park+=.5*w*r[den]*q
      prior=bank[role][c]['rate']
      arms['MLB_PLUS_MINOR'][c]=b[den]*(plain/meanw+strength*prior)/(dn+strength)
      arms['MLB_PLUS_MINOR_PARK'][c]=b[den]*(park/meanw+strength*prior)/(dn+strength)
      traces.append(dict(origin=origin,role=role,mlbam_id=pid,component=c,denominator=den,normalized_combined_exposure=dn,prior_rate=prior,prior_exposure=strength,MLB_seasons=len(mlb),minor_stints=len(usable),distinct_seasons=len(yearweights),mean_recency_weight=meanw))
     for a in ARMS[1:]:arms[a]=coherent(arms[a],role)
    mutable={'1B','2B','3B','HR','H','AVG','OBP','SLG','OPS'} if role=='hitter' else {'H','ER','BB','SO','HR','ERA','WHIP'}
    for a,v in arms.items():
     phase.verify_vector(v,role)
     assert all(v.get(c)==b.get(c) for c in FIELDS[role] if c not in mutable)
     forecasts.append(dict(origin=origin,role=role,mlbam_id=pid,arm=a,supported=supported,history=ctx['history'],freshness=ctx['freshness'],minor_stints_used=len(usable),minor_stints_unsupported=unfit,**{c:v.get(c) for c in FIELDS[role]}))
    coverage_rows.append(dict(origin=origin,role=role,mlbam_id=pid,supported=supported,MLB_baseline_supported=base_supported,minor_stints_used=len(usable),minor_stints_unsupported=unfit,history=ctx['history']))
    metrics=phase.RATES[role]+(('H','HR','R','RBI','SB') if role=='hitter' else ('SO','ER','BB','H','HR','W'))
    truth=phase.observe(actual,origin,role,pid,metrics)
    for c in metrics:
     target=truth[c];pp={a:phase.rate(role,c,v) for a,v in arms.items()}
     if target is None or any(v is None for v in pp.values()):continue
     for cohort in ['ALL',ctx['history']]:
      scorebin[origin,role,c,cohort,'SUPPORTED' if supported else 'FALLBACK'].append((pid,{a:p-target for a,p in pp.items()}))
 scores=[]
 for key,rr in scorebin.items():
  for a in ARMS:
   ee=[v[a] for pid,v in rr];mse=sum(e*e for e in ee)/len(ee)
   scores.append(dict(zip(['season','role','metric','cohort','pool'],key))|dict(arm=a,n=len(rr),membership_sha256=phase.keyhash([p for p,v in rr]),mse=mse,rmse=math.sqrt(mse),mae=sum(abs(e) for e in ee)/len(ee),bias=sum(ee)/len(ee)))
 gates=[]
 for comparison,(base,candidate) in {'MINOR_vs_MLB':ARMS[:2],'PARK_vs_MLB':[ARMS[0],ARMS[2]],'PARK_vs_MINOR':ARMS[1:]}.items():
  # Original gate code unmodified, with methods relabeled for pairwise comparison.
  mapped=[{**r,'experiment':'SKILL','method':'weighted_actuals' if r['arm']==base else 'skill_regression'} for r in scores if r['arm'] in [base,candidate]]
  for origin in [2023,2024,2025,2026]:
   for role in phase.SKILL:gates.append(dict(comparison=comparison,**phase.gate(mapped,role,'SKILL',origin)))
 save(out/'historical_forecasts.csv',forecasts);save(out/'component_trace.csv',traces);save(out/'fitted_context_models.csv',fitrows);save(out/'coverage_by_player.csv',coverage_rows);save(out/'prospect_coverage_only.csv',newpool);save(out/'historical_scores.csv',scores)
 (out/'adoption_gates.json').write_text(json.dumps(gates,indent=2))
 save(out/'adoption_gates.csv',[{**r,'reasons':';'.join(r['reasons']),'years':';'.join(map(str,r['years']))} for r in gates])
 assert all(digest(p)==h for p,h in hashes.items())
 report=dict(version=CONTRACT['version'],decision='RESEARCH_ONLY_NO_AUTOMATIC_ADOPTION',stint_coverage={str(k):v for k,v in coverage.items()},forecast_rows=len(forecasts),support_counts=dict(Counter((str(r['origin'])+' '+r['role']+' '+str(r['supported'])) for r in coverage_rows)),final_gates=[r for r in gates if r['origin']==2026],production_unchanged=True,outcomes_2026_read=False,overlay=ov)
 (out/'report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--output',default='outputs/park_aware_challenger');run(Path(p.parse_args().output))
