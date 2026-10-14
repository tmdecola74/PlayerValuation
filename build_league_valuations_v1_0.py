"""League-specific 5x5 SGP, exact multi-position replacement, and auction values.
Uses established consensus builder; never reads target actual metrics.
"""
from __future__ import annotations
import argparse,csv,hashlib,json,math,re,shutil,tempfile
from contextlib import closing
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
from valuation_math_v1_0 import coherent,finite,sgp,reference_from_pool,Assignment,allocate_cents

NATURAL={'C','1B','2B','3B','SS','OF','UT','P'}
ALIASES={'DH':'UT','LF':'OF','CF':'OF','RF':'OF','SP':'P','RP':'P'}
SLOT_RULES={'C':{'C'},'1B':{'1B'},'2B':{'2B'},'3B':{'3B'},'SS':{'SS'},'CI':{'1B','3B'},'MI':{'2B','SS'},'OF':{'OF'},'UT':{'C','1B','2B','3B','SS','OF','UT'},'P':{'P'}}
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def dump(p,obj):Path(p).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')
def csv_out(p,rows,fields=None):
 fields=fields or list(dict.fromkeys(k for r in rows for k in r)) or ['status']
 with Path(p).open('w',encoding='utf-8-sig',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
  for row in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in row.items()})
def positions(value):
 tokens={ALIASES.get(t.upper(),t.upper()) for t in re.split(r'[,;/| ]+',value.strip()) if t}
 if tokens-NATURAL:raise ValueError('Unknown position token(s): '+str(tokens-NATURAL))
 return tokens

def read_eligibility(path,season):
 result={}
 with Path(path).open(encoding='utf-8-sig',newline='') as f:
  for r in csv.DictReader(f):
   if not r.get('positions','').strip():continue
   if int(r['eligibility_season'])!=season or not r['source'].strip():raise ValueError('Eligibility needs target season and named source')
   if int(r['eligibility_basis_season'])!=season-1:raise ValueError('Preseason eligibility must be based on the prior season; no in-season position gains')
   typ=r['player_type'];pos=positions(r['positions'])
   if typ not in ('hitter','pitcher') or (typ=='hitter' and 'P' in pos) or (typ=='pitcher' and pos!={'P'}):raise ValueError('Eligibility type/position mismatch')
   key=(typ,r['player_id'])
   if key in result:raise ValueError('Duplicate eligibility player/type key')
   result[key]=pos
 return result

def validate_profile(cfg):
 if not isinstance(cfg['teams'],int) or cfg['teams']<2:raise ValueError('League teams must be integer >=2')
 if set(cfg['active_slots'])-set(SLOT_RULES):raise ValueError('Unsupported roster slot')
 if any(not isinstance(n,int) or n<0 for n in cfg['active_slots'].values()):raise ValueError('Invalid slot count')
 if cfg['active_slots'].get('P',0)<=0 or sum(n for g,n in cfg['active_slots'].items() if g!='P')<=0:raise ValueError('Both hitter and pitcher rosters required')
 if not 0<cfg['hitter_budget_share']<1 or cfg['minimum_bid']<=0 or cfg['auction_budget_per_team']<=0:raise ValueError('Invalid auction policy')
 if set(cfg['categories']['hitter'])!={'R','HR','RBI','SB','AVG'} or set(cfg['categories']['pitcher'])!={'W','SV','K','ERA','WHIP'}:raise ValueError('v1 supports coherent standard 5x5; additional rate categories need their own denominator formulas')
 if cfg['rate_reference_method'] not in ('iterated_selected_active_pool','historical_calibration'):raise ValueError('Unsupported reference method')

def candidate_records(players,cfg,eligibility=None):
 out=[];exclusions=[];seen=set()
 for r in players:
  typ=r['player_type'];pid=r['player_id'];key=(typ,pid)
  if key in seen:raise ValueError('Duplicate consensus player/type')
  seen.add(key);m=coherent(typ,r['metrics']);reason=None
  needed=['R','HR','RBI','SB','H','AB','PA'] if typ=='hitter' else ['W','SV','SO','H','BB','ER','IP']
  if any(not finite(m.get(k)) or m[k]<0 for k in needed):reason='MISSING_OR_INVALID_CATEGORY_COMPONENT'
  elif typ=='hitter' and (m['AB']<=0 or m['H']>m['AB']):reason='INVALID_HITTER_RATE_COMPONENTS'
  elif typ=='pitcher' and m['IP']<=0:reason='NONPOSITIVE_IP'
  elif any(m[k]<v for k,v in cfg['minimum_projected_exposure'][typ].items()):reason='BELOW_PROJECTED_EXPOSURE_FLOOR'
  pos=eligibility.get(key) if eligibility is not None else None
  slots={g for g,allowed in SLOT_RULES.items() if cfg['active_slots'].get(g,0)>0 and pos and pos&allowed}
  if not reason and eligibility is not None and not slots:reason='MISSING_POSITION_ELIGIBILITY'
  if reason:exclusions.append(dict(player_type=typ,player_id=pid,name=r['name'],reason=reason));continue
  out.append(dict(r,metrics=m,positions=sorted(pos) if pos else [],eligible_slots=slots))
 return out,exclusions

