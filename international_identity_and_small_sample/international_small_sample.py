"""Priority ID queue and separately specified small-sample research assessment."""
import csv,json,math,hashlib,statistics
from pathlib import Path
from collections import defaultdict,Counter
ROOT=Path('D:/JonAPythonClass/pycharm/PlayerValuation')
IN=Path('outputs/international_intake_2019_2026_v2')
OUT=Path('outputs/international_priority_small_sample_v3');OUT.mkdir(exist_ok=False)
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def save(name,rr):
 if not rr:return
 with (OUT/name).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(dict.fromkeys(k for r in rr for k in r)));w.writeheader();w.writerows(rr)
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
PRIORITY={
 'sa3063811':dict(name='Teruaki Sato',role='hitter',league='NPB',club='Tigers (NPB)',evidence='https://www.mlb.com/news/teruaki-sato-mlb-posting-system',candidate_mlbam='831664',profile='https://www.mlb.com/player/teruaki-sato-831664'),
 'sa3062990':dict(name='Kaima Taira',role='pitcher',league='NPB',club='Lions (NPB)',evidence='https://www.mlb.com/news/kaima-taira-will-enter-mlb-posting-system',candidate_mlbam='',profile=''),
 'sa3063835':dict(name='Hiromi Itoh',role='pitcher',league='NPB',club='Fighters (NPB)',evidence='https://www.mlb.com/news/hiromi-itoh-posted-hokkaido-nippon-ham-fighters',candidate_mlbam='808955',profile='https://www.mlb.com/player/hiromi-itoh-808955'),
 'sa3012734':dict(name='Si-hwan Roh',role='hitter',league='KBO',club='Eagles (KBO)',evidence='https://www.mlb.com/news/si-hwan-roh-and-the-kbo-stars-who-could-be-mlb-bound',candidate_mlbam='823574',profile='https://www.mlb.com/player/si-hwan-roh-823574')}
CONTRACT={'version':'international_small_sample_0.1','date':'2026-11-24','decision':'RESEARCH_ONLY_NO_PRODUCTION_ADOPTION',
 'identity_priorities':['P1 official posting report','P2 exact ID present in supplied 2027 benchmark','P3 recent overseas positive exposure and known prior MLB exposure through 2025','P4 positive 2025/2026 overseas history only','P5 secondary-role review: batting <100 PA with >=30 pitching outs, or pitching <30 outs with >=100 batting PA, same league/year; queue triage only, not model filtering'],
 'identity_policy':'Accept only consistent existing or direct co-occurring FG/MLBAM identifiers. Profile-name matches are review candidates, never auto-merged.',
 'benchmark_policy':'Use identity columns and presence only, never projected stats or playing time to fit or rank talent',
 'fit':'Separate league/role/component normal-normal log-rate-ratio model; no pooling NPB/KBO or borrowing minor coefficients',
 'log_ratio':'log((target_count+0.5)/(target_den+1))-log((source_count+0.5)/(source_den+1))',
 'sampling_variance':'Count inverse variances; subtract denominator inverse terms for PA/AB/TBF binomial approximation; no subtraction for OUTS Poisson rate approximation; floor 0.000001',
 'prior_mean_log_factor':0,'prior_sd_primary':0.35,'prior_sd_sensitivity':[0.2,0.5],
 'prior_interpretation':'Numerical shrinkage toward no change, NOT evidence that overseas statistics equal MLB statistics',
 'fixed_between_player_log_sd':0.25,'minimum_players_for_diagnostic_fit':3,
 'dedup':'First eligible next-year transition per player, selected within earlier-only calibration set; repeated movers are not independent people',
 'origins':[2021,2022,2023,2024,2025],'label_max_year':2025,
 'comparators':['same-prior untranslated rate','MLB population prior'],
 'regression_exposure':{'AB':200,'PA':200,'OUTS':300,'TBF':300},
 'uncertainty':'Conditional 95% factor intervals under fixed assumed prior/heterogeneity; not empirically calibrated forecast intervals',
 'influence':'Leave one calibration player out; log-factor change, no parameter selection',
 'adoption_rules_unchanged':{'minimum_calibration_players':30,'minimum_paired_exposure':1000,'minimum_test_rows':30,'minimum_supported_folds':3},
 'forbidden':['2026 MLB labels or evaluation','prospective MLB PA/IP forecasts','production writes','automatic promotion','threshold relaxation presented as validation','pooling leagues'],
 'limitations':['Few movers','Selected arrivals and returners','Tiny batting samples from pitchers','No age/park adjustments','Retrospective identity links','No independent untouched test','Fixed uncertainty assumptions']}
