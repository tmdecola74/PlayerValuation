# Standalone categorical roles and workload experts v1.2

Extract this ZIP directly into D:\JonAPythonClass\pycharm\PlayerValuation. It adds new files; v1.0 and v1.1 code, forecasts and outputs remain unchanged. Requires installed v1.0 and v1.1 packages and their tests, NumPy and DuckDB. No new data download or broad Statcast rescan is needed.

## Run in order (PowerShell from project root)

```powershell
python -m unittest discover -s tests -p "test_standalone_role_workload_v1_2.py" -v
python backtest_standalone_role_workload_v1_2.py
python evaluate_standalone_role_workload_v1_2.py
```

The evaluator optionally benchmarks workload against Steamer/OOPSY using the existing read-only DuckDB warehouse. Add --skip-benchmarks if that warehouse is unavailable. All scripts support --help.

Defaults:
- Matrix: outputs/standalone_lagged_features_v1_0
- Frozen comparator: outputs/standalone_opportunity_v1_1
- Approved actual labels: outputs/training_labels_v1_0
- Build output: outputs/standalone_role_workload_v1_2
- Evaluation output: outputs/standalone_role_workload_evaluation_v1_2
- Warehouse: data/historical_duckdb_v1_0_bulk/player_valuation.duckdb
- Backups: backups/

Both stages publish only to a NEW output directory and create a complete hash-verified backup before publication. Existing output directories are rejected. On rerun use a fresh --output; supply that build folder with --run to the evaluator. Matrix/schema/reference disagreements and changed input hashes fail instead of silently producing a comparison. Output manifests record the files used.

## What changes, and what stays frozen

The new candidate changes pitcher workload (OUTS/IP) only if historical gates pass. Related v1.1 count components scale together, retaining component-derived ERA/WHIP. Original zero exposure cannot supply component rates; that overlay falls back. Rejected changes retain exact v1.1 forecasts.

SAVES ARE ALWAYS EXACTLY v1.1, including when innings change. Hitter forecasts also remain exactly v1.1; hitter PA is joined for error attribution, not remodeled in this release. This isolates the pitcher role/workload experiment from the previously demonstrated saves improvements. No external projection is a feature or fitting target.

## Categorical role experiment

Fixed target definitions from eligible G/GS:
- STARTER: G>0 and GS/G >=0.5
- RELIEVER: G>0 and GS/G <=0.1
- SWING: intermediate GS/G
- UNKNOWN: missing or invalid G/GS; never assigned a fabricated target class

The comparator retains the strictly previous season's role when known. Its probability vector puts fixed 0.9 mass on that role and 0.1 on fold-training class frequencies. Unknown prior roles use fold-training class frequencies; there is no two-year role backfill or name guessing. All three class frequencies use fixed add-one smoothing. Accuracy uses the retained class, not an averaged GS/G ratio.

The candidate is a multinomial softmax classifier with L2 penalty 0.05 and at most 200 deterministic gradient iterations with descent line search. Numeric missingness, medians, scaling, clipping and era categories are fitted only on that fold's training rows. It uses prior actuals, historical physical features, prior role/usage ratios and volume summaries. No target-year G/GS/OUTS enters its predictors. Low training/class support falls back to the prior-role comparator. Probabilities are normalized but are NOT claimed to be calibrated.

Every target year gets prior-role, categorical and historically selected role probabilities. Selection uses only earlier origins, excluding target 2020. It requires two earlier qualifying folds, at least 30 examples per fold overall and 20 with known prior roles, >=1% lower equal-fold mean multiclass Brier score, at most 1% log-loss degradation, and no decline in accuracy or balanced accuracy. Both the overall and known-prior gates must pass. Otherwise retain the prior-role baseline. The multiclass Brier score is the SUM of three squared class errors (range 0–2), not the binary saves Brier metric from v1.1.

## Role-specific workloads and nested chronology

Role probabilities are first generated chronologically for every matrix target year, including 2016–2018. For a row with target year t, its role model fits only target years <t; its role choice uses only earlier validation origins. Those frozen row probabilities become workload features. The lineage CSV records the latest role fitting year and the validation seasons used. The builder rejects self-year or future role-feature lineage.

At each outer workload origin 2019–2025, workload experts fit only earlier target years using those earlier-generated role probabilities. They do NOT use role probabilities recomputed from a classifier fitted on the entire outer training set. Final 2026 experts similarly use chronological role features for training rows through 2025.

There is one conditional-appearance OUTS expert per actual training role, plus a pooled fallback. Actual role is a training label/cohort defining each expert, never a target-year predictor supplied at inference. The selected predicted role probabilities are included as predictors and mix the three experts' conditional OUTS forecasts. Low-support experts use the pooled model. Each expert has its own training-only preprocessing and ridge fit. All three expert predictions remain auditable.

