"""Explicit frozen projection sources -> existing NFBC valuation and DC simulator."""
import argparse,copy,json,shutil,math
from collections import Counter
from pathlib import Path
from standalone_io_v1_0 import load,dump,sha,verify,start,finish,csvrows,write
from draft_source_registry_v1_14 import load_draft_source
from build_league_valuations_v1_0 import value_players,read_eligibility,validate_profile,csv_out
from entry_branch_v1_14 import POPULATION,HISTORY,CONTEXT,CUTOFFS,intake,CONFIG

SOURCES=['homegrown','reconciled_consensus']
ROLE_FIELDS=['projection_source_choice','player_id','GS','as_of_date','source','evidence_reference','vintage_basis']

def emit(p,rows):csv_out(p,rows)
def role_inputs(path):
 if not path:return {},{}
 rows=csvrows(path);lookup={}
 for r in rows:
  if set(r)!=set(ROLE_FIELDS):raise ValueError('Wrong role schema; use generated template')
  key=r['projection_source_choice'],r['player_id']
  if key[0] not in SOURCES or not key[1] or key in lookup:raise ValueError('Invalid/duplicate source-specific role key')
  from datetime import date
  if date.fromisoformat(r['as_of_date'])>date(2026,3,24):raise ValueError('Future role evidence')
  if r['vintage_basis'] not in ['ARCHIVED_AS_OF_CLAIM','USER_CONFIRMED_PRESEASON_EFFECTIVE','RETROSPECTIVE_EVENT_TIME_ONLY'] or not r['source'] or not r['evidence_reference']:raise ValueError('Role provenance required')
  gs=float(r['GS'])
  if not math.isfinite(gs) or gs<0 or gs>162:raise ValueError('Invalid projected GS')
  lookup[key]=dict(r,GS=gs)
 return lookup,{str(Path(path).resolve()):sha(path)}

def resolve_market_assets(root, assets):
 """Resolve only a frozen NFBC membership plus identical MLBAM bridge, never names."""
 universe=load(Path(root)/'preseason_universe.json');owners={};seen=set();resolved=[];audit=[]
 for u in universe:
  for aid in json.loads(u['nfbc_asset_ids_json']):
   key=str(aid),u['player_type']
   if key in owners:raise ValueError('Duplicate frozen NFBC universe membership: '+str(key))
   owners[key]=u
 for raw in assets:
  r=dict(raw);key=str(r['nfbc_player_id']),r['player_type'];supplied=r.get('player_id') or None
  if key in seen:raise ValueError('Duplicate market asset/role: '+str(key))
  seen.add(key);u=owners.get(key)
  if u is None:raise ValueError('Market asset absent from frozen NFBC universe: '+str(key))
  target=u.get('player_id') or None;method='EXACT_FROZEN_CANONICAL_ID'
  if supplied!=target:
   # v1.13 add() can resolve a canonical owner by unique MLBAM while its asset
   # export deliberately retains the originally blank reviewed player_id.
   if supplied is not None or target is None or not r.get('mlbam_id') or str(r['mlbam_id'])!=str(u.get('mlbam_id')) or not r.get('universe_id') or r['universe_id']!=u.get('universe_id'):
    raise ValueError('Frozen market identity mismatch: '+json.dumps(dict(nfbc_player_id=key[0],player_type=key[1],market_player_id=supplied,universe_player_id=target,market_mlbam=r.get('mlbam_id'),universe_mlbam=u.get('mlbam_id'),market_universe_id=r.get('universe_id'),universe_id=u.get('universe_id'))))
   method='FROZEN_NFBC_MEMBERSHIP_AND_EXACT_MLBAM_BRIDGE'
  if r.get('universe_id') and u.get('universe_id') and r['universe_id']!=u['universe_id']:raise ValueError('Frozen market universe_id mismatch: '+str(key))
  r['player_id']=target;resolved.append(r);audit.append(dict(nfbc_player_id=key[0],player_type=key[1],original_market_player_id=supplied,resolved_player_id=target,mlbam_id=u.get('mlbam_id'),universe_id=u.get('universe_id'),resolution_method=method,original_reference_modified=False))
 if seen!=set(owners):raise ValueError('Market file must cover complete frozen NFBC universe; missing='+str(sorted(set(owners)-seen)[:10]))
 return resolved,audit