(OUT/'experiment_contract.json').write_text(json.dumps(CONTRACT,indent=2))
bench=list(ROOT.glob('2027*111326.csv'))
protected=list((ROOT/'outputs/skill_regressed_release_v1_43').rglob('*'))+list(Path('outputs/park_aware_challenger_run2').glob('*'))
paths=list(IN.glob('*.csv'))+[ROOT/'outputs/training_labels_v1_0/training_labels.csv']+bench+[p for p in protected if p.is_file()]
hashes={str(p):sha(p) for p in paths}
prepared=read(IN/'international_stints_prepared.csv');observed=defaultdict(set);benchmark_presence=defaultdict(set);evidence=defaultdict(set)
for r in prepared:
 if r['resolved_mlbam_id']:observed[r['PlayerId']].add(r['resolved_mlbam_id']);evidence[r['PlayerId'],r['resolved_mlbam_id']].add('EXISTING_EXACT_ID_CROSSWALK')
for p in bench:
 role='hitter' if 'hitters' in p.name else 'pitcher'
 for r in read(p):
  fg=r.get('PlayerId','').strip();mid=r.get('MLBAMID','').strip()
  if fg:benchmark_presence[fg,role].add(p.name)
  if fg and mid:observed[fg].add(mid);evidence[fg,mid].add(p.name)
labels=defaultdict(dict)
for r in read(ROOT/'outputs/training_labels_v1_0/training_labels.csv'):
 y=int(r['season'])
 if y<=2025 and r['eligible'].lower()=='true' and r['label_value']!='':
  v=float(r['label_value'])
  if math.isfinite(v) and v>=0:labels[r['player_type'],y,r['mlbam_id']][r['metric']]=v
prior_mlb=defaultdict(list)
for (role,y,mid),r in labels.items():
 if r.get('PA' if role=='hitter' else 'OUTS',0)>0:prior_mlb[role,mid].append(y)
groups=defaultdict(list)
for r in prepared:
 if r['exposure_status']=='POSITIVE':groups[r['source_league'],r['player_type'],r['PlayerId']].append(r)
pitching=defaultdict(float);batting=defaultdict(float)
for r in prepared:
 if r['player_type']=='pitcher' and r['OUTS']!='':pitching[r['source_league'],r['PlayerId'],int(r['Season'])]+=float(r['OUTS'])
 if r['player_type']=='hitter':batting[r['source_league'],r['PlayerId'],int(r['Season'])]+=float(r['PA'])
queue=[];newlinks=[]
for (league,role,fg),rr in groups.items():
 latest=max(int(r['Season']) for r in rr)
 if latest<2025:continue
 newest=[r for r in rr if int(r['Season'])==latest];name=newest[0]['NameASCII'];candidates=observed[fg]
 mid=next(iter(candidates)) if len(candidates)==1 else ''
 posted=fg in PRIORITY and PRIORITY[fg]['role']==role
 if posted:
  assert league==PRIORITY[fg]['league'] and PRIORITY[fg]['club'] in {r['Team'] for r in newest}
 present=bool(benchmark_presence[fg,role]);prior=bool(mid and prior_mlb[role,mid])
 tier=1 if posted else 2 if present else 3 if prior else 4
 den='PA' if role=='hitter' else 'OUTS';exp=sum(float(r[den]) for r in newest)
 incidental=((role=='hitter' and exp<100 and pitching[league,fg,latest]>=30) or (role=='pitcher' and exp<30 and batting[league,fg,latest]>=100)) and not posted
 if incidental:tier=5
 row=dict(priority=tier,league=league,role=role,PlayerId=fg,name=name,latest_source_season=latest,latest_teams=';'.join(sorted({r['Team'] for r in newest})),latest_source_exposure=exp,exposure_unit=den,resolved_mlbam_id=mid,identity_status='ID_CONFLICT_WITHHELD' if len(candidates)>1 else 'EXACT_ID_LINK' if mid else 'UNRESOLVED_ID',benchmark_presence=';'.join(sorted(benchmark_presence[fg,role])),MLB_history_through2025=prior,latest_known_MLB_season=max(prior_mlb[role,mid]) if prior else '',arrival_status='OFFICIAL_POSTING_REPORT' if posted else 'BENCHMARK_PRESENCE_ONLY' if present else 'RETURNER_WATCHLIST_NOT_SIGNING_EVIDENCE' if prior else 'OVERSEAS_HISTORY_ONLY_NOT_MLB_ARRIVAL',source_url=PRIORITY[fg]['evidence'] if posted else '',candidate_mlbam_id=PRIORITY[fg]['candidate_mlbam'] if posted and not mid else '',candidate_profile=PRIORITY[fg]['profile'] if posted and not mid else '',candidate_status='REVIEW_REQUIRED_NOT_APPLIED' if posted and PRIORITY[fg]['candidate_mlbam'] and not mid else '',as_of='2026-11-24')
 queue.append(row)
 row['role_review_flag']='SECONDARY_ROLE_REVIEW_ONLY' if incidental else ''
 if mid and not any(r['resolved_mlbam_id']==mid for r in rr):newlinks.append(dict(PlayerId=fg,mlbam_id=mid,evidence=';'.join(sorted(evidence[fg,mid])),status='DIRECT_IDENTIFIER_COOCCURRENCE'))
