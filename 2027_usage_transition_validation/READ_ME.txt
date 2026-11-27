FIXED USAGE-TRANSITION HISTORICAL VALIDATION

{
  "status": "FIXED_TEST_COMPLETE_NOT_ADOPTED",
  "origins": [
    2023,
    2024,
    2025
  ],
  "players_by_role": {
    "hitter": 4416,
    "pitcher": 4501
  },
  "prediction_rows": 8917,
  "supported_rows": 8134,
  "fallback_rows": 783,
  "unscored_quarantined_rows": 1,
  "baseline_fields_replayed": 151504,
  "models_fitted": 3,
  "maximum_fit_target": 2024,
  "forecast_errors_2026_scored": false,
  "registered_model_changed": false,
  "thresholds_changed": false,
  "production_changed": false,
  "role_decisions": [
    {
      "role": "hitter",
      "mean_objective_MSE_ratio": 0.9417327330676272,
      "workload_pass": false,
      "core_reasons": [],
      "extra_reasons": [
        "SUBGROUP_WORKLOAD_GUARD_RECENT_POSITIVE",
        "UNSUPPORTED_GUARD_KNOWN_ZERO_RECENT"
      ]
    },
    {
      "role": "pitcher",
      "mean_objective_MSE_ratio": 1.0335285756344532,
      "workload_pass": false,
      "core_reasons": [
        "LOW_HISTORY_GUARD",
        "METRIC_REGRESSION_IP",
        "NO_ONE_PERCENT_MSE_IMPROVEMENT",
        "RECENT_GUARD_2024"
      ],
      "extra_reasons": [
        "SUBGROUP_WORKLOAD_GUARD_RECENT_POSITIVE",
        "SUBGROUP_WORKLOAD_GUARD_STARTER",
        "SUBGROUP_WORKLOAD_GUARD_SWING",
        "SUBGROUP_WORKLOAD_GUARD_RELIEVER",
        "OPPORTUNITY_COUNT_GUARD_GS"
      ]
    }
  ],
  "conditional_complete_count_build_triggered": false
}

METHOD
The frozen executable model was used unchanged. For2023 train targets2020–2022;2024 uses2020–2023;2025 uses2020–2024. The pre-scoring freeze binds models, all predictions and exact metric/cohort memberships before error calculation. The baseline accepted workload vector is independently replayed against the saved original historical vectors. Candidate-only nonappearance certificates supply shared truth and candidate states; they are not injected into baseline history. Planned calendar is162; realized target calendar is used only to invert registered labels to observed counts.

MEMBERSHIPS
SUPPORTED is the frozen eligible candidate with known target. FALLBACK keeps the entire baseline workload. FULL_COHORT includes both on common known targets. Quarantined targets remain in prediction reporting but are unscored. Secondary pitcher batting is unsupported by design, not silently removed from full-cohort reporting. Sparse pool backoff is the registered model rule; pool and training support are exposed. No source year2026 is a scoring target.

GUARDS
The original phase.gate implementation applies workload mean improvement, fold/sample, recent and low-history requirements without alteration. The previous role/freshness and pitcher G/GS safeguards retain their thresholds. Unsupported safeguards are explicit failures. Internal method aliases weighted_actuals/freshness_workload only execute original guard math; report labels identify V1_43 and USAGE_TRANSITION.

COUNTS AND ADOPTION
This model emits workload only. It does not alter skill rates or publish incomplete replacement stat lines. Full fantasy-count and team-opportunity safeguards are not claimed to pass; adoption remains blocked. A passing workload role would trigger a separately specified complete-count/team handling build. Failed workload roles do not trigger that conditional build. Current charts, international estimates, development adjustments and rejected models remain inactive. Retrospective development years are not a new independent holdout.


FINAL REVIEW
Neither role cleared all workload protections, so the conditional complete-count/team-opportunity build is not triggered. The hitter average improvement does not justify adoption: among supported players with recent positive MLB exposure, mean PA MSE worsened25.46%. Its known-zero-recent subgroup lacks the required sample support; that safeguard is reported unsupported, never waived. Pitcher mean IP MSE worsened3.35%, with low-history/recent-origin and role/freshness protections failing; the GS count guard also failed. No method was revised after these errors were seen.

All8917 registered scoring-period player-seasons remain in prediction reporting:8134 supported and783 fallback, including one quarantined target without a score. Fallback values equal the baseline. FULL_COHORT score tables include all8916 known-target records on exactly paired memberships. Hitter rates of improvement differ slightly between supported-only and full-cohort means because the unchanged fallback rows contribute error.

The independent verification recomputed candidate workload directly from frozen node probabilities/means, checked all fallback workload values, and recalculated ALL-cohort error statistics and membership hashes. It did not refit a model. This test is development evidence over previously reviewed years, not a new untouched holdout.
