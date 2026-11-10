# Statcast incremental skill experiment v1.17

Install these new files in the outer PlayerValuation project. Preserve all accepted/research releases. Requires installed v1.16 diagnostics and the original standalone model/IO modules, DuckDB and NumPy. No draft simulator, ADP, SGP, auction, consensus or external projection inputs are used.

## Run historical development and freeze forecasts

```powershell
python -m unittest discover -s tests -p "test_statcast_incremental_v1_17.py" -v
python statcast_incremental_v1_17.py
```

Default output: `outputs/statcast_incremental_v1_17`, with a complete verified backup under `backups/`. Never reuse an existing output folder; use `--output` for another run. The production historical data are on your computer; local validation used synthetic frozen references. Fitting all folds/targets can take materially longer than v1.16's read-only audit. Progress prints each origin.

Inputs retain the existing defaults:

- `--release outputs/projection_release_2026_v1_11_1`
- `--accepted outputs/standalone_holds_attribution_v1_5`
- `--matrix outputs/standalone_lagged_features_v1_0`
- `--labels outputs/training_labels_v1_0`
- `--baseline outputs/standalone_baselines_v1_0`
- `--config config/statcast_incremental_v1_17.json`

The consolidated accepted release must bind the historical/2026 v1.5 forecast files, v1.5 model file and prior-feature matrices. The eligible-label reference and training-label hashes must match. Required source files are individually hash checked. Accepted statistical vectors are validated with existing coherence rules, never repaired in place.

## Experimental design

19 rate targets: 12 hitter targets (AB/PA, hit-type/AB rates, BB/HBP/SF/SH/R/RBI/SB per PA) and seven pitcher targets (H/ER/BB/SO/HR/W/QS per OUTS). Wins/outs and similar targets contain opportunity/team effects, so these are not all pure talent measurements.

Both arms fit the same residual ridge estimator over the same shrunk multiyear historical-rate prior, using the same target-specific eligible training rows, exposure weights/caps, penalty, clipping, sample thresholds and fold-only preprocessing. Common-feature medians/means/scales/categories are checked for exact equality across arms. Targets use the inherited minimum training exposures: 50 PA, 30 AB, or 90 OUTS depending on denominator. Target exposure is a label/training weight, never a forecast predictor.

- **`standard_skill`**: permitted prior actual statistics, prior-history age/depth, and common calendar-era/short-season controls. No Statcast measurement, observation count or Statcast-history flag enters this arm.
- **`statcast_skill`**: the same model plus role-appropriate physical measurements and their observation/coverage/eligibility metadata. Hitters use whiff, chase, zone, EV, hard-hit, barrel and xwOBA-on-contact. Pitchers can also use velocity, spin and extension. Hitter velocity/spin/extension columns are excluded.
- **`accepted_frozen`**: existing accepted forecasts and their implied component rates.
- **`historical_selected`**: a separately labeled research composition following earlier-fold skill decisions. It does not replace the accepted source.

Registered Statcast `_value` fields require the lag's eligibility mask plus positive finite observations/coverage. Unsupported physical values remain null before training-only median imputation; missingness indicators remain explicit in the estimator. Original matrices are unchanged. Metadata are checked for nonnegative observations and coverage in [0,1]. This inherits the registered measurement-sample gate; it does not re-download/re-certify raw Statcast data.

The incremental block contains both physical values **and** availability/sample metadata. An improvement is evidence for that block under this estimator, not proof that physical measurements alone caused it. Correlated-feature importance and statistical significance are not claimed.

## Chronology and guards

Historical origins: 2019–2025. Each fits only earlier target seasons from the frozen historical matrix. The 2020 and 2021 skill folds are retained for fitting, reporting and selection. Inherited prior-2020 volume-feature normalization remains the same in both arms; no unfavorable season is dropped. Workload models themselves are not refitted.

Before each origin's labels can contribute validation errors, decisions are frozen from earlier-origin OOF results only. For each target:

1. Statcast must improve equal-season average rate MSE by at least 1% versus the standard-stat arm, with <=1% MAE degradation.
2. Low-history (<=1 observed history season) and established-history (>=2) guards must have sufficient support and <=2% MSE/MAE degradation.
3. The resulting standard/Statcast candidate must also pass those historical checks against the accepted implied rate before the research composition uses it.

Defaults require >=3 supported prior folds, >=30 paired rows per overall fold and >=20 per guard fold. Missing support rejects adoption; it is not treated as success. Gate comparisons use identical three-way eligible rate pools and only folds where both ridge models fitted. Zero reference MSE conservatively prevents adoption. The controls are fixed research assumptions, not optimized on these results. See `historical_gate_evidence.json` for sample counts/hashes and `rolling_choices.json` for every origin. Final 2026 choices use through-2025 historical results and are frozen before evaluation.

