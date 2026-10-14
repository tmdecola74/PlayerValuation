"""Map a supplied official eligibility export to prepared consensus canonical IDs.
Unique ID first, otherwise unique exact normalized name within supplied player type.
Ambiguous/unmatched rows are retained for review; no position is inferred.
"""
import argparse,csv,json,re,unicodedata
from collections import defaultdict
from pathlib import Path
from build_league_valuations_v1_0 import positions,csv_out,dump

def normalized(s):return ' '.join(''.join(c for c in unicodedata.normalize('NFKD',s.casefold()) if not unicodedata.combining(c)).split())
def map_rows(rows,players,season,source,name_col,position_col,id_col=None):
 names=defaultdict(set);ids=defaultdict(set)
 for p in players:
  typ=p['player_type'];pid=p['player_id']
  for name in [p['name']]+p.get('recorded_names',[]):names[(typ,normalized(name))].add(pid)
  for mid in p.get('mlbam_ids',[]):ids[(typ,str(mid))].add(pid)
 mapped={};issues=[]
 for n,r in enumerate(rows,2):
  pos=positions(r.get(position_col,''))
  if not pos:issues.append(dict(row=n,name=r.get(name_col,''),reason='MISSING_POSITIONS'));continue
  typ='pitcher' if pos=={'P'} else 'hitter'
  if 'P' in pos and len(pos)>1:issues.append(dict(row=n,name=r.get(name_col,''),reason='MIXED_PITCHER_HITTER_POSITIONS_REQUIRES_EXPLICIT_ROLE'));continue
  mid=r.get(id_col,'').strip() if id_col else '';matches=ids[(typ,mid)] if mid else names[(typ,normalized(r.get(name_col,'')))];method='MLBAM_ID' if mid else 'UNIQUE_NORMALIZED_NAME_AND_TYPE'
  if len(matches)!=1:issues.append(dict(row=n,name=r.get(name_col,''),reason='AMBIGUOUS' if len(matches)>1 else 'UNMATCHED',mlbam_id=mid));continue
  pid=next(iter(matches));key=(typ,pid)
  item=dict(player_id=pid,player_type=typ,name=r.get(name_col,''),positions=';'.join(sorted(pos)),eligibility_season=season,eligibility_basis_season=season-1,source=source,match_method=method)
  if key in mapped and mapped[key]['positions']!=item['positions']:raise ValueError('Conflicting eligibility entries for '+pid)
  mapped[key]=item
 return list(mapped.values()),issues

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--csv',required=True);p.add_argument('--prepared-consensus',default='outputs/nfbc15_valuation_inputs_v1_0/consensus');p.add_argument('--name-column',required=True);p.add_argument('--position-column',required=True);p.add_argument('--mlbam-column');p.add_argument('--season',type=int,default=2026);p.add_argument('--source',required=True);p.add_argument('--basis-season',type=int,required=True);p.add_argument('--output',default='data/valuation_inputs/nfbc15_eligibility.csv')
 a=p.parse_args();out=Path(a.output)
 if a.basis_season!=a.season-1:raise ValueError('Declare the prior-season eligibility basis; in-season gains are not allowed')
 if not a.source.strip():raise ValueError('A named eligibility source is required')
 if out.exists():raise ValueError('Eligibility output must not exist')
 players=[]
 for typ in ['hitter','pitcher']:players+=json.loads((Path(a.prepared_consensus)/f'{typ}_consensus.json').read_text(encoding='utf-8'))
 with Path(a.csv).open(encoding='utf-8-sig',newline='') as f:reader=csv.DictReader(f);rows=list(reader);headers=reader.fieldnames
 for col in [a.name_column,a.position_column]+([a.mlbam_column] if a.mlbam_column else []):
  if col not in headers:raise ValueError('Missing requested source heading: '+col)
 mapped,issues=map_rows(rows,players,a.season,a.source,a.name_column,a.position_column,a.mlbam_column)
 out.parent.mkdir(parents=True,exist_ok=True);csv_out(out,mapped,['player_id','player_type','name','positions','eligibility_season','eligibility_basis_season','source','match_method']);csv_out(out.with_suffix('.review.csv'),issues)
 print(json.dumps(dict(mapped=len(mapped),review_rows=len(issues),output=str(out)),indent=2))
if __name__=='__main__':main()
