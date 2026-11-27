PLAYER-ANCHORED WORKLOAD DEVELOPMENT VALIDATION

{
  "status": "DEVELOPMENT_TEST_COMPLETE_NOT_ADOPTED",
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
  "supported_rows": 8113,
  "fallback_rows": 804,
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
      "mean_objective_MSE_ratio": 0.6853343981078207,
      "workload_pass": true,
      "core_reasons": [],
      "extra_reasons": []
    },
    {
      "role": "pitcher",
      "mean_objective_MSE_ratio": 0.9711779787103986,
      "workload_pass": false,
      "core_reasons": [
        "LOW_HISTORY_GUARD"
      ],
      "extra_reasons": [
        "SUBGROUP_WORKLOAD_GUARD_SWING"
      ]
    }
  ],
  "conditional_complete_count_build_triggered": true,
  "evidence_status": "Diagnostic-informed development; not fresh independent validation",
  "feasibility_adjusted_supported_rows": 331,
  "shared_freshness_used_for_both_arms": true
}

METHOD
The frozen executable model was used unchanged. For2023 train targets2020–2022;2024 uses2020–2023;2025 uses2020–2024. The pre-scoring freeze binds models, all predictions and exact metric/cohort memberships before error calculation. The baseline accepted workload vector is independently replayed against the saved original historical vectors. Candidate-only nonappearance certificates supply shared truth and candidate states; they are not injected into baseline history. Planned calendar is162; realized target calendar is used only to invert registered labels to observed counts.

MEMBERSHIPS
SUPPORTED is the frozen eligible candidate with known target. FALLBACK keeps the entire baseline workload. FULL_COHORT includes both on common known targets. Quarantined targets remain in prediction reporting but are unscored. Secondary pitcher batting is unsupported by design, not silently removed from full-cohort reporting. Sparse pool backoff is the registered model rule; pool and training support are exposed. No source year2026 is a scoring target.

GUARDS
The original phase.gate implementation applies workload mean improvement, fold/sample, recent and low-history requirements without alteration. The previous role/freshness and pitcher G/GS safeguards retain their thresholds. Unsupported safeguards are explicit failures. Internal method aliases weighted_actuals/freshness_workload only execute original guard math; report labels identify V1_43 and PLAYER_ANCHORED_RESIDUAL.

COUNTS AND ADOPTION
This model emits workload only. It does not alter skill rates or publish incomplete replacement stat lines. Full fantasy-count and team-opportunity safeguards are not claimed to pass; adoption remains blocked. A passing workload role would trigger a separately specified complete-count/team handling build. Failed workload roles do not trigger that conditional build. The shared freshness ledger is used for both arms without modifying baseline numbers or old failed-run decisions. Feasibility edits and fallbacks are exposed. Current charts, international estimates, age/skill-development adjustments and rejected models remain inactive. This design was informed by already reviewed2023–2025 diagnostics, so these results are development evidence and not fresh independent validation.


FINAL DEVELOPMENT REVIEW
The hitter workload candidate passes the registered core and additional workload safeguards: mean supported PA MSE falls31.47%, with9.50% improvement among recent-positive players. The shared known-zero subgroup is now supported under the pre-registered ledger; both arms use the same grouping and the thresholds remain unchanged. This does not relabel the previous failed experiment. The result supports a separate hitter complete-count/team-opportunity build, not immediate forecast adoption.

Pitcher mean supported IP MSE falls2.88%, but the low-history guard fails (mean MSE worsens6.30%) and the swing-role guard fails (+9.11%). These safeguards remain binding. Do not adopt the pitcher method, weaken thresholds or tune the frozen model after these results.

All8917 player-seasons remain visible. There are8113 supported predictions and804 full-baseline fallbacks, including one unscored quarantined target. Of the fallbacks,21 are new infeasible component combinations detected by the registered rules; independent recalculation verifies those conditions.331 supported rows receive the predeclared nonnegative/coherence projection. Full-cohort known-target reporting includes all8916 scored records on paired identical memberships. No fallbacks are discarded to improve results.

The independent checker reconstructs raw anchors plus frozen mean residuals, reapplies the registered feasibility rules, verifies all fallback workload values, and recalculates ALL-cohort MSE/MAE/bias and membership hashes. Source code, data, baseline files and guard thresholds remain unchanged. No2026 target or new2027 candidate projection is included; Stewart and Misiorowski remain unscored illustrations.

These2023–2025 seasons informed the design. The fold construction is strictly earlier-only, but that does not turn this development test into fresh independent validation. Coherent fantasy counts, team budgets, player-level review and independent evidence remain unresolved steps before any adoption.
