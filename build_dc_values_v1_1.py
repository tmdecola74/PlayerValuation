"""Build Draft Champions values and market ADP comparison, preserving complete backup."""
import argparse,csv,json,shutil,tempfile,sys
from pathlib import Path
from datetime import datetime,timezone
from build_league_valuations_v1_0 import build as build_values,csv_out,dump,sha

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--inputs',default='data/valuation_inputs_dc_v1_1');p.add_argument('--profile',default='config/valuation_nfbc15_dc_v1_1.json');p.add_argument('--consensus-config',default='config/valuation_consensus_v1_0.json');p.add_argument('--warehouse');p.add_argument('--output',default='outputs/nfbc15_dc_values_2026_v1_1');p.add_argument('--backup-root',default='backups');a=p.parse_args()
 root=Path(a.inputs).resolve();out=Path(a.output).resolve()
 if out.exists():raise ValueError('Output must not exist')
 # Run the normal audited engine to a distinct intermediate folder. It is backed up,
 # then the final DC deliverable (including ADP) receives its own full backup.
 intermediate=out.with_name(out.name+'.engine')
 args=argparse.Namespace(profile=a.profile,consensus_config=a.consensus_config,warehouse=a.warehouse,output=str(intermediate),prepare_inputs=False,eligibility=str(root/'nfbc15_dc_eligibility.csv'),calibration=str(root/'nfbc15_dc_sgp_calibration.json'),backup_root=a.backup_root)
 result=build_values(args)
 originals=[root/'nfbc15_dc_adp.csv',root/'dc_input_audit.json',root/'nfbc15_dc_eligibility_review.csv',root/'nfbc15_dc_eligibility.csv'];hashes={str(f):sha(f) for f in originals}
 adp={}
 with originals[0].open(encoding='utf-8-sig',newline='') as f:
  for row in csv.DictReader(f):
   key=(row['player_type'],row['player_id'])
   if key in adp:raise ValueError('Duplicate ADP role/ID')
   adp[key]=row
 # Reviewed eligibility is authoritative for the current NFBC/canonical link.
 # The original ADP export may still contain an empty or obsolete canonical ID.
 with originals[3].open(encoding='utf-8-sig',newline='') as f:
  eligibility=list(csv.DictReader(f))
 for row in eligibility:
  key=(row['player_type'],row['player_id'])
  old=adp.get(key,{})
  adp[key]=dict(old,nfbc_player_id=row['nfbc_player_id'],ADP=row.get('ADP') or old.get('ADP',''))
 with (intermediate/'player_values.csv').open(encoding='utf-8-sig',newline='') as f:values=list(csv.DictReader(f))
 for r in values:
  market=adp.get((r['player_type'],r['player_id']))
  r['nfbc_player_id']=market['nfbc_player_id'] if market else None;r['market_ADP']=float(market['ADP']) if market and market.get('ADP') else None;r['ADP_minus_value_rank']=r['market_ADP']-int(r['draft_rank']) if r['market_ADP'] is not None else None
 stage=Path(tempfile.mkdtemp(prefix=out.name+'.staging-',dir=out.parent))
 try:
  shutil.copytree(intermediate,stage,dirs_exist_ok=True)
  csv_out(stage/'player_values_with_adp.csv',values)
  valued={r['nfbc_player_id'] for r in values if r['nfbc_player_id']};watch={}
  with originals[3].open(encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    if r['nfbc_player_id'] not in valued:watch[r['nfbc_player_id']]=dict(nfbc_player_id=r['nfbc_player_id'],name=r['source_player_name'],team=r['source_team'],player_type=r['player_type'],market_ADP=r['ADP'],reason='MAPPED_BUT_MISSING_OR_BELOW_FLOOR_PROJECTION_COMPONENTS')
  with originals[2].open(encoding='utf-8-sig',newline='') as f:
   for r in csv.DictReader(f):
    # Retain historical review separately, but never reintroduce resolved assets.
    if r['nfbc_player_id'] not in valued and r['nfbc_player_id'] not in watch:
     watch[str(r['nfbc_player_id'])]=dict(nfbc_player_id=r['nfbc_player_id'],name=r['name'],team=r['team'],player_type=r['player_type'],market_ADP=r.get('ADP'),reason=r['reason'])
  csv_out(stage/'unvalued_adp_watchlist.csv',list(watch.values()))
  shutil.copy(originals[1],stage/'dc_input_audit.json');shutil.copy(originals[2],stage/'nfbc15_dc_eligibility_review.csv')
  audit=json.loads((stage/'valuation_audit.json').read_text());audit['unvalued_nfbc_assets']=len(watch);audit['adp_comparison_rows']=len(values);audit['adp_matched_rows']=sum(r['market_ADP'] is not None for r in values);audit['reporting_version']='1.1.1';audit['additional_input_sha256']=hashes;audit['ADP_usage']='ADP is an external price/timing comparison only; it does not determine SGP, projections or model ranks.'
  backup_root=Path(a.backup_root).resolve();backup_root.mkdir(parents=True,exist_ok=True);backup=backup_root/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'));audit['backup']=str(backup);dump(stage/'valuation_audit.json',audit)
  for path,h in hashes.items():
   if sha(path)!=h:raise ValueError('ADP input changed')
  shutil.copytree(stage,backup)
  for path in stage.rglob('*'):
   if path.is_file() and sha(path)!=sha(backup/path.relative_to(stage)):raise ValueError('DC final backup mismatch')
  stage.rename(out);print(json.dumps(dict(audit,output=str(out)),indent=2))
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise
if __name__=='__main__':main()
