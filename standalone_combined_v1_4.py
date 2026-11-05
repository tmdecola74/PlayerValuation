"""Frozen composition of chronological v1.3 selections. No fitting or new selection."""
import csv,hashlib,json,math
from collections import defaultdict
from pathlib import Path
from standalone_io_v1_0 import load,sha,verify,table,validate_features
from standalone_models_v1_0 import finite
from standalone_workload_experiments_v1_3 import gates,gate_statistics,volume_overlay,DISCLOSURE
from workload_experiments_io_v1_3 import read_baseline,iter_csv,probability_bank
from standalone_role_workload_v1_2 import prior_role
from role_workload_io_v1_2 import read_labels,verify_join

METHODS=['frozen_v1_2','selected_probability_experiment','selected_change_experiment','combined_v1_4']
FIELDS=['season','player_type','mlbam_id','method','metric','prediction']
METRICS={'hitter':['PA','AB','H','1B','2B','3B','HR','R','RBI','SB','BB','HBP','SF','SH','AVG','OBP','SLG','OPS'], 'pitcher':['OUTS','IP','H','ER','BB','SO','HR','W','SV','HLD','QS','ERA','WHIP','SV_plus_HLD']}
RESEARCH='workload_change_candidate'

def near(a,b):
 return (a is None and b is None) or (finite(a) and finite(b) and abs(a-b)<=1e-9*max(1.,abs(a),abs(b)))

def coherent(role,values):
 """Validate primitives and derive ratios; missing components stay missing."""
 v=dict(values)
 if any(x is not None and (not finite(x) or x<0) for x in v.values()):raise ValueError('Negative/nonfinite forecast')
 def equation(m,deps,fn):
  expected=fn() if all(finite(v.get(n)) for n in deps) else None
  if not near(v.get(m),expected):raise ValueError('Incoherent '+role+' '+m)
  v[m]=expected
 def upper(total,parts):
  if finite(v.get(total)) and all(finite(v.get(n)) for n in parts) and sum(v[n] for n in parts)>v[total]+1e-8*max(1,v[total]):raise ValueError('Incoherent component bound '+total)
 if role=='hitter':
  equation('H',['1B','2B','3B','HR'],lambda:sum(v[n] for n in ['1B','2B','3B','HR']))
  upper('PA',['AB','BB','HBP','SF','SH']);upper('AB',['H'])
  equation('AVG',['H','AB'],lambda:v['H']/v['AB'] if v['AB']>0 else None)
  equation('OBP',['H','BB','HBP','AB','SF'],lambda:(v['H']+v['BB']+v['HBP'])/(v['AB']+v['BB']+v['HBP']+v['SF']) if v['AB']+v['BB']+v['HBP']+v['SF']>0 else None)
  equation('SLG',['1B','2B','3B','HR','AB'],lambda:(v['1B']+2*v['2B']+3*v['3B']+4*v['HR'])/v['AB'] if v['AB']>0 else None)
  equation('OPS',['OBP','SLG'],lambda:v['OBP']+v['SLG'])
 else:
  equation('IP',['OUTS'],lambda:v['OUTS']/3)
  upper('H',['HR'])
  equation('ERA',['ER','OUTS'],lambda:27*v['ER']/v['OUTS'] if v['OUTS']>0 else None)
  equation('WHIP',['H','BB','OUTS'],lambda:3*(v['H']+v['BB'])/v['OUTS'] if v['OUTS']>0 else None)
  v['SV_plus_HLD']=v['SV']+v['HLD'] if finite(v.get('SV')) and finite(v.get('HLD')) else None
 return v

def choose_for_role(role,choice):
 # Pitcher change is deliberately excluded from combined production candidate.
 return 'selected_change_experiment' if role=='hitter' else 'selected_probability_experiment'

