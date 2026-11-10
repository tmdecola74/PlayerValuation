# Joint pitcher workload experiment and SB feature audit v1.9

This release preserves v1.8 and all earlier releases as frozen research evidence. It tests one joint pitcher calibration against the accepted v1.5 forecast and compares it with the rejected v1.6/v1.8 candidates. It audits existing SB features without fitting another SB replacement, selecting features, or changing accepted SB forecasts. Saves and accepted holds remain exactly fixed.

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, alongside the prior scripts, configurations and tests. All package filenames are new v1.9 files. Existing NumPy and DuckDB dependencies are sufficient. The ZIP contains code and synthetic tests, not your full production matrices or production results.

Run from the project root, in order:

```powershell
python -m unittest discover -s tests -p "test_standalone_joint_workload_v1_9.py" -v
python backtest_standalone_joint_workload_v1_9.py
python evaluate_standalone_joint_workload_v1_9.py
```

The build uses historical outcomes only. It freezes the 2026 model, choices, forecasts and SB feature-bin thresholds before evaluation. The evaluator first reproduces every origin's forecasts and historical choices, then opens previously reviewed 2026 outcomes. Commercial projections are optional evaluation benchmarks only, never predictors. To evaluate without the commercial warehouse, use this instead of the final command:

```powershell
python evaluate_standalone_joint_workload_v1_9.py --skip-benchmarks
```

Build output: `outputs/standalone_joint_workload_v1_9`.
Evaluation output: `outputs/standalone_joint_workload_evaluation_v1_9`.

Every published folder gets a complete hash-verified backup under `backups/`; source hashes are checked before publication. Output folders must be new. For a rerun, supply a different `--output`; do not overwrite frozen releases. Interrupted staging folders and incomplete backups are cleaned up.

## Sources

| Flag | Default folder |
| --- | --- |
| --run18 | outputs/standalone_refinements_v1_8 |
| --run16 | outputs/standalone_growth_sb_v1_6 |
| --diagnostics | outputs/standalone_magnitude_diagnostics_v1_7 |
| --run15 | outputs/standalone_holds_attribution_v1_5 |
| --run14 | outputs/standalone_combined_v1_4 |
| --source | outputs/standalone_workload_experiments_v1_3 |
| --matrix | outputs/standalone_lagged_features_v1_0 |
| --baseline | outputs/standalone_role_workload_v1_2 |
| --labels | outputs/training_labels_v1_0 |

Use the historical-only v1.7 diagnostic folder and the frozen v1.8 build folder, not evaluation copies. Override flags if your local names differ. Build configuration is `config/standalone_joint_workload_v1_9.json`. The evaluator uses `--run outputs/standalone_joint_workload_v1_9` and defaults to `--warehouse data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` for available Steamer/OOPSY comparisons. All frozen manifests must remain intact.

## Joint objective

For a source anchor A, source conditional growth/decline forecasts G/D, frozen growth probability p and frozen participation t, the calibrated forecast is:

`growth = min(OUTS_cap, A + alpha*(G-A))`

`decline = max(0, A - beta*(A-D))`

`forecast = t * (p*growth + (1-p)*decline)`

Alpha and beta are fitted **together against final observed OUTS**, not against separate observed-direction magnitudes. Every eligible example contributes both branches with its own frozen p and t. Observed growth/decline is never used to choose a branch in this fit. Prior-role groups use only prior-season G/GS classifications, not target-season roles.

For each origin, only earlier v1.6 out-of-fold forecasts and eligible frozen actual OUTS/G are used. Actual G must be positive, and the source forecast/anchor/branches must be supported and consistent with the original cap. Missing actuals and nonreturners are not fabricated zeros. The accepted model's participation problem is not redesigned here.

Fit a pooled pair, then prior-role specialist pairs. At least 50 examples are required per fit. Sparse or nonconverged specialists use pooled parameters. A nonconverged/unsupported pooled fit or unsupported source prediction falls back to the accepted v1.5 count. No v1.8 candidate is silently promoted as a fallback.

The fixed multiplier bounds are [0,3]. A penalty pulls each multiplier toward 1, using 50 times its mean squared workload-feature contribution (with a floor of 1). The optimizer uses a bounded quadratic warm start only when it improves the exact capped objective, followed by exact one-coordinate piecewise minimizations. Deterministic coordinate descent has a 200-iteration limit and 1e-8 coefficient tolerance. It must descend and converge; the piecewise capped objective carries no global-optimum guarantee. Parameters include convergence status, iteration counts, fit years, and pre/post training losses. Training loss improvement alone is never an adoption criterion.

The forecast equation, direction probabilities, participation probabilities, original workload anchor and caps are identical at training-objective evaluation and prediction. The pitcher overlay changes other pitcher count components coherently with OUTS while restoring accepted saves and holds exactly. Hitter forecasts remain entirely unchanged.

## Historical selection

Each origin makes its decision before adding that origin's outcomes. The candidate must pass the unchanged overall/prior-starter/prior-reliever gates: two adequate prior validation folds, at least 30 overall or 20 guard rows per fold, 80% supported forecasts, 1% overall MSE improvement, no guard MSE deterioration, and no more than 1% MAE deterioration. Fold losses receive equal weight. Missing guard evidence rejects adoption.

