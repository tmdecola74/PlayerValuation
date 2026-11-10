# Pitcher workload diagnosis and simple SB baselines v1.10

This release preserves v1.9 and all earlier evidence. It pauses pitcher multiplier tuning and changes no accepted pitcher forecast. It tests one predeclared, exposure-aware multiyear SB baseline against the accepted forecast and a last-season-rate comparator. It does not fit another complex SB model. All saves, holds and hitter components other than experimental SB remain fixed.

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, retaining all earlier releases, configurations and tests. Only new v1.10 filenames are included. Existing NumPy/DuckDB dependencies suffice. The package contains code and synthetic validation, not production results.

Run from the project root:

```powershell
python -m unittest discover -s tests -p "test_standalone_history_baselines_v1_10.py" -v
python backtest_standalone_history_baselines_v1_10.py
python evaluate_standalone_history_baselines_v1_10.py
```

The build freezes the population priors, historical choices and 2026 forecasts before opening any 2026 outcomes. The evaluator first reproduces the frozen forecasts and choices, then reads previously reviewed 2026 outcomes. Commercial projections remain benchmark inputs only. For internal evaluation without the commercial warehouse, use this instead of the third command:

```powershell
python evaluate_standalone_history_baselines_v1_10.py --skip-benchmarks
```

Outputs:

- `outputs/standalone_history_baselines_v1_10`
- `outputs/standalone_history_baselines_evaluation_v1_10`

Each output gets a complete hash-verified backup under `backups/`. Existing folders are never overwritten; use a new `--output` for a rerun. Input hashes are checked again before publication, and interrupted staging folders/incomplete backups are cleaned up.

## Inputs

| Flag | Default |
| --- | --- |
| --run19 | outputs/standalone_joint_workload_v1_9 |
| --run18 | outputs/standalone_refinements_v1_8 |
| --run16 | outputs/standalone_growth_sb_v1_6 |
| --diagnostics | outputs/standalone_magnitude_diagnostics_v1_7 |
| --run15 | outputs/standalone_holds_attribution_v1_5 |
| --run14 | outputs/standalone_combined_v1_4 |
| --source | outputs/standalone_workload_experiments_v1_3 |
| --matrix | outputs/standalone_lagged_features_v1_0 |
| --baseline | outputs/standalone_role_workload_v1_2 |
| --labels | outputs/training_labels_v1_0 |

Use build folders, not evaluation copies, and the original historical-only v1.7 audit. Override flags if your frozen folders have different names. The build configuration is `config/standalone_history_baselines_v1_10.json`. The evaluator uses `--run outputs/standalone_history_baselines_v1_10` and defaults to `--warehouse data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` for available benchmark comparisons.

## Pitcher diagnosis: no fitting or new forecasts

The audit compares frozen accepted v1.5, research v1.6/v1.8/v1.9 and selected v1.9 workload counts with eligible actual OUTS. Errors are expressed in decimal IP. Original source branch counts and growth probability remain visible in player-level records.

Fixed prior-only descriptive groups include:

- Normalized prior workload band and prior role.
- Lag-2 to lag-1 role transition from recorded G/GS.
- Prior workload reduction: lag-2 normalized OUTS >=120 and lag-1 <=50% of lag-2.
- Rebound already underway: lag-3 normalized OUTS >=120, lag-2 <=50% of lag-3, and lag-1 > lag-2.
- Known zero lag-1 OUTS versus missing lag-1 workload.
- Gaps between recorded workload histories, and presence/absence across three lags.

These flags are not confirmed injuries, medical recovery labels or proof of a missed season. Missing reference rows and disputed counts remain unknown. A true zero OUTS value can represent an appearance without a recorded out; it is not converted to absence.

Raw prior OUTS and diagnostic normalized OUTS are both retained. The existing 2.7 multiplier is applied to 2020 prior workloads solely for consistent diagnostic group definitions; it is not refitted. These thresholds are fixed research definitions, not optimized against losses.

Retrospective groups additionally show prior-to-actual role transitions and return patterns. Following a prior reduction or recorded-history gap, a return toward older workload means current actual OUTS >=80% of the largest known normalized lag-2/lag-3 workload, provided that reference is >=120 OUTS. Missing actuals/references stay unknown. These observed groups are never predictors or SB selection inputs.

The branch-coverage table reports how often actual OUTS exceeds the original v1.6 growth branch or falls below its decline branch, and the error of the branch consistent with the observed direction. This is an oracle diagnostic, not a usable forecast. Its eligible pool can be smaller than the workload comparison pool; membership hashes and row counts are separate.

All methods share an identical eligible pool within each workload-summary cohort. Overlapping cohorts are not additive. Missing rows remain visible in coverage. Top-25 accepted/research-v1.9 squared-error misses per year retain exact MLBAM identities, prior histories, branches and retrospective outcomes. No names are guessed.

## SB baseline: fixed recipe, historical prior only

Define proxy opportunities as `H-HR+BB+HBP`. This is not measured stealable-base opportunity or an attempts/success model.

