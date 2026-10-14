"""Read-only workbook importer: full per-league DC SGP and preseason NFBC eligibility."""
from __future__ import annotations
import argparse,collections,csv,hashlib,json,math,re,statistics,unicodedata,shutil,tempfile
from datetime import datetime,timezone
from pathlib import Path
import openpyxl
from calibrate_league_sgp_v1_0 import calibrate
from build_league_valuations_v1_0 import positions,csv_out,dump,sha

CATEGORIES=['R','HR','RBI','SB','AVG','W','SV','K','ERA','WHIP']
TEAM_ALIASES={'KC':'KCR','CWS':'CHW','SD':'SDP','SF':'SFG','MLW':'MIL','WAS':'WSN','WSH':'WSN','AZ':'ARI','ARZ':'ARI','TB':'TBR','OAK':'ATH'}
def team(x):return TEAM_ALIASES.get(str(x).upper().strip(),str(x).upper().strip())
def normalized(x):
 x=''.join(c for c in unicodedata.normalize('NFKD',str(x).casefold()) if not unicodedata.combining(c))
 x=re.sub(r'\b(jr|sr|ii|iii|iv)\.?\s*$','',x)
 return re.sub('[^a-z0-9]','',x)
def display_name(x):
 pieces=str(x).split(', ',1)
 return ' '.join(pieces[::-1]) if len(pieces)==2 else str(x)
def innings(x):
 value=float(x);whole=math.floor(value);outs=round((value-whole)*10)
 if value<0 or outs not in (0,1,2) or abs(value-(whole+outs/10))>1e-7:raise ValueError('Invalid baseball innings: '+str(x))
 return whole+outs/3

def read_standings(path):
 workbook=openpyxl.load_workbook(path,read_only=True,data_only=True);out=[];audit=[]
 try:
  for sheet in workbook:
   if sheet.title not in ('2023','2024','2025'):continue
   rows=list(sheet.values);header=next((i for i,r in enumerate(rows) if r[0]=='Rank' and r[3]=='League'),None)
   if header is None:raise ValueError('No team standings heading in '+sheet.title)
   for number,r in enumerate(rows[header+1:],header+2):
    if not r[3]:continue
    if len(r)<25 or any(r[j] is None for j in range(9,25)):raise ValueError('Incomplete team statistic row')
    ip=innings(r[19]);ab=float(r[13]);h=float(r[14]);er=float(r[20]);bb=float(r[22]);ha=float(r[23])
    if ip<=0 or ab<=0:raise ValueError('Nonpositive actual exposure')
    if any(float(r[j])<0 or abs(float(r[j])-round(float(r[j])))>1e-9 for j in [9,10,11,12,13,14,16,17,18,20,22,23]):raise ValueError('Invalid historical count component')
    if h>ab:raise ValueError('Historical hitter H exceeds AB')
    record=dict(season=int(sheet.title),league_id=str(r[3]),team_name=str(r[2]),owner=str(r[1]),source_row=number,draft_position=r[4],AB=ab,H_hit=h,IP=ip,IP_baseball=r[19],ER=er,BB_allowed=bb,H_allowed=ha,R=float(r[9]),HR=float(r[10]),RBI=float(r[11]),SB=float(r[12]),AVG=h/ab,K=float(r[16]),W=float(r[17]),SV=float(r[18]),ERA=9*er/ip,WHIP=(ha+bb)/ip,published_AVG=float(r[15]),published_ERA=float(r[21]),published_WHIP=float(r[24]))
    # 2025 stores AVG 3dp and ERA/WHIP 2dp, with observed two-step rounding from prior 4/3dp; tolerance is the sum of both half-unit bounds.
    tolerances={'AVG':.000551 if sheet.title=='2025' else .000051,'ERA':.005501 if sheet.title=='2025' else .000501,'WHIP':.005501 if sheet.title=='2025' else .000501}
    for cat,tol in tolerances.items():
     if abs(record[cat]-record['published_'+cat])>tol:audit.append(dict(season=record['season'],league_id=record['league_id'],team_name=record['team_name'],metric=cat,recomputed=record[cat],published=record['published_'+cat],reason='BEYOND_EXPECTED_ROUNDING'))
    out.append(record)
 finally:workbook.close()
 groups=collections.defaultdict(list)
 for r in out:groups[(r['season'],r['league_id'])].append(r)
 for key,group in groups.items():
  if len(group)!=15:raise ValueError('Incomplete league: '+str(key))
  if len({r['draft_position'] for r in group})!=15:raise ValueError('Duplicate/missing draft position within league: '+str(key))
 if not out:raise ValueError('No completed 2023-2025 team rows')
 if audit:raise ValueError('Actual rate components do not match published values within rounding tolerance: '+str(audit[:3]))
 return out,groups

