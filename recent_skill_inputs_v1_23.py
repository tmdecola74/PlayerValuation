"""Read-only registered inputs and external projection inventory; never name-match."""
import csv,json,re
from pathlib import Path
from collections import defaultdict,Counter
import duckdb
from standalone_io_v1_0 import load,sha,table
from recent_skill_core_v1_23 import *

ALIASES={'steamer':'Steamer','oopsy':'OOPSY','atc':'ATC','depth charts':'FanGraphs Depth Charts','fangraphs depth charts':'FanGraphs Depth Charts','fangraphs':'FanGraphs Depth Charts','dc':'FanGraphs Depth Charts'}
BENCHMARKS=['Steamer','OOPSY','ATC','FanGraphs Depth Charts']
IMPLEMENTATION_VERSION='1.23.1'

def parquet_rows(p,columns=None):
 with duckdb.connect() as db:
  query='SELECT '+(','.join('"'+n+'"' for n in columns) if columns else '*')+' FROM read_parquet(?)';cur=db.execute(query,[str(p)]);names=[x[0] for x in cur.description]
  return [dict(zip(names,r)) for r in cur.fetchall()]
def labels(p,year=None,scope_audit=None):
 out={};seen=set();counts=Counter();negative=Counter()
 for r in parquet_rows(p):
  k=int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric']
  if k in seen or k[1] not in METRICS or not k[2].isdigit() or int(k[2])<=0 or not (k[0]==year if year is not None else 2015<=k[0]<=2025):raise ValueError('Invalid/duplicate label split')
  seen.add(k)
  if r['eligible'] not in [True,False,0,1]:raise ValueError('Invalid label eligibility')
  # The frozen label reference contains signed rates/context beyond this experiment's scoring scope.
  # Never reinterpret those as invalid counts or make them model targets.
  used=k[3] in set(METRICS[k[1]])|{'G','GS'}
  status='IGNORED_NONSCORING_METRIC' if not used else 'ELIGIBLE_SCORING_LABEL' if r['eligible'] else 'INELIGIBLE_SCORING_LABEL'
  token=k[1],k[3],status;counts[token]+=1
  if finite(r['label_value']) and r['label_value']<0:negative[token]+=1
  if not used:continue
  if r['eligible']:
   v=r['label_value']
   if not finite(v) or v<0:raise ValueError('Invalid eligible scoring label '+str(k)+': '+str(v))
   out[k]=float(v)
 if scope_audit is not None:scope_audit.extend(dict(player_type=role,metric=metric,status=status,rows=n,negative_values_observed=negative[role,metric,status],used_as_label=status=='ELIGIBLE_SCORING_LABEL') for (role,metric,status),n in sorted(counts.items()))
 return out
def feature_rows(path,allow,hold=False):
 context=['target_season','player_type','mlbam_id','max_source_season','source_cutoff']+['source_season_lag'+str(lag) for lag in [1,2,3]]
 if len(allow)!=len(set(allow)) or any(n.startswith('y_') or not n.startswith(('x_actual_lag','x_statcast_lag','tracking_era_lag','short_season_lag')) and n not in ['history_seasons','age_at_target_estimate','has_any_actual_history','has_any_statcast_history'] for n in allow):raise ValueError('Unapproved predictor allowlist')
 rows=parquet_rows(path,sorted(set(context+allow)));seen=set()
 for r in rows:
  k=key(r)
  if k in seen or k[1] not in METRICS or not k[2].isdigit() or int(k[2])<=0 or not(k[0]==2026 if hold else 2016<=k[0]<=2025) or r['max_source_season'] is None or r['max_source_season']>=k[0] or str(r['source_cutoff'])>=str(k[0])+'-01-01' or r['source_cutoff'] is None:raise ValueError('Invalid chronological feature row')
  for lag in [1,2,3]:
   if r.get('source_season_lag'+str(lag)) not in [None,k[0]-lag]:raise ValueError('Wrong prior source year')
   if r.get('source_season_lag'+str(lag)) is None and any(finite(v) for n,v in r.items() if n.startswith(f'x_actual_lag{lag}_') or n.startswith(f'x_statcast_lag{lag}_') and n.endswith('_value')):raise ValueError('Value without registered source season')
  seen.add(k)
 return rows
def accepted_vectors(path,hold=False):
 out=defaultdict(dict);seen=set()
 with path.open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   if r['method']!='accepted_frozen':continue
   k=int(r['season']),r['player_type'],str(r['mlbam_id']);m=r['metric']
   if k[1] not in METRICS or m not in METRICS[k[1]] or (k,m) in seen or not(k[0]==2026 if hold else 2019<=k[0]<=2025) or not k[2].isdigit():raise ValueError('Invalid accepted forecast')
   seen.add((k,m));out[k][m]=number(r['prediction'])
 for k,v in out.items():coherent(k[1],v)
 if not out:raise ValueError('No frozen accepted forecasts')
 return dict(out)
