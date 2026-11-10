# Standalone projection diagnostics and development baseline v1.16

Install in the outer PlayerValuation folder. This release has **no draft-tool dependencies**, ADP, eligibility, SGP, auction or roster inputs. It adds one new module and tests; earlier model/release files remain unchanged.

```powershell
python -m unittest discover -s tests -p "test_standalone_diagnostics_v1_16.py" -v
python standalone_diagnostics_v1_16.py
```

Default output: `outputs/standalone_diagnostics_v1_16`. A complete verified backup is published under `backups/`. Use `--output` with a new path for another run. The command does not fit, repair, overwrite or select models and does not parse any 2026 outcome file.

## Required existing inputs

| Argument | Default |
|---|---|
| `--release` | `outputs/projection_release_2026_v1_11_1` |
| `--accepted` | `outputs/standalone_holds_attribution_v1_5` |
| `--matrix` | `outputs/standalone_lagged_features_v1_0` |
| `--labels` | `outputs/training_labels_v1_0` |
| `--baseline` | `outputs/standalone_baselines_v1_0` |

If your accepted release folder has another name, supply that exact folder with `--release`. Use the homegrown consolidated release, not the reconciled-consensus/draft integration output.

The default `--additional-models` directories are `outputs/standalone_opportunity_v1_1`, `outputs/standalone_role_workload_v1_2`, and `outputs/standalone_workload_experiments_v1_3`. Each supplies its existing `frozen_models.json`. All are required by default so a missing artifact is not silently omitted. Override the list explicitly when stored elsewhere. Do not regenerate model files merely to satisfy this audit. Rejected v1.6–v1.10 research candidates are not substituted into accepted forecasts.

This uses existing `standalone_io_v1_0.py` and `standalone_combined_v1_4.py` and their installed standalone-model dependencies, plus DuckDB/NumPy. It does not import the roster simulator.

## What the development baseline means

The accepted forecasts are the frozen historical `selected_v1_5` vectors. The reference forecasts come from v1.0's `historical_baseline` and `selected_standalone` tables. The historical baseline uses actual-stat history; the selected v1.0 baseline may already include ridge/Statcast choices. Their comparison with v1.5 is **not a clean Statcast ablation**: workload, saves and holds policies also differ.

This build freezes a development contract for the next controlled experiment rather than fitting a replacement. The proposed experiment holds accepted workload fixed, compares a standard-stat skill estimator with the same estimator plus hitter or pitcher Statcast predictors, uses identical eligible metric-specific pools and fold-specific preprocessing, evaluates rate errors before coherent counting totals, and selects only on earlier historical folds. No new hyperparameters or winners are chosen here. Steamer/OOPSY remain external benchmarks; no external projections enter these diagnostics as homegrown predictors. Existing 2026 benchmark reports remain separate and are not rewritten.

## Outputs to review

- **`standalone_diagnostic_report.json`**: input scope, preserved-source assurances, report counts and limitations.
- **`accepted_component_inventory.csv`**: accepted release provenance grouped by role, metric, component origin and method. These are the actual recorded 2026 release descriptions, not a newly inferred component map.
- **`frozen_controls_and_choices.json`**: saved configurations/settings, target specifications and choices, where recorded in each artifact. Inspect sample-size thresholds, priors, fallback controls, normalization and acceptance rules here.
- **`model_predictor_inventory.csv`**: retained numeric/categorical preprocessing features versus dropped features, model paths, fitting support and training seasons where recorded. This is the final saved model inventory. A retained predictor does not prove nonzero influence, improvement or adoption into a particular accepted component. Some later model formats do not record a preprocessing block; absent rows are not proof that no predictor was used. Per-fold fitting feature inventories were not reconstructed.
- **`statcast_measurement_availability.csv`**: finite/missing matrix availability, minimum and maximum, separately by target year and player type for each Statcast/era feature. Lag/source year is encoded in feature names. This audits the already sample-gated matrix, not raw measurement completeness or physical comparability. Availability does not establish predictive value.
- **`historical_scores.csv`**: season-by-season MAE, RMSE and signed bias, with all-player, estimated-age, history-depth, prior-role and actual-exposure cohorts. Actual exposure bins are hitters: zero, <100 PA, 100–299 PA, >=300 PA; pitchers: zero, <20 IP, 20–39 IP, 40–99 IP, >=100 IP. Exposure and actual-role analyses are diagnostics, not preseason predictors. Age is inherited prior-history estimated age, not target-season actual age.
- **`historical_comparison_summary.csv`**: per-comparator matched-pool summaries with pooled and equal-season-weighted errors. Same comparison-group/membership hashes must be used when comparing methods. Never compare the individual eligible pools as if their populations were identical. No acceptance selection is performed.
- **`transition_2021.csv`**: the complete 2021 score slice. 2020 is also retained in the full historical tables, marked as a short season. Old models' exclusion/normalization policies are documented rather than silently changed. No unfavorable season is removed by this diagnostic.
- **`historical_outliers.csv`**: up to 20 largest absolute misses **per season, role, metric and method**, with MLBAM identities. Names, when available, are display-only from the frozen 2026 homegrown release; they do not determine historical inclusion. Different-stat units are never pooled into one outlier ranking.
- **`workload_history_context.csv`**: PA/OUTS errors and observed/predicted changes against raw lag-one workload, lag-two/three history, conservative interruption/return pattern descriptions, prior role and eligible actual role. Pitcher OUTS remain integer-out units for labels and fractional expected outs for forecasts. The lower-recent-workload tag uses <50% of older observed workload, fixed for description only; it is not a fitted injury/return classifier. Recent unknown history remains unknown, not a nonappearance. Prior-2020 history is flagged; no new rescaling is applied.
- **`forecast_label_coverage.csv`** and **`label_exclusions.csv`**: forecast/label availability and explicitly excluded label counts. Missing/excluded targets are never zero-filled or reconstructed from other sources. AVG/OBP/SLG/OPS diagnostics additionally require eligible positive AB; ERA/WHIP require eligible positive OUTS. This conservative rate gate may exclude otherwise published rates whose denominators are disputed.
- **`development_contract.json`**: versioned historical-only experimental plan. 2026 is already-reviewed disclosed evaluation data, not a new untouched holdout. No 2026 outcomes are needed for this build.

## Preservation and interpretation

The accepted historical forecast's exact hash must be bound to the consolidated release. Matrix hashes and label-reference hashes must agree, and the accepted v1.5 training-label hash must match the supplied eligible labels. Required individual files are verified against their registered output manifests; unrelated holdout-label files are not opened. Complete accepted statistical vectors are checked with the prior coherence rules and never repaired. Duplicate keys, invalid numbers, future historical years, outcome predictor names and future fitting years are rejected.

This audits frozen outputs and their saved metadata. It does **not** independently re-fit or replay all original historical selection gates. It does not certify old preprocessing beyond what the artifacts document. A successful diagnostic means report integrity, not approval of a new model or a promise of projection accuracy.

The separate prospect/international/returner branch still requires dated historical minor-league, overseas, roster and availability inputs. These diagnostics do not use the realized 2026 participant list to expand any preseason population.
