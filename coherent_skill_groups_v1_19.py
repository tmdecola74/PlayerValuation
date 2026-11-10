"""Chronological grouped skill replacement against accepted forecasts; research only."""
import argparse,json,math,shutil,hashlib
from pathlib import Path
from collections import defaultdict,Counter
from standalone_io_v1_0 import load,dump,sha,csvrows,start,finish
from standalone_diagnostics_v1_16 import checked,label_index,feature_index,cohorts,score,comparison_summary,emit
from standalone_combined_v1_4 import coherent,METRICS,near
from statcast_incremental_v1_17 import finite
from audit_skill_composition_v1_18 import read_inputs
VERSION='1.19.0'
ARMS=['group_standard','group_statcast']
GROUPS={
 'hitter':dict(name='HITTER_HIT_DISTRIBUTION',targets=['hitter_'+m+'_per_AB' for m in ['1B','2B','3B','HR']],metrics=['AVG','OPS','HR'],changed=['1B','2B','3B','HR','H','AVG','OBP','SLG','OPS']),
 'pitcher':dict(name='PITCHER_H_BB',targets=['pitcher_H_per_OUTS','pitcher_BB_per_OUTS'],metrics=['WHIP','H','BB'],changed=['H','BB','WHIP'])}
DEFAULT=dict(version=VERSION,first_origin=2019,last_historical_origin=2025,evaluation_origin=2026,minimum_folds=3,minimum_rows_per_fold=30,minimum_history_folds=2,minimum_history_rows=20,recent_folds=2,minimum_objective_improvement=.01,maximum_metric_mse_degradation=.01,maximum_metric_mae_degradation=.01,maximum_guard_objective_degradation=.01,maximum_guard_metric_degradation=.02,tie_preference='group_standard',research_only=True)

def member(pids):return hashlib.sha256(json.dumps(sorted(pids)).encode()).hexdigest()
def settings(path):
 c=load(path)
 if c!=DEFAULT:raise ValueError('v1.19 thresholds/contract are fixed; a changed policy requires a separate version')
 return c

def group_vector(role,accepted,rates):
 """Replace only the registered group; freeze every unrelated primitive."""
 g=GROUPS[role];a=dict(accepted);v=dict(a);meta=dict(supported=False,reason=None,hit_scale=None,hit_floor_adjustment=0.)
 if any(not finite(rates.get(t)) or rates[t]<0 for t in g['targets']):meta['reason']='UNSUPPORTED_GROUP_RATE';return a,meta
 required=['AB','BB','HBP','SF'] if role=='hitter' else ['OUTS']
 if any(not finite(a.get(m)) for m in required):meta['reason']='UNSUPPORTED_ACCEPTED_COMPONENT';return a,meta
 if role=='hitter':
  scale=max(1.,sum(rates[t] for t in g['targets']));meta['hit_scale']=scale
  for m in ['1B','2B','3B','HR']:v[m]=a['AB']*rates['hitter_'+m+'_per_AB']/scale
  v['H']=sum(v[m] for m in ['1B','2B','3B','HR']);v['AVG']=v['H']/a['AB'] if a['AB']>0 else None
  den=a['AB']+a['BB']+a['HBP']+a['SF'];v['OBP']=(v['H']+a['BB']+a['HBP'])/den if den>0 else None
  v['SLG']=sum(v[m]*w for m,w in [('1B',1),('2B',2),('3B',3),('HR',4)])/a['AB'] if a['AB']>0 else None
  v['OPS']=v['OBP']+v['SLG'] if v['OBP'] is not None and v['SLG'] is not None else None
 else:
  h=a['OUTS']*rates['pitcher_H_per_OUTS'];v['H']=max(h,a['HR']) if finite(a.get('HR')) else h;meta['hit_floor_adjustment']=v['H']-h
  v['BB']=a['OUTS']*rates['pitcher_BB_per_OUTS'];v['WHIP']=3*(v['H']+v['BB'])/a['OUTS'] if a['OUTS']>0 else None
 coherent(role,v)
 if any(v[m]!=a[m] for m in a if m not in g['changed']):raise ValueError('Unrelated accepted component changed')
 meta.update(supported=True,reason='COHERENT_GROUP_ONLY');return v,meta

def history_class(r):
 h=r.get('history_seasons')
 return 'LOW_HISTORY' if finite(h) and h<=1 else 'ESTABLISHED_HISTORY' if finite(h) and h>=2 else 'UNKNOWN_HISTORY'