queue.sort(key=lambda r:(r['priority'],0 if not r['resolved_mlbam_id'] else 1,-r['latest_source_season'],r['league'],r['role'],-r['latest_source_exposure'],r['PlayerId']))
save('priority_identity_queue.csv',queue);save('priority_1_to_3.csv',[r for r in queue if r['priority']<=3]);save('new_exact_ID_links.csv',newlinks)
# Transition outcomes are the previously audited <=2025 eligible data, not 2026 outcomes.
pairs=read(IN/'component_transition_pairs.csv')
for p in pairs:
 for c in ['source_count','source_den','target_count','target_den','paired_exposure']:p[c]=float(p[c])
 p['source_year']=int(p['source_year']);p['target_year']=int(p['target_year'])
 assert p['target_year']<=2025 and p['target_year']==p['source_year']+1

def posterior(pp,sd=.35):
 # All components in this experiment are count rates. OUTS rates can exceed one;
 # the conservative Poisson 1/count variance is used there, without binomial subtraction.
 people={}
 for r in sorted(pp,key=lambda r:r['target_year']):people.setdefault(r['mlbam_id'],r)
 if len(people)<3:return None
 precision=1/sd**2;numer=0;used=[]
 for r in people.values():
  z=math.log((r['target_count']+.5)/(r['target_den']+1))-math.log((r['source_count']+.5)/(r['source_den']+1))
  variance=1/(r['target_count']+.5)+1/(r['source_count']+.5)
  if r['denominator']!='OUTS':variance-=1/(r['target_den']+1)+1/(r['source_den']+1)
  w=1/(max(.000001,variance)+.25**2);precision+=w;numer+=w*z;used.append(r)
 mean=numer/precision;se=math.sqrt(1/precision)
 return dict(mean_log_factor=mean,posterior_log_sd=se,factor=math.exp(mean),factor_lower95=math.exp(mean-1.96*se),factor_upper95=math.exp(mean+1.96*se),players=len(people),paired_exposure=sum(r['paired_exposure'] for r in used),fit_max_year=max(r['target_year'] for r in used),used=used)

keys=sorted({(r['league'],r['role'],r['component'],r['denominator']) for r in pairs})
models=[];pred=[];influence=[]
for key in keys:
 league,role,component,den=key;pool=[p for p in pairs if (p['league'],p['role'],p['component'],p['denominator'])==key]
 for origin in [2021,2022,2023,2024,2025,2027]:
  train=[p for p in pool if p['target_year']<origin and p['target_year']<=2025]
  test=[p for p in pool if p['target_year']==origin]
  prior_rows=[r for (rr,y,mid),r in labels.items() if rr==role and 2015<=y<min(origin,2026) and component in r and r.get(den,0)>0]
  prior=sum(r[component] for r in prior_rows)/sum(r[den] for r in prior_rows) if prior_rows else None
  for sd in [.35,.2,.5]:
   fit=posterior(train,sd)
   if not fit:continue
   assert fit['fit_max_year']<origin and fit['fit_max_year']<=2025
   meta=dict(league=league,role=role,component=component,denominator=den,origin=origin,prior_log_sd=sd)
   models.append({**meta,**{k:v for k,v in fit.items() if k!='used'},'adoption_calibration_supported':fit['players']>=30 and fit['paired_exposure']>=1000,'MLB_prior':prior,'status':'EXPERIMENTAL_NOT_VALIDATED'})
   if prior is None:continue
   strength=CONTRACT['regression_exposure'][den]
   for p in test:
    prediction=(p['source_count']*fit['factor']+strength*prior)/(p['source_den']+strength)
    if den!='OUTS':prediction=min(1,max(0,prediction))
    pred.append({**meta,'mlbam_id':p['mlbam_id'],'fit_max_year':fit['fit_max_year'],'source_year':p['source_year'],'actual':p['target_count']/p['target_den'],'candidate':prediction,'untranslated':(p['source_count']+strength*prior)/(p['source_den']+strength),'population':prior,'target_den':p['target_den'],'train_players':fit['players'],'train_paired_exposure':fit['paired_exposure'],'target_year':p['target_year']})
   if origin==2027 and sd==.35:
    for person in fit['used']:
     alt=posterior([r for r in train if r['mlbam_id']!=person['mlbam_id']],sd)
     if alt:influence.append({**meta,'omitted_player':person['mlbam_id'],'full_factor':fit['factor'],'leave_one_out_factor':alt['factor'],'absolute_log_factor_change':abs(alt['mean_log_factor']-fit['mean_log_factor'])})
