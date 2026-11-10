"""Paired-source adapter to the unchanged v1.3 Draft Champions draft algorithm."""
import argparse,json,shutil
from pathlib import Path
from standalone_io_v1_0 import load,dump,verify,sha,start,finish
from draft_integration_v1_15 import SOURCES,emit
import dc_roster_simulator_v1_3 as sim

def build(a):
 if not a.sources or len(set(a.sources))!=len(a.sources) or set(a.sources)-set(SOURCES):raise ValueError('Explicit unique sources required')
 if a.repetitions<1 or not a.seats or len(set(a.seats))!=len(a.seats) or any(x<1 or x>15 for x in a.seats):raise ValueError('Invalid repetitions/seats')
 root=Path(a.integration).resolve();watched=verify(root);report=load(root/'source_integration_report.json')
 if report['version']!='1.15.0' or report['source_fallback']:raise ValueError('Wrong integration release')
 watched[str(Path(a.historical).resolve())]=sha(a.historical);watched[str(Path(sim.__file__).resolve())]=sha(sim.__file__)
 hist=sim.History(a.historical);out,backups,stage=start(a.output,a.backup_root,watched);results=[];statuses=[]
 try:
  for source in a.sources:
   d=stage/source;d.mkdir();coverage=load(root/source/'coverage_report.json');players=load(root/source/'simulation_pool.json')
   for p in players:p['slots']=set(p['slots'])
   role_missing=coverage['missing_role_rows']
   profile=load(root/source/'valuation_context.json')['profile'];expected={x:sim.SLOTS.count(x) for x in set(sim.SLOTS)};format_ok=profile['teams']==15 and profile['active_slots']==expected and profile['bench_per_team']==27
   if not format_ok or coverage['status']!='VALUED' or role_missing or len(players)<750:
    statuses.append(dict(source=source,status='BLOCKED_INPUTS',missing_role_rows=role_missing,draft_pool=len(players),format_matches_DC15=format_ok,reason='Require NFBC DC15/50-round profile, successful valuations, >=750 market assets, and source-specific GS for all otherwise supported pitchers'));continue
   for rep in range(a.repetitions):
    for seat in a.seats:
     for strategy in ['value','category']:
      seed=a.seed+rep;print(f'{source}: seed {seed}, seat {seat}, {strategy}',flush=True)
      # Solver failure is a research failure; never silently switch source or report success.
      try:s,logs,cover,assign=sim.draft(players,hist,seed,seat-1,strategy)
      except ValueError as e:
       statuses.append(dict(source=source,status='SIMULATION_FAILED',seed=seed,seat=seat,strategy=strategy,reason=str(e)));continue
      s.update(projection_source_choice=source,recommendation_eligible=bool(s['all_constraints_pass']));results.append(s)
      job=d/f'{seed}_{seat}_{strategy}';job.mkdir();emit(job/'team_results.csv',[s]);emit(job/'draft_log.csv',logs);emit(job/'reserve_coverage.csv',cover);emit(job/'active_assignments.csv',assign)
      pitching,reserves,inventory=sim.production_reports(players,logs)
      for name,rows in [('active_pitching',pitching),('reserve_production_inventory',reserves),('reserve_players',inventory),('single_absence_stress',sim.reserve_stress(players,logs)),('save_capable_roster',sim.save_depth_roster(players,logs)),('closer_acquisitions',sim.closer_acquisitions(players,logs))]:emit(job/(name+'.csv'),rows)
   completed=sum(r['projection_source_choice']==source for r in results)
   statuses.append(dict(source=source,status='SIMULATIONS_COMPLETED' if completed==a.repetitions*len(a.seats)*2 else 'COMPLETED_WITH_RESEARCH_FAILURES',results=completed))
  emit(stage/'team_results_by_source.csv',results);emit(stage/'source_status.csv',statuses)
  pairs=[];ix={(r['projection_source_choice'],r['seed'],r['seat'],r['strategy']):r for r in results}
  for key,r in ix.items():
   if key[0]!='homegrown':continue
   other=ix.get(('reconciled_consensus',)+key[1:])
   if other:pairs.append(dict(seed=key[1],seat=key[2],strategy=key[3],both_pass=bool(r['all_constraints_pass'] and other['all_constraints_pass']),interpretation='Different projection-source forecasts of synthetic drafted teams; not realized outcomes or evidence of superiority',**{c+'_consensus_minus_homegrown':other[c]-r[c] if other[c] is not None and r[c] is not None else None for c in sim.CATS}))
  emit(stage/'paired_sources.csv',pairs)
  audit=dict(version='1.15.0',sources=a.sources,seed=a.seed,repetitions=a.repetitions,seats=a.seats,paired_source_rows=len(pairs),statuses=statuses,simulations=len(results),all_constraints_pass=sum(r['all_constraints_pass'] for r in results),models_fitted=False,evaluation_outcomes_read=False,historical_target_seasons=hist.seasons,limitations=['Unchanged v1.3 NFBC 15-team/50-round policies; not a Yahoo simulator.','Same seed/seat/strategy and common market ordering, but later choices and rosters can diverge by source.','No automatic fallback; blocked sources and failed drafts remain explicit.','Static projected production and illustrative market noise; no weekly injury/lineup model.','Source-specific projected GS is role context; it does not alter accepted projection statistics.','2026 previously reviewed evaluation data is not read or used for selection.'])
  dump(stage/'source_simulation_report.json',audit);backup=finish(out,backups,stage,watched);return dict(audit,output=str(out),backup=backup)
 except BaseException:shutil.rmtree(stage,ignore_errors=True);raise

def parser():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sources',nargs='+',choices=SOURCES,required=True);p.add_argument('--integration',default='outputs/draft_source_integration_v1_15');p.add_argument('--historical',default='data/valuation_inputs_dc_v1_1/dc_historical_team_stats.csv');p.add_argument('--repetitions',type=int,default=1);p.add_argument('--seats',type=int,nargs='+',default=[8]);p.add_argument('--seed',type=int,default=20260324);p.add_argument('--output',default='outputs/draft_source_simulation_v1_15');p.add_argument('--backup-root',default='backups');return p
if __name__=='__main__':print(json.dumps(build(parser().parse_args()),indent=2))
