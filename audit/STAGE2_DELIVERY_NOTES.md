# Stage 2 delivery

Start with outputs/accuracy_v1_0/accuracy_report.md. The evaluator has already
run on data/warehouse_resolved/historical_projection_warehouse.sqlite.

* All 53,291 selected projections are accounted for: 13,497 matched player
  projections and 39,794 unmatched records excluded from accuracy scoring.
* 4,692 source/season/metric/cohort summary rows and 1,323 pairwise comparisons.
* Common-player comparisons require the exact same eligible players and complete
  statistics from every participating source; source-specific diagnostics are
  separated and never used for direct source rankings.
* Uneven source/year and metric coverage is retained. Seasons are not pooled.
* Errors, Pearson correlation, Spearman correlation, average tied-rank absolute
  errors, sample sizes and PA/IP thresholds are reported. Positive bias means
  overprojection. Scores are equal-weight by player; rate scores are unweighted.
* Actual OPS is derived from OBP + SLG where absent and logged.
* Stage 1B selections remain intact; Greg Jones's four unresolved metrics stay
  excluded. No missing or unmatched values are assigned zero.
* Warehouse opened read-only, with SHA-256 checked before and after evaluation.
* 23 tests pass across Stages 1B and 2, including hand-calculated error formulas,
  tied ranks, common sample fairness, playing-time floors, missing values,
  duplicate key rejection, exact actual links, warehouse hash preservation and
  full original-file round-trip checks.

The main tables use actual PA >= 300 for hitters and actual IP >= 40 for
pitchers. These actual-time cohorts condition on players' realized playing time;
other cohorts are in the detailed outputs. Lower MAE is descriptive, without
claims of statistically significant superiority. No consensus weights are fitted.

For hitters' HR among common players with at least 300 actual PA, THE BAT X
has the lowest MAE in 2024 and Steamer in 2025 and 2026. Category-specific results
vary, so there is no universal source winner. See the report for the full tables.

To run again, use a new directory:
python evaluate_historical_projection_accuracy_v1_0.py --output outputs/accuracy_run2
