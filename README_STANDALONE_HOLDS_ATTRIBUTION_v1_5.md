# Standalone holds opportunity and error attribution v1.5

This release preserves v1.4 and all earlier releases. It adds exact workload/rate attribution for HR, SB, W and SO (K), a separate holds-opportunity candidate, and role/workload cohort diagnostics. Only HLD and its derived SV+HLD sum may change in selected v1.5 forecasts. Saves, workloads, skill rates, hitter projections and hard role labels remain frozen.

## Install and run

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, with the new Python files in the project root and the new test/config in their matching folders. Keep the installed v1.0–v1.4 code and completed outputs. The integration tests reuse the earlier releases' test fixtures, so keep those test files too. NumPy and DuckDB are the existing dependencies.

```powershell
python -m unittest discover -s tests -p "test_standalone_holds_attribution_v1_5.py" -v
python backtest_standalone_holds_attribution_v1_5.py
python evaluate_standalone_holds_attribution_v1_5.py
```

Defaults:

| Input | Path |
|---|---|
| Frozen combined forecasts | `outputs/standalone_combined_v1_4` |
| Frozen workload experiments | `outputs/standalone_workload_experiments_v1_3` |
| Frozen v1.2 baseline | `outputs/standalone_role_workload_v1_2` |
| Lagged matrix | `outputs/standalone_lagged_features_v1_0` |
| Eligible frozen labels | `outputs/training_labels_v1_0` |
| New controls | `config/standalone_holds_attribution_v1_5.json` |
| Benchmark warehouse | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |

Use `--help` for alternative paths. An existing output folder is rejected; use a new `--output` when rerunning. The evaluator includes read-only Steamer/OOPSY comparisons by default. `--skip-benchmarks` explicitly skips those comparisons and records that omission.

No source ingestion, network request, identity merge, label correction or reference replacement occurs. The scripts verify the frozen full forecasts and their source bindings, then join the original eligible frozen labels directly by season, player type, MLBAM ID and metric. They do not re-import the duplicated comparison-group rows from the earlier evaluation-pairs report. This avoids counting a player repeatedly across source-comparison groups.

## Workload versus rate attribution

The attribution is retrospective arithmetic, not a causal estimate or a new forecast. “Skill” in the output means the implied count rate, including opportunity and context. Wins per out are not pure pitching talent; HR per PA also includes the AB share of PA.

For a forecast count F, forecast exposure Ef, actual count A and actual exposure Ea:

- Forecast rate rf = F / Ef.
- Actual rate ra = A / Ea.
- Workload contribution = (Ef − Ea) × (rf + ra) / 2.
- Skill/rate contribution = (rf − ra) × (Ef + Ea) / 2.
- F − A = workload contribution + skill/rate contribution.

This symmetric allocation splits the interaction evenly rather than assigning it to whichever factor is changed first. It uses PA for hitter HR and SB, and OUTS for pitcher W and SO. OUTS remain out units, not decimal baseball innings.

Each player row also reports two diagnostic counterfactuals: actual exposure × forecast rate, and forecast exposure × actual rate. They use target-season actuals only in the audit, never as model predictors. Both forecast and actual exposures must be positive. A true zero count with positive exposure is valid. A missing/excluded component or zero denominator remains explicitly unresolved, with its raw values and status retained.

Summaries compare frozen v1.2 and combined v1.4 on identical eligible numerator/denominator pools. v1.5 does not change these four count forecasts, so another identical v1.5 attribution column would add no information. MSE is checked as:

`total_mse = workload_mse + skill_mse + interaction_mse`

where interaction is the mean of twice the product of the two contributions. Interaction can be negative when errors offset. Do not add only the two squared contributions or interpret them as independent causal percentages.

`count_outliers.csv` ranks the top 25 by squared count error for each season/metric/method and retains both contributions and their share of that group's squared error. `ratio_outliers.csv` ranks the top 25 ERA/WHIP errors by season on the internal v1.4 pool, with actual innings and prior/actual roles. These pools are not necessarily identical to external benchmark pools. IDs are MLBAM IDs; no uncertain name matching is added.

## Separate holds-opportunity candidate

The candidate uses prior actuals, approved lagged Statcast/context features and the frozen chronological categorical role probabilities. Hard role classification stays unchanged. No Steamer/OOPSY input enters fitting or selection.

Expected holds are:

`frozen participation probability × predicted relief appearances × probability of any hold given relief × positive holds per relief appearance`

Three components are fitted separately:

1. Relief appearances: G − GS among observed active seasons with both eligible components. A fixed ridge model forecasts 0–90 relief appearances.
2. Hold occurrence: L2 logistic probability of positive HLD among observed seasons with relief appearances and eligible HLD.
3. Positive holds rate: ridge forecast of HLD per relief appearance among positive-HLD seasons with at least five relief appearances. The rate is bounded 0–1, with a fixed 20-appearance historical prior.

The final expected count is bounded 0–60 HLD. These are fixed initial research controls, not optimized limits. The model requires at least 50 eligible fit rows for each component and at least five examples of each occurrence class. Unsupported components yield an unavailable raw candidate, then an explicitly marked v1.4 fallback. Missing labels never become zero-hold examples. All targets are checked against the frozen eligible reference, including G/GS consistency. Valid zero relief appearances can train the appearances model but never supply a hold-rate denominator.

