# Draft Champions roster-balance simulator 1.0

This is a reproducible preseason simulation experiment for 15-team, 50-round, 5x5 Draft Champions. March 24, 2026 is the user-confirmed effective date for projections and ADP. Exact historical export timestamps and the underlying ADP draft interval remain undocumented. No 2026 outcomes or Statcast target-season data are used.

## Install and run

Extract into D:\JonAPythonClass\pycharm\PlayerValuation. Existing valuation/configuration/input files are not overwritten. Install the simulation dependencies in your active virtual environment:

python -m pip install -r requirements_simulator_v1_0.txt
python -m unittest discover -s tests -p "test_dc_roster_simulator_v1_0.py" -v
python dc_roster_simulator_v1_0.py --repetitions 5

This runs 150 synthetic drafts: 15 seats x 5 seeds x 2 strategies. For a quick two-draft check:

python dc_roster_simulator_v1_0.py --repetitions 1 --seats 1 --output outputs/dc_simulator_quickcheck

Each output path must be new. All outputs are copied to a complete verified backup in backups/. No source inputs are edited. Keep the script, tests, requirements and README in Git. Generated outputs and backups remain ignored under the established .gitignore.

Default inputs:
- outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix/player_values_with_adp.csv
- outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix/unvalued_adp_watchlist.csv
- data/valuation_inputs_dc_v1_1/nfbc15_dc_eligibility.csv
- data/valuation_inputs_dc_v1_1/nfbc15_dc_eligibility_review.csv
- data/valuation_inputs_dc_v1_1/dc_historical_team_stats.csv

The pilot supplied here was run with equivalent corrected local inputs: the reviewed ranking export, the 17 unresolved assets after removing the three resolved mappings, explicit reviewed links for those three, and eligibility from the original NFBC review. Exact hashes are recorded, so local eligibility serialization may differ from your files without changing the assets. The simulator reads the SQLite/DuckDB warehouse neither directly nor indirectly.

## Draft rules and evaluation

Snake order reverses every round. Each asset can be drafted once across the league. Every team drafts 50 players. Opponents use ADP plus per-team/per-asset normal noise of 12 picks and a modest preference for filling active eligibility. Late picks prioritize a feasible known-projection active lineup when possible. Target strategies share the same opponent shocks for each seed, so paired comparisons isolate strategy changes within this synthetic market; subsequent opponent picks naturally react to availability.

The value strategy chooses highest SGP above replacement, with mandatory late active-slot coverage. The category strategy examines a top-16 value shortlist plus market coverage candidates. It uses concave counting-category progress toward equal-season historical 80th-percentile benchmarks, exposure-scaled ratio percentile changes, 0.15 x baseline value and a 2-point active coverage bonus. These are fixed heuristic controls, not optimized coefficients. Both strategies enforce late coverage. Category percentiles are not predicted league standings points.

Both strategies receive the same final evaluator: maximum raw-SGP legal active assignment (14 hitters, 9 pitchers), with a large coverage priority and explicit empty slots. Each player occupies at most one slot. Active totals use H/AB, 9 ER/IP, and (H allowed + BB)/IP. Negative category contributions are retained. Reserves are not added to active totals.

Market-only players remain eligible for opponent draft selection. They have no utility or invented stats, and are not selected into projected active lineups. Their eligible reserve coverage is distinguished from projected reserve coverage. The target strategies conservatively prefer known production rather than pretending that a prospect's option value is zero. This is a limitation, not a valuation conclusion. The one known role for a two-way player is preserved; weekly hitter/pitcher switching is not valued.

## Historical comparisons

Historical percentile distributions use 2023, 2024 and 2025, weighted equally by season. A target-season historical row is rejected. Ratio reference distributions exclude individual teams with less than 950 IP. Benchmarks do not reconstruct official penalty standings. Projected IP below 950 is explicitly flagged.

Static projected active-season totals are compared with realized historical DC teams whose results include weekly lineup choices. This is a benchmark diagnostic, not an unbiased season forecast. It excludes reserve deployment, injuries, call-ups, opponent schedules, platoons and weekly optimization. It cannot yet establish real competitive advantage or chance of winning. Incomplete lineups remain visibly flagged and percentile results for them are not valid complete-roster comparisons.

## Outputs

- strategy_summary.csv: aggregate comparisons across the simulated seats/seeds.
- paired_comparison.csv: category strategy minus value strategy for matched seeds/seats. Complete-lineup flags identify usable pairs.
- team_results.csv: each active roster's totals, historical category percentiles, weakest category, 80th-percentile count and IP flag.
- active_assignments.csv: all 23 slots for each target roster.
- draft_log.csv: all 750 picks for every draft. Each target roster is found where team equals seat.
- reserve_coverage.csv: eligibility coverage by reserve position. Multi-position players overlap, so counts are not additive.
- single_absence_stress.csv: remove each active player and reassign the remaining 49. Reports legality and raw-SGP opportunity loss. This is one simultaneous absence, not a simulated injury season or probability.
- simulation_audit.json: input hashes, effective date, legality controls, assumptions, limitations and complete backup location.

config/dc_simulation_assumptions_v1_0.json documents fixed constants; it is not read as a runtime tuning interface. Seeds, repetitions, seats and input/output paths are command-line controls.

## What comes next

Inspect weak categories and reserve position holes across seats, then calibrate an availability model with actual draft-level pick distributions if available. Add weekly lineups and explicit playing-time/absence scenarios before interpreting deep reserves or multi-position flexibility as realized production. Keep the simple value baseline frozen for comparisons. Do not tune to 2026 outcomes.
