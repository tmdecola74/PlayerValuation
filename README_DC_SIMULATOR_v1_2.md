# Draft Champions simulator 1.2: requested roster composition

This adds a separate dc_roster_simulator_v1_2.py. V1.0 and v1.1 remain unchanged, as do projections and valuations. The effective date remains March 24, 2026.

## Run

Extract into D:\JonAPythonClass\pycharm\PlayerValuation and use the existing NumPy/SciPy environment:

python -m unittest discover -s tests -p "test_dc_roster_simulator_v1_2.py" -v
python dc_roster_simulator_v1_2.py --repetitions 5 --workers 2

Default output: outputs/dc_roster_simulator_v1_2. It must not exist. The baseline comparison reads outputs/dc_roster_simulator_v1_1/team_results.csv and hashes dc_roster_simulator_v1_1.py without editing either. All 150 original matched seed/seat/strategy keys are reused (seeds 20260324-20260328, every seat, both strategies).

## Constraints

Each target team's 50-player roster must have either 22 pitchers/28 hitters or 23 pitchers/27 hitters. Draft picks exceeding 23 pitchers or 28 hitters are filtered out before utility is scored. Since the completed roster contains exactly 50 assets, these caps also enforce the respective minimums. The feasibility-completion solver includes the same type caps, preventing a required coverage/innings pick from silently violating composition. Type classification comes from the published projection/eligibility asset role; two-way assets retain their established single role.

The prior independent constraints remain: normal active lineup exactly 14 hitters and 9 pitchers, at least 950 projected active IP, and legal reassignment after any single active-player absence. The 950-IP requirement is not separately required for every absence scenario. Opponents retain the frozen market behavior so target roster changes can be compared on the same random shocks. All target-team roster counts and gate results are reported explicitly.

## Saves interpretation

Roster composition is a hard constraint. It is NOT a saves target, SP/RP quota, or closer count. Adding reserve hitters or changing total pitcher count cannot ensure that nine active pitchers reach the historical 80th-percentile saves benchmark. That benchmark is approximately 70.33 saves using the existing equal-year 2023-2025 historical calculation. Active saves, reserve saves inventory and all ten category percentiles remain separate. No reserves are added to active totals and no closer roles are fabricated.

The category-aware and value utility coefficients are unchanged. This delivery changes composition only; it does not tune those coefficients to produce a desired result. Weekly deployment is still unmodeled.

## Outputs

- team_results.csv adds total_pitchers, total_hitters, roster_composition_pass, and retains all constraint gates.
- strategy_summary.csv adds passes_composition, mean_total_pitchers and mean_total_hitters.
- comparison_to_frozen_v1_1.csv pairs the same seed/seat/strategy against v1.1.
- saves_target_audit.csv compares active saves to the historical 80th-percentile benchmark and shows reserve saves separately. It does not impose that benchmark as a constraint.
- active_pitching.csv separates active IP, starts, W, K, saves, ERA and WHIP.
- reserve_production_inventory.csv and reserve_players.csv report reserves separately as projection inventory, not usable incremental team production.
- Other inherited reports retain draft picks, active assignments, positional reserve coverage, single-absence checks and full audit/backup metadata.

Complete verified backups are written under backups/. Inputs are hashed and unchanged. Any infeasible completion or final gate failure remains explicit; failed rosters are not valid recommendations.

The supplied validation output under outputs/dc_roster_simulator_v1_2_validation was run using the same 961-valued/17-market-only assets and reviewed identities as before. Local serialized inputs may have different hashes. The local comparison table was reconstructed directly from the user's uploaded v1.1 comparison report's current-version IP and percentile columns, preserving each seed/seat/strategy, rather than inventing or rerunning the baseline. On your PC the default comparison reads your original v1.1 team_results.csv directly.

Commit the new script, tests, requirements and documentation. Existing .gitignore rules exclude generated outputs and backups. This is a synthetic experiment, not a backtest of actual 2026 performance or a probability of winning a league.

## Confirmed saves benchmarks

The historical workbook yields 80th-percentile saves of 74 (2023), 71 (2024), and 66 (2025). The user confirmed 2024/2025 and reported 67 for 2026. The 2026 preseason experiment keeps its decision-time target at the prior-season equal-year mean of 70.33. The 2026 figure is documented only as retrospective context, not a decision input. See SAVES_BENCHMARK_PROVENANCE.json. Nothing in the v1.2 roster-composition constraint forces a particular saves total.