def dc_calibration(records,groups,minimum_ip=950):
 years=sorted({r['season'] for r in records});annual={};fits=[];penalties=[]
 for year in years:
  grids=[];clean_grids=[];year_groups={k:g for k,g in groups.items() if k[0]==year}
  for (_,league),group in sorted(year_groups.items()):
   sorted_stats={cat:sorted((r[cat] for r in group),reverse=cat not in ('ERA','WHIP')) for cat in CATEGORIES}
   grid=[dict(season=year,league_id=league,rank=i+1,points=15-i,**{cat:sorted_stats[cat][i] for cat in CATEGORIES}) for i in range(15)]
   grids.extend(grid)
   if all(r['IP']>=minimum_ip for r in group):clean_grids.extend(grid)
   else:penalties.append(dict(season=year,league_id=league,teams_below_minimum=sum(r['IP']<minimum_ip for r in group),policy='Exclude entire league from ERA/WHIP slope fitting; retain all counting and AVG categories'))
  # Penalized teams receive special standings points not encoded in this workbook.
  # Avoid inventing those points: rate calibration uses complete penalty-free leagues.
  ordinary=calibrate(grids,15,2026,{cat:{} for cat in CATEGORIES if cat not in ('ERA','WHIP')},'Completed NFBC Draft Champions standings',True)
  rates=calibrate(clean_grids,15,2026,{cat:{} for cat in ('ERA','WHIP')},'Complete DC leagues with every team >=950 IP',True)
  annual[year]={**ordinary['slopes'],**rates['slopes']};fits+=ordinary['league_fits']+rates['league_fits']
 combined={cat:statistics.fmean(annual[y][cat] for y in years) for cat in CATEGORIES}
 components={}
 for year in years:
  hitters=[r for r in records if r['season']==year]
  pitchers=[r for k,g in groups.items() if k[0]==year and all(x['IP']>=minimum_ip for x in g) for r in g]
  components[year]=dict(team_AB=statistics.fmean(r['AB'] for r in hitters),team_H=statistics.fmean(r['H_hit'] for r in hitters),team_IP=statistics.fmean(r['IP'] for r in pitchers),team_ER=statistics.fmean(r['ER'] for r in pitchers),team_H_allowed=statistics.fmean(r['H_allowed'] for r in pitchers),team_BB=statistics.fmean(r['BB_allowed'] for r in pitchers))
 avg={k:statistics.fmean(components[y][k] for y in years) for k in components[years[0]]}
 reference=dict(AVG=avg['team_H']/avg['team_AB'],ERA=9*avg['team_ER']/avg['team_IP'],WHIP=(avg['team_H_allowed']+avg['team_BB'])/avg['team_IP'],team_AB=avg['team_AB'],team_IP=avg['team_IP'])
 result=dict(version='1.1.0',target_season=2026,teams=15,format='Draft Champions',full_season=True,source='User supplied 2023-2025 DC Category Stats - Overall.xlsx, full team rows grouped by season and league',seasons=years,slopes=combined,annual_slopes=annual,rate_reference=reference,rate_reference_components_by_season=components,method='Within-league OLS on sorted category rank grid; equal-league annual averages, then equal-season mean across 2023/2024/2025',minimum_ip_policy=dict(threshold=minimum_ip,rate_categories='Only complete leagues with every team meeting the threshold; no fabricated penalty points',counts_and_AVG='All complete leagues'),league_fits=fits,league_count=len(groups),team_rows=len(records))
 return result,penalties

def eligibility_mapping(adp_path,players):
 index=collections.defaultdict(list)
 for p in players:
  for name in set([p['name']]+p.get('recorded_names',[])):index[(p['player_type'],normalized(name))].append(p)
 mapped=[];review=[];used={};adp=[]
 w=openpyxl.load_workbook(adp_path,read_only=True,data_only=True)
 try:
  for sheet in w:
   values=list(sheet.values)
   if not values or 'Player ID' not in values[0]:continue
   headings=list(values[0]);native_names=collections.defaultdict(set)
   for raw in values[1:]:
    r=dict(zip(headings,raw))
    if not r.get('Player'):continue
    ps=positions(str(r['Position(s)']));ts=['hitter','pitcher'] if 'P' in ps and len(ps)>1 else ['pitcher'] if ps=={'P'} else ['hitter']
    for t in ts:native_names[(t,normalized(display_name(r['Player'])))].add(str(r['Player ID']))
   for number,values_row in enumerate(values[1:],2):
    row=dict(zip(headings,values_row))
    if not row.get('Player'):continue
    name=display_name(row['Player']);pos=positions(str(row['Position(s)']));types=['hitter','pitcher'] if 'P' in pos and len(pos)>1 else ['pitcher'] if pos=={'P'} else ['hitter']
    for typ in types:
     candidates={p['player_id']:p for p in index[(typ,normalized(name))]};anchored=[p for p in candidates.values() if p.get('mlbam_ids')]
     same_team=[p for p in anchored if team(row['Team']) in {team(t) for t in p.get('teams',[])}]
     method='UNIQUE_ANCHORED_NORMALIZED_NAME_TEAM'
     if len(same_team)==1:chosen=same_team[0]
     elif len(anchored)==1 and (not row.get('Team') or team(row['Team'])=='FA' or not anchored[0].get('teams') or set(map(team,anchored[0].get('teams',[])))=={'FA'}):
      chosen=anchored[0];method='UNIQUE_ANCHORED_NORMALIZED_NAME_TEAM_UNAVAILABLE'
     elif len(anchored)==1 and len(native_names[(typ,normalized(name))])==1:
      chosen=anchored[0];method='UNIQUE_ANCHORED_NAME_OFFSEASON_TEAM_DISAGREEMENT'
     else:
      review.append(dict(nfbc_player_id=row['Player ID'],name=row['Player'],team=row['Team'],positions=row['Position(s)'],player_type=typ,reason='AMBIGUOUS_OR_TEAM_DISAGREEMENT' if candidates else 'NO_PROJECTION_IDENTITY',candidate_ids=list(candidates),source_row=number,ADP=float(row['ADP'])));continue
     key=(typ,chosen['player_id']);nfbc_id=str(row['Player ID'])
     if key in used and used[key]!=nfbc_id:
      raise ValueError('Two NFBC assets mapped to the same role/canonical ID')
     used[key]=nfbc_id
     selected_pos={'P'} if typ=='pitcher' else pos-{'P'}
     mapped.append(dict(player_id=chosen['player_id'],player_type=typ,name=chosen['name'],positions=';'.join(sorted(selected_pos)),eligibility_season=2026,eligibility_basis_season=2025,source='User supplied DCADP-pre2026.xlsx',nfbc_player_id=nfbc_id,source_player_name=row['Player'],source_team=row['Team'],match_method=method,warehouse_mlbam_ids=chosen['mlbam_ids'],ADP=float(row['ADP']),min_pick=row['Min Pick'],max_pick=row['Max Pick'],picks=row['# Picks']))
     adp.append(dict(player_id=chosen['player_id'],player_type=typ,nfbc_player_id=nfbc_id,ADP=float(row['ADP'])))
 finally:w.close()
 return mapped,review,adp

