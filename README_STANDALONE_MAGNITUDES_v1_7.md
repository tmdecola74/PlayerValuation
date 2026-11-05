# Frozen standalone diagnostics v1.7

Extract the files into the PlayerValuation project root alongside v1.0–v1.6. This release adds new files only. Keep all prior scripts, configurations, output folders, and frozen references. Dependencies are the already installed DuckDB and NumPy used by earlier releases. This package contains code and synthetic tests, not your production data or newly fitted models.

Run in PowerShell from the project root:

```powershell
python -m unittest discover -s tests -p "test_standalone_magnitudes_v1_7.py" -v
python audit_standalone_magnitudes_v1_7.py
```

The default historical-only output is `outputs/standalone_magnitude_diagnostics_v1_7`. For separately disclosed, previously reviewed 2026 evaluation:

```powershell
python audit_standalone_magnitudes_v1_7.py --include-2026 --output "outputs/standalone_magnitude_diagnostics_evaluation_v1_7"
```

Output folders must be new. A complete hash-verified backup is created under `backups/`; all source folders are verified and left unchanged. No network requests, new fit, recalibration, selection change, or forecast overlay is performed. Source v1.6 choices are replayed and final predictions reproduced from their frozen models. Saves and accepted holds remain untouched. The rejected pitcher-change research evidence remains in earlier releases; it is not promoted here.

## Inputs

Defaults match the existing v1.6 build: `--run outputs/standalone_growth_sb_v1_6`, `--run15 outputs/standalone_holds_attribution_v1_5`, `--run14 outputs/standalone_combined_v1_4`, `--source outputs/standalone_workload_experiments_v1_3`, `--matrix outputs/standalone_lagged_features_v1_0`, `--baseline outputs/standalone_role_workload_v1_2`, and `--labels outputs/training_labels_v1_0`. Override flags only if your frozen folders have different names. Hash manifests must remain intact.

Historical forecasts use their own chronological models and adoption choices. Eligible actual components come directly from the frozen label tables; disputed components stay excluded. The default does not parse holdout outcomes. Source integrity verification can hash holdout file bytes. Only `--include-2026` reads holdout labels for diagnostic joins. Neither mode modifies historical or final choices.

## Reports

| File | Purpose |
| --- | --- |
| magnitude_diagnostic_report.json | Scope, preservation assertions, row counts, limitations |
| season_stability.csv | All years 2019–2025, plus optional disclosed 2026; matched baseline/candidate/selected RMSE, MAE, bias and MSE |
| historical_stability_rollup.csv | Equal-fold summaries under the unchanged development policy and a separate all-historical summary including 2020 stress |
| pitcher_magnitude_summary.csv | Growth and decline magnitude bias, MAE and RMSE by prior role, raw workload, normalized workload and joint role/workload |
| pitcher_error_components.csv | Conditional branch error, probability mixing, participation and fallback, including all MSE interaction terms |
| growth_probability_bins.csv | Fixed probability deciles and observed growth fractions; no fitted recalibration |
| pitcher_player_diagnostics.csv | Frozen inputs, forecasts, eligible actuals and exact error components per player-season |
| pitcher_largest_misses.csv | Top 25 count and branch-magnitude misses per year; MLBAM identity, details and share of cohort squared error |
| transition_2021.csv | All 2021 pitcher rows, showing observed 2020 OUTS, frozen normalized anchor and observed 2021 OUTS |
| sb_error_components.csv | Paired opportunity-proxy versus implied-propensity decomposition |
| sb_three_factor_components.csv | Further separates opportunity into PA volume and on-base yield |
| sb_player_diagnostics.csv | All player/method rows, component counts, proxy, raw probability/rate, cap/fallback and missing statuses |
| sb_largest_misses.csv | Top 25 each year/method, overall and established runners, including misses with unavailable decomposition |
| diagnostic_coverage.csv | Every observed diagnostic availability status by year and role |
| source_rolling_choices_v1_6.json | Unchanged frozen source choices |

Start by sending the JSON report, `pitcher_magnitude_summary.csv`, `pitcher_error_components.csv`, `sb_error_components.csv`, `season_stability.csv`, and both largest-miss files. Full player details stay available locally for targeted follow-up.

## Interpretation

Pitcher counts are in OUTS; divide by 3 for decimal IP. Annual stability includes IP explicitly. Growth means actual OUTS exceeds the prior anchor; decline includes flat outcomes. Branch magnitude assessment requires known eligible actual OUTS and G>0 because v1.6 conditional change models were trained on participating pitchers. Missing G, missing OUTS and nonparticipation do not become zero change. Scalar forecast errors remain reported where known. Positive magnitude bias means too much predicted change in the observed direction. An anchor above the count cap can produce negative predicted growth magnitude; this is exposed rather than hidden.

Let A be actual OUTS, g/d the frozen conditional growth/decline counts, p the growth probability, t the participation probability, q=p*g+(1-p)*d, and b the branch consistent with the observed direction. The raw forecast error is `(b-A)+(q-b)+(t-1)*q`. The effective candidate adds its fallback difference. These are algebraic identities, not causal effects or a claim that probability mixing is inherently wrong. Conditional summaries and unconditional count errors have different eligibility requirements; inspect their row counts.

The SB proxy is `H-HR+BB+HBP`. It is not measured stealable-base opportunities. Effective implied propensity is forecast SB divided by projected proxy, including caps and fallback. The raw model occurrence probability and positive rate are retained separately. Exact symmetric two-factor terms sum to forecast-minus-actual SB. A hierarchical decomposition splits the proxy term into PA volume and on-base yield; its three terms also sum exactly. Squared-error tables retain signed interactions: separate component MSEs alone do not sum to total MSE. Counterfactual counts are diagnostic only, not new forecasts.

Established runners use the already frozen prior-SB threshold from v1.6. Workload cohorts use prior information; observed growth/decline groups are explicitly retrospective diagnostics. Baseline, candidate and selected methods share identical eligible comparison pools. Missing or zero denominators remain unknown for rate attribution, while valid true-zero counts remain in count-error scores. Outlier ranking uses squared error, never date or model selection.

All unfavorable years remain visible. The existing development rollup excludes 2020 from selection policy; the additional all-historical rollup includes it as a stress year. Both retain 2021. Empty annual overall pools remain visible with n=0. The 2021 table exposes the already frozen 2.7 normalization of 2020 prior OUTS; no alternative normalization is fitted. Historical sources are retrospective, not archived as-of vintages. 2026 was previously reviewed and cannot determine new choices.