save('experimental_factor_models.csv',models);save('chronological_diagnostic_predictions.csv',pred);save('leave_one_player_out_influence.csv',influence)
scores=[];bins=defaultdict(list)
for r in pred:bins[tuple(r[c] for c in ['league','role','component','denominator','origin','prior_log_sd'])].append(r)
for key,rr in bins.items():
 meta=dict(zip(['league','role','component','denominator','origin','prior_log_sd'],key));membership=sha_string='|'.join(sorted(r['mlbam_id'] for r in rr))
 for method in ['candidate','untranslated','population']:
  errors=[r[method]-r['actual'] for r in rr]
  scores.append({**meta,'method':method,'n':len(rr),'membership_sha256':hashlib.sha256(membership.encode()).hexdigest(),'mse':sum(e*e for e in errors)/len(errors),'mae':sum(abs(e) for e in errors)/len(errors),'bias':sum(errors)/len(errors),'adoption_fold_supported':len(rr)>=30 and min(r['train_players'] for r in rr)>=30 and min(r['train_paired_exposure'] for r in rr)>=1000})
save('chronological_diagnostic_scores.csv',scores)
# Conditional, unaged translated source-history rates for priorities only. No PA/IP forecasts.
scenarios=[]
for q in queue:
 if q['priority']>3:continue
 rr=[r for r in prepared if r['source_league']==q['league'] and r['player_type']==q['role'] and r['PlayerId']==q['PlayerId'] and 2023<=int(r['Season'])<=2026]
 for m in models:
  if m['origin']!=2027 or m['prior_log_sd']!=.35 or m['league']!=q['league'] or m['role']!=q['role']:continue
  c=m['component'];d=m['denominator'];eligible=[r for r in rr if r.get(c,'')!='' and r.get(d,'')!='' and float(r[d])>0]
  if not eligible:continue
  raw=sum((int(r['Season'])-2022)*float(r[c]) for r in eligible)/sum((int(r['Season'])-2022)*float(r[d]) for r in eligible)
  scenarios.append(dict(priority=q['priority'],league=q['league'],role=q['role'],PlayerId=q['PlayerId'],name=q['name'],component=c,denominator=d,raw_recency_weighted_rate=raw,experimental_translated_rate=raw*m['factor'],factor_lower_scenario_rate=raw*m['factor_lower95'],factor_upper_scenario_rate=raw*m['factor_upper95'],status='UNAGED_SOURCE_HISTORY_SCENARIO_NOT_A_2027_FORECAST',identity_status=q['identity_status']))
save('priority_rate_scenarios.csv',scenarios)
assert all(sha(p)==h for p,h in hashes.items())
(OUT/'source_manifest.json').write_text(json.dumps(hashes,indent=2));(OUT/'posting_evidence.json').write_text(json.dumps(PRIORITY,indent=2))
report={'decision':'RESEARCH_ONLY_DO_NOT_ADOPT','priority_counts':dict(Counter(r['priority'] for r in queue)),'queue_rows':len(queue),'new_exact_ID_links':len(newlinks),'P1_resolved_exact':sum(r['priority']==1 and bool(r['resolved_mlbam_id']) for r in queue),'P1_profile_candidates_not_applied':sum(r['priority']==1 and bool(r['candidate_mlbam_id']) for r in queue),'experimental_model_rows':len(models),'diagnostic_predictions':len(pred),'supported_adoption_score_rows':sum(r['adoption_fold_supported'] for r in scores),'protected_hashes_unchanged':True,'MLB_2026_outcomes_used':False,'prior_note':'Shrinkage-to-one is an assumption, not MLB equivalence. Sensitivity and factor intervals are conditional and uncalibrated.'}
(OUT/'assessment_report.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2));print('P1',json.dumps([r for r in queue if r['priority']==1],indent=2))
