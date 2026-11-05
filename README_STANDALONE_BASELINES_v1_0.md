# Standalone baseline projections v1.0

Extract this ZIP directly into D:\JonAPythonClass\pycharm\PlayerValuation. It adds new scripts/config/tests; no prior scripts or data need replacement. Dependencies: NumPy and DuckDB, listed in requirements_standalone_v1_0.txt. Do not overwrite your main requirements file.

## Run in order (PowerShell)

```powershell
python -m unittest discover -s tests -p "test_standalone_baselines_v1_0.py" -v
python backtest_standalone_baselines_v1_0.py
python evaluate_standalone_holdout_v1_0.py
python compare_standalone_benchmarks_v1_0.py
```

Defaults use outputs/standalone_lagged_features_v1_0, outputs/training_labels_v1_0, and data/historical_duckdb_v1_0_bulk/player_valuation.duckdb. Each command creates its own new output folder and a complete hash-verified backup under backups/. Existing output folders are rejected: use --output with a fresh name if rerunning, and pass the corresponding --run to later commands. All three commands support --help. Frozen references, physical Statcast, and projection warehouses remain unchanged. No network calls.

## Model and chronology

There are 23 separately fitted component targets: hitter PA and pitcher OUTS for playing time, twelve hitter skill rates, and nine pitcher skill rates. IP is decimal innings derived from OUTS/3. Each target has a weighted historical baseline and a ridge residual candidate with fixed alpha=1. Numeric missingness, medians, scaling, dropped columns, and era categories are learned only from that fold's fitting years. Target outcomes and actual target exposure never enter predictor columns. Actual exposure supplies rate labels and capped training weights only.

Historical inner origins run 2018–2025; reported outer forecasts run 2019–2025. At each origin, fit target years are strictly earlier; candidate selection uses only earlier out-of-sample origins. Selection requires two qualifying prior origins, at least 30 paired observations per origin, at least 1% lower equal-fold mean MSE, and no more than 1% MAE degradation. Otherwise retain baseline. These are fixed research controls, not a tuned search. Final choices use origins through 2025, refit through 2025, and write frozen 2026 forecasts before the separate evaluator reads 2026 outcomes. File hashes bind evaluation and benchmarking to that freeze.

Playing-time training/selection excludes target 2020; 2020 scores remain stress-test reports. Source-2020 volume predictors use fixed 162/60 normalization; skill baseline shrinkage retains observed exposure. No automatic normalization of all 2020 targets. Rate training floors: 50 PA or 30 AB for hitters; 90 OUTS for pitchers. Prior-save/hold/QS zero baselines remain zero with observed positive exposure; ridge can learn changes. This is not an explicit closer-role model.

Hitter AB/BB/HBP/SF/SH components cannot exceed PA jointly; hit types sum to H and cannot exceed AB. Pitcher HR cannot exceed H. AVG/OBP/SLG/OPS/ERA/WHIP derive from projected components. Zero denominators produce null rates. R/RBI/SB and pitcher decisions/saves remain independently modeled count rates; no team-level opportunity allocation is imposed.

## Read the results

- outputs/standalone_baselines_v1_0/standalone_build_report.json: final ridge count and limitations.
- historical_scores.csv: year/role/metric MAE, RMSE, bias, pool size, membership hash for baseline and selected standalone.
- historical_component_scores.json and rolling_selections.json: candidate evidence and choice at each origin.
- fit_chronology_audit.json: latest fitting target year and ridge status for every fold/target.
- frozen_models.json and freeze_manifest.json: preprocessing, coefficients, choices, target specs, and forecast hashes.
- frozen_2026_forecasts.csv: long-format coherent predictions for prior-history candidates.
- outputs/standalone_holdout_evaluation_v1_0/holdout_scores.csv: 2026 baseline/standalone results after freeze.
- outputs/standalone_benchmarks_v1_0/benchmark_scores.csv: separate Steamer-paired, OOPSY-paired, and all-available-source groups for 2024–2026. Compare methods only within the same year/role/metric/group; differing source pools can give different scores.
- benchmark_coverage.csv and identity_review.csv: coverage and rejected missing/ambiguous MLBAM links. No name guessing. OOPSY absent in a season stays absent.
- All paired-prediction files preserve actuals and player IDs for investigation. External source record IDs and analytical metric exclusions are retained.

The benchmark labels come from the frozen FanGraphs label tables with the discrepancy exclusions, not warehouse actuals. External published rates are scored as supplied; only missing rates with permitted components are derived. Steamer/OOPSY are never fitting, selection, imputation, or population inputs.

## Interpretation limits

This is a first research baseline, not production approval. Evaluation is conditional on eligible observed labels. Missing target outcomes are not zero; non-return participation, injuries, prospects/minor leaguers, and a full preseason roster universe remain unmodeled. Low-exposure players can receive predictions but are excluded from rate-candidate selection below the fixed floors. Final count/rate forecast scoring uses eligible labels without those extra selection floors. Coverage and sample sizes must accompany accuracy claims. Historical physical measurements are retrospective and era controls do not establish instrument comparability. The effective projection/ADP date remains user-confirmed 2026-03-24 rather than independently archived. No result demonstrates real draft improvement or statistical significance.

The supplied tests use synthetic fixtures. Production accuracy and selected-model counts are determined only when you run the commands against your full local data. Send the three JSON reports plus historical_scores.csv, holdout_scores.csv and benchmark_scores.csv for review before changing model choices or draft recommendations. Do not retune on the 2026 report.
