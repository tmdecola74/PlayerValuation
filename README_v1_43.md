v1.43 — published skill-regressed release, baseline workload unchanged

Extract into D:\JonAPythonClass\pycharm\PlayerValuation alongside installed v1.42
and prior shared dependencies. No new downloads, feature search or model fitting.

Run in this order:
  python -m unittest discover -s tests -p "test_skill_regressed_release_v1_43.py" -v
  python skill_regressed_release_v1_43.py
  python evaluate_skill_release_v1_43.py

Publication output:
  outputs/skill_regressed_release_v1_43
Separate evaluation output:
  outputs/skill_regressed_release_v1_43_evaluation
Both reject existing output folders. Use --output with a fresh folder if rerunning;
the evaluator's --release must point to the new publication path.
Complete verified backups go under backups.

PUBLISHED DEFAULTS
projections_2027_hitters.csv
projections_2027_pitchers.csv
One row per frozen v1.42 player-role; standard stat columns, names, support/fallback,
coherence and coverage exceptions, source version and method metadata.
These now contain the skill-regressed candidate values, not the old weighted
baseline, except where the entire skill group is unsupported.

Hitter mutable fields: 1B/2B/3B/HR/H/AVG/OBP/SLG/OPS.
PA/AB/R/RBI/SB/BB/HBP/SF/SH stay exactly at baseline.
Pitcher mutable fields: H/ER/BB/SO/HR/ERA/WHIP.
IP/OUTS/W/G/GS/QS/SV/HLD/SV+HLD stay exactly at baseline.
This specifically publishes the v1.42 regression arm. No additional Statcast overlay,
workload rule, clipping policy, prior strength or benchmark adjustment is introduced.
Pitcher baseline QS is preserved; hybrid QS is blank.
Valuation wiring stays off.

REFERENCES
references/original_baseline_2027_hitters.csv
references/original_baseline_2027_pitchers.csv
  Byte-preserved original baseline exports.
references/unchanged_pitcher_workload_saves_holds.csv
  Original anchors as a separately readable reference.
references/inactive_workload_challenger_2027_hitters.csv
references/inactive_workload_challenger_2027_pitchers.csv
  Explicitly inactive research only; pitcher workload QS remains blank.
references/v1_42_frozen_choices.json
references/v1_42_source_bindings.json
  Prior coefficients/decisions and historical source hashes.

release_exceptions.csv retains unresolved names, stale/sparse history, missing labels
and unsupported skill groups. Extreme flags are recalculated from the new release;
baseline-only extreme flags are not blindly copied.
baseline_to_release_changes.csv logs every published metric versus original baseline.
Coherence failure or changed workload/opportunity anchor prevents publication.
A coherent forecast is not necessarily an accurate forecast or a confirmed roster member.
No player population is expanded; minor-league/overseas/prospect gaps remain explicit.

FROZEN 2026 REPORTING
The publication also writes frozen_2026_forecasts.csv and publication_freeze.json.
2026 forecasts use only 2022–2025 player history, with frozen population priors
through 2025. This is the four-season recipe already tested in v1.42, not a claim
to use only 2023–2025 or an archived original preseason release.
2027 projections inherit 2023–2026 player history from frozen v1.42 values.
No 2026 outcome file is opened during v1.43 publication.

evaluate_skill_release_v1_43.py verifies the published hashes before opening
2026 eligible labels and the certified v1.29 G/OUTS overlay. It does not fit, select,
retune or write into the publication. 2026 was already repeatedly reviewed and
remains disclosed reporting data, not independent confirmation.

Evaluation reports:
evaluation_2026_scores.csv — MSE/RMSE/MAE/bias, identical paired memberships.
evaluation_2026_deltas.csv — release minus baseline RMSE/MAE; negative favors release.
evaluation_2026_player_comparisons.csv — actuals, both forecasts and signed errors.
evaluation_2026_participation_coverage.csv — known appeared/non-appeared/unknown.
evaluation_report.json — reporting-only status and freeze checksum.

Pools: MATCHED_ALL, SUPPORTED, BASELINE_FALLBACK.
Cohorts: all, prior history, prior sample size, known participation and actual exposure.
ERA/WHIP require positive eligible actual OUTS; hitter rates require positive AB.
Actual IP cohorts: <20, 20–<100, >=100; actual PA: <200, 200–<450, >=450.
These outcome cohorts diagnose the frozen release; they never select settings.
Count populations may differ by metric: unknown SO/W/etc remain unknown even
where certified non-appearance establishes G=0 and OUTS=0. No zeros are fabricated.
Actual IP is derived exactly from eligible OUTS/3, not decimal baseball notation.

SOURCE / DECISION CHECKS
Requires v1.42 historical SKILL gates eligible for BOTH roles and the original fixed
experiment contract. Gate definitions, prior strengths and model coefficients cannot
be edited for this publication. 2026 actuals cannot choose the winning settings.
The workload gate is not used for adoption; all workload research remains inactive.

Default paths:
Publisher:
--phase outputs/projection_phase_v1_42
--labels outputs/training_labels_v1_0
--overlay outputs/participation_label_overlay_v1_27
--research outputs/recent_history_skills_v1_23
Evaluator:
--release outputs/skill_regressed_release_v1_43
--labels outputs/training_labels_v1_0
--evaluation outputs/pitcher_evaluation_v1_29

Eight local tests cover exact frozen-candidate publication, unchanged anchors,
missing-label fallback, coherent vectors, original decision contract, earlier-only
forecast generation, paired/exposure scoring, certified zeros vs unknown counts,
publication-before-evaluation, outcome-mutation isolation, source immutability,
complete backup equality and tamper/no-overwrite.
End-to-end filesystem tests use synthetic fixtures and isolate prior data adapters.
Production source files must be verified by running in your project.

No claim every metric or season improved. The accepted historical skill bundles
passed the original aggregate/guard contract; e.g. hitter OPS and pitcher SO can
still have unfavorable seasons or cohorts. Remaining release exceptions and the
already-reviewed 2026 scores must be disclosed. No valuation enablement is implied.