def evidence(year,role,accepted,candidates,support,actual,features):
 """All three methods, all group metrics: one identical eligible fitted bundle pool."""
 g=GROUPS[role];groups=defaultdict(list)
 for k,a in accepted.items():
  if k[0]!=year or k[1]!=role or not all(support[k+(arm,)]['supported'] and support[k+(arm,)]['group_models_fitted'] for arm in ARMS):continue
  truth={m:actual.get(k+(m,)) for m in g['metrics']}
  if any(not finite(v) for v in truth.values()) or any(not finite(a.get(m)) or any(not finite(candidates[k+(arm,)].get(m)) for arm in ARMS) for m in g['metrics']):continue
  if role=='hitter' and actual.get(k+('AB',),0)<=0:continue
  if role=='pitcher' and actual.get(k+('OUTS',),0)<=0:continue
  for cohort in ['ALL',history_class(features.get(k,{}))]:groups[cohort].append((k,a,truth))
 out=[]
 for cohort,rows in sorted(groups.items()):
  for m in g['metrics']:
   row=dict(season=year,player_type=role,group=g['name'],cohort=cohort,metric=m,n=len(rows),membership_sha256=member([k[2] for k,a,t in rows]))
   for arm in ['accepted_frozen']+ARMS:
    errors=[(a[m] if arm=='accepted_frozen' else candidates[k+(arm,)][m])-t[m] for k,a,t in rows]
    row[arm+'_mse']=sum(x*x for x in errors)/len(errors);row[arm+'_mae']=sum(abs(x) for x in errors)/len(errors)
   out.append(row)
 return out

def gate(history,role,origin,c):
 """Decision before origin outcomes enter history; equal metric and season weights."""
 g=GROUPS[role];past=[r for r in history if r['season']<origin and r['player_type']==role];results={}
 for arm in ARMS:
  checks={};overall=None;passed=True
  for cohort in ['ALL','RECENT','LOW_HISTORY','ESTABLISHED_HISTORY']:
   source='ALL' if cohort=='RECENT' else cohort;rows=[r for r in past if r['cohort']==source]
   years=list(range(c['first_origin'],origin))
   if cohort=='RECENT':years=years[-c['recent_folds']:]
   minimum=c['minimum_rows_per_fold'] if cohort in ['ALL','RECENT'] else c['minimum_history_rows']
   # Guard support must not silently skip either recent season or unsupported metrics.
   valid=[y for y in years if all(any(r['season']==y and r['metric']==m and r['n']>=minimum for r in rows) for m in g['metrics'])]
   need=c['minimum_folds'] if cohort=='ALL' else c['recent_folds'] if cohort=='RECENT' else c['minimum_history_folds']
   supported=len(valid)>=need and (cohort!='RECENT' or len(years)==need and valid==years)
   rr=[r for r in rows if r['season'] in valid];ratios=[];metric_checks={}
   for m in g['metrics']:
    mr=[r for r in rr if r['metric']==m];rat=[r[arm+'_mse']/r['accepted_frozen_mse'] for r in mr if r['accepted_frozen_mse']>0]
    ba=sum(r['accepted_frozen_mae'] for r in mr);ca=sum(r[arm+'_mae'] for r in mr)
    ratio=sum(rat)/len(rat) if rat and len(rat)==len(mr) else None;mar=ca/ba if ba>0 else None
    limit=c['maximum_metric_mse_degradation'] if cohort=='ALL' else c['maximum_guard_metric_degradation'];malimit=c['maximum_metric_mae_degradation'] if cohort=='ALL' else c['maximum_guard_metric_degradation']
    ok=ratio is not None and mar is not None and ratio<=1+limit and mar<=1+malimit
    metric_checks[m]=dict(normalized_mse_ratio=ratio,equal_season_mae_ratio=mar,pass_gate=ok);ratios.extend(rat)
   objective=sum(ratios)/len(ratios) if ratios and len(ratios)==len(rr) else None
   threshold=1-c['minimum_objective_improvement'] if cohort=='ALL' else 1+c['maximum_guard_objective_degradation']
   ok=bool(supported and objective is not None and objective<=threshold and all(x['pass_gate'] for x in metric_checks.values()))
   checks[cohort]=dict(pass_gate=ok,sufficient_support=supported,seasons=valid,objective=objective,metrics=metric_checks);passed=passed and ok
   if cohort=='ALL':overall=objective
  results[arm]=dict(pass_gate=bool(passed),overall_objective=overall,checks=checks)
 eligible=[arm for arm in ARMS if results[arm]['pass_gate']];chosen=min(eligible,key=lambda arm:(results[arm]['overall_objective'],arm!=c['tie_preference'])) if eligible else 'accepted_frozen'
 return dict(origin=origin,player_type=role,group=g['name'],selected=chosen,arms=results,selection_max_season=origin-1,evaluation_used=False)

