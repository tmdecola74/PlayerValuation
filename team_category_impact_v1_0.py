"""Exact team numerator/denominator changes for explicit roster swaps."""
import argparse,csv,json
from pathlib import Path
from valuation_math_v1_0 import finite

def totals(players):
 keys={'hitter':['R','HR','RBI','SB','H','AB'],'pitcher':['W','SV','SO','H','BB','ER','IP']};parts={'hitter':{},'pitcher':{}};seen=set()
 for row in players:
  if row['player_id'] in seen:raise ValueError('Duplicate canonical asset in roster')
  seen.add(row['player_id']);typ=row['player_type'];m=row['metrics']
  for k in keys[typ]:
   if not finite(m.get(k)) or m[k]<0:raise ValueError('Missing/invalid roster component: '+k)
   parts[typ][k]=parts[typ].get(k,0)+m[k]
 h=parts['hitter'];p=parts['pitcher']
 if h.get('AB',0)<=0 or p.get('IP',0)<=0:raise ValueError('Team must have positive hitter AB and pitcher IP')
 result={k:h[k] for k in ['R','HR','RBI','SB']};result.update({k:p[v] for k,v in [('W','W'),('SV','SV'),('K','SO')]})
 result.update(AVG=h['H']/h['AB'],ERA=9*p['ER']/p['IP'],WHIP=(p['H']+p['BB'])/p['IP'])
 return result,parts

def exact_change(before,after,slopes):
 b,bparts=totals(before);a,aparts=totals(after)
 return dict(before=b,after=a,before_components=bparts,after_components=aparts,category_sgp_change={k:(a[k]-b[k])*(-1 if k in ('ERA','WHIP') else 1)/slopes[k] for k in b})

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--roster-json',required=True);p.add_argument('--add-player-json',required=True);p.add_argument('--drop-player-id',required=True);p.add_argument('--calibration',required=True);p.add_argument('--output',required=True)
 a=p.parse_args();before=json.loads(Path(a.roster_json).read_text());add=json.loads(Path(a.add_player_json).read_text());cal=json.loads(Path(a.calibration).read_text());out=Path(a.output)
 if out.exists():raise ValueError('Output must not exist')
 if sum(r['player_id']==a.drop_player_id for r in before)!=1:raise ValueError('Drop must identify exactly one roster player')
 after=[r for r in before if r['player_id']!=a.drop_player_id]+[add]
 result=exact_change(before,after,cal['slopes']);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
