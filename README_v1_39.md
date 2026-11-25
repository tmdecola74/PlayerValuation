v1.39 — 2027 side-by-side research export

Extract into D:\JonAPythonClass\pycharm\PlayerValuation alongside installed v1.31, v1.35, v1.37 and their dependencies. No v1.38 installation or 2022 data is required.

Run from the project root:
  python -m unittest discover -s tests -p "test_project_2027_side_by_side_v1_39.py" -v
  python project_2027_side_by_side_v1_39.py

Default inputs:
  outputs/homegrown_2027_v1_31
  outputs/statcast_leaderboards_v1_21
  outputs/2027_statcast_pull_air_v1_37
Default output:
  outputs/2027_side_by_side_v1_39
Existing output folders cannot be overwritten; use --output for a fresh destination.
A complete timestamped backup is created under backups.

Review:
  side_by_side_2027_hitters.csv
  side_by_side_2027_pitchers.csv
Columns use method__metric:
  weighted_actuals__SO, residual_only__SO, pull_air_only__SO, etc.
Each player appears once in each role's table. Default method remains weighted_actuals.
baseline_2027_hitters.csv and baseline_2027_pitchers.csv are byte-preserved copies.
Original baseline metadata, including prior hybrid context, may appear in the wide table;
only method__metric columns describe the three skill projections. hybrid_qs is blank.

player_adjustments.csv lists every metric for each candidate, its original baseline,
candidate value, signed delta, support status and model checksum.
largest_changes.csv ranks up to 30 nonzero changes per candidate, role and metric.
Compare deltas within a metric; they are not comparable across units.
player_feature_provenance.csv records source year, exported BBE, recency weight,
exposure weight and aggregate predictor. Weights are 1/2/3/4 for 2023/2024/2025/2026,
multiplied by BBE, excluding missing or masked observations.
statcast_input_audit.csv summarizes admission/masking by source year and metric.
frozen_models.json preserves the exact reused model coefficients and preprocessing.
input_hashes.json and output_sha256.json record bindings and output integrity.

No refitting: reuse v1.37's frozen models trained on 2024–2025 targets. 2026 actuals
are inherited only through the frozen 2027 weighted baseline; eligible 2026
leaderboard values enter only 2027 predictors. No evaluation outcome tables are read.
2026 leaderboard scope remains normalization-only, not event-reconciled.

No new validation or candidate selection. The pull-air arm was nominated after
inspecting the only 2025 development fold. The full overlay is not exported as
another candidate here; it remains research evidence in v1.37.
Hitter candidates change only 2B and 3B, recomputing H/AVG/OBP/SLG/OPS.
Pitcher candidates change only SO. The inherited half-strength residual and
50%-of-baseline cap are unchanged. All arms use common full-vector support;
even bias-only retains baseline where full feature support is missing.
Walks, WHIP, workload, wins, ERA, saves, holds, baseline QS and other counts stay fixed.
accepted_ip is the workload default. Hybrid QS stays blank. Valuations remain off.
Population is exactly the frozen v1.31 population; no prospect or roster expansion.

Local verification: six tests cover frozen categories, coherence, missingness,
identity/population guards, recipe validation, full synthetic pipeline, input binding,
no refitting, read-only sources, complete backup and no-overwrite behavior.
The user's full production dataset is not present in the build environment.
