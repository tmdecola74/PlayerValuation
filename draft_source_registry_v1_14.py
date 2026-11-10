"""Explicit source selection; no fallback or blend between projection sources."""
import json
from pathlib import Path
from standalone_io_v1_0 import load,sha,verify
from projection_release_v1_11_1 import METRICS,finite

PROFILES={'nfbc5x5':{'hitter':['PA','AB','H','R','HR','RBI','SB','AVG'],'pitcher':['IP','H','ER','BB','W','SV','SO','ERA','WHIP']},'yahoo6x6':{'hitter':['PA','AB','H','R','HR','RBI','SB','AVG','OPS'],'pitcher':['IP','H','ER','BB','W','SO','QS','SV_plus_HLD','ERA','WHIP']}}

def eligible_records(rows,profile):
 if profile not in PROFILES:raise ValueError('Unknown league category profile')
 players=[];excluded=[];seen=set()
 for r in rows:
  role=r['player_type'];pid=r['player_id'];k=role,pid or ('MLBAM:'+r['mlbam_id'] if r.get('mlbam_id') else r.get('projection_key'))
  if k in seen:raise ValueError('Duplicate canonical role in source')
  seen.add(k);needed=PROFILES[profile][role];missing=[m for m in needed if not finite(r.get(m)) or r[m]<0];exposure=r.get('AB' if role=='hitter' else 'IP')
  reason='MISSING_CANONICAL_ID' if not pid else 'UNSUPPORTED_CATEGORY_COMPONENTS' if missing else 'BELOW_AB_OR_IP_FLOOR' if exposure is None or exposure<1 else None
  if reason:excluded.append(dict(player_type=role,player_id=pid,name=r['name'],reason=reason,missing_metrics_json=json.dumps(missing)));continue
  players.append(dict(season=2026,player_type=role,player_id=pid,name=r['name'],mlbam_ids=[r['mlbam_id']] if r['mlbam_id'] else [],teams=json.loads(r['teams']),projection_source=r['projection_source'],metrics={m:r.get(m) for m in METRICS[role]}))
 return players,excluded

def load_draft_source(root,source,profile='nfbc5x5'):
 root=Path(root).resolve();verify(root);registry=load(root/'projection_source_registry.json')
 if source not in ['homegrown','reconciled_consensus']:raise ValueError('Select homegrown or reconciled_consensus explicitly; references cannot supply valuations')
 entry=registry['sources'][source]
 if not entry['supported']:raise ValueError('Requested source did not pass the export audit; no fallback applied')
 for n in ['projection_source_registry.json',entry['record_file']]:
  expected=load(root/'source_registry_freeze.json').get(n);p=(root/n).resolve()
  if root not in p.parents or expected!=sha(p):raise ValueError('Source registry binding failure')
 return eligible_records(load(root/entry['record_file']),profile)