def unique_market_assets(assets,ranked):
 """One NFBC asset can have two role rows; engine already chooses one canonical role."""
 groups={};selected={(r['player_type'],r['player_id']) for r in ranked};out=[];excluded=[]
 for a in assets:groups.setdefault(str(a['nfbc_player_id']),[]).append(a)
 for aid,rr in groups.items():
  if len(rr)==1:out.extend(rr);continue
  ids={r.get('player_id') for r in rr};roles={r['player_type'] for r in rr};prices={str(r.get('ADP') or r.get('market_ADP') or '') for r in rr}
  if len(rr)!=2 or roles!={'hitter','pitcher'} or len(ids)!=1 or not next(iter(ids)):
   raise ValueError('Conflicting repeated NFBC asset; cannot merge identity: '+aid)
  parsed=[float(v) for v in prices if v]
  if len(parsed)>1 and max(parsed)!=min(parsed):raise ValueError('Conflicting ADP for repeated NFBC asset: '+aid)
  choices=[r for r in rr if (r['player_type'],r['player_id']) in selected]
  if len(choices)>1:raise ValueError('Valuation selected multiple roles for one NFBC asset: '+aid)
  if choices:
   out.extend(choices)
   for r in rr:
    if r is not choices[0]:excluded.append(dict(nfbc_player_id=aid,player_type=r['player_type'],player_id=r['player_id'],name=r['name'],reason='TWO_WAY_NONSELECTED_ROLE_ONE_NFBC_ASSET'))
  else:
   for r in rr:excluded.append(dict(nfbc_player_id=aid,player_type=r['player_type'],player_id=r['player_id'],name=r['name'],reason='TWO_WAY_NO_VALUED_ROLE_CANNOT_GUESS_MARKET_ROLE'))
 return out,excluded

def pool_from_values(ranked,assets,adp,eligibility,roles,source):
 assets,role_exclusions=unique_market_assets(assets,ranked)
 valued={(r['player_type'],r['player_id']):r for r in ranked};pool=[];ex=[dict(r,projection_source_choice=source) for r in role_exclusions];seen=set()
 for a in assets:
  aid=str(a['nfbc_player_id']);key=a['player_type'],a.get('player_id');r=valued.get(key);price=a.get('ADP') or a.get('market_ADP');pos=a.get('positions','');reason=None
  if aid in seen:raise ValueError('Duplicate NFBC asset')
  seen.add(aid)
  try:price=float(price)
  except (TypeError,ValueError):price=None
  if price is None or not math.isfinite(price) or price<=0:reason='MISSING_OR_INVALID_ADP'
  slots=eligibility.get(key)
  if not slots:reason=reason or 'MISSING_PRESEASON_POSITION_ELIGIBILITY'
  if not r:reason=reason or 'NO_VALUED_PROJECTION_IN_SELECTED_SOURCE'
  role=roles.get((source,key[1])) if key[0]=='pitcher' else None
  if r and key[0]=='pitcher' and not role:reason=reason or 'MISSING_SOURCE_SPECIFIC_PROJECTED_GS'
  known=reason is None
  if reason:ex.append(dict(nfbc_player_id=aid,player_type=key[0],player_id=key[1],name=a['name'],reason=reason,projection_source_choice=source))
  # Unknown market assets stay in opponent market pool; never receive fabricated production.
  if price is None or not math.isfinite(price) or price<=0:continue
  natural=sorted(slots) if slots else []
  from dc_roster_simulator_v1_3 import eligible
  p=dict(id=aid,nfbc_player_id=aid,player_id=key[1],name=a['name'],player_type=key[0],adp=price,known=known,slots=eligible(';'.join(natural),key[0]) if slots else set(),value=r['sgp_above_replacement'] if known else None,raw=r['raw_sgp'] if known else None,projection_source_choice=source)
  if r:p.update(r['metrics'])
  if role:p.update(GS=role['GS'],GS_provenance=role)
  pool.append(p)
 knownids=[p['player_id'] for p in pool if p['known']]
 if len(knownids)!=len(set(knownids)):raise ValueError('Multiple known NFBC assets share one canonical player; explicit platform identity policy required')
 return sorted(pool,key=lambda p:(p['adp'],p['id'])),ex

