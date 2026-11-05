# Standalone lagged feature matrix v1.0

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`. This package adds three new Python modules, configuration and tests. It does not alter the source reference, prior label build, reconciliation, existing Statcast feature builds or warehouses.

## Run

DuckDB is the only external dependency and is already used by your project.

```powershell
python -m unittest discover -s tests -p "test_lagged_features_v1_0.py" -v
python build_lagged_features_v1_0.py --labels "outputs/training_labels_v1_0" --reference "data/actuals_reference_v1_0_min0ip" --source-windows "outputs/actuals_statcast_reconciliation_v1_0_error_evidence/source_windows.json" --output "outputs/standalone_lagged_features_v1_0"
```

The source-window manifest is the frozen file in your latest reconciliation folder. No additional downloads, projection files or new all-era Statcast feature build are required. The builder reads the exact daily Parquet versions named in that manifest and checks raw, Parquet and schedule hashes. Do not run a refresh that edits those versions during the build. New unrelated downloads need not be used.

The full source files reside on your PC, so this delivery contains the tested generator, not production matrices. It has been tested against synthetic end-to-end Parquet fixtures and the real importer/manifest schemas. The production run will scan the 2015–2025 archive, write the matrices and verify a complete output backup under `backups`. Existing output folders are rejected; use a new name for another run.

## Matrix contract

Training targets are 2016–2025. The separate holdout target is 2026. Source history is restricted to 2015–2025, and every target uses only the previous one, two and three seasons. The 2015 labels have no earlier source history and do not enter these matrices. Missing early lags stay null.

Actual-stat features come from the eligible, exclusion-aware training labels. A disputed prior H or PA and its masked dependent rates are not backfilled from raw counts. Official PA/IP and outcome rates are not reconstructed from terminal Statcast pitches in this build. Physical swing/contact measurements retain the observed batter/pitcher ownership.

The feature population is the union of prior actuals and Statcast participants in the configured three-year history. Target-season actual appearances do not select feature rows. Players with no prior history are listed in a separate cold-start audit; prospects/minor-league histories and a complete preseason roster universe are not supplied. Prior players who do not appear in the target season retain missing target labels, not zero outcomes.

Names or projection crosswalks are not used. Keys are target season, role and MLBAM ID. Hitter/pitcher roles remain separate. Approximate target age is prior FanGraphs season Age plus elapsed years; target-season Age is never read into features. This is not a verified birth-date calculation.

No Steamer, OOPSY, consensus, ADP or other projection/market values are read. Those belong in a later, separately keyed benchmark comparison.

## Output files

| File | Contents |
|---|---|
| `training_features.parquet` / `.csv` | Prior-history predictors for training targets |
| `holdout_features.parquet` / `.csv` | Prior-history predictors for the 2026 holdout |
| `training_matrix.parquet` / `.csv` | Training feature rows with eligible target labels attached |
| `holdout_matrix.parquet` / `.csv` | Physically separate holdout features and outcomes |
| `feature_schema.json` | Predictor allowlist, categorical era columns and target mappings |
| `lag_lineage.csv` | Source season and cutoff for every observed history lag |
| `candidate_pool_audit.csv`, `target_join_coverage.csv` | Historical candidate universe and label-join coverage |
| `cold_start_targets.csv` | Labeled target participants without prior history; not inserted into the feature pool |
| `measurement_availability_by_era.csv` | Pooled measurement observations/opportunities and available-player counts by year/role/metric/era |
| `measurement_player_season_audit.csv` | Raw measurement, usable value status, sample counts, coverage and missingness |
| `measurement_schema_audit.csv` | Whether each measurement field exists in each source-year schema |
| `rolling_origin_folds.json` | Historical evaluation years 2019–2025, each trained only on earlier target years |
| `lagged_build_report.json` | Row counts, chronology scope, source hashes and backup location |

`x_` columns are lagged predictors. `y_` columns are outcomes; `y_eligible_*` gates each scalar target. Never include either kind of `y_` column among predictors. Use `feature_schema.json`'s predictor allowlist rather than selecting all numeric columns. Era codes are categorical, not an assumed linear scale. The feature-only CSVs are frozen and hashed before 2026 outcome values are opened.

For coherent joint-target fitting, additionally use the matching joint-bundle eligibility from the label build. Per-metric eligibility does not imply an entire target vector is eligible.

## Measurement controls

The fixed thresholds in config require 100 observations for whiff/chase/velocity/spin/extension, 200 for zone rate and 30 for contact measures. At least 50% measurement coverage is required. Raw values and observation counts remain in the audit even when a usable feature is null. These controls are not fitted against outcomes. Missing fields, nonfinite measurements and insufficient samples do not become zero.

Hitter measurements: whiff, chase, zone, EV, hard-hit rate, barrel rate and contact-only expected wOBA. Pitchers use the same allowed/contact measures plus velocity, spin and extension. Pitcher velocity is the all-pitch average, not a pitch-type-adjusted fastball measure. Bat tracking, location coordinates, arsenal deltas and inferred team context are omitted in this first standalone matrix.

Savant documents a change in release-speed sourcing after 2016. MLB documents the 2020 tracking-system change. These are represented by source-season era codes, with an additional 2024–2025 era indicator. No cross-era multiyear mean or year-over-year delta is calculated, and no correction is claimed to make eras interchangeable. Audit coverage before deciding which measurements a model can use.

Sources: https://baseballsavant.mlb.com/csv-docs and https://www.mlb.com/news/2020-statcast-update-includes-pose-tracking-capabilities . The 2024–2025 code is an explicit research grouping, not a claim that all measurements or players have full bat-tracking coverage; no bat measurements are used.

## Remaining modeling gates

Sources were downloaded retrospectively. Chronology here concerns event/season time, not archived-as-of vintages. No imputation, scaling, shrinkage, model fitting, tuning or accuracy reporting occurs. Fit all learned transforms within each rolling training fold. The 2020 short season is flagged per lag and preserved without automatic rescaling. Measurement availability does not certify physical comparability or every possible scoring outcome.

`model_ready: false` remains intentional pending feature/era review. Use 2026 outcomes only after model selection and forecasts are frozen. Future 2026 pitch windows are ignored; this build never needs them to predict 2026.

After running, send `lagged_build_report.json`, `measurement_availability_by_era.csv` and `target_join_coverage.csv`. Those files are enough for the next review without uploading the matrices initially.
