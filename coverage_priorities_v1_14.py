"""Preseason review ordering only; no actuals or model selection."""
import json
from collections import defaultdict
from projection_release_v1_11_1 import finite,HOME

def priorities(universe,assets,originals,home):
 published={(r['player_type'],r['player_id']):r['metrics'] for r in originals};home_by={(r['player_type'],r['player_id']):r for r in home if r['projection_source']==HOME and r['player_id']};index={r['universe_id']:r for r in universe};market=[];nonmarket=[];unknown=[]
 def details(u):
  role=u['player_type'];m='PA' if role=='hitter' else 'IP';values=published.get((role,u['player_id']))
  basis='ORIGINAL_PUBLISHED_PRESEASON_CONSENSUS' if values is not None else 'FROZEN_HOMEGROWN' if (role,u['player_id']) in home_by else 'UNAVAILABLE'
  value=values.get(m) if values is not None else home_by.get((role,u['player_id']),{}).get(m)
  if not finite(value) or value<0:value=None
  gap='IDENTITY_REVIEW' if not u['player_id'] else 'MISSING_HOMEGROWN' if not u['homegrown_forecast_present'] else 'HOMEGROWN_COMPONENT_OR_EXPOSURE_GAP' if not u['homegrown_basic_valuation_ready'] else 'CLASSIFICATION_REVIEW'
  return dict(universe_id=u['universe_id'],player_type=role,player_id=u['player_id'],mlbam_id=u['mlbam_id'],name=u['name'],preseason_stratum=u['preseason_stratum'],coverage_gap=gap,homegrown_forecast_present=u['homegrown_forecast_present'],homegrown_basic_valuation_ready=u['homegrown_basic_valuation_ready'],reconciled_candidate_basic_valuation_ready=u['reconciled_candidate_basic_valuation_ready'],projected_workload=value,workload_metric=m,workload_source=basis,preseason_evidence_present=u['preseason_evidence_present'])
 seen=set()
 for asset in assets:
  k=asset['player_type'],asset['nfbc_player_id']
  if k in seen or asset['universe_id'] not in index:raise ValueError('Duplicate/orphan NFBC asset')
  seen.add(k);u=index[asset['universe_id']]
  if u['homegrown_basic_valuation_ready']:continue
  value=asset.get('market_ADP');adp=None if value in ['',None] else float(value)
  if adp is not None and (not finite(adp) or adp<=0):raise ValueError('Invalid preseason ADP')
  band='ADP_UNKNOWN' if adp is None else 'ADP_LE150' if adp<=150 else 'ADP_151_345' if adp<=345 else 'ADP_346_750' if adp<=750 else 'ADP_GT750'
  market.append(dict(**details(u),nfbc_player_id=k[1],market_ADP=adp,ADP_band=band))
 market.sort(key=lambda r:(r['market_ADP'] is None,r['market_ADP'] or 0,r['player_type'],-(r['projected_workload'] if r['projected_workload'] is not None else -1),r['nfbc_player_id']))
 for n,r in enumerate(market,1):r['review_rank']=n
 market_universe={a['universe_id'] for a in assets}
 for u in universe:
  if not u['preseason_evidence_present'] or u['homegrown_basic_valuation_ready'] or u['universe_id'] in market_universe:continue
  row=details(u);floor=100 if row['player_type']=='hitter' else 20
  (nonmarket if row['projected_workload'] is not None and row['projected_workload']>=floor else unknown).append(row)
 nonmarket.sort(key=lambda r:(r['player_type'],-r['projected_workload'],r['universe_id']));rank=defaultdict(int)
 for r in nonmarket:rank[r['player_type']]+=1;r['role_review_rank']=rank[r['player_type']]
 unknown.sort(key=lambda r:(r['player_type'],r['projected_workload'] is None,-(r['projected_workload'] or 0),r['universe_id']))
 return market,nonmarket,unknown
