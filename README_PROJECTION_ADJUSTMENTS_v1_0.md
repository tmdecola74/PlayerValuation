# Projection adjustment backtest v1.0

Extract this ZIP into `D:\JonAPythonClass\pycharm\PlayerValuation`, preserving config and tests subfolders. These are new files; the SQLite reference, prior evaluators, original projections, and model-input builder remain unchanged. Python standard library only: no additional numerical dependency is needed.

Run from the project folder:

```powershell
python -m unittest discover -s tests -p "test_projection_adjustments_v1_0.py" -v
python backtest_projection_adjustments_v1_0.py --evaluate-holdout
```

Defaults: inputs `outputs/statcast_model_inputs_2026_v1_0`, SQLite `data/warehouse_resolved/historical_projection_warehouse.sqlite`, output `outputs/projection_adjustments_v1_0`, backup root `backups`. An existing output is never overwritten. For reruns use a new --output. Without --evaluate-holdout the script still fits, validates, freezes models, and generates 2026 forecasts, but does not query 2026 actuals.

## Frozen chronology

1. Fits each available source/statistic model on 2024 labels and pre-2024 features.
2. Uses 2025 labels and pre-2025 features only to accept/reject that fixed candidate.
3. Does not refit on 2025 after validation and does not search a hyperparameter grid.
4. Writes frozen_models.json and forecasts_2026.jsonl before querying 2026 actuals.
5. Evaluates 2026 on paired baseline/adjusted rows, then verifies frozen model and forecast hashes unchanged.

Feature dates, team context dates, missing-value sample controls, duplicate player/source keys, and training label dates are checked. The input build must have a COMPLETE pitch trace. Holdout/future labels accidentally added to training_labels.jsonl are rejected.

## Candidate model

A fixed ridge regression predicts residuals relative to each source's original baseline. Count statistics are fitted as residual rates per PA (hitters) or IP (pitchers), using actual training exposures; at prediction time projected PA/IP remain fixed. AVG, ERA, and WHIP are fitted as residual rates directly. The exposure/playing-time projection is not learned here.

Player predictors are the sample-gated features already assembled: swing decisions, contact quality, scored K/BB, and pitcher velocity. Team predictors are prior-year runs, stolen-base attempt rate, and pitcher team winning context as applicable. Baseline rate is also a predictor. Training-only feature mean and scale are frozen. Observed standardized player features are multiplied by their existing reliability scores, missing values use neutral standardized coordinates plus availability indicators. A minimum of two usable PLAYER features is needed; team context alone does not permit an adjustment.

One candidate per source/statistic, ridge strength 10, >=80 fit players and >=60 validation players. Fixed caps: R/RBI +/-10%, HR/SB +/-20%, W/SO +/-15%, SV +/-20%, AVG +/-0.010, ERA +/-0.35, WHIP +/-0.05. Counts/rates stay nonnegative; AVG stays <=1. Sources without 2024 samples, rejected models, missing features, zero baseline counts, nonpositive projected exposures, and excluded metrics use explicit fallback statuses. Saves adjustments additionally require projected SV>=5. Actual zero saves are preserved in fitting/scoring; missing actuals are never imputed as zero.

Training uses 2024 players with actual PA>=300 or IP>=40. Validation requires >=2% MAE improvement and no RMSE worsening in BOTH all-matched and headline samples (PA>=300/IP>=40). These are initial fixed research controls, not tuned weights. No 2026 value determines selection.

Each source is compared with its own baseline on identical per-metric player sets. This is not a cross-source ranking: different sources have different coverage. Missing/excluded metrics and actual exposure<=0 are explicitly omitted and counted. Individual per-source projections are preserved; the established consensus/blend is not replaced or recalculated.

## Output files

* frozen_models.json: configuration, coefficients, training-only scaling, fit sample sizes, validation metrics and accept/reject reasons.
* validation_pairs.csv: paired source baseline/candidate/2025 actual rows. These show rejected candidates too, intentionally.
* validation_scores.csv: 2025 candidate MAE/RMSE/bias-related selection diagnostics by source/statistic/cohort.
* forecasts_2026.jsonl: all per-metric frozen forecasts and exact baseline/fallback provenance, including rows without holdout actuals.
* holdout_pairs.csv and holdout_scores.csv: paired 2026 evaluation, only when --evaluate-holdout is supplied.
* omissions.json: missing labels/metrics/exposure counts in validation and holdout.
* adjustment_backtest_audit.json: input/code hashes, selected models, changed forecasts, reference hash and backup location.

The complete new output is copied to a timestamped backups folder and every file hash checked before publication. Existing input files are fingerprinted before/after. SQLite is opened read-only and its hash checked before/after evaluation.

## Result of the supplied-data run

45 source/statistic candidates; 18 could be fitted and 27 lacked enough fit data. ZERO models passed both validation-cohort gates. All 109,065 per-metric 2026 forecast rows retain their baseline or existing missing/excluded status. The frozen 2026 evaluation therefore has identical baseline and deployed-model errors, as expected.

The run in `results_from_supplied_data` used the supplied SQLite reference, physical feature tables, and the user's full pitch-trace reconciliation. The model input CSV was reconstructed here from those supplied counts using the same assembler rules because the original pitch Parquet exists on the user's PC. The raw ingestion was not rerun here. Run locally against your actual completed model-input folder for final reproduction. The included results were independently checked against every original analytical projection metric; no forecast baseline was altered.

This is a completed conservative experiment, not evidence that Statcast can never help projections. Some candidates helped a narrow cohort but failed the broader gate. Do not loosen gates based on the now-observed 2026 holdout. A separately specified subsequent experiment should have a new version and acknowledge that 2026 is already inspected.

## Limits and next stage

Only one fit season and one validation season are available. Multiple per-source/statistic tests can overfit validation; no significance claim is made. Inputs were downloaded retrospectively, so this is not an archived-as-of historical simulation. The one Canzone 2025 PA provider discrepancy remains documented; reference counts/rates are retained. Per-metric research forecasts are not a component-coherent production projection vector and do not yet calculate SGP or dollar values.

Since this version selects no adjustments, the established consensus remains the supported statistical baseline. A next useful build is league-specific valuation/SGP over that baseline; separate playing-time/role modeling can be researched later without claiming new untouched 2026 holdout evidence.