Target 2020 remains an explicit stress season excluded from fitting and selection under the existing policy. Target 2021 is never removed and is eligible for later calibration and validation. The earliest OOF source year is 2019, so that origin lacks calibration evidence and retains the accepted baseline. 2021 can calibrate from 2019; no 2021 actual enters its own calibration. The dedicated 2021 table retains all source rows, including missing actuals/unsupported rows.

All 2026 forecasts and choices are frozen from historical information before evaluation. 2026 was previously reviewed and is disclosed evaluation data, not a fresh untouched holdout. It cannot determine any new model choice.

## SB audit scope

This is a descriptive investigation of the existing prior-actual/Statcast feature allowlist plus explicitly derived prior SB rate, prior on-base yield, prior SB-rate change, prior CS rate when available, and a known calendar-era indicator. No new source is fetched. Missing CS, sprint-speed or other features remain missing. Availability across measurement eras is reported rather than assumed.

The opportunity proxy is `H-HR+BB+HBP`, not measured stealable-base opportunities. A change is current `SB/proxy` minus raw prior-season `SB/proxy`. Both current and prior proxies require at least 20 eligible opportunities, and both SB labels must be eligible. True zero SB remains zero when its denominator is known. Missing, disputed and insufficient-exposure components never become zeros or get substituted from another reference.

Cohorts are all hitters, established runners (raw prior SB >=10), low-history hitters (raw prior PA missing or <100), and prior zero-SB hitters. They can overlap. Many genuine cold starts cannot have an eligible prior rate; these remain in coverage and the audit must not be generalized to them.

For each origin and feature, quintile boundaries use **only earlier predictor populations**, excluding target 2020 under the existing policy, without requiring those earlier rows' target labels. The 2026 boundaries are frozen before evaluation. Duplicate boundaries can create empty bands; bands 0–4, MISSING and NO_PRIOR_DISTRIBUTION remain explicit. No current-season distribution is used to redefine a band.

Annual reports contain Pearson/Spearman associations with propensity change, companion Spearman associations with current propensity level, feature coverage and per-band observed changes. Associations need at least 30 eligible pairs and feature/target variation. Band sample sufficiency is explicit. Raw per-player rates and denominators remain inspectable. The stability table reports all development years including 2021, positive/negative correlation counts, and equal-fold averages. No feature is selected or ranked into a winning model, and no significance claim is made.

These associations are not proof of predictive skill. Prior propensity appears in the change target, creating mathematical coupling and regression-to-the-mean effects. Small denominators, correlated features, era shifts and multiple comparisons can create apparent relationships. Numeric treatment of era indicators is descriptive. Current-outcome associations must be tested in a later chronological prediction experiment before proposing an SB replacement; disclosed 2026 must not choose features.

## Reports

| File | Purpose |
| --- | --- |
| joint_workload_build_report.json | Historical choices, preservation, scope and limitations |
| joint_workload_evaluation_report.json | Separate disclosed evaluation summary, in evaluation folder |
| historical_gate_evidence.json / rolling_choices.json | Prior-fold losses and chronological decisions |
| joint_calibration_parameters.csv | Joint coefficients, role pooling, convergence and training loss |
| joint_calibration_fit_members.csv | Exact earlier OOF examples and both branch/probability inputs |
| workload_comparison.csv | Accepted v1.5, research v1.6/v1.8, candidate/selected v1.9; identical pools, OUTS and decimal IP |
| transition_2021.csv | Raw prior OUTS, frozen anchor, all candidate counts, coefficients and observed 2021 OUTS |
| category_scores.csv / category_coverage.csv | Coherent category effects and eligible comparison pools |
| comparison_pairs.csv | Count-level paired outcomes, focused on experimental/downstream counts |
| sb_propensity_coverage.csv | Missing/inadequate/eligible change counts by season and cohort |
| sb_feature_associations.csv | Annual per-feature coverage and descriptive associations |
| sb_feature_bins.csv | Earlier-defined bands and their observed propensity changes |
| sb_feature_stability.csv | Historical sign consistency and availability; no feature selections |
| sb_propensity_players.csv | Eligible/excluded player-level proxy/rate/change trace |
| sb_frozen_feature_bins.json | Predictor-only boundaries for every origin including 2026 |
| preservation_audit.csv | Preserved accepted saves, holds, SB and coherent vectors |

The evaluation folder repeats comparison/category/SB reports through 2026. Its historical stability table still excludes 2026 and target-2020 stress from development summaries; annual stress and disclosed rows remain separately visible. Frozen original vectors and role inputs are also retained in the build.

Category method names `workload_candidate` and `selected_workload_experiment` refer to v1.9 within this versioned folder. `frozen_v1_5` is the accepted reference. `workload_comparison.csv` explicitly labels the rejected v1.6/v1.8 comparators. RMSE/MAE comparisons must use the same cohort, category and comparison group; commercial source pairing can change the eligible pool.

After running, send the two JSON reports, build `historical_gate_evidence.json`, `joint_calibration_parameters.csv`, `transition_2021.csv`, `sb_propensity_coverage.csv`, `sb_feature_stability.csv`, and evaluation `workload_comparison.csv` and `category_scores.csv`. Keep the larger SB association/bin/player tables locally for targeted follow-up, or attach them for detailed feature review.

This package's tests use synthetic fixtures. Production improvements or adoption cannot be claimed until your local results are reviewed. All original references and releases remain unchanged, with complete output backups.
