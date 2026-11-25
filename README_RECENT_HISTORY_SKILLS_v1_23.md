# PlayerValuation v1.23 — recent-history weighting and expanded skill experiments

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`. This package adds versioned files and preserves all accepted releases. It needs the existing `standalone_io_v1_0.py`, NumPy and DuckDB already used by the standalone model.

## Run

Run these commands from the project root in the existing virtual environment:

```powershell
python -m unittest discover -s tests -p "test_recent_history_skills_v1_23.py" -v

python inventory_projection_benchmarks_v1_23.py

python recent_history_skills_v1_23.py

python evaluate_recent_history_skills_v1_23.py
```

The inventory is an optional preflight, useful for checking available benchmark seasons before fitting. The development build repeats and freezes that inventory and the benchmark predictions it will later compare. Benchmark coverage does not select features, players, weights or methods.

Default outputs:

| Step | New folder |
| --- | --- |
| Inventory | `outputs/projection_benchmark_inventory_v1_23` |
| Development/frozen forecasts | `outputs/recent_history_skills_v1_23` |
| Disclosed 2026 evaluation | `outputs/recent_history_skills_v1_23_evaluation` |

Each successful step creates a complete hash-verified backup under `backups`. Existing output folders are never overwritten. Use a new `--output` name for a repeat run; give the evaluator the corresponding development folder with `--run`.

## Frozen inputs

| Argument | Default |
| --- | --- |
| `--reference` | `outputs/statcast_incremental_v1_17` |
| `--matrix` | `outputs/standalone_lagged_features_v1_0` |
| `--labels` | `outputs/training_labels_v1_0` |
| `--expanded` | `outputs/expanded_statcast_v1_20` |
| `--supplement` | `outputs/statcast_leaderboards_v1_21` |
| `--audit` | `outputs/statcast_scope_audit_v1_22` |
| `--warehouse` | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |
| `--benchmark-dir` | `../last3yrsproj` |
| `--config` | `config/recent_history_skills_v1_23.json` |

The reference consists only of the frozen `accepted_frozen` copies in v1.17, not its rejected/selected research overlays. These are the accepted homegrown forecasts used in that earlier comparison. Hashes, reference freezes, matrix/label bindings, expanded-feature bindings and the v1.22 scope audit are checked before fitting. Manifest keys with either Windows or POSIX separators are supported without changing the original files or bypassing hashes.

Benchmark aliases are explicit: Steamer, OOPSY, ATC and FanGraphs Depth Charts (`Depth Charts`, `FanGraphs Depth Charts`, `FanGraphs`, `DC`). No consensus is substituted for a missing system. The warehouse's analytical selections, metric exclusions and unique MLBAM ownership are retained. Migration object hashes are verified for integrity; only projection/identity tables are queried, never actual-statistic tables.

The optional raw-file inventory recognizes source/year hints in CSV, TSV and XLSX filenames. It does not silently import files, infer their export date or establish that their contents cover the hinted year. Discovered files missing from the warehouse must be registered through the existing warehouse intake before they can supply benchmark scores. Files hinted as 2027 are inventoried without opening or hashing them. Missing/ambiguous identities remain exceptions; names never resolve identities.

## What is tested

### Three prior seasons of player history

Every historical origin uses only its three preceding event seasons. The 2026 candidate therefore uses **2023, 2024 and 2025**. No fourth/older player-history fallback is introduced. Historical target seasons 2019–2025 teach forecasting relationships; 2020 and 2021 remain in the reports and eligible historical development pools.

The fixed lag weights, listed newest to oldest, are:

| Weighting | Relative weights | Selection status |
| --- | --- | --- |
| Equal | 1, 1, 1 | Control |
| Recent | 3, 2, 1 | Historical candidate |
| Strong recent | 5, 2, 1 | Historical candidate |

Rates and physical summaries use **recency weight times eligible exposure/observations**. These are not fixed percentages of a player's forecast: unequal samples and missing seasons change the effective shares. Counts used as contextual workload features are weighted means. Missing seasons are omitted from aggregation, never filled with zero; missing aggregated predictors receive training-fold median imputation plus missingness indicators inside the estimator. Eligible zero event rates remain zero. Tracking-era shares, observation totals, available-lag counts and the 2020 window flag are explicit. No automatic rescaling of 2020 counts is performed.

### Paired skill groups

The standard arm uses prior actuals plus the inherited classic Statcast features. The expanded arm adds registered v1.20 measures at the **same recency weighting**, with the same estimator, fitted target population and fold-only preprocessing.

- Hitter group: `1B/AB`, `2B/AB`, `3B/AB`, `HR/AB`. Accepted AB and PA stay fixed; hits, AVG, OBP, SLG and OPS are recomputed coherently.
- Pitcher group: `H/OUTS`, `BB/OUTS`, `ER/OUTS`, `SO/OUTS`, `HR/OUTS`. Accepted OUTS/IP stay fixed; ERA and WHIP are recomputed and H is floored at HR if necessary.
- **SV, HLD and SV+HLD stay exactly frozen.** Unrelated primitives, including hitter R/RBI/SB and pitcher W/QS, also remain accepted. This is a focused skill experiment, not a replacement workload, running-opportunity or wins model.

The estimator fits exposure-weighted ridge residuals against accepted implied skill rates from earlier historical forecasts. It is not a Steamer/OOPSY blend. Minimum fitting exposures are 30 AB or 90 OUTS; scoring includes lower positive exposures in separate cohorts. The fitted models require at least 50 eligible training rows. With no earlier accepted forecasting examples in the first origin, the accepted group remains the explicit fallback.

The new recency weights apply to the residual model's prior-feature summaries. They do not rewrite the accepted baseline's internal weights or previously fitted components. This design tests additions directly against the accepted forecast while preserving it as the control.

Expanded hitter inputs include classified GB/LD/FB/popup/air rates, LA distribution measures, zone/outside-zone contact, overall contact, zone swing, swinging strikes and called-strike-plus-whiff rates. Pitchers add overall raw movement summaries and pitch-type usage, velocity and whiff measures. Pitch types are fixed buckets with OTHER and UNKNOWN retained. Raw movement is not claimed to be induced break or handedness-normalized movement.

Coordinate pull proxies, unresolved official direction substitutions, supplemental mean EV/mean LA/sweet-spot measures, EV50 and baserunning run values are **not added**. The inherited classic physical EV feature retains its original archive definition; it is not replaced by a scope-held leaderboard value. Availability/sample masks are enforced before model preprocessing. Era indicators do not certify physical comparability.

### Bat tracking: separate short-history experiment

The supplementary arm adds bat speed, hard-swing rate, squared-up/contact and squared-up/swing, blast/contact and blast/swing, and swing length. The 2023 partial period remains explicit. Its control has the same expanded features, eligibility population, partial-period indicator and training exposures, but lacks the bat-tracking metric block. Both arms are fitted only where prior bat measurements exist.

The two short-history arms are **never selectable**. Their historical target support is currently 2024–2025; this cannot meet the three-fold acceptance rule. Missing bat measurements retain the accepted group and are reported as fallbacks. No missing pre-2023 bat tracking is invented.

## Historical choices are frozen before 2026 evaluation

For each origin, decisions use only completed earlier-origin forecast errors. Equal-weight controls are not selectable. A recent standard arm must pass against both accepted forecasts and its equal-weight control. An expanded recent arm must pass against accepted forecasts, the standard arm with the same weighting, and its expanded equal-weight control.

The fixed coherent-statistic objective uses AVG/OPS/HR for hitters and ERA/WHIP/SO/HR for pitchers, with equal weights across metrics and seasons after normalizing each MSE by its reference MSE. It requires at least 1% overall improvement, at least three supported folds with 30 players, no metric MSE/MAE regression beyond 1%, explicit support for the two immediately preceding seasons, and low-history/established-history safeguards. History cohorts require two supported folds of at least 20 players; guard metric degradation cannot exceed 2%. Unsupported/zero-reference-error gates reject promotion to a research choice. Ties follow the fixed arm order.

All six long-history fitted arms and all group labels share one historical selection pool. Reports additionally show per-method paired coverage, fitted-only comparisons and separate actual-exposure cohorts. Recent 2023–2025 results and 2021 are exported directly. No unfavorable season is removed. The final research choices are written and hashed before parsing the frozen 2026 accepted vectors and generating the 2026 candidate forecasts. No 2026 labels are read by development.

Historical folds have already been inspected during earlier research. These are further development experiments, not independent confirmation or significance tests. A historically selected research arm does not replace the accepted release.

## Review development outputs

Start with:

- `recent_history_build_report.json`
- `benchmark_inventory.csv` and `benchmark_raw_file_inventory.csv`
- `historical_comparison_summary.csv` and `historical_rate_comparison_summary.csv`
- `recent_2023_2025_scores.csv` and `transition_2021_scores.csv`
- `frozen_choices_2026.json`
- `bat_short_history_scores.csv`

Other key files:

- `projection_table_2026_hitters.csv`, `projection_table_2026_pitchers.csv`: wide tables, separate rows for accepted and historically selected research sources. Names are display-only warehouse identities, with an MLBAM-ID fallback.
- `frozen_2026_forecasts.csv`, `frozen_2026_skill_rates.csv`: all research arms, including controls and exploratory bat predictions.
- `composition_ledger.csv`: raw skill rate/count, coherent count and adjustment, accepted count and fallback status.
- `component_provenance_2026.csv`: component source and explicit accepted-group fallbacks.
- `historical_scores.csv`, `historical_fitted_scores.csv`, `historical_rate_scores.csv`, `historical_forecasts.csv`: season/player/metric research evidence.
- `composition_support.csv`, `fold_fit_chronology.csv`, `feature_family_availability.csv`: support, fitting chronology and measurement availability.
- `fold_models_<year>.json`, `frozen_models_2026.json`, `historical_gate_evidence.json`, `rolling_choices.json`: complete reproducible model/selection evidence.
- `frozen_benchmark_predictions.csv`, `benchmark_identity_exceptions.csv`: the external comparison snapshot and identity exceptions, never modeling inputs.

## Separate 2026 evaluation

The evaluator verifies the entire forecast freeze and unchanged label reference, then reads eligible 2026 labels. **2026 has already been reviewed; it is reporting data, not an untouched holdout.** No model, weighting, feature set, cap or gate is fitted or changed during evaluation.

Start with:

- `recent_history_evaluation_report.json`
- `evaluation_skill_rate_scores.csv`
- `evaluation_scores.csv` and `evaluation_fitted_scores.csv`
- `matched_benchmark_scores.csv`
- `benchmark_comparison_coverage.csv`

Player-level files are `evaluation_player_comparisons.csv` and `matched_benchmark_player_comparisons.csv`. The former reports all research arms with fitted-group support and explicit missing/ineligible statuses. The latter uses common eligible pools for accepted/selected/source comparisons, each available benchmark separately, and all available benchmarks together. Exposure and history cohorts use identical memberships within every comparison group. Sources absent for a metric are not substituted or zero-filled. Rate metrics additionally need eligible positive actual denominators. Actual zero counts remain valid labels. Participants outside the frozen homegrown population are reported in `actual_participants_outside_forecast_universe.csv` and never added based on their 2026 outcomes.

Full score tables include accepted-group fallbacks. Fitted-only tables isolate supported research forecasts. The native record-level metric exclusions remain in force. Missing/ineligible labels are never replaced by another source's actuals.

## 2027 plan

`plan_2027.json` records **2023–2026** as the primary player-history window, emphasizing 2026 and 2025. It does not invent four-year weights or fit 2027 projections. A subsequent build must prepare a fourth lag and compare four-year weighting choices chronologically before fitting 2027. Older player-history fallback remains disabled unless explicitly defined. Older target seasons can still teach forecasting relationships and audit stability.

All outputs are retrospective preseason reconstructions using prior event seasons, not independently archived as-of forecasts. Prospect/international/returner coverage and dated availability inputs remain separate work. No draft-tool integration or accepted-source promotion occurs here.
