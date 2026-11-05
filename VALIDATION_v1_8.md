# Validation

The 15 supplied tests pass on Python 3.12.14 / NumPy 2.5.4 with both DuckDB 1.4.3 (10.942 seconds) and DuckDB 2.0.0 (11.680 seconds).

Tests cover: shrinkage and multiplier caps; earlier-fold-only calibration; prior-role rather than current-role fitting; unchanged direction and participation probabilities; exact calibrated mixture arithmetic; direct SB rate fitting with true zero labels; missing proxy fallback versus valid zero rate; low-history/established/zero-SB guards; exclusion of 2020 and future targets from selection; separate coherent overlays with frozen saves, holds and hitter components; full source-chain build and forecast reproduction; immutable v1.6/v1.7 evidence; complete verified backups; no holdout-outcome parsing during build; no refitting during evaluation; target-year calibration isolation; changed disclosed evaluation outcomes cannot alter frozen forecasts or choices; identical category comparison pools; existing-output guard; interruption cleanup; and forecast tamper rejection.

The end-to-end fixture builds the earlier release chain, historical v1.7 audit, v1.8 build and disclosed evaluation using synthetic data. It is a correctness and compatibility check, not evidence of improved forecast accuracy. The user's full frozen production matrices and labels are not present in this environment. Production historical and disclosed 2026 results require the supplied local commands.

All new Python files compile. The ZIP is verified with CRC checks and a per-member SHA-256 package manifest. Earlier release files are not included or overwritten.
