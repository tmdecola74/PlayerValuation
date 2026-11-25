Extract alongside v1.35 in PlayerValuation. From the project root:

    python -m unittest discover -s tests -p "test_statcast_skill_ablation_v1_36.py" -v
    python statcast_skill_ablation_v1_36.py

Same frozen paths as v1.35; no 2026 leaderboard file is required.
New output: outputs/2027_statcast_ablation_v1_36. Existing files stay intact.

For hitters, adjust 2B and 3B, keeping 1B and HR fixed; XBH includes fixed HR.
For pitchers, adjust only SO. Workload, walks, WHIP and QS remain fixed.
The residual-only control estimates the exposure-weighted mean residual on
the same rows used by the full and leave-one-feature-out models. All apply
the same half-strength/capped adjustment, and all require common feature
support to isolate the effect; missing support falls back to baseline.
Workload bands use projected PA (<200, 200–449…, 450+) and IP
(<30, 30–99…, 100+) and are never defined by realized workload.

Compare full versus residual-only in statcast_incremental_deltas.csv:
negative values favor full Statcast. For feature ablations, negative full
minus without-feature indicates lower error when the feature was included,
conditional on the other features. All arms have matched membership per
score row. See historical_2025_scores.csv and reporting_only_2026_scores.csv
for absolute RMSE, MAE, bias and sample counts.

The 2025 comparison fits on 2024 targets, and the 2026 reporting-only
comparison fits on 2024–2025 targets before opening holdout labels.
Single historical fold, exploratory; no feature selection.
accepted_ip default stays fixed; hybrid QS stays blank; valuations stay off.
No 2027 forecasts overwritten.
