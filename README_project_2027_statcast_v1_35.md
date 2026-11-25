# 2027 Statcast research export v1.35

Extract in the PlayerValuation project root alongside the installed v1.31
and the Windows-compatible v1.23.1/overlay dependencies. Uses the same
virtual environment (NumPy and DuckDB). Run from the project root:

```powershell
python -m unittest discover -s tests -p "test_project_2027_statcast_v1_35.py" -v
python project_2027_statcast_v1_35.py
```

Requires existing manifest-verified outputs: homegrown_2027_v1_31,
statcast_leaderboards_v1_21 (including 2026 quarantine), training_labels_v1_0,
participation_label_overlay_v1_27, and recent_history_skills_v1_23.
Use --help to override paths. No downloads or edits to existing inputs.
The default output folder is outputs/homegrown_2027_statcast_v1_35; choose
a fresh --output for a repeat run. A complete backup is verified on publish.

- baseline_2027_hitters.csv / baseline_2027_pitchers.csv: byte-for-byte
  copies of frozen v1.31 forecasts. Despite the v1.31 column alias, this
  2027 export's IP is weighted actuals, not a regenerated legacy model.
- statcast_2027_hitters.csv / statcast_2027_pitchers.csv: same identities and
  workload, with candidate skill overlays, source years and fallback statuses.
- comparison_2027_hitters.csv / comparison_2027_pitchers.csv: long-format
  baseline and challenger fields side by side. largest_changes_by_metric.csv:
  up to 30 largest absolute differences per role and metric.
- player_input_coverage.csv, statcast_input_audit.csv and
  actual_label_availability.csv: eligible inputs, exclusions, and cohort coverage.
- historical_2025_scores.csv and reporting_only_2026_scores.csv: identical
  eligible rows per metric across methods, pool hashes, RMSE/MAE/bias, including
  per-exposure skill errors. These are reconstructed workload baselines.
- frozen_skill_models.json: coefficients, predictor order, and fold membership years.

The fixed challenger uses GB, LD, FB and pull-air fractions from v1.21, with
the original row-level sample and definition masks; it never substitutes
archive proxies. It pools available seasons with exposure and 1:2:3:4
recency weighting. It adjusts hitter 1B/2B/3B and pitcher SO/BB, then derives
affected ratios. The overlay uses half of the fitted residual capped at
half of the baseline count. An unsupported row keeps baseline values.
Bat tracking, exit velocity and baserunning are audited only. The 2026
leaderboard rows use v1.21 checks; they were not event-reconciled by v1.22
and do not constitute an independent preseason archive. Batted-ball inputs
are experimental even when they pass normalization.

Forecast 2025 fits on 2024 targets only. The 2026 reporting comparison and
2027 challenger use the same coefficients fit on 2024–2025 targets. No
2026 outcome is used to fit or select the challenger. The 2027 projections
use available 2023–2026 batted-ball history and the frozen actuals baseline.
There is no point-in-time claim for this retrospective experiment.
No production default changed; valuation export remains off. PA, IP,
HR, ERA, wins, baseline QS, saves and holds remain frozen, and hybrid QS
is blank. No new prospect or playing-time model.
