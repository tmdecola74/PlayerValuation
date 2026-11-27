PLAYER-ANCHORED WORKLOAD RESIDUAL EXPERIMENT

{
  "status": "REGISTERED_EXECUTABLE_UNSCORED",
  "panel_rows": 17907,
  "eligible_rows": 15917,
  "cohort_and_eligibility_unchanged": true,
  "historical_fits": 0,
  "historical_errors_scored": 0,
  "new_forecasts": 0,
  "synthetic_and_structural_tests": 26,
  "retained_declines_and_zeros": [
    {
      "role": "hitter",
      "eligible_rows": 7273,
      "negative_primary_residuals": 2435,
      "zero_primary_exposure_targets": 3998,
      "positive_anchor_to_zero_targets": 841
    },
    {
      "role": "pitcher",
      "eligible_rows": 8644,
      "negative_primary_residuals": 3319,
      "zero_primary_exposure_targets": 4653,
      "positive_anchor_to_zero_targets": 1487
    }
  ],
  "baseline_changed": false,
  "guards_thresholds_changed": false,
  "old_failed_run_reclassified": false,
  "independent_validation_claimed": false
}

DECISION AND DESIGN
One diagnostic-informed experiment is registered, not fitted to historical players. The candidate predicts signed workload change and adds that change to each player's own latest reconciled workload. This replaces the rejected absolute peer mean with an individual offset. Nonappearance and declining seasons remain, including large negative residuals. There is no universal growth bonus, positive PA/IP floor, new injury feature or chart assumption.

EXPOSURE AND COHERENCE
Anchors and targets are normalized by their own observed source-season calendars, preserving the prior calendar policy. Hitter G/PA and pitcher start/relief components remain joint vectors. Only nonnegative feasibility projection is applied, with no positive workload floor. Infeasible positive counts without matching appearances fall back to the entire baseline. Raw vectors/feasibility edits are exposed for a future scored build. The estimator is an unconditional residual point estimator; it does not advertise calibrated role/medical probabilities or uncertainty intervals.

SHARED FRESHNESS LEDGER
Both arms will use the same pre-origin cohort labels: positive, certified zero, or unknown. Original context labels and their provenance remain in the ledger, and the baseline's original numerical inputs/forecasts stay untouched. This fixes a comparison-protocol mapping issue identified in the failed test, not a shortage of all absence evidence. The15-row and2% subgroup thresholds are unchanged. The old failed run is not retroactively relabeled or declared a pass.

SCOPE
The entire17907-record historical comparison pool and prior eligibility rules are retained. Danny Jansen2024 is quarantined as a target and a required latest anchor; Jeffers/Keys2026 remain outside this historical build. Secondary pitcher batting retains its pre-origin fallback. No current charts, age curves, minor/international translations or rejected Statcast predictors enter. Stewart and Misiorowski remain in an unscored source-history appendix, with no candidate projections.

TESTING AND LIMITS
The executable's tests fit synthetic examples only. They check preserved individual workload differences within a shared pool, retained declines/nonappearances, chronology, sparse support and coherent outputs. Historical label/support counts are not accuracy tests. No historical estimator was fitted, no historical forecast errors were scored, and no2026 errors were used. Support floors, prior50 and deterministic pool backoff are fixed before scoring. Full fantasy counts and team-opportunity constraints are still pending future work; no forecast adoption is authorized by this registration.

NEXT BUILD
Run this frozen candidate against unchanged v1.43 for2023/2024/2025 with strictly earlier training and shared freshness labels. Freeze metric memberships before errors, carry every fallback, and retain all prior workload/count/role/freshness guards. Treat results as diagnostic-informed development on already reviewed seasons, not fresh independent validation. Only after workload passes may complete-count and team-opportunity work be separately implemented/reviewed.