The final count/ratio reports do not choose or retune models. Skill gate passage is not automatic approval of a complete statistical projection source.

## Fixed workloads and coherent counts

**Hitter PA and pitcher OUTS/IP remain exactly equal to the accepted forecast. Pitcher SV, HLD and SV+HLD remain exactly unchanged.**

AB is a modeled opportunity fraction under fixed PA, not an additional fixed exposure in this experiment. Hit-type fractions and PA components are normalized under the existing coherent composition formulas, H/AVG/OBP/SLG/OPS and ERA/WHIP are recomputed, and pitcher HR cannot exceed H. Mixed selected rates can therefore alter multiple non-anchored components, even when one underlying component retains an accepted-rate fallback. `composition_adjustments.csv` records the statistical changes; `composition_support.csv` records full-vector fallback and fit support. Unsupported skill vectors retain the entire accepted vector for count reporting, rather than inventing components. Primary fitted-only reports distinguish those cases.

Every research projection is separately labeled. No accepted file, coefficient, workload forecast, saves forecast or holds forecast is overwritten.

## Reports

Review these first:

- `incremental_build_report.json`: final per-target historical choices, incremental gate passes, scope and limitations.
- `historical_rate_comparison_summary.csv`: pooled and equal-season rate errors for standard/Statcast/accepted/selected matched groups. **`standard_vs_statcast`** is the direct two-arm skill comparison.
- `historical_paired_statistic_summary.csv`: direct standard-versus-Statcast comparisons of coherent counts and ratios on identical metric/cohort pools.
- `rolling_choices.json` and `historical_gate_evidence.json`: chronology, guard support, errors and membership hashes.
- `statcast_availability.csv`: supported physical values and values masked by the registered sample metadata, by origin/role/feature.

Additional outputs:

- `historical_rate_scores.csv`, `historical_paired_statistic_scores.csv`, `historical_count_and_ratio_scores.csv`: season-by-season scores with low/unknown history, estimated age, prior role and target-exposure cohorts. Target-exposure bins are retrospective diagnostics only. All methods within a comparison group share membership; different groups may have different populations.
- `historical_fitted_rate_scores.csv`, `historical_fitted_statistic_scores.csv`: comparisons restricted to fitted arms (and, for full vectors, no unsupported-vector fallback). Inspect these alongside fallback-inclusive reports.
- `transition_2021_rates.csv`, `transition_2021_counts.csv`: explicit full 2021 slices. 2020 remains in the complete tables.
- `historical_skill_rates.csv`, `historical_forecasts.csv`: player-level historical rate and coherent-statistic forecasts, including fit status for each skill target.
- `fold_fit_chronology.csv`, `fold_predictor_inventory.csv`, `fold_models_2019.json` through `fold_models_2026.json`: exact per-fold support, fit years, shared fitting-pool hashes, retained/dropped predictors, fitted preprocessing and coefficients. These are new experimental models, not replacements for old artifacts.
- `historical_count_comparison_summary.csv`, `historical_count_outliers.csv`, `historical_label_coverage.csv`: accepted-source comparisons, largest metric-specific misses and label coverage.
- `frozen_2026_skill_rates.csv`, `frozen_2026_forecasts.csv`, `frozen_models.json`, `forecast_freeze.json`: frozen choices and research forecasts; no target outcomes are read to create them.
- `experiment_contract.json`: role feature sets, fixed anchors, policies and research-only release status.

Rate reporting includes all eligible positive denominators, including exposures below training floors, so small-sample errors remain visible. Gate selection uses the target-specific minimum exposure. Excluded labels/denominators remain missing and are never reconstructed or supplied from other providers. Cold starts outside the accepted prior-feature universe are not added through their realized participation.

## Separate disclosed 2026 evaluation

After the historical build has frozen choices and forecasts:

```powershell
python evaluate_statcast_incremental_v1_17.py
```

Default output: `outputs/statcast_incremental_v1_17_evaluation`, with complete backup. This command verifies the experiment freeze, feature/reference binding and eligible holdout labels. It does not fit, select, repair, change caps or modify forecasts.

Outputs include `incremental_evaluation_report.json`, `evaluation_rate_comparison_summary.csv`, `evaluation_rate_scores.csv`, `evaluation_paired_statistic_scores.csv`, `evaluation_count_and_ratio_scores.csv`, fitted-only rate/statistic reports, comparison summary, label coverage and outliers. These are **previously reviewed 2026 evaluation data**, not a new untouched holdout. Keep new decisions historical-only after inspecting them. Steamer/OOPSY remain separate benchmark sources, not predictors; this experiment compares accepted and paired homegrown arms rather than re-running the warehouse benchmark pipeline.

No roster construction or draft recommendations are part of this release.
