"""Separate 2027 research release from frozen, historically tested non-park arm."""
import sys,json,csv,math,hashlib
from pathlib import Path
from collections import defaultdict,Counter
sys.path.insert(0,str(Path('work').resolve()))
import park_challenger as pc
from recent_skill_inputs_v1_23 import labels
from participation_label_overlay_v1_27 import apply_overlay
ROOT=pc.ROOT;O=Path('outputs/minor_history_2027_research');O.mkdir(exist_ok=False)
def save(n,rr):pc.save(O/n,rr)
def dump(n,r):(O/n).write_text(json.dumps(r,indent=2))
gates=json.loads(Path('outputs/park_aware_challenger_run2/adoption_gates.json').read_text())
assert all(next(r for r in gates if r['origin']==2026 and r['comparison']=='MINOR_vs_MLB' and r['role']==role)['eligible'] for role in pc.phase.SKILL)
train=ROOT/'outputs/training_labels_v1_0/training_labels.parquet';hp=ROOT/'outputs/recent_history_skills_v1_23/historical_forecasts.csv';ov=ROOT/'outputs/participation_label_overlay_v1_27'
inputpaths=[train,hp,ov/'participation_label_overlay.csv',ov/'report.json',ROOT/'outputs/projection_phase_v1_42/frozen_choices.json',Path('outputs/park_aware_challenger_run2/experiment_contract.json'),Path('outputs/park_aware_challenger_run2/adoption_gates.json'),Path('outputs/historical_affiliate_mapping/affiliate_park_crosswalk.csv')]
inputpaths += [Path(d)/f'{role}s_stints_linkable.csv' for d in ['outputs/minor_league_coverage_2019_2022','outputs/minor_league_coverage_min0'] for role in pc.phase.SKILL]
published=ROOT/'outputs/skill_regressed_release_v1_43'
inputpaths +=[p for p in published.rglob('*') if p.is_file()]+[Path('outputs/international_intake_2019_2026_v2/international_stints_prepared.csv')]
hashes={str(p):pc.digest(p) for p in inputpaths}
actual=labels(train);actual,_=apply_overlay(ov,actual,train,hp,dict(hashes))
bank=json.loads((ROOT/'outputs/projection_phase_v1_42/frozen_choices.json').read_text())['skill_population']
maps={(int(r['season']),pc.org(r['organization_code']),r['level']):r for r in pc.read(inputpaths[7])}
minor=defaultdict(list);stint_flags=[]
for role in pc.phase.SKILL:
 for directory in ['outputs/minor_league_coverage_2019_2022','outputs/minor_league_coverage_min0']:
  for line,r in enumerate(pc.read(Path(directory)/f'{role}s_stints_linkable.csv'),2):
   y=int(r['Season']);den='AB' if role=='hitter' else 'OUTS';m=maps.get((y,pc.org(r['Team']),r['Level']))
   counts={c:pc.val(r.get(c)) for c in [den,*pc.phase.SKILL[role]]}
   eligible=bool(m and y>=2021 and r['Level'] in ['AAA','AA','A+','A'] and all(v is not None for v in counts.values()) and counts[den]>0)
   if eligible:minor[role,y,r['MLBAMID']].append(dict(level=r['Level'],**counts))
   if 2023<=y<=2026:stint_flags.append(dict(role=role,season=y,mlbam_id=r['MLBAMID'],level=r['Level'],source_directory=directory,source_row=line,eligible=eligible,affiliate=m['affiliate_as_supplied'] if m else '',park_factor_used=False,reason='VERIFIED_AFFILIATE_NO_PF_PREDICTOR' if eligible else 'UNSUPPORTED_LEVEL_YEAR_OR_COUNTS'))
save('minor_stint_eligibility.csv',stint_flags)

