"""Separate MiLB component bridge experiment. Standard library only; never edits model."""
import argparse,csv,json,math,hashlib,random
from collections import defaultdict
from pathlib import Path

def load(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(p,rows):
 if not rows:return
 fields=list(dict.fromkeys(k for r in rows for k in r))
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def number(x):
 try:
  v=float(x)
  return v if math.isfinite(v) and v>=0 else None
 except (ValueError,TypeError):return None

COMPONENTS={'hitter':[(c,'PA') for c in ['BB','SO','HBP']]+[(c,'AB') for c in ['1B','2B','3B','HR']],
 'pitcher':[(c,'TBF') for c in ['SO','BB','HR']]+[(c,'OUTS') for c in ['H','ER','BB','SO','HR']]}
CONTRACT={'version':'MiLB_component_bridge_pilot_0.1','decision':'RESEARCH_ONLY_NO_PRODUCTION_ADOPTION',
 'forecast_design':'prior-year minor level to next-year MLB, conditional on observed eligible MLB exposure',
 'forecast_test_origins':[2024,2025],'paired_same_year_diagnostic_origins':[2024,2025],
 'fit_rule':'Only pair target years strictly before evaluation target year; no MLB labels after 2025',
 'calibration':'Per component and level: sum(min(source_den,target_den)*MLB_rate) / sum(min(source_den,target_den)*minor_rate)',
 'minimum_calibration_players':30,'minimum_paired_exposure':1000,
 'prior_strength':{'PA':200,'AB':200,'TBF':300,'OUTS':300},
 'prior_rule':'Pooled eligible MLB component numerator/denominator from 2023 through year before evaluation origin',
 'candidate':'(source_count*factor + prior_strength*prior_rate)/(source_den+prior_strength)',
 'comparators':['untranslated_raw','untranslated_with_identical_prior','MLB_population_prior'],
 'scoring':'one forecast per player-level-component; equal-player and target-exposure-weighted MSE/MAE; exact paired membership',
 'multiple_levels':'Evaluate separately; do not stack level predictions or combine them into a player forecast',
 'original_adoption_floor':{'minimum_supported_folds':3,'minimum_rows_per_fold':30,'minimum_improvement':0.01,'max_metric_degradation':0.02},
 'adoption_note':'Original floor is necessary, not sufficient; full original guard/coherent-vector tests are not implemented by this pilot',
 'forbidden':['2026 MLB outcomes','workload fitting','production release changes','automatic lower-level fallback','park or age coefficients without evidence'],
 'limitations':['No park or minor subleague IDs','No archived availability vintages','Selected movers, not all prospects','Next-year effects include development and role changes','Same-year pairs do not establish promotion timing','Only one trainable next-year evaluation fold with source seasons starting 2023','No independent untouched validation','No NPB/KBO factors']}

def fit(pairs,min_players=30,min_exposure=1000):
 # Matched player-level observations. Exposure caps prevent tiny target samples dominating.
 if len({p['pid'] for p in pairs})<min_players:return None
 w=sum(min(p['sd'],p['td']) for p in pairs)
 x=sum(min(p['sd'],p['td'])*p['sx']/p['sd'] for p in pairs)
 y=sum(min(p['sd'],p['td'])*p['ty']/p['td'] for p in pairs)
 if w<min_exposure or x<=0:return None
 return {'factor':y/x,'players':len({p['pid'] for p in pairs}),'pairs':len(pairs),'paired_exposure':w,'source_rate':x/w,'target_rate':y/w}

def run(args):
 CONTRACT.update({'version':'MiLB_component_bridge_extended_0.2','forecast_test_origins':list(range(2020,2026)),
 'paired_same_year_diagnostic_origins':list(range(2020,2026)),
 'prior_rule':'Pooled eligible MLB component rates from 2019 through year before origin',
 'level_policy':'Keep 2019 R and A- distinct; do not relabel as CPX/DSL/A. Tier labels A/A+ persist across reorganization but subleague context remains missing.',
 'pandemic_policy':'No 2020 minor rows expected; never treat missing season as zero. 2019-to-2020 pairs retained with sensitivity excluding 2020 target calibration.',
 'limitations':['Missing park/subleague IDs','Retrospective availability','Selected movers','Next-year development and role confounding','No independent untouched validation','No coherent production integration','2020 shortened MLB season and 2021 minor reorganization'],
 'prior_pilot_preserved':True})
 out=Path(args.output)
 if out.exists():raise FileExistsError('Choose a fresh output directory')
 out.mkdir(parents=True)
 # Written before any eligible MLB label is read.
 (out/'experiment_contract.json').write_text(json.dumps(CONTRACT,indent=2))
 sources=[Path(root)/f'{r}_stints_linkable.csv' for root in [args.minor,args.older] for r in ['hitters','pitchers']]+[Path(args.labels)]
 release=Path(args.release)
 hashes={str(p):sha(p) for p in sources+list(release.glob('*.csv'))}
 mlb=defaultdict(dict);rejected=defaultdict(int)
 with Path(args.labels).open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   season=int(r['season'])
   if not 2018<=season<=2025:continue
   v=number(r['label_value'])
   if r['eligible'].lower()=='true' and v is not None:mlb[(r['player_type'],season,r['mlbam_id'])][r['metric']]=v
 minor=defaultdict(lambda:defaultdict(float));rows=defaultdict(int);ages=defaultdict(list)
 for role in COMPONENTS:
  for r in load(Path(args.older)/f'{role}s_stints_linkable.csv')+load(Path(args.minor)/f'{role}s_stints_linkable.csv'):
   season=int(r['Season'])
   if season>2025:continue
   key=(role,season,r['MLBAMID'],r['Level']);rows[key]+=1
   # Only additive source counts; never sum dashboard rates or multiply baseball IP.
   needed={c for pair in COMPONENTS[role] for c in pair}|{'G','GS'}
   for c in needed:
    v=number(r.get(c))
    if v is not None:minor[key][c]+=v
    else:minor[key]['missing__'+c]+=1
   if number(r.get('Age')) is not None:ages[key].append(float(r['Age']))
 pairs=[]
 for (role,s,pid,level),counts in minor.items():
  for design,lag in [('NEXT_YEAR',1),('SAME_YEAR_DIAGNOSTIC',0)]:
   t=s+lag
   if t>2025:continue
   target=mlb.get((role,t,pid),{})
   for c,d in COMPONENTS[role]:
    if counts.get('missing__'+c) or counts.get('missing__'+d):rejected['missing_source_component']+=1;continue
    if c not in target or d not in target:rejected['missing_or_ineligible_target']+=1;continue
    if counts[d]<=0 or target[d]<=0:rejected['nonpositive_denominator']+=1;continue
    prior=mlb.get((role,s-1,pid),{})
    prior_exp=prior.get('PA' if role=='hitter' else 'OUTS',0)
    pairs.append({'design':design,'role':role,'source_year':s,'target_year':t,'pid':pid,'level':level,'component':c,'denominator':d,'sx':counts[c],'sd':counts[d],'ty':target[c],'td':target[d],
      'age':sum(ages[(role,s,pid,level)])/len(ages[(role,s,pid,level)]) if ages[(role,s,pid,level)] else '',
      'prior_MLB_cohort':'PRIOR_MLB_EXPOSURE' if prior_exp>0 else 'NO_PRIOR_YEAR_MLB_EXPOSURE',
      'source_pitcher_role':'STARTER' if role=='pitcher' and counts['G']>0 and counts['GS']/counts['G']>=.5 else 'RELIEVER' if role=='pitcher' and counts['GS']==0 else 'SWING' if role=='pitcher' else 'HITTER'})
 factors=[];pred=[];support=[]
 for design in ['NEXT_YEAR','SAME_YEAR_DIAGNOSTIC']:
  for origin in range(2020,2026):
   for role,components in COMPONENTS.items():
    for c,d in components:
     eligible_prior=[r for (rr,s,pid),r in mlb.items() if rr==role and 2019<=s<origin and c in r and d in r and r[d]>0]
     prior=sum(r[c] for r in eligible_prior)/sum(r[d] for r in eligible_prior) if eligible_prior else None
     for level in ['AAA','AA','A+','A','CPX','DSL','A-','R']:
      pool=[p for p in pairs if p['design']==design and p['role']==role and p['component']==c and p['denominator']==d and p['level']==level]
      train=[p for p in pool if p['target_year']<origin and (not args.exclude_pandemic or p['target_year']!=2020)]
      test=[p for p in pool if p['target_year']==origin]
      f=fit(train)
      metadata={'design':design,'origin':origin,'role':role,'level':level,'component':c,'denominator':d}
      support.append({**metadata,'calibration_pairs':len(train),'calibration_players':len({p['pid'] for p in train}),'test_pairs':len(test),'supported':bool(f and prior is not None),'status':'SUPPORTED_PILOT' if f and prior is not None else 'INSUFFICIENT_EARLIER_DATA'})
      if not f or prior is None:continue
      assert max(p['target_year'] for p in train)<origin
      factors.append({**metadata,**f,'MLB_prior':prior,'fit_max_target_year':max(p['target_year'] for p in train)})
      strength=CONTRACT['prior_strength'][d]
      for p in test:
       source=p['sx']/p['sd'];estimate=(p['sx']*f['factor']+strength*prior)/(p['sd']+strength)
       # Components over PA/AB/TBF are bounded probabilities; rates per OUTS need not be <=1.
       if d!='OUTS':estimate=min(1,max(0,estimate))
       pred.append({**metadata,'mlbam_id':p['pid'],'source_year':p['source_year'],'source_count':p['sx'],'source_den':p['sd'],'target_count':p['ty'],'target_den':p['td'],'actual':p['ty']/p['td'],'untranslated_raw':source,'untranslated_with_identical_prior':(p['sx']+strength*prior)/(p['sd']+strength),'MLB_population_prior':prior,'translated':estimate,'factor':f['factor'],'age':p['age'],'prior_MLB_cohort':p['prior_MLB_cohort'],'source_pitcher_role':p['source_pitcher_role'],'fit_max_target_year':max(p['target_year'] for p in train)})
 grouped=defaultdict(list)
 for p in pred:
  base=tuple(p[c] for c in ['design','origin','role','level','component','denominator'])
  grouped[base+('ALL',)].append(p)
  grouped[base+(p['prior_MLB_cohort'],)].append(p)
  if p['role']=='pitcher':grouped[base+(p['source_pitcher_role'],)].append(p)
 scores=[]
 for k,pp in grouped.items():
  meta=dict(zip(['design','origin','role','level','component','denominator','cohort'],k))
  membership=hashlib.sha256('|'.join(sorted(p['mlbam_id'] for p in pp)).encode()).hexdigest()
  for weighting in ['EQUAL_PLAYER','TARGET_EXPOSURE']:
   w=[1 if weighting=='EQUAL_PLAYER' else p['target_den'] for p in pp];den=sum(w)
   for method in ['untranslated_raw','untranslated_with_identical_prior','MLB_population_prior','translated']:
    mse=sum(ww*(p[method]-p['actual'])**2 for ww,p in zip(w,pp))/den
    scores.append({**meta,'weighting':weighting,'method':method,'n':len(pp),'membership_sha256':membership,'MSE':mse,'RMSE':math.sqrt(mse),'MAE':sum(ww*abs(p[method]-p['actual']) for ww,p in zip(w,pp))/den,'bias':sum(ww*(p[method]-p['actual']) for ww,p in zip(w,pp))/den})
 save(out/'transition_pairs.csv',pairs);save(out/'factor_support.csv',support);save(out/'fitted_factors.csv',factors);save(out/'validation_predictions.csv',pred);save(out/'validation_scores.csv',scores)
 # Equal-level/component averages are descriptive, not a promotion gate.
 deltas=[]
 for k,pp in grouped.items():
  if k[-1]!='ALL':continue
  errors={m:sum((p[m]-p['actual'])**2 for p in pp)/len(pp) for m in ['translated','untranslated_with_identical_prior','MLB_population_prior']}
  deltas.append({**dict(zip(['design','origin','role','level','component','denominator','cohort'],k)),'n':len(pp),'translated_MSE':errors['translated'],'shrunk_untranslated_MSE':errors['untranslated_with_identical_prior'],'MSE_ratio_vs_shrunk_untranslated':errors['translated']/errors['untranslated_with_identical_prior'] if errors['untranslated_with_identical_prior'] else '', 'MSE_ratio_vs_population':errors['translated']/errors['MLB_population_prior'] if errors['MLB_population_prior'] else ''})
 save(out/'validation_deltas.csv',deltas)
 assert all(p['fit_max_target_year']<p['origin'] and p['origin']<=2025 for p in pred)
 assert all(sha(p)==h for p,h in hashes.items())
 report={'decision':'DO_NOT_ADOPT','reason':'Adoption guard review required; unadjusted park/subleague context; component vectors not integrated or jointly validated',
 'exclude_2020_calibration':args.exclude_pandemic,
 'training_label_max_year':2025,'2026_outcomes_read':False,'production_changed':False,'source_hashes_unchanged':True,
 'pair_count':len(pairs),'prediction_count':len(pred),'factor_count':len(factors),'excluded_pair_reasons':dict(rejected),
 'supported_forecast_origins':sorted({p['origin'] for p in pred if p['design']=='NEXT_YEAR'}),'minimum_adoption_folds':3,
 'score_summary':{}}
 for design in ['NEXT_YEAR','SAME_YEAR_DIAGNOSTIC']:
  for role in COMPONENTS:
   dd=[r for r in deltas if r['design']==design and r['role']==role and r['n']>=30]
   ratios=[r['MSE_ratio_vs_shrunk_untranslated'] for r in dd if isinstance(r['MSE_ratio_vs_shrunk_untranslated'],float)]
   report['score_summary'][design+'_'+role]={'cells_with_at_least_30_rows':len(dd),'cells_improving_over_identically_shrunk_untranslated':sum(v<1 for v in ratios),'mean_cell_MSE_ratio':sum(ratios)/len(ratios) if ratios else None}
 (out/'validation_report.json').write_text(json.dumps(report,indent=2));(out/'source_manifest.json').write_text(json.dumps(hashes,indent=2))
 print(json.dumps(report,indent=2))

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--minor',default='outputs/minor_league_coverage_min0');p.add_argument('--older',default='outputs/minor_league_coverage_2019_2022');p.add_argument('--exclude-pandemic',action='store_true');p.add_argument('--labels',default='D:/JonAPythonClass/pycharm/PlayerValuation/outputs/training_labels_v1_0/training_labels.csv');p.add_argument('--release',default='D:/JonAPythonClass/pycharm/PlayerValuation/outputs/skill_regressed_release_v1_43');p.add_argument('--output',default='outputs/minor_league_translation_extended');run(p.parse_args())
