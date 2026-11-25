v1.41 — read-only baseline reliability audit

Extract into D:\JonAPythonClass\pycharm\PlayerValuation alongside the installed prior releases.
No 2022 data or v1.38 run is needed.
Run:
  python -m unittest discover -s tests -p "test_baseline_reliability_v1_41.py" -v
  python baseline_reliability_v1_41.py

Default output: outputs/baseline_reliability_v1_41
Use --output with a fresh destination if that folder exists. Complete backup under backups.

Reads the verified v1.40 named tables; v1.31 baseline source bindings; frozen training
and holdout labels; historical v1.27 participation overlay; certified v1.29 2026
appearance overlay; and the four original November 13 benchmark snapshots.
2026 actuals are read only as past history for 2027, not for candidate selection.
No evaluation scores are read.
Run python baseline_reliability_v1_41.py --help for path overrides.

Outputs:
player_history_reliability.csv:
  known/unknown/zero exposure per year, latest positive season, number of positive
  seasons, projected PA/IP, raw recorded PA/OUTS, and diagnostic flags.
  A missing latest season is unknown, not zero; zero OUTS with G>0 is an appearance.
  Flags identify positive forecasts without recent positive exposure, not proof that
  a player is inactive or unavailable. No dated 2027 roster inputs are supplied.

rate_component_samples.csv:
  every AVG/OPS/ERA/WHIP primitive's actual numerator and denominator by source year,
  fixed recency weights, paired years, unweighted paired totals, weighted totals,
  and weighted component rate.
  These are label-eligible MLB samples only; they do not include minor/overseas data.
  Missing or excluded primitives remain missing and are not fabricated.
  Composite rates need not share a single sample: AVG/OPS use separate hit-component
  rates; OPS also depends on PA-based BB/HBP/SF/AB estimates; ERA uses ER/OUTS;
  WHIP uses H/OUTS and BB/OUTS separately.
  Numeric v1.31 reconstruction must reproduce the frozen baseline first.
  Hitter coherence adjustments and pitcher bounds are inherited, not removed.
  Extreme estimates are NOT clipped or corrected.

extreme_rate_samples.csv:
  component sample rows for estimates outside fixed diagnostic bounds:
  AVG .150–.350; OPS .400–1.100; ERA 1.50–7.00; WHIP .80–1.80.
  Bounds are review triggers, not fitted thresholds, physical validity limits,
  stabilization guarantees or candidate-selection settings.

prioritized_exceptions.csv:
  one row per player issue, ranked WITHIN ROLE by projected PA/IP descending.
  Multiple issues for the same player are deliberately retained.
  Low recorded history triggers: under 200 PA or under 150 OUTS (50 IP).
  Limited positive history: fewer than two positive seasons.
  Do not sum raw pitcher OUTS as decimal baseball innings.

benchmark_save_hold_raw_audit.csv:
  source file, row, raw text, numeric value and classification for every SV/HLD cell.
  COLUMN_ABSENT, BLANK_MISSING, EXPLICIT_ZERO and POSITIVE_VALUE stay distinct.
  Original raw fields are preserved. Invalid numerics fail rather than become zero.
benchmark_save_hold_summary.csv:
  counts and exported totals per system/metric. An all-zero numeric column is
  flagged for scope review. Mixed values do not certify each individual zero.
  A zero remains the exported value; no automatic placeholder interpretation or
  metric substitution is performed.
diagnostic_contract.json: fixed audit definitions, not fitted policy.

Default inputs:
--review outputs/projection_review_v1_40
--baseline outputs/homegrown_2027_v1_31
--labels outputs/training_labels_v1_0
--overlay outputs/participation_label_overlay_v1_27
--research outputs/recent_history_skills_v1_23
--evaluation outputs/pitcher_evaluation_v1_29
--benchmarks data/benchmarks_2027

Local checks: six tests cover paired missing/zero data, distinct component denominators,
stale/zero/appeared histories, priority ranking, source-cell scope, future/duplicate
identities, immutable forecasts and numeric replay rejection.
The full production labels are not available in the build environment, so the
source-bound production audit must run in the user's project.
The core benchmark audit was run on the supplied original snapshots:
Steamer SV: 5050 zero / 120 positive; HLD: 4628 zero / 542 positive.
Depth Charts SV: 714 zero / 120 positive; HLD: 292 zero / 542 positive.
No blank or missing columns for either metric in these exports.

Next research stage (not fitted or promoted by this build):
  1. A sample-size regression candidate with workloads frozen.
  2. A workload-freshness candidate with skill rates frozen.
Develop and score separately using earlier-origin folds, known participation zeros
and matched eligible pools, retaining unfavorable seasons. 2026 stays disclosed
reporting data for any such selection exercise. No candidate settings are selected
from the 2027 benchmark disagreements.

All forecasts are preserved. weighted_actuals and accepted_ip remain defaults,
hybrid QS stays blank, and valuation wiring remains off.