def decisions(predictions,rows,truth,settings):
 """Replay gates BEFORE adding each origin's outcomes. Never includes 2026 truth."""
 histories=defaultdict(list);result=[]
 for year in range(2019,2027):
  pc={n:gates(histories['probability_'+n],year,settings) for n in ['control','frozen']}
  choice=dict(season=year,probability_experiment=dict(adopt=all(x['adopt'] for x in pc.values()),comparisons=pc),change_experiment={r:gates(histories['change_'+r],year,settings) for r in ['hitter','pitcher']});result.append(choice);fold=defaultdict(list)
  for key,p in predictions.items():
   if key[0]!=year:continue
   role=key[1];r=rows[key];metric='PA' if role=='hitter' else 'OUTS';b=p['frozen_v1_2'];cat=p['categorical_probability_candidate'];control=p['prior_probability_control'];change=p[RESEARCH]
   expected_probability=cat if role=='pitcher' and choice['probability_experiment']['adopt'] else b
   expected_change=change if choice['change_experiment'][role]['adopt'] else b
   if not near(p['selected_probability_experiment'],expected_probability) or not near(p['selected_change_experiment'],expected_change):raise ValueError('Forecast does not follow chronological selection')
   if year==2026:continue
   a=truth.get(key+(metric,))
   if a is None or not finite(b):continue
   from standalone_workload_experiments_v1_3 import anchor
   anc=anchor(r,settings);guard=prior_role(r)=='STARTER' if role=='pitcher' else anc is not None and anc>=settings['hitter_guard_prior_PA']
   if role=='pitcher' and finite(cat) and finite(control):
    for name,comp in [('control',control),('frozen',b)]:
     item=(key[2],a,comp,cat);fold['probability_'+name,'all'].append(item)
     if guard:fold['probability_'+name,'guard'].append(item)
   if finite(change):
    item=(key[2],a,b,change);fold['change_'+role,'all'].append(item)
    if guard:fold['change_'+role,'guard'].append(item)
  for (name,cohort),items in fold.items():histories[name].append(gate_statistics(year,cohort,items))
 return result