Fold-specific preprocessing and all coefficients use strictly earlier target years. The role probability features were themselves generated chronologically within the earlier release; they are not in-sample role labels from the outer fitting fold. All predictors come from prior-season information. Predicted OUTS do not scale the new holds candidate.

The existing participation forecast is inherited rather than refitted. Unverified missing seasons are not manufactured nonappearances. Prospect coverage, injuries, bullpen hierarchy, leverage and roster transitions remain limitations. This is not a complete team bullpen model.

## Historical selection and 2026 disclosure

For each origin from 2019 through 2026, the candidate is tested against BOTH unchanged v1.2 holds and innings-scaled v1.4 holds. Adoption requires:

- At least two earlier qualifying validation folds.
- At least 1% reduction in equal-fold mean MSE overall versus each baseline.
- At most 1% equal-fold mean MAE deterioration.
- Non-worse MSE and at most 1% MAE deterioration in both prior-reliever and observed prior-HLD ≥5 cohorts.
- Minimum fold sizes: 30 overall, 20 prior relievers, 10 prior-HLD ≥5 pitchers.
- At least 80% supported raw candidates in each qualifying fold/cohort.

Prior HLD ≥5 uses observed prior-season counts, not a normalized 2020 count. A known prior reliever is defined by the preserved prior G/GS rule. Unknown prior roles remain separate in diagnostics.

Failure or insufficient support retains v1.4 holds. The model does not automatically revert to v1.2 simply because v1.2 wins a report comparison. The rejected candidate remains visible as a separate research arm. No selection is made on actual-role, actual-positive-HLD or actual-workload cohorts.

Target 2020 is excluded from fitting and selection and retained only as a stress report. Prior-2020 volume features retain fixed 162/60 normalization inherited from earlier releases. The derived prior relief-appearance feature follows that same normalization.

The builder does not parse 2026 outcome labels or the outcome-bearing holdout matrix. It can read file bytes for integrity verification. It freezes the final models, candidate forecasts, selected projections and historical choices first. The evaluator verifies these, replays earlier-fold selection, reproduces the 2026 raw forecasts from the sealed model, and only then opens eligible 2026 actuals. It never refits or retunes.

2026 has already been reviewed in earlier releases. It is disclosed evaluation data, not an independent untouched holdout. Source files remain retrospective rather than archived preseason vintages. Keep these limitations in all accuracy interpretations.

## Diagnostics and comparison pools

Historical and disclosed evaluation reports retain:

- Prior starter/reliever/swing/unknown role cohorts.
- Actual-role cohorts, explicitly retrospective.
- Prior and actual workload bands: hitters below 100, 100–299 and at least 300 PA; pitchers below 40, 40–99.999 and at least 100 IP.
- Prior-HLD ≥5 and actual-positive-HLD cohorts.

Attribution status coverage includes unresolved rows rather than hiding them. The holds comparisons use identical eligible pools across all four methods: frozen v1.2, combined v1.4, holds candidate and selected v1.5. External HLD and SV+HLD comparisons separately use Steamer-paired, OOPSY-paired and all-available-source pools. Source IDs and coverage are preserved. Missing or excluded actual SV+HLD is not reconstructed. External combined metrics respect the earlier read-only exclusion policy.

## Outputs and review files

Build folder: `outputs/standalone_holds_attribution_v1_5`

- `holds_attribution_build_report.json`
- `frozen_models.json`, `fit_audit.json`
- `historical_holds_choices.json`, `historical_gate_evidence.json`
- `holds_predictions.csv`: all raw components, support flags, candidate, baselines and selection.
- `historical_forecasts.csv`, `frozen_2026_forecasts.csv`: selected v1.5 full vectors. Only HLD/SV+HLD may differ from v1.4.
- `historical_holds_scores.csv`, `historical_holds_coverage.csv`
- `count_error_attribution.csv`, `attribution_summary.csv`, `attribution_coverage.csv`: historical seasons only.
- `count_outliers.csv`, `ratio_outliers.csv`: historical ranked cases.
- Unchanged `classification_and_probability_inputs.csv`.

Evaluation folder: `outputs/standalone_holds_attribution_evaluation_v1_5`

- `holds_attribution_evaluation_report.json`
- `holds_scores.csv`, `holds_coverage.csv`
- `holds_benchmark_scores.csv`, `holds_benchmark_pairs.csv`, `holds_benchmark_coverage.csv`
- `identity_review.csv`
- `count_error_attribution.csv`, `attribution_summary.csv`, `attribution_coverage.csv`: historical and disclosed 2026 evaluation.
- `count_outliers.csv`, `ratio_outliers.csv`: historical and disclosed 2026 ranked cases.

Each successful output folder has a complete hash-verified backup under `backups`, input/output hashes and a freeze manifest where applicable. Prior releases and frozen reference files are never overwritten. Existing destinations are rejected. Unpublished interrupted stages and incomplete backups are cleaned up.

Send these after the full-data run:

1. `holds_attribution_build_report.json`
2. `holds_attribution_evaluation_report.json`
3. `holds_scores.csv`
4. `holds_benchmark_scores.csv`
5. `attribution_summary.csv`
6. `count_outliers.csv` and `ratio_outliers.csv`

The supplied tests use synthetic data. No production improvement, model adoption or player-level explanation is claimed until your full-data reports are reviewed. Keep v1.4 frozen and do not tune this release on 2026.