def getfits(origin):
 pairbank=defaultdict(list)
 for (role,s,pid),rr in minor.items():
  target=s+1
  if target>=origin or target>2025:continue
  den='AB' if role=='hitter' else 'OUTS';td=actual.get((target,role,pid,den))
  if not td:continue
  levels=defaultdict(list)
  for r in rr:levels[r['level']].append(r)
  for level,ss in levels.items():
   sd=sum(r[den] for r in ss)
   for c in pc.phase.SKILL[role]:
    ty=actual.get((target,role,pid,c))
    if ty is not None:pairbank[role,level,c].append(dict(pid=pid,target=target,x=sum(r[c] for r in ss)/sd,y=ty/td,w=min(sd,td),logpf=0,league='NOT_USED'))
 fits={}
 for k,pp in pairbank.items():
  f=pc.fitted(pp)
  if f:fits[k]=f
 return fits

def combine(base,role,pid,origin,fits):
 den='AB' if role=='hitter' else 'OUTS';strength=200 if role=='hitter' else 300
 use=[];unsupported=0
 for y,w in zip(range(origin-4,origin),(1,2,3,4)):
  for r in minor.get((role,y,pid),[]):
   if all((role,r['level'],c) in fits for c in pc.phase.SKILL[role]):use.append((y,w,r))
   else:unsupported+=1
 candidate=dict(base);trace=[]
 if not use:return candidate,False,trace,unsupported
 for c in pc.phase.SKILL[role]:
  mlb=[(y,w,actual.get((y,role,pid,c)),actual.get((y,role,pid,den))) for y,w in zip(range(origin-4,origin),(1,2,3,4))]
  mlb=[(y,w,n,d) for y,w,n,d in mlb if n is not None and d is not None and d>0]
  yearweights={y:w for y,w,n,d in mlb}|{y:w for y,w,r in use};meanw=sum(yearweights.values())/len(yearweights)
  denominator=(sum(w*d for y,w,n,d in mlb)+.5*sum(w*r[den] for y,w,r in use))/meanw
  n=sum(w*n for y,w,n,d in mlb)
  for y,w,r in use:
   rate=fits[role,r['level'],c]['factor']*r[c]/r[den]
   if den=='AB':rate=min(1,max(0,rate))
   n+=.5*w*r[den]*rate
  prior=bank[role][c]['rate']
  # Historical replay uses its own earlier-only prior bank, never the final bank.
  if origin<2027:prior=historical_bank[role][c]['rate']
  if prior is None or base.get(den) is None or not base.get(den):return dict(base),False,[],unsupported
  rate=(n/meanw+strength*prior)/(denominator+strength);candidate[c]=base[den]*rate
  trace.append(dict(role=role,mlbam_id=pid,origin=origin,component=c,denominator=den,rate=rate,normalized_exposure=denominator,prior_rate=prior,prior_exposure=strength,minor_stints=len(use),source_minor_seasons=';'.join(map(str,sorted({y for y,w,r in use}))),includes_2026_minor=any(y==2026 for y,w,r in use)))
 return pc.coherent(candidate,role),True,trace,unsupported

# Verify that replacing PF-presence sample control with verified affiliate membership
# does not change ANY historical forecast. No PF values or park coefficient are used.
old=pc.read('outputs/park_aware_challenger_run2/historical_forecasts.csv');historyfits={};banks={};replayed=0
for r in old:
 if r['arm']!='MLB_PLUS_MINOR':continue
 origin=int(r['origin']);role=r['role'];pid=r['mlbam_id']
 if origin not in banks:banks[origin]=pc.phase.population(actual,origin)
 historical_bank=banks[origin]
 if origin not in historyfits:historyfits[origin]=getfits(origin)
 b=pc.project(actual,role,pid,origin);base,bs,_=pc.phase.skill_candidate(b,actual,role,pid,origin,historical_bank)
 candidate,supported,_,_=combine(base,role,pid,origin,historyfits[origin]) if bs else (dict(base),False,[],0)
 assert supported==(r['supported']=='True')
 for c in pc.FIELDS[role]:
  x=pc.val(r[c]);y=candidate.get(c)
  assert (x is None)==(y is None)
  if x is not None:assert math.isclose(x,y,rel_tol=1e-10,abs_tol=1e-10),(origin,role,pid,c,x,y)
 replayed+=1
