"""Build an immutable discrepancy register and modeling-label exclusion plan, offline."""
import argparse,csv,json,hashlib,shutil,tempfile
from pathlib import Path
from collections import Counter
from datetime import datetime,timezone
from modeling_labels_v1_0 import decision,COUNTS,DEPS

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):
 with Path(p).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def write(p,rows):
 with p.open('w',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def tree(p):return {str(x.relative_to(p)):sha(x) for x in p.rglob('*') if x.is_file()}
def build(evidence,policy_path,confirmation_path,output,backup_root):
 evidence,policy_path,confirmation_path,output,backup_root=map(lambda p:Path(p).resolve(),(evidence,policy_path,confirmation_path,output,backup_root))
 if output.exists():raise FileExistsError('Choose a new output folder')
 for a,b in [(output,evidence),(output,backup_root),(backup_root,evidence)]:
  if a==b or a in b.parents or b in a.parents:raise ValueError('Overlapping folders')
 policy=json.loads(policy_path.read_text(encoding='utf-8-sig'));confirmation=json.loads(confirmation_path.read_text(encoding='utf-8-sig'))
 if policy['version']!='1.0.0' or policy['cross_source_component_substitution'] or policy['disputed_metric_action']!='EXCLUDE_METRIC_AND_DEPENDENT_LABELS':raise ValueError('Unsupported label policy')
 files=[x for x in evidence.rglob('*') if x.is_file()]+[policy_path,confirmation_path];hashes={str(p):sha(p) for p in files}
 baseline=read(evidence/'discrepancies.csv');report=json.loads((evidence/'reconciliation_report.json').read_text(encoding='utf-8-sig'))
 expected={k.split('\\')[-1]:v for k,v in report['input_sha256'].items() if k.endswith(('actual_counts.parquet','player_seasons.parquet'))}
 if policy['expected_reference_hashes']!=expected:raise ValueError('Reference snapshot policy mismatch')
 if len(baseline)!=report['discrepancy_metric_rows']:raise ValueError('Baseline report mismatch')
 hit=evidence/'hit_review/results';differences=read(hit/'differing_games.csv');seasons=read(hit/'season_comparisons.csv');boxes=read(hit/'game_boxscore_inspections.csv')
 plays=json.loads((evidence/'play_review/play_comparisons.json').read_text(encoding='utf-8-sig'))
 if confirmation['basis']!='USER_CONFIRMED_IN_CONVERSATION' or sorted(confirmation['expected_dates'])!=sorted(p['expected_historical_date'] for p in plays):raise ValueError('Year confirmation mismatch')
 def key(r):return (int(r['season']),r['player_type'],str(r['mlbam_id']),r['metric'])
 hits={key(r):r for r in differences};sums={key(r):r for r in seasons}
 if len(hits)!=len(differences):raise ValueError('Duplicate hit evidence metric')
 register=[];seen=set()
 for b in baseline:
  k=key(b)
  if k in seen or k[0]>policy['training_max_season']:raise ValueError('Duplicate or holdout baseline case')
  seen.add(k)
  if int(b['evidence_count'])-int(b['fangraphs_actual'])!=int(b['final_difference']):raise ValueError('Bad baseline arithmetic')
  case_id='case_'+hashlib.sha256('|'.join(map(str,k)).encode()).hexdigest()[:20]
  r=dict(case_id=case_id,register_version='1.0.0',**b,register_status='RETAINED_PRIOR_DIFFERENCE_REVIEW_PENDING',classification='NOT_RECLASSIFIED_BY_HIT_REVIEW',game_pk='',historical_date='',workbook_date='',date_basis='',play_evidence='',label_action=policy['disputed_metric_action'],primary_label_source=policy['primary_season_label_source'],source_count_modified=False,scoring_revision_proven=False)
  if k in hits:
   h=hits[k];s=sums[k]
   if int(s['fangraphs_log_sum'])!=int(b['fangraphs_actual']) or int(s['reconstructed'])!=int(b['evidence_count']):raise ValueError('Hit evidence baseline mismatch')
   if int(s['mlb_log_sum'])!=int(b['evidence_count']) or int(h['fangraphs_game_count'])-int(h['mlb_game_count'])!=-int(b['final_difference']):raise ValueError('Game evidence bridge mismatch')
   candidates=[p for p in plays if str(p['game_pk'])==h['game_pk']]
   if len(candidates)!=1:raise ValueError('Missing/ambiguous play evidence')
   p=candidates[0]
   if p['expected_historical_date']!=h['date']:raise ValueError('Historical date mismatch')
   feed=hit/'mlb_game_feeds'/f"{h['game_pk']}.json";meta=json.loads(feed.with_name(feed.stem+'.source.json').read_text(encoding='utf-8-sig'))
   if sha(feed)!=meta['sha256']:raise ValueError('MLB feed hash failure')
   data=json.loads(feed.read_text(encoding='utf-8-sig'))
   if str(data['gamePk'])!=h['game_pk'] or data['gameData']['datetime']['officialDate']!=h['date']:raise ValueError('MLB game identity mismatch')
   actual=[v for v in data['liveData']['plays']['allPlays'] if v['about']['atBatIndex']==p['mlb_play_index']]
   if len(actual)!=1 or actual[0]['result']['eventType']!=p['mlb_event']:raise ValueError('MLB event mismatch')
   box=[v for v in boxes if key(v)==k]
   if len(box)!=1 or box[0]['feed_agrees_with_frozen_mlb']!='True':raise ValueError('MLB boxscore not verified')
   status='FANGRAPHS_PLAY_TEXT_VS_EXPORTED_TOTALS' if p['outcome_agrees'] else 'CROSS_PROVIDER_SINGLE_VS_ERROR'
   r.update(register_status='DOCUMENTED_SOURCE_DISCREPANCY',classification=status,game_pk=h['game_pk'],historical_date=h['date'],workbook_date=p['workbook_date'],date_basis=confirmation['basis'],play_evidence='hit_review/results/mlb_game_feeds/'+feed.name+';play_review/play_comparisons.json')
  elif b['metric'] in {'H','1B','2B','3B','HR'}:raise ValueError('Hit case lacks reviewed evidence')
  register.append(r)
 if set(hits)!=set(k for k in seen if k[3] in {'H','1B','2B','3B','HR'}):raise ValueError('Unaccounted hit cases')
 plan=[]
 for y,role,pid in sorted({(int(r['season']),r['player_type'],r['mlbam_id']) for r in register}):
  for metric in sorted(COUNTS[role]|set(DEPS[role])):
   d=decision(y,role,pid,metric,register,policy)
   if not d['eligible']:plan.append(dict(season=y,player_type=role,mlbam_id=pid,metric=metric,case_ids=';'.join(d['case_ids']),reason=';'.join(d['reasons']),label_value=None,primary_source=d['source']))
 if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('Evidence changed during build')
 output.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=output.name+'.staging-',dir=output.parent))
 try:
  write(stage/'discrepancy_register.csv',register);dump(stage/'discrepancy_register.json',register);write(stage/'label_exclusion_plan.csv',plan)
  dump(stage/'modeling_label_policy.json',policy);dump(stage/'play_log_year_confirmation.json',confirmation);dump(stage/'input_hashes.json',hashes)
  shutil.copytree(evidence,stage/'evidence')
  events=[dict(case_id=r['case_id'],release='1.0.0',from_status=r['status'],to_status=r['register_status'],classification=r['classification'],counts_modified=False) for r in register]
  (stage/'register_events.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in events),encoding='utf-8')
  backup=backup_root/(output.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
  summary=dict(version='1.0.0',build_implementation_version='1.0.1',baseline_discrepancy_rows=len(register),classifications=dict(Counter(r['classification'] for r in register)),direct_disputed_metrics=len(register),derived_and_direct_exclusion_rows=len(plan),primary_season_label_source=policy['primary_season_label_source'],reference_counts_modified=False,source_evidence_unchanged=True,training_labels_materialized=False,full_actuals_reference_present=False,model_ready=False,backup=str(backup),scope='Versioned register, dependency exclusions and label resolver API; not a full training dataset build')
  dump(stage/'build_report.json',summary);dump(stage/'output_sha256.json',tree(stage))
  backup_root.mkdir(parents=True,exist_ok=True);shutil.copytree(stage,backup)
  if tree(stage)!=tree(backup):raise ValueError('Backup verification failed')
  if any(sha(p)!=v for p,v in hashes.items()):raise ValueError('Input changed before publication')
  stage.rename(output);return summary
 finally:
  if stage.exists():shutil.rmtree(stage)
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--evidence',default='evidence/discrepancy_register_v1_0');p.add_argument('--policy',default='config/modeling_label_policy_v1_0.json');p.add_argument('--confirmation',default='config/play_log_year_confirmation_v1_0.json');p.add_argument('--output',default='outputs/discrepancy_register_v1_0');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(build(a.evidence,a.policy,a.confirmation,a.output,a.backup_root),indent=2))