def source_files(root,names,watched):
 for n in ['input_hashes.json','forecast_freeze.json','incremental_build_report.json']+names:checked(root,n,watched)
 rep=load(root/'incremental_build_report.json')
 if rep['version']!='1.17.0' or rep.get('evaluation_outcomes_read'):raise ValueError('Require frozen v1.17 experiment')
 freeze=load(root/'forecast_freeze.json')
 for n in ['incremental_build_report.json']+names:
  if freeze.get(n)!=sha(root/n):raise ValueError('Source freeze mismatch')
 return load(root/'input_hashes.json')

def candidate_bank(rates,vectors):
 accepted={k[:3]:v for k,v in vectors.items() if k[3]=='accepted_frozen'};candidates={};support={};ledger=[]
 for k,a in sorted(accepted.items()):
  coherent(k[1],a);g=GROUPS[k[1]]
  for arm,rate_method,fitcol in [('group_standard','standard_skill','standard_fit_status'),('group_statcast','statcast_skill','statcast_fit_status')]:
   rows=[rates[k+(t,)] for t in g['targets']];r={t:rates[k+(t,)][rate_method] for t in g['targets']};v,meta=group_vector(k[1],a,r);meta['group_models_fitted']=all(row.get(fitcol)=='FITTED' for row in rows)
   candidates[k+(arm,)]=v;support[k+(arm,)]=meta
   for m in g['changed']:ledger.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],group=g['name'],method=arm,metric=m,accepted=a[m],candidate=v[m],delta=v[m]-a[m] if finite(v[m]) and finite(a[m]) else None,**meta))
 return accepted,candidates,support,ledger

def flatten(accepted,candidates,choices):
 rows=[]
 for k,a in sorted(accepted.items()):
  choice=choices[k[0],k[1]]['selected'];values=dict(accepted_frozen=a,**{arm:candidates[k+(arm,)] for arm in ARMS});values['historical_selected']=a if choice=='accepted_frozen' else candidates[k+(choice,)]
  for arm,v in values.items():
   for m,value in v.items():rows.append(dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=arm,metric=m,prediction=value))
 return rows

def scored(rows,actual,features):
 bank={(r['season'],r['player_type'],r['mlbam_id'],r['metric'],'accepted_v1_5' if r['method']=='accepted_frozen' else r['method']):r['prediction'] for r in rows}
 return score(bank,actual,features)