def prepare(args):
 inputs=[Path(args.adp).resolve(),Path(args.standings).resolve()];consensus=Path(args.consensus).resolve()
 for typ in ['hitter','pitcher']:inputs.append(consensus/f'{typ}_consensus.json')
 fingerprint={str(p):sha(p) for p in inputs};out=Path(args.output).resolve()
 if out.exists():raise ValueError('Prepared DC input folder must not exist')
 out.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix=out.name+'.staging-',dir=out.parent))
 try:
  records,groups=read_standings(inputs[1]);cal,penalties=dc_calibration(records,groups)
  players=sum([json.loads((consensus/f'{t}_consensus.json').read_text(encoding='utf-8')) for t in ['hitter','pitcher']],[])
  mapped,review,adp=eligibility_mapping(inputs[0],players)
  csv_out(stage/'nfbc15_dc_eligibility.csv',mapped);csv_out(stage/'nfbc15_dc_eligibility_review.csv',review);csv_out(stage/'nfbc15_dc_adp.csv',adp)
  csv_out(stage/'dc_historical_team_stats.csv',records);csv_out(stage/'dc_rate_penalty_exclusions.csv',penalties);csv_out(stage/'dc_annual_sgp_slopes.csv',[dict(season=y,**v) for y,v in cal['annual_slopes'].items()]);dump(stage/'nfbc15_dc_sgp_calibration.json',cal)
  for p,h in fingerprint.items():
   if sha(p)!=h:raise ValueError('Input changed during preparation')
  audit=dict(status='DC_INPUTS_PREPARED',input_sha256=fingerprint,inputs_unchanged=True,league_count=len(groups),team_rows=len(records),leagues_by_season={str(y):sum(k[0]==y for k in groups) for y in [2023,2024,2025]},mapped_eligibility_role_rows=len(mapped),mapped_unique_nfbc_assets=len({r['nfbc_player_id'] for r in mapped}),review_rows=len(review),annual_slopes=cal['annual_slopes'],combined_slopes=cal['slopes'],rate_penalty_leagues_excluded=len(penalties),notes=['Unique anchored identities may bridge offseason team differences only when the NFBC name/type also identifies one asset; those cases retain a separate match method.','Header summaries and overall ranks are not used in SGP fitting.','2025 AVG/ERA/WHIP reconstructed at full component precision.','Two-way Ohtani has role rows sharing one canonical asset; no double counting.','Name/team candidates lacking MLBAM anchors are not merged into the warehouse.'])
  backup_root=Path(args.backup_root).resolve()
  if backup_root==out or out in backup_root.parents:raise ValueError('Backup must be outside output')
  backup_root.mkdir(parents=True,exist_ok=True);backup=backup_root/(out.name+'_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f'))
  audit['backup']=str(backup);dump(stage/'dc_input_audit.json',audit)
  shutil.copytree(stage,backup)
  for path in stage.rglob('*'):
   if path.is_file() and sha(path)!=sha(backup/path.relative_to(stage)):raise ValueError('DC input backup mismatch')
  stage.rename(out);return audit
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--adp',required=True);p.add_argument('--standings',required=True);p.add_argument('--consensus',default='outputs/nfbc15_valuation_inputs_v1_0/consensus');p.add_argument('--output',default='data/valuation_inputs_dc_v1_1');p.add_argument('--backup-root',default='backups');a=p.parse_args();print(json.dumps(prepare(a),indent=2))
if __name__=='__main__':main()
