# Validation

22 tests passed in the development environment with DuckDB 1.4.3 and NumPy. Tests cover:

- Hitter group normalization, coherent ratios, fixed AB and unrelated primitives.
- Pitcher H/BB grouping, H≥HR floor, exact workload/saves/holds and unrelated fields.
- Missing group fallback, immutable configuration and unchanged-rate rejection.
- Positive gates, fixed tie preference, independent role decisions, minimum support.
- Current/future outcomes excluded from origin decisions; 2021 retained.
- Recent regression, missing recent seasons, missing history guards and individual-metric deterioration rejecting otherwise favorable candidates.
- Zero-reference-error handling; identical complete-label/fitted arm pools; missing versus valid zero actual counts.
- Complete backups, source immutability, output guards, tampering and interrupted-stage cleanup.
- No holdout file reads during development; changing holdout outcomes leaves historical forecasts, frozen 2026 forecasts and choice digest unchanged.
- Separate evaluation does not call the selection function or change the experiment.

A compatibility run first generated a complete synthetic v1.17 release using its own builder, then ran v1.19: 28 historical player-seasons and four frozen 2026 player-seasons. Development completed with holdout paths blocked. Separate evaluation completed with 2,240 score rows. Both groups conservatively retained accepted on this small fixture, as support is below the production thresholds.

The full production experiment has not been run here: the user's frozen raw rate files, matrices and labels reside on their PC. No production improvement or adoption is claimed from synthetic validation. The new grouped policy is a fixed historical research experiment, not an independent statistical validation of already inspected historical data.
