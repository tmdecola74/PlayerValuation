# Explicit draft-source integration v1.15

Install these new files into the outer PlayerValuation project, preserving all earlier releases. Requires the installed v1.14 draft-source release, earlier standalone dependencies, `build_league_valuations_v1_0.py`, `valuation_math_v1_0.py`, and unchanged `dc_roster_simulator_v1_3.py`. No old code/config/output is overwritten by this package. Requirements: existing DuckDB/NumPy dependencies and SciPy with `milp` (SciPy >=1.11).

## Run valuations and prepare coverage intake

```powershell
python -m unittest discover -s tests -p "test_draft_integration_v1_15.py" -v
python draft_integration_v1_15.py --sources homegrown reconciled_consensus
```

Output: `outputs/draft_source_integration_v1_15`. Each source has its own `player_values.csv` (native nested engine fields), `player_values_flat.csv`, `valuation_context.json`, `coverage_report.json`, `source_exclusions.csv`, `valuation_exclusions.csv`, `simulation_exclusions.csv`, and `simulation_pool.json`.

Top-level `source_integration_report.json` gives counts by source. Separate denominators: source records eligible for category valuation, valuation-ranked players with platform eligibility, and the NFBC market simulation pool. Eligible nonmarket players can enter valuation replacement calculations, but cannot enter an ADP-driven draft simulation without a valid market asset/price. No absent ADP is fabricated. Missing or unsupported projected components remain unknown. Market-only assets remain in the opponent market pool with no production. No source fallback or blending occurs.

Valuations use the existing standard 5x5 SGP engine, ratio components, exact positional assignment/replacement, exposure floors, calibrated historical rate references, reserve ranking, and budget allocation. An insufficient pool/replacement path is a reported source failure, not a switch to consensus. Arithmetic/other errors stop publication. This release does **not** implement Yahoo 6x6 valuation or simulation; the earlier Yahoo projection adapter remains available separately. Yahoo requires its own eligibility, roster and historical calibration; do not relabel NFBC values as Yahoo values.

The default market file is `outputs/preseason_coverage_v1_13/draft_asset_coverage.csv`. Its exact hash must occur in v1.14's bound inputs, and its complete NFBC asset/canonical identity domain must match the frozen universe. Reviewed aliases therefore cannot silently revert. Eligibility defaults to the reviewed NFBC input, with target season 2026/prior-season basis 2025 validation. No name joins or inferred position gains occur.

## Pitcher role dependency

Accepted projection exports do not contain GS. For reconciled consensus, the adapter reads GS **only from its preserved original consensus record**, when available. It never supplies those GS to homegrown. Homegrown requires a separate source-specific frozen projected-GS input before a complete paired simulation. This is a role-context dependency, not permission to change homegrown PA/IP/skill/saves/holds.

`homegrown/roles_needed.csv` and `reconciled_consensus/roles_needed.csv` enumerate missing role inputs. Copy verified values into the exact seven-column `source_specific_roles_TEMPLATE.csv`; remove the extra descriptive `name` column if using a roles-needed list as a starting point. Do not enter zero for unknown GS. Required fields:

`projection_source_choice,player_id,GS,as_of_date,source,evidence_reference,vintage_basis`

Source choices are `homegrown` and `reconciled_consensus`. GS must be finite in [0,162]. As-of dates must be <=2026-03-24. Use ISO dates and one of `ARCHIVED_AS_OF_CLAIM`, `USER_CONFIRMED_PRESEASON_EFFECTIVE`, `RETROSPECTIVE_EVENT_TIME_ONLY`. These are disclosed provenance claims, not independently certified archived timestamps. No 2026 actual GS/IP or realized team role may be used. A rejected research role model must not be relabeled accepted. If suitable frozen homegrown GS does not exist, retain the simulation block; a separately versioned historical role adapter must be developed before using that source for role-constrained recommendations.

Rerun to a NEW output, for example:

```powershell
python draft_integration_v1_15.py --sources homegrown reconciled_consensus --roles "config/draft_source_roles_v1_15.csv" --output "outputs/draft_source_integration_v1_15_roles"
```

`role_inputs_used.csv` records actual supplied/derived role context. A supplied source-specific record takes precedence over original consensus GS; its origin is explicit and never copied between sources.

## Paired simulations

```powershell
python simulate_draft_sources_v1_15.py --sources homegrown reconciled_consensus --repetitions 1 --seats 8
```

