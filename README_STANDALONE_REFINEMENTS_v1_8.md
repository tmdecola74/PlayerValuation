# Separate standalone refinements v1.8

This release preserves v1.6/v1.7 as research evidence and adds two independent candidates. It does not overwrite the accepted v1.5 projections, combine the experiments, or promote a result based on 2026. Full production data must be processed on your PC; the package contains code and synthetic tests only.

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, retaining every earlier release. All filenames in this package are new v1.8 files. Existing NumPy/DuckDB dependencies are sufficient.

Run these commands in order from the project root:

```powershell
python -m unittest discover -s tests -p "test_standalone_refinements_v1_8.py" -v
python backtest_standalone_refinements_v1_8.py
python evaluate_standalone_refinements_v1_8.py
```

The second command completes the historical experiment and freezes 2026 forecasts without reading 2026 outcomes. Only the third command opens the previously reviewed 2026 labels, after verifying immutable forecasts, models and historical choices. The third command also compares against available commercial warehouse sources; those remain evaluation benchmarks only. To evaluate internally without commercial benchmarks:

```powershell
python evaluate_standalone_refinements_v1_8.py --skip-benchmarks
```

Use one evaluation command, not both into the same output folder. Outputs must be new; to rerun, supply a different `--output`. Every published output folder receives a complete hash-verified backup under `backups/`. Staging folders and incomplete backups are removed on failure or interruption. Inputs are verified again before publication.

## Source folders

| Flag | Default |
| --- | --- |
| --run16 | outputs/standalone_growth_sb_v1_6 |
| --diagnostics | outputs/standalone_magnitude_diagnostics_v1_7 |
| --run15 | outputs/standalone_holds_attribution_v1_5 |
| --run14 | outputs/standalone_combined_v1_4 |
| --source | outputs/standalone_workload_experiments_v1_3 |
| --matrix | outputs/standalone_lagged_features_v1_0 |
| --baseline | outputs/standalone_role_workload_v1_2 |
| --labels | outputs/training_labels_v1_0 |

The build uses `config/standalone_refinements_v1_8.json`. Evaluation uses `--run outputs/standalone_refinements_v1_8`. Commercial benchmarks default to `--warehouse data/historical_duckdb_v1_0_bulk/player_valuation.duckdb`. Override flags if your frozen folder names differ. The v1.7 input must be the original historical-only audit bound to this v1.6 forecast set, not its optional 2026 evaluation copy.

## Pitcher magnitude calibration

For each origin, collect only earlier v1.6 out-of-fold forecasts with eligible actual OUTS and G>0, known anchor and supported source forecasts. Observed growth/decline determines which conditional branch supplies a training example. This observed direction is used only in historical fitting; current-season prediction still mixes both branches with the original frozen v1.6 growth probability.

Fit separate growth and decline multipliers through the origin, minimizing magnitude squared error with a penalty toward multiplier 1. The penalty equals 50 average example squared magnitudes. Multipliers are bounded to [0,3]. Each pooled branch requires 50 examples. Prior-role-specific STARTER/RELIEVER/SWING/UNKNOWN calibration requires 50 examples per branch and otherwise uses pooled calibration. These fixed research controls are not optimized in this build.

At prediction, recalibrated growth is anchor plus scaled source growth magnitude; recalibrated decline is anchor minus scaled source decline magnitude. Counts retain the frozen v1.6 OUTS cap and participation multiplier. Growth and participation probabilities, hard role labels and accepted saves/holds are never recalibrated. Missing branches, insufficient calibration, unsupported source predictions or an inconsistent branch/anchor retain the accepted v1.5 forecast. A zero magnitude does not become missing, but an all-zero calibration design cannot estimate a multiplier.

Earliest v1.6 OOF predictions are 2019, so the first origin has no calibration evidence and falls back. The 2021 calibration can use 2019 evidence; 2020 outcomes remain stress-only. The dedicated transition table retains raw 2020 OUTS, its original normalized anchor, source branch forecasts, calibrated branches, multipliers and actual 2021 OUTS. No 2021 observations enter their own calibration. Later origins may learn from 2021.

## Direct SB propensity candidate

Fit an unconditional SB-per-on-base-proxy rate using eligible historical SB, including true zero-SB seasons. This tests an alternative to v1.6's positive-SB rate multiplied by an occurrence probability. The proxy remains `H-HR+BB+HBP`; it is not actual stealable-base opportunities or an attempts/success model.

