# Validation — v1.12.0

14 tests passed using Python 3.12.14 and DuckDB 1.4.3. These are synthetic end-to-end fixtures, not the user's production audit. The command help page was also checked.

Tests cover source-pool effects, weight effects, source-level quarter-hit residuals, rounding-scale uncertainty, missing/nonreplayable provenance, nonnegative PA budgets, cohort boundaries, zero/missing exposures, matched memberships, conserving exposure partitions, missing-history/role/identity classifications, chronology guards, input binding/tamper checks, interruption cleanup, no model-fit invocation, unchanged projection inputs and complete backup equality.

All previous projection releases remain installed and unchanged. Production diagnostics are generated only when the user runs the audit against their frozen local files. The delivery ZIP is CRC-checked.