Expected workload = probability-weighted conditional expert OUTS × the exact frozen v1.1 participation multiplier. Unsupported participation therefore remains conditional-on-appearance as in v1.1; this release does not create nonappearance labels.

Adoption compares the mixture with frozen v1.1 on identical eligible OUTS pools. It needs two earlier qualifying folds, >=1% improvement in equal-fold mean MSE, and no more than 1% MAE deterioration. A separate prior-STARTER cohort gate (at least 20 per fold) also requires non-worse mean MSE and no more than 1% MAE deterioration. Failed/insufficient gates retain v1.1. There is no forced workload change. G/GS are role targets here; v1.2 does not invent a new coherent G/GS forecast from category probabilities.

Target 2020 is excluded from role/workload fitting and selection; scores for it are stress-test reports. The existing fixed source-2020 volume normalization and era controls remain. Prior-actual change attribution reports observed counts, so jumps from shortened 2020 require that context.

## Frozen actual PA/OUTS joins

The join reads the approved eligible FanGraphs training-label tables with discrepancy exclusions applied. It does not substitute raw disputed counts, MLB evidence or Statcast totals. Label keys are season/player_type/MLBAM/metric; duplicate keys, split contamination and matrix-versus-label disagreement fail. Eligible zero counts remain zero. Missing/disputed actuals remain unknown and do not enter accuracy pools.

The builder reads training_labels.parquet only, and never parses holdout_matrix.parquet or holdout_labels.parquet. Input manifest verification may hash those files' bytes without reading their outcomes into modeling. Only the separate evaluator opens 2026 outcomes after confirming the model/forecast freeze. Frozen references and label tables are read-only and checked unchanged before publication.

## Files to review

Build folder:
- role_workload_build_report.json: final categorical/prior-role choice and workload gate results.
- role_candidate_scores.json, role_choices.json: historical role metrics and selection evidence.
- role_predictions.csv: all three methods and probability vectors; 2026 actual roles remain NOT_READ.
- role_probability_lineage.csv and role_fit_audit.json: chronological provenance for each probability row and role fit.
- workload_candidate_scores.json and workload_choices.json: mixture versus v1.1 gate evidence.
- workload_fit_audit.json: expert and pooled fitting years, sample sizes and fallbacks.
- workload_expert_predictions.csv: separate expert outputs, mixture, participation multiplier and application support.
- workload_attribution.csv, workload_scores.csv, workload_coverage.csv: historical PA/OUTS joins and paired errors.
- frozen_models.json, frozen_2026_forecasts.csv, historical_forecasts.csv, freeze_manifest.json.

Evaluation folder:
- role_workload_evaluation_report.json.
- role_scores.csv: prior_role, categorical, selected_role; same pools for accuracy, balanced accuracy, Brier and log loss. Known-prior and all-label cohorts reported separately.
- role_confusion.csv and role_predictions_with_actuals.csv: class errors and individual forecasts.
- workload_attribution.csv: actual PA/OUTS, both versions, errors, prior actual volume, actual change, prior/actual roles and decimal-IP equivalents.
- workload_scores.csv: matched-pool MAE/RMSE/bias by role and exposure cohorts. Actual-role/actual-exposure/change cohorts are retrospective attribution, not deployable preseason selections.
- workload_coverage.csv: candidate, eligible-label and paired counts; missing outcomes never become zeros.
- workload_benchmark_scores.csv, workload_benchmark_pairs.csv, workload_benchmark_coverage.csv, identity_review.csv: PA/OUTS/IP comparisons with Steamer/OOPSY separately and together. These are workload-only benchmarks; source selections, record IDs and analytical exclusions remain intact.

Send these first: role_workload_build_report.json from the build folder, plus role_workload_evaluation_report.json, role_scores.csv, role_confusion.csv, workload_scores.csv and workload_benchmark_scores.csv from the evaluation folder. Individual attribution/expert files can follow for discrepancies.

## Limits and evaluation disclosure

2026 has already been reviewed during v1.0/v1.1 development. It remains a disclosed evaluation set, not a new untouched holdout. Model designs/defaults are research controls; no 2026 outcome enters fitting, preprocessing or gates. Further model choice must use historical folds, with a future prospective freeze needed for independent evidence.

This is not a full roster, prospect, injury, offseason depth-chart or team-opportunity model. Role probabilities are conditional on appearance/known role labels; non-return participation remains a separate unresolved data gate. Retrospective vintages and measurement-era limitations persist. No statistical significance or production approval is claimed. Tests use synthetic fixtures; the full-data fit and accuracy must be run on your PC.