The model uses the existing prior actual/Statcast feature allowlist, lagged proxy features and the existing calendar-era indicator. Each origin fits its own preprocessing and ridge model from earlier historical targets. The fit uses the existing workload-model ridge settings, 100 prior proxy opportunities, minimum 20 observed proxy opportunities and at least 50 eligible training rows. Predicted rate is capped at 3 and count at 120. These are fixed controls, not a hyperparameter search. Published 2026 or commercial projections are never predictors.

Forecast SB equals the new rate times accepted v1.5 projected proxy. Accepted PA, H, HR, BB, HBP and all other hitter statistics remain unchanged. Missing proxy or an unsupported model retains accepted SB. True zero rates produce zero forecasts, not missing values. Excluded components are never filled from another source.

## Selection and interpretation

Separate rolling decisions compare each candidate with accepted v1.5. Both require at least two adequate earlier validation folds, 1% overall MSE improvement, no MSE degradation in required guard cohorts, and at most 1% MAE degradation. A fold needs 30 overall rows or 20 guard rows and at least 80% supported candidate forecasts. Fold losses receive equal weight.

Pitcher guards cover prior starters and relievers. SB guards cover established runners (prior SB >=10), prior zero-SB hitters, and low-history hitters (raw prior-season PA missing or <100). Cohorts can overlap. Missing SB history is not treated as zero. Inadequate evidence in any required guard rejects adoption; it is not silently dropped. Low-history uses raw prior PA even for 2020, as a fixed research definition.

Target 2020 is excluded from fitting/selection under the existing development policy, but its forecasts and errors remain visible as a stress season. All eligible 2021 results remain in fitting for later years and in validation; no unfavorable year is selectively removed. Small guard cohorts can fail sample requirements, and their counts remain reported. The 2026 choices use only historical folds and are frozen before evaluation.

Both experiments retain accepted saves and holds exactly. The workload arm scales other pitcher count components coherently with OUTS; the SB arm changes only SB. They are published separately, never as an inferred combined winner. Rates use component denominators. All accuracy comparisons use identical eligible player pools per category/cohort/comparison group, with membership hashes and missing coverage. Historical actual-role/workload cohorts are retrospective diagnostics, not gate features.

## Outputs and files to send

Build folder: `outputs/standalone_refinements_v1_8`

- `refinement_build_report.json`: final historical choices, model support and preservation statements.
- `historical_gate_evidence.json`, `rolling_choices.json`: prior-fold losses and chronological decisions.
- `calibration_parameters.csv`, `calibration_fit_members.csv`: branch coefficients, pooling, counts and exact earlier-fold membership.
- `transition_2021.csv`: explicit 2021 pitcher comparisons; OUTS / 3 gives decimal IP.
- `target_comparison.csv`: accepted v1.5 versus research v1.6 versus v1.8 candidate and selected forecasts for OUTS/SB, including established/low-history cohorts.
- `category_scores.csv`, `category_coverage.csv`, `comparison_pairs.csv`: full statistical category effects and identical-pool comparisons.
- `origin_models.json`, `frozen_models.json`, `freeze_manifest.json`: historical models and frozen final choices.
- `experiment_predictions.csv`, `historical_forecasts.csv`, `frozen_2026_forecasts.csv`: scalar experiments and separate coherent vectors.
- `preservation_audit.csv`, `classification_and_probability_inputs.csv`: preserved saves/holds and source role evidence.

Evaluation folder: `outputs/standalone_refinements_evaluation_v1_8`

- `refinement_evaluation_report.json`: disclosed evaluation and source availability.
- `target_comparison.csv`, `category_scores.csv`, `category_coverage.csv`, `comparison_pairs.csv`: historical and disclosed 2026 results, with commercial comparison groups if enabled.
- `benchmark_identity_review.csv`: unmatched/ambiguous benchmark identities.

Send the two JSON reports, build `historical_gate_evidence.json`, `calibration_parameters.csv`, `transition_2021.csv`, and evaluation `target_comparison.csv` and `category_scores.csv`.

Method labels in category scores retain the earlier naming convention: `frozen_v1_5`, `workload_candidate`, `SB_candidate`, `selected_workload_experiment`, `selected_SB_experiment`. Here the candidate/selected labels refer to v1.8 because the output directory and reports are v1.8. `target_comparison.csv` explicitly distinguishes `research_v1_6`, `candidate_v1_8` and `selected_v1_8`.

These are retrospective research experiments. There is no claim of archived preseason data, statistical significance, reliable cold-start coverage, or improved production performance until the local historical results are reviewed. 2026 has already been reviewed and remains disclosed evaluation data.