def context(source,matrix,baseline,labels):
 source,matrix,baseline,labels=map(lambda p:Path(p).resolve(),(source,matrix,baseline,labels));watched={}
 for root in [source,matrix,baseline,labels]:watched.update(verify(root))
 frozen=load(source/'frozen_models.json')
 for n,h in load(source/'freeze_manifest.json').items():
  if sha(source/n)!=h:raise ValueError('v1.3 freeze mismatch')
 for name,key in [('training_matrix.parquet','training_matrix_sha256'),('holdout_features.parquet','holdout_features_sha256'),('feature_schema.json','feature_schema_sha256')]:
  if sha(matrix/name)!=frozen[key]:raise ValueError('Frozen matrix binding mismatch')
 if sha(labels/'training_labels.parquet')!=frozen['training_labels_sha256'] or load(labels/'label_build_report.json')['reference_sha256']!=frozen['label_reference_sha256'] or load(labels/'label_build_report.json')['primary_source']!='FROZEN_FANGRAPHS_ACTUALS':raise ValueError('Frozen label binding mismatch')
 if sha(baseline/'frozen_models.json')!=frozen['source_v1_2_model_sha256']:raise ValueError('Frozen v1.2 binding mismatch')
 old=load(baseline/'frozen_models.json');freeze12=load(baseline/'freeze_manifest.json')
 if sha(baseline/'role_predictions.csv')!=frozen['source_role_probabilities_sha256']:raise ValueError('v1.3 probability-source binding mismatch')
 if sha(baseline/'frozen_2026_forecasts.csv')!=freeze12['forecasts_sha256'] or sha(baseline/'frozen_models.json')!=freeze12['models_sha256']:raise ValueError('v1.2 freeze mismatch')
 allow=load(matrix/'feature_schema.json')['predictor_allowlist'];train=validate_features(table(matrix/'training_matrix.parquet'),allow,True,2025);hold=validate_features(table(matrix/'holdout_features.parquet'),allow,False,2026)
 if any(r['target_season']!=2026 or any(k.startswith('y_') for k in r) for r in hold):raise ValueError('Evaluation features contain outcomes/wrong season')
 truth=verify_join(train,read_labels(labels,'training'));rows={(r['target_season'],r['player_type'],r['mlbam_id']):r for r in train+hold};base=read_baseline(baseline);predictions={}
 from standalone_workload_experiments_v1_3 import METHODS as INPUT_METHODS
 for r in iter_csv(source/'workload_predictions.csv'):
  key=(int(r['season']),r['player_type'],r['mlbam_id'])
  if key in predictions or key not in base or key not in rows or not 2019<=key[0]<=2026:raise ValueError('Invalid/duplicate workload domain')
  p={m:None if r[m]=='' else float(r[m]) for m in INPUT_METHODS}
  if any(x is not None and (not finite(x) or x<0) for x in p.values()):raise ValueError('Invalid workload value')
  metric='PA' if key[1]=='hitter' else 'OUTS'
  if not near(p['frozen_v1_2'],base[key].get(metric)):raise ValueError('Changed baseline workload')
  predictions[key]=p
 expected={k for k in rows if 2019<=k[0]<=2026}
 if set(predictions)!=set(base) or set(predictions)!=expected:raise ValueError('Incomplete forecast domain')
 choices=decisions(predictions,rows,truth,frozen['settings'])
 if choices!=load(source/'rolling_choices.json'):raise ValueError('Historical gate replay differs from v1.3')
 if choices[-1]['probability_experiment']!=frozen['models']['probability_choice'] or choices[-1]['change_experiment']!=frozen['models']['change_choices']:raise ValueError('Final model choices disagree')
 for r in load(source/'fit_audit.json'):
  if not 2019<=r['origin']<=2026 or any(y>=r['origin'] or y==2020 for y in r['fit_years']):raise ValueError('Model fit chronology violation')
 bank=probability_bank(baseline,train+hold,freeze12);classes={}
 for r in iter_csv(source/'classification_and_probability_inputs.csv'):
  key=(int(r['season']),'pitcher',r['mlbam_id']);src=bank[key[0],key[2]]['prior_role']
  if key in classes or key not in predictions or r['classification_label']!=src['predicted_role'] or r['prior_role']!=src['prior_role']:raise ValueError('Prior-role classification changed')
  classes[key]=r
 if set(classes)!={k for k in predictions if k[1]=='pitcher'}:raise ValueError('Incomplete classification domain')
 # Validate complete full-vector source, including missing rows and duplicates.
 seen=set()
 for filename in ['historical_forecasts.csv','frozen_2026_forecasts.csv']:
  for r in iter_csv(source/filename):
   key=(int(r['season']),r['player_type'],r['mlbam_id']);m=r['method'];token=(key,m,r['metric'])
   if key not in predictions or m not in METHODS[:3] or token in seen or (key[0]==2026)!=(filename.startswith('frozen')):raise ValueError('Invalid/duplicate full forecast')
   seen.add(token);value=None if r['prediction']=='' else float(r['prediction']);expected_value=volume_overlay(base[key],predictions[key][m],key[1]).get(r['metric'])
   if r['metric'] not in base[key] or not near(value,expected_value):raise ValueError('Full vector differs from frozen selected overlay')
 expected_count=sum(3*len(v) for v in base.values())
 if len(seen)!=expected_count:raise ValueError('Incomplete source full-vector forecast')
 return dict(source=source,matrix=matrix,baseline=baseline,labels=labels,watched=watched,frozen=frozen,rows=rows,base=base,predictions=predictions,choices=choices,classes=classes)

def vectors(c,key):
 p=c['predictions'][key];base=c['base'][key];role=key[1];out={}
 for m in METHODS[:3]:out[m]=coherent(role,volume_overlay(base,p[m],role))
 out['combined_v1_4']=dict(out[choose_for_role(role,None)])
 if any(v.get('SV')!=base.get('SV') for v in out.values()):raise ValueError('Saves forecast changed')
 return out