def addon(path,family):
 out={};audit=[]
 with duckdb.connect() as db:
  db.read_parquet(str(path)).create_view('a')
  if db.execute("SELECT count(*) FROM a WHERE target_season IS NULL OR target_season NOT BETWEEN 2016 AND 2026 OR source_season IS NULL OR source_season<>target_season-lag OR source_season>2025 OR lag IS NULL OR lag NOT IN (1,2,3) OR player_type IS NULL OR player_type NOT IN ('hitter','pitcher')").fetchone()[0]:raise ValueError('Invalid add-on chronology')
  metric='metric' if family=='expanded' else "replace(feature,'savant_bat_tracking_','')"
  allowed=sorted(set(EXPANDED['hitter']+EXPANDED['pitcher'])) if family=='expanded' else BAT
  condition=metric+' IN ('+','.join("'"+m+"'" for m in allowed)+')'+(" AND family='bat_tracking'" if family=='bat' else '')
  invalid='value IS NOT NULL AND (eligible IS NOT TRUE OR NOT isfinite(value) OR denominator IS NULL OR NOT isfinite(denominator) OR denominator<=0'+(" OR coverage IS NULL OR coverage<.5 OR coverage>1" if family=='expanded' else '')+')'
  if db.execute('SELECT count(*) FROM a WHERE '+condition+' AND ('+invalid+')').fetchone()[0]:raise ValueError('Unmasked add-on value or invalid sample control')
  if family=='bat' and db.execute('SELECT count(*) FROM a WHERE '+condition+' AND value IS NOT NULL AND source_season<2023').fetchone()[0]:raise ValueError('Bat tracking before available source history')
  if db.execute('SELECT count(*) FROM (SELECT target_season,player_type,mlbam_id,lag,'+metric+' FROM a WHERE '+condition+' GROUP BY ALL HAVING count(*)>1)').fetchone()[0]:raise ValueError('Duplicate add-on feature')
  for y,role,m,n,available in db.execute('SELECT target_season,player_type,'+metric+',count(*),count(value) FROM a WHERE '+condition+' GROUP BY ALL ORDER BY ALL').fetchall():audit.append(dict(target_season=y,player_type=role,metric=m,population_rows=n,available_rows=available,family=family))
  for source,role,pid,m,v,den in db.execute('SELECT DISTINCT source_season,player_type,CAST(mlbam_id AS VARCHAR),'+metric+',value,denominator FROM a WHERE '+condition+' AND value IS NOT NULL').fetchall():
   if family=='expanded' and m not in EXPANDED[role]:continue
   k=int(source),role,str(pid),m
   if k in out and out[k]!=(v,den):raise ValueError('Inconsistent repeated source feature')
   out[k]=(v,den)
 return out,audit
def arsenal(path):
 groups=defaultdict(list);seen=set()
 with duckdb.connect() as db:
  cur=db.execute("SELECT source_season,player_type,mlbam_id,metric,pitch_type,eligible,value,denominator FROM read_parquet(?) WHERE player_type='pitcher' AND metric IN ('pitch_type_usage','release_speed_mean','whiff_pct')",[str(path)]);names=[x[0] for x in cur.description];rows=[dict(zip(names,r)) for r in cur.fetchall()]
 for r in rows:
  y=int(r['source_season']);role=r['player_type'];pid=str(r['mlbam_id']);m=r['metric'];pt=r['pitch_type']
  if not 2015<=y<=2025:raise ValueError('Future arsenal source')
  if role!='pitcher' or m not in PTMETRICS:continue
  if (y,role,pid,pt,m) in seen:raise ValueError('Duplicate arsenal source')
  seen.add((y,role,pid,pt,m))
  bucket=pt if pt in PTYPES else 'OTHER';k=y,role,pid,bucket,m
  if r['eligible'] in [True,1] and finite(r['value']) and finite(r['denominator']) and r['denominator']>0:
   # Usage uses the common player's total-pitch denominator; other means/rates pool measured observations.
   groups[k].append((r['value'],r['denominator']))
 result={}
 for k,ss in groups.items():
  if k[-1]=='pitch_type_usage':
   if len({n for v,n in ss})!=1:raise ValueError('Inconsistent arsenal usage denominator')
   v=sum(v for v,n in ss);den=ss[0][1]
  else:den=sum(n for v,n in ss);v=sum(v*n for v,n in ss)/den
  result[k]=(v,den)
 return result

def published(values,excluded):
 v={m:float(x) for m,x in values.items() if finite(x) and x>=0 and m not in excluded}
 def derive(m,deps,fn):
  if m not in v and m not in excluded and all(d in v and d not in excluded for d in deps):
   x=fn()
   if finite(x):v[m]=x
 derive('SO',['K'],lambda:v['K']);derive('OUTS',['IP'],lambda:3*v['IP']);derive('AVG',['H','AB'],lambda:v['H']/v['AB'] if v['AB'] else None);derive('ERA',['ER','IP'],lambda:9*v['ER']/v['IP'] if v['IP'] else None);derive('WHIP',['H','BB','IP'],lambda:(v['H']+v['BB'])/v['IP'] if v['IP'] else None);derive('OPS',['OBP','SLG'],lambda:v['OBP']+v['SLG']);derive('SV_plus_HLD',['SV','HLD'],lambda:v['SV']+v['HLD'])
 return v