def prepare_branch(stage,source,a,watched):
 directory=stage/'coverage_branch';directory.mkdir()
 for name,fields in [('population',POPULATION),('history',HISTORY),('context',CONTEXT),('cutoffs',CUTOFFS)]:write(directory/(name+'_TEMPLATE.csv'),[],fields)
 gaps=csvrows(Path(source)/'nfbc_coverage_priorities.csv');emit(directory/'preseason_collection_requests.csv',[dict(r,requested_inputs='Dated population evidence; prior minor/overseas primitive counts; roster and availability evidence',classification_action='REVIEW_DO_NOT_INFER_BRANCH_CLASS_FROM_NAME_OR_2026_OUTCOMES') for r in gaps])
 rows,folds,report,w=intake(a.branch_population,a.branch_history,a.branch_context,a.branch_cutoffs);watched.update(w)
 for name,rr in rows.items():emit(directory/('validated_'+name+'.csv'),rr)
 emit(directory/'fold_plan.csv',folds);dump(directory/'intake_report.json',report);dump(directory/'contract.json',CONFIG)
 emit(directory/'historical_collection_plan.csv',[dict(origin_season=y,cutoff=f'{y}-01-01' if y<2026 else '2026-03-24',split='HISTORICAL_DEVELOPMENT' if y<2026 else 'DISCLOSED_EVALUATION',population='Freeze dated eligible population independently of later MLB participation',history='Prior-season minor-league/overseas/MLB primitive counts with level, competition, identity and evidence',context='Dated roster, role, injury and availability evidence',requirement='Missing participants are unknown until complete MLB appearance evidence; preserve 2020/2021') for y in range(2016,2027)])
 return report