For each origin, estimate a population rate from earlier eligible frozen FanGraphs actuals:

`population_rate = sum(SB) / sum(proxy)`

At least 50 eligible player-season rows with positive proxy are required. Disputed/missing components are not backfilled. Actual target-2020 rows are excluded under the existing development policy. Earlier eligible 2015 labels may contribute to the 2019 prior even though the lagged model matrix starts in 2016; they were already historical information at that origin. No future label enters a prior.

For each player, use usable prior lags with fixed weights 3, 2, 1:

`multiyear_rate = (sum(weight*SB) + 100*population_rate) / (sum(weight*proxy) + 100)`

Missing numerator or any missing proxy component excludes that lag. A known zero SB with positive proxy is a valid zero-rate observation. Zero proxy is not a known zero rate. Short-season 2020 lag observations use their raw observed counts for reliability: ratio information is retained, but their sample size is not inflated by 2.7.

Multiply this rate by the **accepted v1.5 projected proxy**. Accepted PA, H, HR, BB, HBP and all other hitter components are unchanged. Rates are capped at 3 and counts at 120, retaining earlier fixed controls. There is no parameter search.

With no usable prior history, the candidate uses the earlier population rate; `population_only` identifies these research forecasts. This is not a claim of adequate prospect/minor-league coverage. Missing projected proxy or an unsupported population prior retains accepted SB.

The comparator uses raw lag-1 `SB/proxy`, with the same rate/count caps. When that rate or projected proxy is undefined, it retains accepted SB. `last_supported` distinguishes a genuine last-season rate from this explicit fallback. It does not fabricate missing histories as zeros.

## Chronological comparison and adoption

The reports compare four methods: `frozen_v1_5`, `last_season_rate`, `multiyear_candidate`, `selected_SB_experiment`.

Choices require historical evidence against **both** accepted and last-season comparators. Each comparison uses the same predeclared gates: at least two adequate earlier validation folds, 30 overall/20 guard rows, >=80% supported candidate forecasts, >=1% overall MSE improvement, no MSE degradation in guard cohorts, and <=1% MAE degradation. Fold losses receive equal weight. All required gates must pass; inadequate evidence rejects adoption.

Guards cover established runners (raw lag-1 SB >=10), prior zero-SB hitters, and low-history hitters (raw lag-1 PA missing or <100). Cohorts may overlap. Unlike the earlier rate-change audit, count-error evaluation does not require a known actual proxy or prior proxy when eligible actual SB and the compared forecasts exist. This allows population-only/low-history research forecasts to be evaluated without inventing prior rates. Coverage and fallback counts remain explicit.

Target 2020 stays visible as stress and is excluded from fitting/selection. 2021 is retained for reporting, later priors and later selection subject to the same sample gates. Each origin selects before adding its own outcomes. Frozen 2026 choices use historical folds only. 2026 was previously reviewed and remains disclosed evaluation, not an untouched holdout or a tuning dataset.

## Reports and follow-up

Build folder:

| File | Purpose |
| --- | --- |
| history_baselines_build_report.json | Scope, final historical choice, population prior and preservation |
| historical_gate_evidence.json | Separate accepted/last-season historical gate losses |
| rolling_choices.json | Chronological decisions before each origin's outcomes |
| SB_population_priors.csv / origin_population_priors.json | Per-origin population sufficient statistics and fit years |
| SB_population_fit_members.csv | Exact earlier eligible population-prior members |
| SB_comparison.csv | Annual identical-pool losses, low-history and population-only counts |
| experiment_predictions.csv | Candidate/comparator counts, rates, weighted exposures and fallback flags |
| pitcher_history_summary.csv | Workload errors by prior/retrospective history groups |
| pitcher_history_coverage.csv | Paired and missing workload rows |
| pitcher_branch_coverage.csv | Original growth/decline range and observed-branch diagnostics |
| pitcher_history_players.csv | Complete raw/normalized history, role and loss trace |
| pitcher_history_largest_misses.csv | Largest annual misses and squared-error concentration |
| category_scores.csv / category_coverage.csv | Coherent category effects and identical-pool coverage |
| preservation_audit.csv | Unchanged pitcher forecasts/saves/holds and hitter non-SB components |

The evaluation folder contains `history_baselines_evaluation_report.json` plus comparison, category and pitcher-diagnostic tables through disclosed 2026. Optional commercial comparisons are separately paired; do not compare RMSEs across different comparison groups or cohorts.

Send the two JSON reports, build `historical_gate_evidence.json`, `SB_population_priors.csv`, `pitcher_history_summary.csv`, `pitcher_branch_coverage.csv`, `pitcher_history_coverage.csv`, and evaluation `SB_comparison.csv` and `category_scores.csv`. Keep player-level detail and largest misses available for targeted follow-up.

Prior releases and original references remain unchanged. Sources are retrospective and not independently archived preseason vintages. Synthetic tests validate code behavior; only your local historical results can establish whether the simple SB candidate merits adoption. No new pitcher model is proposed by this release.