def benchmark_snapshot(path,rawdir,watched):
 path=Path(path).resolve();result=[];issues=[];inventory=[];names={};count=Counter();owned=defaultdict(set);ids=defaultdict(set);seen=set();rawcounts=Counter()
 if path.exists():
  ap=path.parent/'migration_audit.json';audit=load(ap)
  if not audit.get('pass'):raise ValueError('Warehouse migration audit must pass')
  watched.update({str(path):sha(path),str(ap):sha(ap)})
  # Migration objects can back read-only analytical views. Integrity hashing is not outcome-table querying.
  for obj in audit.get('objects',[]):
   pp=(path.parent/obj['parquet_file']).resolve()
   if path.parent not in pp.parents or sha(pp)!=obj['parquet_sha256']:raise ValueError('Migrated warehouse object hash/path mismatch')
   watched[str(pp)]=obj['parquet_sha256']
  # Only analytical projection views and the identity crosswalk are queried. Actuals are never queried.
  with duckdb.connect(str(path),read_only=True) as db:
   tables={r[0] for r in db.execute('SHOW TABLES').fetchall()}
   if 'players' in tables:
    cols={r[0] for r in db.execute('DESCRIBE players').fetchall()}
    if {'player_id','preferred_name'}<=cols:names=dict(db.execute('SELECT player_id,preferred_name FROM players').fetchall())
   for pid,ns,external in db.execute('SELECT player_id,namespace,external_id FROM player_id_crosswalk').fetchall():
    if str(ns).lower()=='mlbam' and str(external).isdigit() and int(str(external))>0:ids[str(pid)].add(str(int(external)));owned[str(int(external))].add(str(pid))
   for role in METRICS:
    table='analytical_'+role+'_projections';required={'season','source','player_id','record_id','metrics_json','excluded_metrics_json'};cols={r[0] for r in db.execute('DESCRIBE '+table).fetchall()}
    if not required<=cols:raise ValueError('Projection warehouse schema differs')
    for y,source,pid,record,metrics,excluded in db.execute('SELECT season,source,player_id,record_id,metrics_json,excluded_metrics_json FROM '+table+' WHERE season BETWEEN 2023 AND 2026').fetchall():
     canonical=ALIASES.get(str(source).strip().lower())
     if canonical is None:continue
     rawcounts[int(y),role,canonical]+=1;pid=str(pid);mapped=ids[pid]
     if len(mapped)!=1 or len(owned[next(iter(mapped))])!=1:issues.append(dict(season=y,player_type=role,source=canonical,player_id=pid,record_id=record,reason='MISSING_OR_AMBIGUOUS_MLBAM'));continue
     mid=next(iter(mapped));values=published(json.loads(metrics),set(json.loads(excluded)))
     for m,v in values.items():
      if m not in METRICS[role]:continue
      k=int(y),role,mid,m,canonical
      if k in seen:raise ValueError('Duplicate selected source/player/metric')
      seen.add(k);result.append(dict(season=int(y),player_type=role,mlbam_id=mid,name=names.get(pid),player_id=pid,source=canonical,metric=m,prediction=v,source_record_id=str(record)));count[int(y),role,canonical]+=1
 for y in range(2023,2027):
  for role in METRICS:
   for source in BENCHMARKS:inventory.append(dict(season=y,player_type=role,source=source,selected_records=rawcounts[y,role,source],mapped_metric_rows=count[y,role,source],status='AVAILABLE' if count[y,role,source] else 'NO_MAPPED_METRICS' if rawcounts[y,role,source] else 'NOT_REGISTERED_IN_WAREHOUSE',timestamp_policy='RETROSPECTIVE_EXPORT_NOT_ARCHIVE_CERTIFIED'))
 raw_inventory=[];root=Path(rawdir).resolve()
 if root.exists():
  for p in sorted(root.iterdir()):
   if not p.is_file() or p.suffix.lower() not in ['.csv','.tsv','.xlsx']:continue
   source=next((v for token,v in [('steamer','Steamer'),('oopsy','OOPSY'),('atc','ATC'),('fangraphs','FanGraphs Depth Charts'),('dc','FanGraphs Depth Charts')] if p.name.lower().startswith(token)),None)
   if source is None:continue
   years=sorted(set(map(int,re.findall(r'20(?:23|24|25|26|27)',p.name))));future=any(y>2026 for y in years)
   h=sha(p) if years and not future else None
   if h:watched[str(p)]=h
   raw_inventory.append(dict(path=str(p),source_hint=source,filename_year_hints=json.dumps(years),sha256=h,status='FUTURE_FILE_NOT_OPENED' if future else 'DISCOVERED_NOT_IMPORTED_USE_REGISTERED_WAREHOUSE' if years else 'YEAR_UNKNOWN_NOT_OPENED'))
 return result,inventory,issues,raw_inventory