Use `--integration "outputs/draft_source_integration_v1_15_roles"` after adding verified role context. A first run can record `BLOCKED_INPUTS` without drafting. The report states missing role counts, pool size, and whether the valuation profile matches DC15. Both complete source role coverage and >=750 priced market assets are required. Valuations remain usable independently of simulation readiness.

Output: `outputs/draft_source_simulation_v1_15`. Every source/seed/seat/strategy has its own draft log, team result, active assignments, single-absence checks, active pitching, reserve production inventory, reserve players, closer acquisitions and save-capable roster. Top-level: `source_simulation_report.json`, `source_status.csv`, `team_results_by_source.csv`, `paired_sources.csv`.

The wrapper calls the unchanged v1.3 algorithm; no new drafting policy or forecast component is fitted. Normal-lineup constraints remain 950 active IP; 7 SP/2 save-capable RP; two distinct 30+/20+ projected-save closers by round 23; 22–23 total pitchers and 27–28 hitters; >=6 save-capable pitchers (7 preferred); full-roster single-absence legality with reassignment. As inherited, the single-absence check requires legal role/position coverage, not a 950-IP/closer-tier guarantee after each loss. Known reserve full-season projections are reported as inventory, never added to active totals.

Defaults preserve seed 20260324; repetitions increment that seed by one. Both strategies and sources receive the same seed/seat schedule and common ADP/asset ordering, so their initial market random draws match. Later rosters can diverge. Explicit failures/blocking remain in reports; only all-constraint-passing results are marked recommendation-eligible. Paired-source differences are **projected** differences, not realized accuracy or evidence one projection source is better. These sources have different supported populations; an identical market pool is not an identical known-production pool. Inspect exclusions before interpreting comparisons. Broader testing: `--repetitions 5 --seats 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15` with a new output folder. Do not broaden until smoke results and gates are reviewed.

## Dated coverage-branch inputs

`coverage_branch/` contains:

- `preseason_collection_requests.csv`: the frozen 107-asset priority list (production count), preserving preseason ADP ordering, not 2026 outcomes.
- `historical_collection_plan.csv`: origins 2016–2026, with earlier-origin development and explicit 2021 retention.
- Empty `population_TEMPLATE.csv`, `history_TEMPLATE.csv`, `context_TEMPLATE.csv`, `cutoffs_TEMPLATE.csv` with exact v1.14 schemas.
- `contract.json`, `fold_plan.csv`, `intake_report.json`, and supplied validated tables.

Populate origins using dated minor-league/overseas exports plus dated roster/availability evidence. Freeze the complete contemporaneous prospect/international/returner population before looking at later MLB participation; do not collect only players who subsequently reached MLB. Use verified MLBAM identities, source record IDs, evidence references, retrieval timestamp with timezone, and explicit vintage basis. Prior counts must be nonnegative integers; pitching exposure is integer OUTS, never decimal baseball innings. Level/competition belongs in `competition`; separate league/park translation has not been fitted. Blank values stay unknown. Branch class must be documented; the program does not guess prospect versus international from names.

Historical cutoffs remain conservative Jan 1, with documented overrides allowed only through Feb 28 under the v1.14 contract. 2026 cutoff is March 24 user-confirmed. History must predate target origin and as-of cutoff; roster/availability must also meet the cutoff. Current rosters cannot be backdated as historical evidence. Retrospective data and independently archived snapshots must stay distinguishable. See generated contract for metric/signal allowlists.

```powershell
python draft_integration_v1_15.py --sources homegrown reconciled_consensus --branch-population "config/entry_population.csv" --branch-history "config/entry_history.csv" --branch-context "config/entry_context.csv" --output "outputs/draft_source_integration_v1_15_dated"
```

No historical minor/overseas exports or dated roster archives were supplied for this build. Therefore templates and collection requests are prepared, **not populated with invented evidence**. The branch remains not fitted/not fit-ready, even after schema validation. Future work must join frozen eligible historical MLB labels only after populations/features freeze; establish complete appearance coverage for nonparticipation targets; develop historical translations/sample controls and role/availability candidates on earlier folds. Missing actual-export rows are not zero. Preserve 2020 and 2021; 2026 is already-reviewed evaluation only. No labels/evaluation tables are opened by either new command.

All output folders must be new. Publication verifies watched hashes, creates a complete matching backup under `backups/`, and cleans unpublished staging on errors/interruptions. Original projection/warehouse/reference files and earlier releases remain untouched.
