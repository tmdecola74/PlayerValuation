# Separate pitcher workload and stolen-base experiments v1.6

This release preserves v1.5 and all earlier releases. It tests two separate improvements: role-informed pitcher workload growth/decline and a hitter stolen-base opportunity/rate model. It never combines the selected experiments into a new winning ensemble. The accepted v1.5 holds and saves forecasts remain exactly fixed in every arm.

## Install and run

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation` with the new Python files at the project root. Merge the new config/test into the existing `config` and `tests` folders. Installed v1.0–v1.5 code and completed frozen output folders are prerequisites. Keep their tests for the integration fixtures. NumPy and DuckDB remain the existing dependencies.

```powershell
python -m unittest discover -s tests -p "test_standalone_growth_sb_v1_6.py" -v
python backtest_standalone_growth_sb_v1_6.py
python evaluate_standalone_growth_sb_v1_6.py
```

Default inputs:

| Input | Folder |
|---|---|
| Frozen v1.5 holds/projections | `outputs/standalone_holds_attribution_v1_5` |
| Frozen v1.4 combined projections | `outputs/standalone_combined_v1_4` |
| Frozen v1.3 experiments | `outputs/standalone_workload_experiments_v1_3` |
| Frozen v1.2 reference | `outputs/standalone_role_workload_v1_2` |
| Historical matrix and evaluation features | `outputs/standalone_lagged_features_v1_0` |
| Eligible frozen labels | `outputs/training_labels_v1_0` |
| New controls | `config/standalone_growth_sb_v1_6.json` |
| Read-only commercial benchmarks | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |

Use `--help` for alternate paths. Existing output destinations are rejected. Choose a new `--output` folder to rerun; do not remove prior results. The evaluator includes Steamer/OOPSY comparisons by default. Use `--skip-benchmarks` only when the warehouse is unavailable; that omission is explicit in the report.

## Experiment 1: relative pitcher workload growth/decline

The earlier v1.3 change model used absolute OUTS gains and losses. This candidate uses relative change magnitudes and role-specific experts while retaining the prior-role hard classification policy.

1. Anchor on strictly lag-1 observed OUTS. A missing prior is unavailable, not zero and not an older-year substitution. Known zero is retained.
2. Fit a binary growth model on whether actual OUTS exceeds the anchor, conditional on an observed active season with eligible OUTS and G. Ties are non-growth.
3. Fit separate nonnegative growth and decline magnitudes in log(1+OUTS) space. Positive-growth and non-growth cases are not mixed as fabricated zero targets.
4. Fit starter, reliever and swing experts for each magnitude, plus pooled models. Training uses eligible actual G/GS role labels only to form fitting groups. At prediction time it uses the frozen chronological categorical role probabilities, never target-season actual role.
5. Sparse role/sign experts fall back to their pooled counterpart. An unsupported direction classifier or either unsupported pooled magnitude leaves the raw candidate unavailable.
6. Convert each expert's log magnitude into a bounded conditional OUTS count, mix those counts using role probabilities, and then mix growth/decline counts using the growth probability. Multiply by the frozen participation probability.

The count mixture is arithmetic after transforming each directional forecast back to OUTS; it is not the exponential of an average log forecast. Growth, decline and final conditional counts are bounded 0–900 OUTS. Prior-2020 anchor and volume features retain the fixed 162/60 normalization. Target 2020 is never fitted or used for selection.

All preprocessing, class frequencies, ridge coefficients and classifier coefficients are fitted within each historical origin. Role-probability inputs were themselves generated chronologically for their own target years. Hard role labels are copied unchanged. There is no new classification model or relaxed class gate.

The final workload candidate can scale a coherent v1.5 pitcher vector only when its original OUTS is positive. A zero/missing baseline OUTS cannot supply implied count rates and retains the original vector. Missing anchors or unsupported models also retain v1.5. Raw candidates and support reasons remain visible.

Workload overlays scale OUTS, IP, H, ER, BB, SO, HR, W and QS together. Both SV and HLD are restored to their exact frozen v1.5 values; SV+HLD is unchanged. ERA and WHIP are checked/recomputed from their components. This is a set of fractional expected components, not an integer event simulation. Zero-OUTS forecasts with positive preserved SV/HLD are flagged in the preservation audit rather than changing the accepted forecasts.

## Experiment 2: standalone stolen-base opportunity/rate

This arm keeps v1.5 hitter playing time and every hitter statistic except SB unchanged. It uses no Steamer/OOPSY input.

The projected on-base opportunity proxy is:

`projected non-HR hits + projected BB + projected HBP`

Those components come from the frozen standalone v1.5 projections. The proxy is not measured stealable-base opportunities: it omits base occupancy, errors, fielder's choices, inning state, teammate effects and managerial decisions. No attempt/success probabilities or CS counts are invented.

Two new models use eligible frozen historical actuals:

- L2 logistic probability that an active hitter with a positive on-base proxy records any SB.
- Ridge forecast of positive SB per on-base proxy among positive-SB seasons with at least 20 such opportunities. It uses a fixed 100-opportunity historical prior and is bounded 0–3; this rate is not a probability.

The candidate is:

`frozen projected on-base proxy × probability of any SB × positive SB rate`

The final count is bounded 0–120 SB. These are fixed initial research controls, not tuned limits. Missing H, HR, BB or HBP leaves the opportunity proxy unavailable and retains the v1.5 SB forecast. Known zero projected opportunity can yield a genuine zero count. Missing or excluded actual components are not rebuilt, substituted from another source, or used as zero-SB examples.

Prior positive-SB aliases are created only with known positive prior SB and a valid positive prior opportunity proxy. Observed zero SB is retained for the occurrence model, not relabelled as a zero positive-case rate. Prior count features follow the existing fixed source-2020 normalization; observed counts remain the basis of rate-prior reliability.

The SB feature set adds a fixed known-calendar indicator for target years 2023 onward. It contains no target outcomes. A fitting fold that has not observed that calendar regime cannot estimate its effect from future data. Prior actuals and approved lagged Statcast/context features supply the remaining predictors. No new sprint-speed, attempts, minor-league, injury or team-policy dataset is introduced.

## Historical selection

Each origin from 2019 through 2026 fits only earlier target seasons. Its choices are made before adding that origin's scores to the validation history. All final 2026 choices use only historical folds through 2025. Target 2020 is excluded from fitting/selection and remains a stress report.

Each experiment must pass separately against its frozen v1.5 target forecast:

- At least two earlier qualifying folds.
- At least 1% reduction in equal-fold mean MSE overall.
- At most 1% equal-fold mean MAE deterioration.
- Non-worse MSE and at most 1% MAE deterioration in each prior-information guard cohort.
- At least 30 players per overall fold, 20 per guard fold, and 80% supported raw candidates in each qualifying fold/cohort.

Workload guards are known prior starters and known prior relievers. SB guards are observed prior SB ≥10 and observed prior SB =0. Prior-count thresholds use observed counts. Actual-role or actual-workload cohorts never determine selection.

Rejected/unsupported models retain v1.5. The previous rejected v1.3 pitcher-change forecast is reported in `prior_change_comparison.csv` on matched pools, but it cannot select itself or replace a gate. Neither experiment changes the accepted holds or saves model.

## Freeze and evaluation

The builder verifies the frozen v1.2–v1.5 outputs, their inherited source bindings, and label hashes. It does not parse 2026 outcome labels or the outcome-bearing holdout matrix. Integrity checks can read file bytes without interpreting outcomes.

After freezing the new models and forecasts, the evaluator verifies the input bindings, replays every historical choice, reproduces the 2026 candidates from frozen models, and verifies the full vectors. Only then does it open eligible 2026 labels. No fitting or retuning occurs in evaluation.

2026 was reviewed during earlier releases. It is disclosed evaluation data, not an untouched independent holdout. Historical source retrieval was retrospective and does not certify archived preseason vintages. Participation/non-return, prospect, injury and roster-universe limitations remain.

## Forecasts and diagnostics

Published full forecasts contain three methods:

| Method | Behavior |
|---|---|
| `frozen_v1_5` | Unchanged reference |
| `selected_workload_experiment` | Historically selected pitcher workload change; hitters unchanged |
| `selected_SB_experiment` | Historically selected SB change; pitchers unchanged |

Category scores additionally show both raw candidate arms with explicit fallback behavior. The evaluator scores all available categories/components on identical eligible pools per metric/cohort/comparison group. It retains true zeros, excludes missing/undefined outcomes, and reports coverage and membership hashes. Do not compare error magnitudes across different metric units or sum them into a winner score.

Prior and actual role/workload cohorts remain separate. Actual-role/workload cohorts are retrospective diagnostics. ERA/WHIP include cumulative actual 40/100-IP cohorts; hitter ratios and SB include cumulative actual 100/300-PA cohorts. The calendar-2020 stress rows remain visible. The growth-direction probability report compares Brier error with its own training-fold class-frequency baseline; it does not claim probability calibration.

Steamer/OOPSY comparisons use read-only analytical warehouse selections and exclusions, by unique MLBAM identity. Sources absent in a year are absent, never zero. No name matching is added. The selected holds/saves forecasts and both ratio denominators retain their original policy.

## Outputs

Build: `outputs/standalone_growth_sb_v1_6`

- `growth_sb_build_report.json`
- `frozen_models.json`, `freeze_manifest.json`, `fit_audit.json`
- `rolling_choices.json`, `historical_gate_evidence.json`
- `experiment_predictions.csv`: raw/effective candidates, baseline, selection, support reasons and component predictions. Pitcher rows also retain the rejected v1.3 workload candidate.
- `historical_forecasts.csv`, `frozen_2026_forecasts.csv`: the three separate full methods above.
- `preservation_audit.csv`: holds/saves, coherence and zero-OUTS flags.
- `classification_and_probability_inputs.csv`: exact copy of frozen v1.5 evidence.
- `category_scores.csv`, `category_coverage.csv`, `comparison_pairs.csv`: historical-only scores.
- `growth_direction_scores.csv`, `direction_frequencies.json`: historical direction diagnostics/frozen frequencies.

Evaluation: `outputs/standalone_growth_sb_evaluation_v1_6`

- `growth_sb_evaluation_report.json`
- `category_scores.csv`, `category_coverage.csv`: historical plus disclosed 2026, internal and commercial comparisons.
- `comparison_pairs.csv`: all-player pairs for SB, OUTS, IP, W and SO, with source record IDs. Other metrics/cohorts retain scores and coverage to avoid duplicating millions of identical pair rows.
- `prior_change_comparison.csv`: matched workload comparison with v1.3 research candidate. Errors are OUTS; divide by three for IP units.
- `growth_direction_scores.csv`
- `identity_review.csv`

Successful output folders receive complete hash-verified backups under `backups`. Input/output manifests are retained. Prior releases are never overwritten. Existing destinations are rejected; interrupted unpublished stages and incomplete backups are cleaned up.

## Send after your full-data run

1. `growth_sb_build_report.json`
2. `growth_sb_evaluation_report.json`
3. Evaluation `category_scores.csv`
4. Evaluation `category_coverage.csv`
5. `growth_direction_scores.csv`
6. `prior_change_comparison.csv`

The package tests use synthetic fixtures. Full-data model adoption and accuracy are determined only by your local run. Keep v1.5 frozen, review historical fold/cohort tradeoffs, and do not tune this release on 2026.
