EXECUTABLE USAGE-TRANSITION MODEL REGISTRATION

{
  "status": "REGISTERED_EXECUTABLE_UNSCORED",
  "historical_panel_rows": 17907,
  "eligible_panel_rows": 15917,
  "ineligible_rows": 1990,
  "exclusion_counts": {
    "SECONDARY_PITCHER_BATTING": 1988,
    "UNKNOWN_OR_QUARANTINED_TARGET_USAGE": 1,
    "QUARANTINED_LATEST_PLAYER_SEASON": 1
  },
  "target_years": [
    2020,
    2021,
    2022,
    2023,
    2024,
    2025
  ],
  "historical_models_fitted": 0,
  "historical_errors_scored": 0,
  "synthetic_tests_passed": 19,
  "real_data_support_preflight": [
    {
      "origin": 2023,
      "role": "hitter",
      "training_target_years": "2020;2021;2022",
      "known_labels": 3640,
      "positive": 1633,
      "zero": 2007,
      "state_counts": "{\"NO_PA\": 2007, \"REGULAR_STARTER\": 991, \"LIMITED_OR_BENCH\": 326, \"PART_TIME_STARTER\": 316}",
      "pure_start": 0,
      "pure_relief": 0,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2023,
      "role": "pitcher",
      "training_target_years": "2020;2021;2022",
      "known_labels": 4143,
      "positive": 1956,
      "zero": 2187,
      "state_counts": "{\"NO_PITCHING_APPEARANCE\": 2187, \"RELIEF\": 857, \"ROTATION\": 429, \"SWING_OR_LIMITED\": 670}",
      "pure_start": 371,
      "pure_relief": 1096,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2024,
      "role": "hitter",
      "training_target_years": "2020;2021;2022;2023",
      "known_labels": 4850,
      "positive": 2175,
      "zero": 2675,
      "state_counts": "{\"NO_PA\": 2675, \"REGULAR_STARTER\": 1357, \"LIMITED_OR_BENCH\": 397, \"PART_TIME_STARTER\": 421}",
      "pure_start": 0,
      "pure_relief": 0,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2024,
      "role": "pitcher",
      "training_target_years": "2020;2021;2022;2023",
      "known_labels": 5596,
      "positive": 2624,
      "zero": 2972,
      "state_counts": "{\"NO_PITCHING_APPEARANCE\": 2972, \"RELIEF\": 1137, \"ROTATION\": 575, \"SWING_OR_LIMITED\": 912}",
      "pure_start": 496,
      "pure_relief": 1453,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2025,
      "role": "hitter",
      "training_target_years": "2020;2021;2022;2023;2024",
      "known_labels": 6028,
      "positive": 2715,
      "zero": 3313,
      "state_counts": "{\"NO_PA\": 3313, \"REGULAR_STARTER\": 1719, \"LIMITED_OR_BENCH\": 478, \"PART_TIME_STARTER\": 518}",
      "pure_start": 0,
      "pure_relief": 0,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2025,
      "role": "pitcher",
      "training_target_years": "2020;2021;2022;2023;2024",
      "known_labels": 7078,
      "positive": 3297,
      "zero": 3781,
      "state_counts": "{\"NO_PITCHING_APPEARANCE\": 3781, \"RELIEF\": 1438, \"ROTATION\": 733, \"SWING_OR_LIMITED\": 1126}",
      "pure_start": 649,
      "pure_relief": 1830,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2026,
      "role": "hitter",
      "training_target_years": "2020;2021;2022;2023;2024;2025",
      "known_labels": 7273,
      "positive": 3275,
      "zero": 3998,
      "state_counts": "{\"NO_PA\": 3998, \"REGULAR_STARTER\": 2063, \"LIMITED_OR_BENCH\": 570, \"PART_TIME_STARTER\": 642}",
      "pure_start": 0,
      "pure_relief": 0,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    },
    {
      "origin": 2026,
      "role": "pitcher",
      "training_target_years": "2020;2021;2022;2023;2024;2025",
      "known_labels": 8644,
      "positive": 3996,
      "zero": 4648,
      "state_counts": "{\"NO_PITCHING_APPEARANCE\": 4648, \"RELIEF\": 1742, \"ROTATION\": 904, \"SWING_OR_LIMITED\": 1350}",
      "pure_start": 789,
      "pure_relief": 2220,
      "global_support_pass": true,
      "support_reasons": "",
      "model_fitted": false,
      "errors_scored": false
    }
  ],
  "baseline_changed": false,
  "guard_thresholds_changed": false,
  "source_files_changed": false,
  "forecast_files_published": false,
  "candidate_only_additional_pitcher_zero_certificates": 1116,
  "additional_pitcher_zero_targets_2020_2025": 957
}

LABEL DECISION
Hitters model positive PA, not simply any MLB appearance. Zero PA and no MLB G are distinct labels in the source certificates. Pitchers model credited pitching appearance, retaining zero-out/no-pitch cases. Secondary pitcher batting is a pre-origin fallback rule (>=5 prior-year pitching games and <100 PA); those records are retained in the baseline cohort and disclosed as unsupported rather than silently removed.

EXCEPTIONS
Danny Jansen's2024 player-season remains quarantined for target use and required latest usage in2025. Ryan Jeffers/Sean Keys2026 are outside this historical panel; later2027 feature construction must retain their quarantine. No source count has been repaired.

EXECUTABLE MODEL
usage_transition_model.py exposes usage_state, recent_state, vector, global_support, fit and predict. It has no import-time fitting or I/O. The frozen JSON contract gives thresholds, label/calendar definitions, support, smoothing and hierarchy. Whole-role global support failure and unsupported latest histories retain the full baseline; sparse supported role pools back off deterministically with parent support disclosed. The root and cell means preserve joint workload quantities, so expected starts and innings per start are not multiplied as independent averages. No medical risk, growth bonus, minimum PA/IP floor or chart assumption is imposed.

REGISTRATION AND TESTS
Contract, implementation and preserved guards were hashed before historical panel construction. Historical support counts are preflight only; no estimator was fitted to historical rows and no historical forecast error was scored. Executable tests use synthetic records for probability sums, chronological restrictions, joint partitions, sparse support and fallbacks.

IMPORTANT LIMITS
State definitions and calendar normalization are hypotheses awaiting testing. Pitcher normalized outing counts and hitter PA do not yet form complete fantasy projections. Team opportunity budgets and role/team-dependent count recomputation are not implemented in this arm. No adoption or2027 replacement is possible from this build. Current depth charts, age/development, minor translations, injury effects and rejected workload/Statcast methods remain inactive. Source vintages are retrospective; earlier reviewed years are not new independent holdouts.

NEXT BUILD
Run the fixed model against the unchanged v1.43 baseline for2023/2024/2025 using strictly earlier training targets and frozen supported memberships. Carry every fallback in full-cohort reporting, retain unchanged adoption guards and extra role/freshness/count protections, and report support failures without threshold changes. Keep2026 errors excluded. If workload passes, separately implement/review complete-count and team-opportunity handling before any forecast adoption.


Additional label certification: 1,116 candidate-only pitcher nonappearance certificates cover 2019-2025; 957 close target-label gaps in the 2020-2025 modeling panel. They require complete reconstructed season coverage, a pre-origin positive-OUTS identity and no positive source contradiction. Original labels and baselines remain unchanged. The initial unscored freeze and pre-scoring data amendment are retained. All 19 executable checks use synthetic or structural evidence; none score historical projection errors.