fits=getfits(2026)
factorrows=[dict(role=k[0],level=k[1],component=k[2],**{a:v for a,v in f.items() if a in ['factor','players','pairs','paired_exposure','max_target_year']}) for k,f in fits.items()]
save('frozen_minor_factors.csv',factorrows)
freeze=dict(version='MINOR_HISTORY_2027_RESEARCH_0.1',active='MLB_PLUS_MINOR',park_context_active=False,international_active=False,selection_max_year=2025,factor_max_target_year=max(f['max_target_year'] for f in fits.values()),evidence_weight=.5,recency_weights=[1,2,3,4],skill_population=bank,source_contract_sha256=hashes[str(inputpaths[5])],factor_sha256=pc.digest(O/'frozen_minor_factors.csv'),historical_vectors_replayed=replayed,eligibility_clarification='Verified full-season affiliate membership, not PF presence, controls non-park source eligibility. Historical 2021-25 membership and every forecast unchanged; this permits mapped 2026 stints without a missing PF proxy.',history_2026_opened=False)
dump('publication_freeze.json',freeze);freezehash=pc.digest(O/'publication_freeze.json')
# Only now may 2026 labels be opened, strictly as individual player history.
hold=ROOT/'outputs/training_labels_v1_0/holdout_labels.parquet';hashes[str(hold)]=pc.digest(hold)
actual.update(labels(hold,2026))
overlaypath=ROOT/'outputs/pitcher_evaluation_v1_29/evaluation_label_overlay_2026.csv'
certpath=overlaypath.parent/'report.json';hashes[str(overlaypath)]=pc.digest(overlaypath);hashes[str(certpath)]=pc.digest(certpath)
cert=json.loads(certpath.read_text());assert cert['version']=='1.29.0' and cert['season_certified'] and cert['complete_pool_scored']
seen=set()
for r in pc.read(overlaypath):
 pid=r['mlbam_id'];assert r['season']=='2026' and pid not in seen;seen.add(pid)
 assert r['status'] in ['VERIFIED_APPEARED','VERIFIED_NO_APPEARANCE']
 g,o=int(r['evaluation_g']),int(r['evaluation_outs']);assert g>=0 and o>=0
 assert (r['status']=='VERIFIED_APPEARED' and g>0) or (r['status']=='VERIFIED_NO_APPEARANCE' and g==o==0)
 for c,v in [('G',g),('OUTS',o)]:
  k=2026,'pitcher',pid,c;assert actual.get(k,v)==v;actual[k]=v
assert len(seen)==cert['preseason_pool']
international=pc.read('outputs/international_intake_2019_2026_v2/international_stints_prepared.csv')
intl=defaultdict(list)
for r in international:
 if r['resolved_mlbam_id'] and int(r['Season'])>=2025 and r['exposure_status']=='POSITIVE':intl[r['player_type'],r['resolved_mlbam_id']].append(r)