def build(a):
 if not a.sources or len(a.sources)!=len(set(a.sources)) or set(a.sources)-set(SOURCES):raise ValueError('Explicit unique source choices required')
 root=Path(a.sources_root).resolve();watched=verify(root);cfg=load(a.profile);validate_profile(cfg)
 if cfg['season']!=2026:raise ValueError('Frozen source release is for 2026')
 for p in [a.profile,a.eligibility,a.calibration,a.assets]:watched[str(Path(p).resolve())]=sha(p)
 eligibility=read_eligibility(a.eligibility,2026);calibration=load(a.calibration);assets=csvrows(a.assets);roles,w=role_inputs(a.roles);watched.update(w)
 # Binding market identity/ADP to the frozen v1.13 universe avoids stale aliases.
 bindings=load(root/'input_hashes.json')
 if bindings.get(str(Path(a.assets).resolve()))!=sha(a.assets):raise ValueError('Market file is not the frozen v1.14-bound preseason input')
 assets,identity_audit=resolve_market_assets(root,assets)
 for r in load(root/'original_consensus_records.json'):
  if r['player_type']=='pitcher' and ('reconciled_consensus',r['player_id']) not in roles:
   gs=r['metrics'].get('GS')
   if isinstance(gs,(int,float)) and math.isfinite(gs) and 0<=gs<=162:roles['reconciled_consensus',r['player_id']]=dict(GS=gs,source='FROZEN_ORIGINAL_CONSENSUS_GS',as_of_date='2026-03-24',evidence_reference=str(root/'original_consensus_records.json'),vintage_basis='USER_CONFIRMED_PRESEASON_EFFECTIVE')
 for name in ['branch_population','branch_history','branch_context','branch_cutoffs']:
  path=getattr(a,name,None)
  if path:watched[str(Path(path).resolve())]=sha(path)
 out,backups,stage=start(a.output,a.backup_root,[root]+list(watched))
 summaries=[]
 try:
  emit(stage/'market_identity_resolution.csv',identity_audit)
  for source in a.sources:
   print(source+': valuing frozen source independently',flush=True);d=stage/source;d.mkdir();players,source_ex=load_draft_source(root,source,'nfbc5x5')
   emit(d/'source_exclusions.csv',source_ex)
   try:ranked,valuation_ex,reference,thresholds,iterations,budgets=value_players(players,copy.deepcopy(cfg),eligibility,calibration)
   except ValueError as e:
    # A structurally insufficient pool is a reported source failure, never a consensus fallback.
    if not any(s in str(e) for s in ['Insufficient eligible','No replacement path']):raise
    ranked=[];valuation_ex=[];reference={};thresholds={};iterations=[];budgets={};error=str(e)
   else:error=None
   emit(d/'valuation_exclusions.csv',valuation_ex);emit(d/'player_values.csv',ranked)
   pool,pool_ex=pool_from_values(ranked,assets,None,eligibility,roles,source);emit(d/'simulation_exclusions.csv',pool_ex)
   serial=[dict(p,slots=sorted(p['slots'])) for p in pool];dump(d/'simulation_pool.json',serial)
   # Native flattened rankings for existing tools; source remains explicit in each row.
   emit(d/'player_values_flat.csv',[dict(player_id=r['player_id'],player_type=r['player_type'],name=r['name'],projection_source_choice=source,draft_rank=r['draft_rank'],sgp_above_replacement=r['sgp_above_replacement'],raw_sgp=r['raw_sgp'],auction_value=r['auction_value'],positions=';'.join(r['positions']),**r['metrics']) for r in ranked])
   dump(d/'valuation_context.json',dict(profile=cfg,reference=reference,replacement_thresholds=thresholds,reference_iterations=iterations,auction_budget_cents=budgets))
   emit(d/'role_inputs_used.csv',[dict(rr,projection_source_choice=source,player_id=pid) for (ss,pid),rr in roles.items() if ss==source])
   emit(d/'roles_needed.csv',[dict(projection_source_choice=source,player_id=r['player_id'],name=r['name'],GS='',as_of_date='',source='',evidence_reference='',vintage_basis='') for r in pool_ex if r['reason']=='MISSING_SOURCE_SPECIFIC_PROJECTED_GS'])
   summary=dict(projection_source_choice=source,status='VALUED' if ranked else 'INSUFFICIENT_SOURCE_ROSTER_DEPTH',valuation_error=error,source_eligible=len(players),source_exclusions=len(source_ex),valuation_exclusions=len(valuation_ex),ranked_players=len(ranked),market_assets=len(assets),simulation_pool=len(pool),simulation_known=sum(p['known'] for p in pool),simulation_exclusions=len(pool_ex),missing_role_rows=sum(r['reason']=='MISSING_SOURCE_SPECIFIC_PROJECTED_GS' for r in pool_ex),budget_cents=budgets)
   dump(d/'coverage_report.json',summary);summaries.append(summary)
  branch=prepare_branch(stage,root,a,watched);write(stage/'source_specific_roles_TEMPLATE.csv',[],ROLE_FIELDS)
  report=dict(version='1.15.0',build_implementation_version='1.15.1',frozen_market_identity_bridges=sum(r['resolution_method']=='FROZEN_NFBC_MEMBERSHIP_AND_EXACT_MLBAM_BRIDGE' for r in identity_audit),sources=summaries,branch=branch,accepted_homegrown_modified=False,source_statistics_modified=False,models_fitted=False,evaluation_outcomes_read=False,selection_uses_2026_outcomes=False,source_fallback=False,valuation_scope='Existing NFBC standard 5x5 engine; Yahoo 6x6 valuation is not implemented by that engine',simulation_scope='Existing v1.3 DC draft algorithm; source-specific GS required; market-only assets have no projected production',effective_date='2026-03-24',date_basis='User-confirmed preseason snapshot; retrospective retrieval, not archive certification')
  dump(stage/'source_integration_report.json',report);backup=finish(out,backups,stage,watched);return dict(report,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',nargs='+',choices=SOURCES,required=True)
 defaults=dict(sources_root='outputs/draft_projection_sources_v1_14',profile='config/valuation_nfbc15_dc_v1_1.json',eligibility='data/valuation_inputs_dc_v1_1/nfbc15_dc_eligibility.csv',calibration='data/valuation_inputs_dc_v1_1/nfbc15_dc_sgp_calibration.json',assets='outputs/preseason_coverage_v1_13/draft_asset_coverage.csv',roles=None,output='outputs/draft_source_integration_v1_15',backup_root='backups',branch_population=None,branch_history=None,branch_context=None,branch_cutoffs=None)
 for n,v in defaults.items():p.add_argument('--'+n.replace('_','-'),default=v)
 return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
