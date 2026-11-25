v1.40 — readable frozen projection review

Extract into D:\JonAPythonClass\pycharm\PlayerValuation alongside v1.31/v1.39 and prior shared helpers.
  python -m unittest discover -s tests -p "test_projection_review_v1_40.py" -v
  python projection_review_v1_40.py

Inputs:
  --export outputs/2027_side_by_side_v1_39
  --baseline outputs/homegrown_2027_v1_31
  --benchmarks data/benchmarks_2027
Output:
  outputs/projection_review_v1_40
Use --output for a fresh destination; existing output is never overwritten.
Complete verified backup goes under backups.

Requires the four original 2026-11-13 snapshot files named by v1.31 FILES:
2027steamerhitters111326.csv, 2027steamerpitchers111326.csv,
2027fgdepthchartshitters111326.csv, 2027fgdepthchartspitchers111326.csv.
Hashes must match the frozen v1.31 bindings; do not replace them with newer exports.
The v1.39 export must also bind to that same v1.31 release.
Snapshot dates are inherited from the original registration, not independently certified.

Outputs:
named_2027_hitters.csv / named_2027_pitchers.csv: all original v1.39 values plus
name, name_status, name_evidence, feature_vintage, eligible_2026_metrics.
Names join only on role + MLBAM ID; Steamer is the explicit display priority
when both snapshots provide names. Alternate spellings are reported, not used
to match or merge players. Rows with no benchmark name remain unresolved.

feature_vintage:
CURRENT_2026_ALL_FOUR: four eligible 2026 metrics
CURRENT_2026_PARTIAL: one to three eligible 2026 metrics
OLDER_ONLY: eligible 2023-25 observations but no eligible 2026 observation
NO_ELIGIBLE_FEATURES: no eligible observation
This describes measurement vintage, not whether a full vector or baseline is supported.
The original status column remains the model-support status.

named_largest_changes.csv / named_player_adjustments.csv:
original skill-adjustment rows plus ID-linked names and feature-vintage labels.

matched_baseline_comparisons.csv:
weighted baseline versus each snapshot, per player and available metric.
Signed delta = homegrown minus benchmark. Missing values remain unscored.
Only the weighted baseline is benchmarked; skill challengers remain research columns.

benchmark_disagreement_summary.csv:
PAIRWISE and COMMON_BOTH comparison pools. COMMON_BOTH requires the player
and metric in both systems; membership hashes permit identical-pool checks.
Mean absolute differences describe disagreements, NOT predictive accuracy.
No 2027 actuals or 2026 evaluation outcomes are read.

largest_baseline_benchmark_differences.csv:
top 30 absolute differences per system, role and metric. large_difference uses
the inherited metric-specific v1.31 thresholds where defined; ranking includes
smaller differences if fewer than 30 are large. Never rank across statistic units.

workload_rate_disagreements.csv:
count delta = (home exposure - benchmark exposure) * benchmark rate
            + home exposure * (home rate - benchmark rate).
This is an exact accounting of FORECAST disagreements, not attribution of errors.
PA is the exposure for hitter HR/R/RBI/SB; IP for pitcher SO/W.
Zero or missing exposure prevents rate decomposition. No QS starts model is invented.

ranked_player_coverage.csv:
matched, homegrown-only and benchmark-only players, ordered within source/role/status
by the larger available projected exposure (PA or IP). No missing forecast is zero-filled.
identity_exceptions.csv and benchmark_input_exceptions.csv keep gaps explicit.

Five tests cover names, exact ID/role joins, vintage, matched pools, count accounting,
missing-versus-zero, source bindings, end-to-end synthetic build, immutable inputs,
backup equality and no-overwrite behavior.
The uploaded production tables were also checked through the core review function:
2,211 rows had names from exact benchmark IDs; 300 remained unresolved.
Full project manifest verification must run on your local project.

No forecasts, model choices or default sources change. weighted_actuals and
accepted_ip remain default; hybrid QS blank; valuations off. No additional validation.