changes=[];traces=[];exceptions=[];summary={};baseline_replays=0
for role in pc.phase.SKILL:
 released=[];mutable={'1B','2B','3B','HR','H','AVG','OBP','SLG','OPS'} if role=='hitter' else {'H','ER','BB','SO','HR','ERA','WHIP'}
 source=pc.read(published/f'projections_2027_{role}s.csv')
 for r in source:
  pid=r['mlbam_id'];base={c:pc.val(r[c]) for c in pc.FIELDS[role]}
  primitive=pc.project(actual,role,pid,2027)
  replay,bs,_=pc.phase.skill_candidate(primitive,actual,role,pid,2027,bank)
  for c in pc.FIELDS[role]:
   x,y=base.get(c),replay.get(c);assert (x is None)==(y is None)
   if x is not None:assert math.isclose(x,y,rel_tol=1e-9,abs_tol=1e-9),(role,pid,c,x,y)
  baseline_replays+=1
  c,supported,t,unfit=combine(base,role,pid,2027,fits) if bs else (dict(base),False,[],0)
  flags=[]
  if not supported:flags.append('V1_43_WHOLE_VECTOR_FALLBACK_NO_SUPPORTED_MINOR_GROUP')
  if unfit:flags.append('UNSUPPORTED_MINOR_LEVEL_STINTS_EXCLUDED')
  if intl[role,pid]:flags.append('INTERNATIONAL_HISTORY_UNTRANSLATED_SKILL_GAP_VISIBLE')
  for stat in pc.FIELDS[role]:
   if stat not in mutable:assert c.get(stat)==base.get(stat)
   if c.get(stat) is not None and base.get(stat) is not None and not math.isclose(c[stat],base[stat],rel_tol=1e-12,abs_tol=1e-12):changes.append(dict(role=role,mlbam_id=pid,name=r['name'],metric=stat,v1_43=base[stat],research=c[stat],delta=c[stat]-base[stat]))
  pc.phase.verify_vector(c,role);traces+=t
  out={**r,**c,'projection_source':'MINOR_HISTORY_2027_RESEARCH_0_1','skill_method':'MLB_PLUS_TRANSLATED_MINOR' if supported else r['skill_method'],'source_release':'v1.43 preserved','minor_supported':supported,'park_context_active':False,'international_translation_active':False,'minor_source_seasons':t[0]['source_minor_seasons'] if t else '', 'includes_2026_minor':any(x['includes_2026_minor'] for x in t),'research_exceptions':';'.join(flags),'release_status':'RESEARCH_ONLY_WITH_EXCEPTIONS','valuation_enabled':False}
  released.append(out)
  for issue in flags:exceptions.append(dict(role=role,mlbam_id=pid,name=r['name'],issue=issue,source='RESEARCH_BRANCH'))
 summary[role]=dict(players=len(released),minor_supported=sum(r['minor_supported'] for r in released),includes_2026_minor=sum(r['includes_2026_minor'] for r in released),international_history_flagged=sum(bool(intl[role,r['mlbam_id']]) for r in released))
 save(f'research_2027_{role}s.csv',released)
save('v1_43_to_research_changes.csv',changes);save('component_trace_2027.csv',traces);save('research_exceptions.csv',exceptions)
save('international_coverage_exceptions.csv',[dict(role=r['player_type'],league=r['source_league'],PlayerId=r['PlayerId'],mlbam_id=r['resolved_mlbam_id'],name=r['NameASCII'],source_year=r['Season'],identity_status=r['identity_status'],status='NOT_TRANSLATED_NO_INTERNATIONAL_FORECAST_OR_WORKLOAD') for r in international if r['Season']=='2026' and r['exposure_status']=='POSITIVE'])
assert pc.digest(O/'publication_freeze.json')==freezehash
assert all(pc.digest(p)==h for p,h in hashes.items())
dump('source_manifest.json',hashes)
dump('release_report.json',dict(version=freeze['version'],status='SEPARATE_RESEARCH_RELEASE_NOT_PRODUCTION',summary=summary,baseline_2027_vectors_replayed=baseline_replays,historical_vectors_replayed=replayed,changed_cells=len(changes),settings_frozen_before_2026_history=True,freeze_sha256=freezehash,history_2026_used_only_for_2027=True,outcomes_2026_used_for_fit_selection_scoring=False,all_workload_anchors_unchanged=True,production_unchanged=True,international_coefficients_used=False,park_coefficients_used=False))
print(json.dumps(json.loads((O/'release_report.json').read_text()),indent=2))
