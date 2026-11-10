# Validation

17 tests passed in the development environment (Python, DuckDB 1.4.3, NumPy).

Covered: exact replay, accepted implied-rate validation, PA normalization, hit normalization, pitcher HR clipping, exact frozen anchors, squared-error telescoping, accepted-rate reproduction, missing-vector fallback, missing versus zero labels, positive ratio denominators, 2021/history cohorts, future historical rows, duplicate rates, file/reference tampering, full verified backup, output guard and interruption cleanup.

An additional compatibility run generated a complete synthetic v1.17 release using its own fixture/builder, then audited it: 28 historical player-seasons, 798 component trace rows, 1,344 statistic trace rows. Access to paths containing holdout or 2026 was blocked during the audit; it completed successfully. This checks inherited file shapes and replay behavior; it is not a run against the user's full production dataset.

The accepted forecasts and v1.17 files are never edited. No fitting, candidate selection or 2026 outcome access occurs. Production performance and the substantive reason for attenuation await the user's local audit reports.
