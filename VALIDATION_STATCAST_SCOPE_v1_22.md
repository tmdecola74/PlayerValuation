# Validation — v1.22.0

19 automated tests pass against DuckDB 1.4.3 on the development runtime. Tests use a complete synthetic three-year daily manifest with nonempty physical pitch fixtures, frozen historical leaderboard snapshots and replayable reconciliation summaries. No full user archive is available in this runtime.

Coverage includes:

- Distinguishing numerator disagreements, measured-only rate matches, total-BBE-only matches, unresolved rates and missing denominators.
- Zero measured events remaining valid; missing rates/measurements never becoming zero.
- Fixed rounding units and denominator candidates remaining accounting leads.
- Deterministic substantial-sample target selection within metric, role and season.
- Existing eligibility masks staying held; direction proxies never certified by a match.
- Full immutable-input build, reconstruction replay, count comparisons and complete backup equality.
- Event/game bridge totals and missing event measurements.
- No future pitch, holdout, quarantine-table or label file opens.
- Configuration/no-overwrite guards; staged interruption cleanup.
- Raw snapshot tampering, duplicate physical pitches despite updated file hashes, replay mismatches, missing daily windows and wrong archive bindings.
- Production-shaped null raw text preserving blank original CSV values.
- Unknown historical normalization cases failing explicitly.

An additional accounting regression used the six supplied historical EV exports and all supplied reconciliation details. It reproduced 9,108 hard-hit/barrel comparison rows, 52 prior hard-hit residuals and 100 historical count/rate flags. All 52 exported hard-hit counts agree with integer numerators implied by the prior summaries. This regression does not replace independent physical-event reconstruction; that is performed when the user runs the build against the local archive. See `SUPPLIED_ACCOUNTING_REGRESSION_v1_22.json`.

No model was fitted, no accepted forecast changed and no 2026 outcome was used. The package makes no claim that source comparability or predictive improvement has been established.