def read_all_labels(root,split):
 values={};seen=set()
 for r in table(Path(root)/('training_labels.parquet' if split=='training' else 'holdout_labels.parquet')):
  y=int(r['season']);role=r['player_type'];pid=str(r['mlbam_id']);metric=r['metric'];key=(y,role,pid,metric)
  if key in seen or role not in METRICS or not pid.isdigit() or int(pid)<=0 or (split=='training' and not 2015<=y<=2025) or (split!='training' and y!=2026):raise ValueError('Invalid/duplicate label or split')
  seen.add(key)
  if r['eligible']:
   if not finite(r['label_value']) or (metric in METRICS[role] and r['label_value']<0):raise ValueError('Invalid eligible actual')
   values[key]=float(r['label_value'])
 # Missing labels may represent dependency exclusions. Never reconstruct them.
 return values

SCORE_FIELDS=['season','player_type','metric','cohort','comparison_group','method','n','mae','rmse','bias','membership_sha256','stress_season']
COVERAGE_FIELDS=['season','player_type','metric','cohort','comparison_group','method','eligible_actuals','available_forecasts','common_pool']
PAIR_FIELDS=['season','player_type','mlbam_id','metric','cohort','comparison_group','method','prediction','actual','source_record_id']

def score_all(c,actual,score_writer,coverage_writer,pair_writer,external=None,available=None,maximum=2026):
 """Identical pools per metric/cohort/group, streamed pair rows, no outcome imputation."""
 external=external or {};available=available or {};counts=defaultdict(int)
 for year in range(2019,maximum+1):
  for role,metrics in METRICS.items():
   pool={k[2]:vectors(c,k) for k in c['predictions'] if k[:2]==(year,role)}
   groups=[('internal',METHODS)]
   sources=sorted(available.get(year,set()))
   groups += [(s+'_paired',METHODS+[s]) for s in sources]
   if sources:groups.append(('all_available_sources',METHODS+sources))
   for metric in metrics:
    eligible={pid:actual[year,role,pid,metric] for pid in pool if (year,role,pid,metric) in actual}
    cohorts=['all_eligible']
    if metric in ['ERA','WHIP']:cohorts+=['actual_IP_ge40','actual_IP_ge100']
    if metric in ['AVG','OBP','SLG','OPS']:cohorts+=['actual_PA_ge100','actual_PA_ge300']
    for cohort in cohorts:
     subset=eligible
     if cohort!='all_eligible':
      denom='IP' if 'IP' in cohort else 'PA';floor=int(cohort.split('ge')[-1]);subset={pid:a for pid,a in eligible.items() if finite(actual.get((year,role,pid,denom))) and actual[year,role,pid,denom]>=floor}
     for group,methods in groups:
      def value(pid,m):return pool[pid][m].get(metric) if m in METHODS else external.get((year,role,pid,metric,m),(None,None))[0]
      common=sorted(pid for pid in subset if all(finite(value(pid,m)) for m in methods));membership=hashlib.sha256(json.dumps(common).encode()).hexdigest()
      for m in methods:
       errors=[value(pid,m)-subset[pid] for pid in common];n=len(errors);stats=dict(season=year,player_type=role,metric=metric,cohort=cohort,comparison_group=group,method=m,n=n,mae=sum(abs(x) for x in errors)/n if n else None,rmse=math.sqrt(sum(x*x for x in errors)/n) if n else None,bias=sum(errors)/n if n else None,membership_sha256=membership,stress_season=year==2020);score_writer.writerow(stats);counts['score_rows']+=1
       coverage_writer.writerow(dict(season=year,player_type=role,metric=metric,cohort=cohort,comparison_group=group,method=m,eligible_actuals=len(subset),available_forecasts=sum(finite(value(pid,m)) for pid in subset),common_pool=n))
       for pid in common:
        pair_writer.writerow(dict(season=year,player_type=role,mlbam_id=pid,metric=metric,cohort=cohort,comparison_group=group,method=m,prediction=value(pid,m),actual=subset[pid],source_record_id='FROZEN_STANDALONE' if m in METHODS else external[year,role,pid,metric,m][1]));counts['pair_rows']+=1
 return dict(counts)