def value_players(players,cfg,eligibility,calibration):
 validate_profile(cfg)
 if calibration['target_season']!=cfg['season'] or calibration['teams']!=cfg['teams'] or not calibration.get('full_season') or not calibration.get('source') or not calibration.get('seasons') or max(calibration['seasons'])>=cfg['season']:raise ValueError('Calibration must match league and use completed prior seasons')
 slopes=calibration['slopes'];categories={k for cats in cfg['categories'].values() for k in cats}
 if categories-set(slopes) or any(not finite(slopes[k]) or slopes[k]<=0 for k in categories):raise ValueError('Missing/nonpositive SGP slopes')
 records,excluded=candidate_records(players,cfg,eligibility);demands={g:n*cfg['teams'] for g,n in cfg['active_slots'].items() if n}
 hc=sum(n for g,n in demands.items() if g!='P');pc=demands['P']
 h=sorted((r for r in records if r['player_type']=='hitter'),key=lambda r:(-r['metrics']['PA'],r['player_id']))[:hc]
 p=sorted((r for r in records if r['player_type']=='pitcher'),key=lambda r:(-r['metrics']['IP'],r['player_id']))[:pc]
 if len(h)<hc or len(p)<pc:raise ValueError('Insufficient eligible candidates for starter counts')
 reference=reference_from_pool(h+p,cfg['teams']) if cfg['rate_reference_method']=='iterated_selected_active_pool' else calibration['rate_reference']
 if any(not finite(reference.get(k)) or reference[k]<=0 for k in ['AVG','ERA','WHIP','team_AB','team_IP']):raise ValueError('Invalid historical reference rates/exposures')
 visited=set();iterations=[];assignment=None
 for iteration in range(cfg['maximum_reference_iterations']):
  scored=[]
  for row in records:
   cat=sgp(row['player_type'],row['metrics'],slopes,reference,cfg['categories'][row['player_type']])
   scored.append(dict(row,category_sgp=cat,raw_sgp=sum(cat.values())))
  assignment=Assignment(scored,demands)
  new=reference_from_pool(assignment.selected,cfg['teams']);signature=tuple(sorted((r['player_id'],r['player_type']) for r in assignment.selected))
  iterations.append(dict(iteration=iteration+1,objective=assignment.objective,reference=reference,new_reference=new))
  if cfg['rate_reference_method']=='historical_calibration' or all(abs(new[k]-reference[k])<1e-8 for k in reference):break
  if signature in visited:raise ValueError('Rate reference pool cycled; no values published')
  visited.add(signature);reference=new
 else:raise ValueError('Rate reference pool did not converge; no values published')
 margins,alternatives,thresholds=assignment.margins();active=[]
 for r in assignment.selected:active.append(dict(r,**margins[r['player_id']]))
 cents,factors,budgets=allocate_cents(active,cfg['teams'],cfg['auction_budget_per_team'],cfg['minimum_bid'],cfg['hitter_budget_share'])
 chosen={r['player_id']:r for r in active}
 for r in active:r['auction_value']=cents[r['player_id']]/100;r['auction_equivalent']=r['auction_value'];r['reserve_selected']=False
 # One canonical asset: choose best undrafted role by comparable budget-scaled marginal utility.
 remaining={}
 for r in alternatives:
  r['auction_value']=0.0;r['auction_equivalent']=cfg['minimum_bid']+factors[r['player_type']]*r['sgp_above_replacement'];r['reserve_selected']=False
  pid=r['player_id']
  if pid not in remaining or (r['auction_equivalent'],r['raw_sgp'],r['player_type'])>(remaining[pid]['auction_equivalent'],remaining[pid]['raw_sgp'],remaining[pid]['player_type']):remaining[pid]=r
 reserves=sorted(remaining.values(),key=lambda r:(-r['auction_equivalent'],-r['raw_sgp'],r['player_id']))
 for r in reserves[:cfg['bench_per_team']*cfg['teams']]:r['reserve_selected']=True
 if cfg.get('draft_rank_method')=='sgp_above_replacement':
  ranked=sorted(active+reserves,key=lambda r:(not r['selected'],-r['sgp_above_replacement'],-r['raw_sgp'],r['player_id']))
  reserves=sorted(remaining.values(),key=lambda r:(-r['sgp_above_replacement'],-r['raw_sgp'],r['player_id']))
  for r in reserves:r['reserve_selected']=False
  for r in reserves[:cfg['bench_per_team']*cfg['teams']]:r['reserve_selected']=True
 else:ranked=sorted(active+reserves,key=lambda r:(not r['selected'],-r['auction_equivalent'],-r['raw_sgp'],r['player_id']))
 for rank,r in enumerate(ranked,1):r['draft_rank']=rank
 return ranked,excluded,reference,thresholds,iterations,budgets

