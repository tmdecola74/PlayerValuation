"""Fit full-season SGP slopes from prior-season category standings rank grids."""
import argparse,csv,hashlib,json,math,statistics
from collections import defaultdict
from pathlib import Path
from valuation_math_v1_0 import finite

def calibrate(rows,teams,target,categories,source,full_season):
 if not full_season or not source.strip():raise ValueError('A named full-season historical source is required')
 groups=defaultdict(list)
 for row in rows:
  year=int(row['season'])
  if year>=target:raise ValueError('Calibration includes target/future season')
  if not row['league_id'].strip():raise ValueError('Missing historical league ID')
  groups[(year,row['league_id'])].append(row)
 if not groups:raise ValueError('No calibration data')
 fitted=[]
 for (year,league),group in sorted(groups.items()):
  if len(group)!=teams or sorted(int(r['rank']) for r in group)!=list(range(1,teams+1)):raise ValueError('Each rank grid must contain the complete league ranks once')
  pts=[float(r['points']) for r in group]
  if any(abs(float(r['points'])-(teams+1-int(r['rank'])))>1e-9 for r in group):raise ValueError('Rank-grid points must equal teams+1-rank')
  mx=statistics.fmean(pts);var=sum((p-mx)**2 for p in pts)
  for category,rule in categories.items():
   vals=[float(r[category]) for r in group]
   if not all(finite(v) and v>=0 for v in vals):raise ValueError('Invalid calibration statistic')
   if category=='AVG' and any(v>1 for v in vals):raise ValueError('AVG must be fractional, not percentage')
   ordered=sorted(zip(pts,vals));lower=category in ('ERA','WHIP');direction=-1 if lower else 1
   if any(direction*(v2-v1)<-1e-9 for (_,v1),(_,v2) in zip(ordered,ordered[1:])):raise ValueError('Category rank grid is not ordered correctly: '+category)
   my=statistics.fmean(vals);slope=sum((p-mx)*(v-my) for p,v in zip(pts,vals))/var
   if abs(slope)<1e-12 or direction*slope<=0:raise ValueError('Degenerate category slope: '+category)
   fitted.append(dict(season=year,league_id=league,category=category,signed_stat_units_per_point=slope,sgp_slope=abs(slope),teams=teams))
 slopes={cat:statistics.fmean(r['sgp_slope'] for r in fitted if r['category']==cat) for cat in categories}
 return dict(version='1.0.0',target_season=target,teams=teams,full_season=True,source=source,seasons=sorted({y for y,_ in groups}),method='OLS statistic against rank points within each complete league; equal league-season average of slope magnitudes',slopes=slopes,league_fits=fitted)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--standings',required=True);p.add_argument('--source',required=True);p.add_argument('--full-season',action='store_true');p.add_argument('--profile',default='config/valuation_nfbc15_v1_0.json');p.add_argument('--output',default='data/valuation_inputs/nfbc15_sgp_calibration.json')
 a=p.parse_args();cfg=json.loads(Path(a.profile).read_text(encoding='utf-8'));out=Path(a.output)
 if out.exists():raise ValueError('Calibration output must not exist')
 with Path(a.standings).open(encoding='utf-8-sig',newline='') as f:rows=list(csv.DictReader(f))
 categories={k:v for typ in cfg['categories'].values() for k,v in typ.items()};result=calibrate(rows,cfg['teams'],cfg['season'],categories,a.source,a.full_season)
 result['standings_sha256']=hashlib.sha256(Path(a.standings).read_bytes()).hexdigest();out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
if __name__=='__main__':main()