def build(a):
 if Path(a.output).exists():raise FileExistsError('Choose a new output folder')
 c=settings(a.config);watched={str(Path(a.config).resolve()):sha(a.config)};root=Path(a.run).resolve();labels=Path(a.labels).resolve();matrix=Path(a.matrix).resolve()
 print('Verifying frozen inputs; fixed coherent-group contract; no model refitting...',flush=True)
 bindings=source_files(root,['historical_skill_rates.csv','historical_forecasts.csv'],watched)
 paths=[checked(labels,'training_labels.parquet',watched),checked(matrix,'training_matrix.parquet',watched),checked(matrix,'feature_schema.json',watched),checked(labels,'label_build_report.json',watched)]
 if any(bindings.get(str(p))!=sha(p) for p in paths):raise ValueError('Frozen label/matrix/reference binding mismatch')
 actual,_=label_index(paths[0]);_,features=feature_index(paths[1],load(paths[2])['predictor_allowlist']);rates,vectors=read_inputs(root);accepted,candidates,support,ledger=candidate_bank(rates,vectors)
 if not set(accepted).issubset(features):raise ValueError('Forecast missing chronological context')
 history=[];choices={}
 for year in range(2019,2026):
  print(f'{year}: selecting group arms using earlier folds only',flush=True)
  for role in GROUPS:choices[year,role]=gate(history,role,year,c)
  for role in GROUPS:history.extend(evidence(year,role,accepted,candidates,support,actual,features))
 for role in GROUPS:choices[2026,role]=gate(history,role,2026,c)
 # Freeze decisions in memory before opening any 2026 forecast or feature file.
 frozen_choices={role:choices[2026,role] for role in GROUPS};choice_sha=hashlib.sha256(json.dumps(frozen_choices,sort_keys=True).encode()).hexdigest()
 source_files(root,['frozen_2026_skill_rates.csv','frozen_2026_forecasts.csv'],watched);hr,hv=read_inputs(root,True);ha,hc,hs,hl=candidate_bank(hr,hv)
 forecasts=flatten(accepted,candidates,choices);future=flatten(ha,hc,choices);scores,coverage,outliers=scored(forecasts,actual,features)
 fittedkeys={k for k in accepted if all(support[k+(arm,)]['supported'] and support[k+(arm,)]['group_models_fitted'] for arm in ARMS)};fitted_scores,_,_=scored([r for r in forecasts if (r['season'],r['player_type'],r['mlbam_id']) in fittedkeys],actual,features)
 output,backups,stage=start(a.output,a.backup_root,[root,labels,matrix,a.config])
 try:
  dump(stage/'experiment_contract.json',dict(settings=c,groups=GROUPS,comparison='Direct accepted reference; same fitted bundle pool for both arms, all group metrics',objective='Equal-weight mean of per-season/per-metric candidate MSE / accepted MSE',source='Frozen chronological v1.17 raw rates, not individually selected components',purpose='Historical research selection only; no accepted source promotion'))
  dump(stage/'rolling_choices.json',list(choices.values()));dump(stage/'frozen_choices_2026.json',frozen_choices)
  reproduction=defaultdict(Counter)
  for k,a0 in accepted.items():
   for arm in ARMS:
    ctr=reproduction[k[0],k[1],arm];meta=support[k+(arm,)];ctr['player_seasons']+=1;ctr['supported']+=int(meta['supported']);ctr['group_models_fitted']+=int(meta['group_models_fitted']);ctr['new_final_group_forecast']+=int(any(not near(a0[m],candidates[k+(arm,)][m]) for m in GROUPS[k[1]]['changed']));ctr['same_final_as_accepted']+=int(all(near(a0[m],candidates[k+(arm,)][m]) for m in GROUPS[k[1]]['changed']))
  emit(stage/'group_reproduction_summary.csv',[dict(season=y,player_type=role,method=arm,**dict(ctr)) for (y,role,arm),ctr in sorted(reproduction.items())])
  for n,rr in [('historical_forecasts',forecasts),('frozen_2026_forecasts',future),('historical_scores',scores),('historical_comparison_summary',comparison_summary(scores)),('historical_fitted_scores',fitted_scores),('historical_fitted_summary',comparison_summary(fitted_scores)),('historical_gate_evidence',history),('historical_component_ledger',ledger),('frozen_2026_component_ledger',hl),('historical_label_coverage',coverage),('historical_outliers',outliers),('recent_2023_2025',[r for r in scores if r['season']>=2023]),('transition_2021',[r for r in scores if r['season']==2021])]:emit(stage/(n+'.csv'),rr)
  emit(stage/'group_support.csv',[dict(season=k[0],player_type=k[1],mlbam_id=k[2],method=k[3],**v) for bank in [support,hs] for k,v in sorted(bank.items())])
  report=dict(version=VERSION,status='COHERENT_GROUP_RESEARCH_CHOICES_FROZEN',historical_player_seasons=len(accepted),forecast_2026_player_seasons=len(ha),final_choices={r:v['selected'] for r,v in frozen_choices.items()},historical_seasons=sorted({k[0] for k in accepted}),group_models_refitted=False,group_selection_performed=True,selection_max_season=2025,choices_frozen_before_2026_forecast_access=True,frozen_choices_sha256=choice_sha,workload_saves_holds_fixed=True,accepted_forecasts_modified=False,new_source_promoted=False,evaluation_outcomes_read=False,inputs_unchanged=True,limitations=['Post-diagnostic research using previously inspected historical folds; not independent confirmation or significance.', 'Only two predefined groups/arms; frozen v1.17 models and preprocessing are inherited, not refitted.', 'Bundle gate requires all group labels and fitted arm rates; full reporting includes fallback rows separately.', 'Hitter accepted AB and non-hit components are fixed; hit fractions normalize only if sum exceeds one.', 'Pitcher accepted HR is fixed; H is floored at HR to preserve coherence, adjustment is logged.', '2020 and 2021 retained; unsupported recent/history guards reject candidates.', '2026 previously reviewed; separate evaluator reports frozen choices without retuning.', 'No external projections, draft data or accepted-source replacement.'])
  dump(stage/'group_build_report.json',report);dump(stage/'forecast_freeze.json',{p.name:sha(p) for p in stage.iterdir() if p.is_file()});backup=finish(output,backups,stage,watched);return dict(report,output=str(output),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__)
 for n,v in dict(run='outputs/statcast_incremental_v1_17',labels='outputs/training_labels_v1_0',matrix='outputs/standalone_lagged_features_v1_0',config='config/coherent_skill_groups_v1_19.json',output='outputs/coherent_skill_groups_v1_19',backup_root='backups').items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