def backup_publish(stage,out,backup_root):
 backup_root.mkdir(parents=True,exist_ok=True)
 if backup_root==out or out in backup_root.parents:raise ValueError('Backup must be outside output')
 backup=backup_root/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
 audit_file=stage/'valuation_audit.json'
 if audit_file.is_file():
  audit=json.loads(audit_file.read_text(encoding='utf-8'));audit['backup']=str(backup);dump(audit_file,audit)
 shutil.copytree(stage,backup)
 for p in stage.rglob('*'):
  if p.is_file() and sha(p)!=sha(backup/p.relative_to(stage)):raise ValueError('Backup verification failed')
 stage.rename(out);return backup

def build(args):
 cfg=json.loads(Path(args.profile).read_text(encoding='utf-8'));validate_profile(cfg);profile_path=Path(args.profile).resolve();project=profile_path.parent.parent
 consensus_cfg=Path(args.consensus_config).resolve();warehouse=Path(args.warehouse or project/json.loads(consensus_cfg.read_text())['warehouse']).resolve()
 out=Path(args.output or ('outputs/nfbc15_valuation_inputs_v1_0' if args.prepare_inputs else 'outputs/nfbc15_values_2026_v1_0')).resolve()
 if out.exists():raise ValueError('Output must not already exist')
 inputs=[profile_path,consensus_cfg,warehouse];elig_path=Path(args.eligibility or project/cfg['eligibility_file']).resolve();calib_path=Path(args.calibration or project/cfg['calibration_file']).resolve()
 if not args.prepare_inputs:inputs.extend([elig_path,calib_path])
 if any(out==p or out in p.parents for p in inputs):raise ValueError('Output cannot contain inputs')
 if warehouse.suffix.lower()=='.duckdb':
  manifest=warehouse.parent/'migration_audit.json';inputs.append(manifest)
  for obj in json.loads(manifest.read_text(encoding='utf-8'))['objects']:inputs.append(warehouse.parent/obj['parquet_file'])
 fingerprints={str(p):sha(p) for p in inputs};out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=out.name+'.staging-',dir=out.parent))
 try:
  from build_consensus_projections_duckdb_v1_0 import build as consensus_build
  from warehouse_readonly_v1_0 import open_warehouse
  with closing(open_warehouse(warehouse)) as ref:
   if ref.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise ValueError('Warehouse integrity verification failed')
  print('Building established coherent consensus, read-only...',flush=True)
  report=consensus_build(consensus_cfg,stage/'consensus',warehouse)
  if report['season']!=cfg['season'] or report['invalid_source_values']:raise ValueError('Consensus season/invalid values require review')
  players=[]
  for typ in ['hitter','pitcher']:players.extend(json.loads((stage/'consensus'/f'{typ}_consensus.json').read_text(encoding='utf-8')))
  base_audit=dict(version='1.0.0',league=cfg['league'],season=cfg['season'],teams=cfg['teams'],source_config='Established consensus component weights; no Statcast adjustments selected',reference_read_only=True,input_sha256=fingerprints,consensus_players=len(players))
  if args.prepare_inputs:
   candidates,excluded=candidate_records(players,cfg)
   template=[dict(player_id=r['player_id'],player_type=r['player_type'],name=r['name'],mlbam_ids=';'.join(r['mlbam_ids']),positions='',eligibility_season=cfg['season'],eligibility_basis_season=cfg['season']-1,source='') for r in candidates]
   csv_out(stage/'nfbc15_eligibility_TEMPLATE.csv',template)
   fields=['season','league_id','rank','points']+list({k:None for cats in cfg['categories'].values() for k in cats})
   csv_out(stage/'historical_rank_grid_TEMPLATE.csv',[],fields)
   dump(stage/'sgp_calibration_TEMPLATE.json',dict(target_season=cfg['season'],teams=cfg['teams'],full_season=True,source='',seasons=[],slopes={k:None for cats in cfg['categories'].values() for k in cats}))
   dump(stage/'input_requirements.json',dict(eligibility='Supply authoritative preseason NFBC eligibility. Map canonical IDs; positions and source must be completed. Blank positions are excluded, not guessed.',calibration='Completed 15-team 5x5 category standings from 2025 or earlier. 2026 in-season FAAB sgpcalcs.xlsx is excluded from this preseason build.',supported='NFBC 15-team 5x5; 14 hitter/9 pitcher active slots, 7 reserves. $260 auction-equivalent active budget, hitter share .67 is editable policy.',candidates=len(candidates)))
   csv_out(stage/'candidate_exclusions.csv',excluded)
   audit=dict(base_audit,status='INPUTS_PREPARED',eligible_projection_candidates=len(candidates),values_published=False,missing_inputs=['Authoritative 2026 preseason position eligibility','Completed prior-season NFBC15 SGP calibration'])
  else:
   eligibility=read_eligibility(elig_path,cfg['season']);calibration=json.loads(calib_path.read_text(encoding='utf-8'))
   ranked,excluded,reference,thresholds,iterations,budgets=value_players(players,cfg,eligibility,calibration)
   export=[]
   for r in ranked:
    row={k:r[k] for k in ['player_id','player_type','name','draft_rank','assigned_slot','raw_sgp','sgp_above_replacement','effective_replacement_sgp','selected','reserve_selected','auction_value','auction_equivalent']}
    row['positions']=';'.join(r['positions'])
    if cfg.get('format')=='Draft Champions':
     row['auction_equivalent_value']=row.pop('auction_value');row['scaled_marginal_value']=row.pop('auction_equivalent')
    row.update(r['metrics']);row.update({'SGP_'+k:v for k,v in r['category_sgp'].items()});export.append(row)
   csv_out(stage/'player_values.csv',export);csv_out(stage/'starter_assignments.csv',[r for r in export if r['selected']]);csv_out(stage/'reserve_rankings.csv',[r for r in export if not r['selected']]);csv_out(stage/'candidate_exclusions.csv',excluded)
   csv_out(stage/'positional_replacement.csv',[dict(slot=g,league_slots=cfg['active_slots'][g]*cfg['teams'],marginal_entry_threshold_sgp=v) for g,v in thresholds.items()])
   dump(stage/'rate_reference.json',dict(**reference,method=cfg['rate_reference_method']+'; linear excess-numerator SGP, not additive changes in team rate',iterations=iterations))
   dump(stage/'effective_calibration.json',calibration)
   audit=dict(base_audit,status='VALUES_BUILT',values_published=True,ranked_unique_players=len(ranked),starter_players=sum(r['selected'] for r in ranked),reserve_players=sum(r['reserve_selected'] for r in ranked),league_auction_total=sum(round(r['auction_value']*100) for r in ranked)/100,auction_budget_cents=budgets,rate_reference=reference,reference_iterations=len(iterations),category_slopes=calibration['slopes'],method='Exact optimal roster assignment; drafted value is optimal roster score loss when removing that player; undrafted value is optimal roster inclusion gain',hitter_budget_share=cfg['hitter_budget_share'],limitations=['SGP is relative roto contribution, not a promise of final standings points.','Rate contributions are linear excess-numerator SGP at a common full-roster denominator. Actual roster changes require recomputing numerator and denominator totals.','Marginal replacement values are joint roster opportunity costs and are not additive team utilities.','Auction budget includes active slots only. Reserves are ranked separately and cost zero in this active auction allocation.','One canonical two-way player can occupy only one projected role in the global roster. Platform-specific dual-asset formats need distinct supplied identities.'])
  if cfg.get('format')=='Draft Champions' and not args.prepare_inputs:
   audit['version']='1.1.0';audit['format']='Draft Champions';audit['draft_rank_method']='SGP above replacement';audit['auction_equivalent_total']=audit.pop('league_auction_total');audit['value_currency']='Illustrative auction-equivalent reference only; DC uses a 50-round snake draft';audit['reserve_slots_required']=27*cfg['teams'];audit['reserve_shortfall']=max(0,27*cfg['teams']-audit['reserve_players']);audit['limitations']+=['Static season-long reserve ordering does not model weekly lineup coverage, injury probability, or prospect call-up timing.']
  for p,h in fingerprints.items():
   if sha(p)!=h:raise ValueError('Input changed during valuation build')
  audit['inputs_unchanged']=True;dump(stage/'valuation_audit.json',audit)
  backup=backup_publish(stage,out,Path(args.backup_root).resolve())
  return dict(audit,output=str(out),backup=str(backup))
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--profile',default='config/valuation_nfbc15_v1_0.json');p.add_argument('--consensus-config',default='config/valuation_consensus_v1_0.json');p.add_argument('--warehouse');p.add_argument('--eligibility');p.add_argument('--calibration');p.add_argument('--prepare-inputs',action='store_true');p.add_argument('--output');p.add_argument('--backup-root',default='backups')
 print(json.dumps(build(p.parse_args()),indent=2))
if __name__=='__main__':main()
