# PlayerValuation v1.19 — coherent skill-group experiment

Install by extracting this ZIP into the existing PlayerValuation project root. It adds versioned files and preserves v1.17/v1.18, the accepted homegrown release, and all frozen inputs. Requires the installed v1.17/v1.18/v1.16 modules and their existing dependencies. No new packages are needed.

## Historical experiment

```powershell
python -m unittest discover -s tests -p "test_coherent_skill_groups_v1_19.py" -v
python coherent_skill_groups_v1_19.py
```

Default output: `outputs/coherent_skill_groups_v1_19`. Inputs are `outputs/statcast_incremental_v1_17`, `outputs/training_labels_v1_0` and `outputs/standalone_lagged_features_v1_0`. A verified complete backup is created under `backups`. Existing outputs are rejected; use `--output` with a fresh path for reruns.

This experiment reuses v1.17's saved chronological **raw standard and Statcast rates**, not its individually selected components. It does not refit the regressions or their preprocessing. The new experiment is the grouped substitution and end-to-end historical acceptance test.

## Two independent groups

| Role | Rates replaced together | Primary resulting statistics | Frozen fields |
|---|---|---|---|
| Hitter | 1B/AB, 2B/AB, 3B/AB, HR/AB | AVG, OPS, HR | Accepted PA, AB, BB, HBP, SF, SH, R, RBI, SB |
| Pitcher | H/OUTS, BB/OUTS | WHIP, H, BB | Accepted OUTS/IP, HR, ER/ERA, K, W, QS, SV, HLD, SV+HLD |

Each group tests two alternatives: `group_standard` and `group_statcast`. Both compare **directly with accepted forecasts**. An arm does not have to beat the other arm to pass, but must pass every accepted-reference gate. The passing arm with the lower overall objective is selected; exact ties favor standard. Neither passing retains accepted. The groups can make different choices.

Hitter hit fractions normalize only if their sum exceeds one; H, AVG, OBP, SLG and OPS are then derived coherently. There is no PA-fraction recomposition: accepted AB and every non-hit primitive remain exact. Pitcher H is floored at accepted HR if needed, keeping HR frozen. Every adjustment is logged. Missing group rates or required accepted components retain that player's accepted vector with an explicit fallback. Missing values never become zero.

## Fixed policy, declared before the production experiment

`config/coherent_skill_groups_v1_19.json` is immutable for this version; edits are rejected. The following controls are fixed research choices, not optimized values or statistical significance thresholds.

- Origins: historical 2019–2025; decisions for 2026 use only history through 2025.
- At each origin, calculate decisions **before adding that origin's errors**.
- Minimum three earlier scored seasons, with at least 30 common fitted player-seasons per season. Insufficient support retains accepted.
- Primary objective: equal-weight mean across seasons and group metrics of `candidate MSE / accepted MSE`. Require at least **1% improvement** (ratio ≤ 0.99). Normalization prevents counts and ratios from being added in incompatible units.
- Each metric must have mean normalized MSE ratio ≤ 1.01 and equal-season MAE ratio ≤ 1.01.
- Recent guard: both immediately preceding experiment seasons must have support; do not skip an unfavorable or unsupported recent season. Objective ratio ≤ 1.01; every metric MSE/MAE ratio ≤ 1.02.
- History guards: low history ≤ one prior season and established history ≥ two prior seasons. Each requires at least two supported earlier seasons and 20 common fitted rows per season. Objective ratio ≤ 1.01; every metric MSE/MAE ratio ≤ 1.02.
- Zero reference MSE/MAE is not divided by zero and cannot establish an improvement. Missing metric evidence rejects the arm.
- 2020 and 2021 stay in the experiment. The first possible decision with three earlier experiment seasons is 2022. Actual-exposure cohorts are reporting-only, never preseason selection rules.

The gate's bundle pool requires eligible labels for **all** group metrics, positive eligible actual AB/OUTS for the role, supported candidates and fitted component models in **both** arms. Accepted, standard and Statcast use exactly the same rows in each gate. History guards use prior-feature history. Missing labels remain unknown. Reporting also includes metric-specific paired pools; the separate fitted summaries exclude unsupported/unfitted candidate cases but do not impose the gate's complete-label bundle.

## Outputs to review first

- `group_build_report.json`: historical final choices, preservation and chronology checks.
- `rolling_choices.json`: every arm's objective, metric checks, support, recent/history guards and rejection/pass decisions at each origin.
- `historical_comparison_summary.csv`: full-statistic paired comparisons against accepted, including equal-season error.
- `historical_fitted_summary.csv`: comparisons restricted to jointly supported, fitted group candidates.
- `group_reproduction_summary.csv`: player-season counts whose final group forecasts already match accepted versus genuinely differ.
- `recent_2023_2025.csv` and `transition_2021.csv`: year/cohort scoring, with paired membership hashes.

Detailed local evidence:
- `historical_gate_evidence.csv`: common bundle pools and per-season/per-cohort errors used by the gates.
- `historical_forecasts.csv`: complete long-format accepted, standard-group, Statcast-group and historical-selected forecasts.
- `historical_component_ledger.csv`: changed group fields, original values, candidates, deltas, normalization/floor and support flags.
- `group_support.csv`: supported/fitted status, fallback reason and group composition controls, including frozen 2026 forecasts.
- `historical_scores.csv`, `historical_fitted_scores.csv`, `historical_label_coverage.csv`, `historical_outliers.csv`: scoring and exceptions.
- `experiment_contract.json`, `frozen_choices_2026.json`, `forecast_freeze.json`: frozen policy, historical decisions and output bindings.
- `frozen_2026_forecasts.csv`, `frozen_2026_component_ledger.csv`: generated only after the historical choices are fixed; no 2026 actuals read.

These are research outputs, not an automatic replacement for the accepted projection source. The original models' retrospective source-vintage limitations remain. Reusing inspected historical folds makes this development research, not independent confirmation.

## Separate 2026 reporting

After the historical build completes, this command reports the frozen choices without fitting or selection:

```powershell
python evaluate_coherent_skill_groups_v1_19.py
```

Default output: `outputs/coherent_skill_groups_v1_19_evaluation`, with its own complete backup. It verifies the frozen choices and input bindings, then reads separate eligible 2026 labels. No thresholds, choices, caps, coefficients or forecasts change. It writes `group_evaluation_report.json`, `evaluation_comparison_summary.csv`, `evaluation_fitted_summary.csv`, scores, coverage and player outliers. **2026 is previously reviewed reporting data; it is not an untouched holdout or a selection source.**

Return the build report, rolling choices, historical comparison/fitted summaries, reproduction summary and recent/2021 CSVs first. Keep detailed forecasts and ledgers locally for follow-up. If you run the evaluator, return its report and comparison/fitted summaries separately.
