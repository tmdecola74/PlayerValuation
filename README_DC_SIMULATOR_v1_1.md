# Draft Champions constrained roster simulator 1.1

Extract into D:\JonAPythonClass\pycharm\PlayerValuation. This adds dc_roster_simulator_v1_1.py and new tests. It does not replace v1.0, the warehouse, valuations, eligibility inputs or previous outputs.

## Run the same paired seeds

Use the existing simulation dependencies (NumPy and SciPy). If needed:

python -m pip install -r requirements_simulator_v1_1.txt
python -m unittest discover -s tests -p "test_dc_roster_simulator_v1_1.py" -v
python dc_roster_simulator_v1_1.py --repetitions 5 --workers 2

Default seeds are 20260324 through 20260328, all 15 draft positions, both value and category strategies: 150 drafts, 75 strategy pairs. The frozen comparison reads outputs/dc_roster_simulator_v1_0/team_results.csv and hashes dc_roster_simulator_v1_0.py without editing either. The baseline file must contain matching seed/seat/strategy keys. --workers 1 runs sequentially. Workers use separate processes, and output ordering is fixed.

Default v1.1 output: outputs/dc_roster_simulator_v1_1. Choose a new --output if it already exists. Complete verified output backups are written under backups/.

## Independent hard constraints

1. Active IP must be at least 950, independently of category utility. Final hitting assignment maximizes raw SGP with legal eligibility. Pitching selection maximizes raw SGP among exactly nine pitchers subject to >=950 projected IP. A certified mixed-integer solution is required when unconstrained selection fails the innings floor. Infeasibility is reported, never repaired by adding bench innings or inventing production.

2. The known-projection roster must restore a legal 23-player active lineup after any single active-player absence. Multi-position reassignment is allowed and each asset has capacity one. An exact matching stress test verifies every active player's removal. Eligibility is required after absence; the 950 IP guarantee applies to the normal active lineup, not every absence scenario. No missing projections are treated as known production.

Starting at round 24, a completion solver evaluates currently owned and currently available known-projection assets. Hall matching constraints require enough eligible neighbors to fill every slot subset after one removal; a separate binary witness selects nine pitchers >=950 IP. The objective minimizes additional picks, then favors earlier ADP within minimum-pick completions. When additional picks are necessary, a completion candidate MUST be drafted before either category or value preferences can take precedence. These are actual picks in chronological draft order, not post-draft substitutions, trades or access to players already drafted by opponents. Market-only assets stay visible in opponent drafts and inventory.

This is a conservative completion guard, not a next-pick survival probability model. It may reach for a coverage player early and does not guarantee that opponents leave a future completion intact. If no available completion remains or it needs more than the remaining picks, an explicit guard event records the failure and the final gates disqualify that roster. Solver timeouts raise an error rather than claiming a certified solution. The 150 matched runs are an engineering test of these constraints, not a guarantee for all random seeds.

Opponents retain v1.0 behavior: ADP plus fixed per-team/per-asset random shocks and basic active-slot awareness. Only target-team drafting/evaluation gets the new constraints. No category weights or coefficients were tuned using the new results. All projections and ADP use March 24, 2026 as the user-confirmed effective date; retrospective archive provenance limitations remain documented.

## Reports

- strategy_summary.csv: feasibility and descriptive category summaries for each strategy.
- comparison_to_frozen_v1_0.csv: matched seed/seat/strategy changes in IP, percentiles and final gates.
- team_results.csv: active totals, category percentiles, single-absence gate, all-constraints gate, mandatory feasibility picks and any completion failures.
- active_pitching.csv: ACTIVE-only IP, GS, W, K, saves, ERA and WHIP. No reserves included.
- reserve_production_inventory.csv: full-season projection inventory of the reserves, separately reporting PA, IP, W, K, saves and hitter counts. This is not incremental usable production; it is never added to active totals.
- reserve_players.csv: player-level reserve identities, eligibility, projection availability, PA/IP and saves.
- single_absence_stress.csv: each active-player removal and legal reassignment result. Opportunity-loss values are relative to the normal IP-constrained lineup and an eligibility-only replacement lineup. These are not injury-season forecasts; a relaxed replacement could even have higher raw SGP while missing the normal innings gate.
- reserve_coverage.csv: eligible depth by position, with overlapping multi-position eligibility explicitly not additive.
- active_assignments.csv, draft_log.csv: trace each roster and actual pick. feasibility_pick identifies mandatory completion picks.
- simulation_audit.json: frozen baseline hashes, unchanged inputs, results and full backup.

No weekly pitcher usage, injury probabilities, simultaneous absences or call-up timelines are modeled. Saves are projected totals, not guarantees of a closer role. Positive saves or GS counts do not create a formal SP/RP classification. Historic benchmarks use actual 2023-2025 DC team results, equally weighted by season; they are diagnostic comparisons with static projected lineups, not predicted winning probabilities or an outcomes backtest.

## Files and backups

The supplied validation outputs are under outputs/dc_roster_simulator_v1_1_validation. They used equivalent reviewed local inputs: the 961-player ranking export, 17 unresolved watchlist assets, three confirmed identity mappings and original NFBC eligibility. Local serialized eligibility/watchlist hashes differ from your files, but the assets and roles are equivalent. The comparison baseline is your uploaded five-seed v1.0 team_results.csv. Your local rerun uses your own inputs and frozen v1.0 output directly.

Keep the new script, tests, README and requirements in Git. Keep generated outputs, downloaded data and backups outside Git under the existing .gitignore.
