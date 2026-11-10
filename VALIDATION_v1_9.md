# Validation

All 16 supplied tests pass on Python 3.12.14 / NumPy 2.5.4 with DuckDB 1.4.3 (13.212 seconds) and DuckDB 2.0.0 (13.853 seconds).

Tests verify the joint solution against an independently solved uncapped quadratic, the exact capped deployed objective, coefficient bounds, zero-information fallback, fixed growth/participation probabilities, earlier-fold-only calibration membership, no fabricated activity, historical selection retaining 2021 and excluding stress/future targets, missing-versus-zero SB components, earlier-only feature bins, rank ties, annual audit coverage and nonselection flags, complete source-chain replay, unchanged v1.8 evidence, accepted hitter/SB preservation, complete verified backups, no build-time holdout-outcome parsing, no SB replacement fitting, no evaluation refitting, changed disclosed outcomes cannot change frozen forecasts/choices/bins, identical comparison pools, forecast tamper rejection, output guards and interrupted-stage cleanup.

Integration fixtures build v1.0–v1.8 dependencies and the v1.7 audit before the v1.9 build/evaluation. This validates correctness on synthetic data, not production accuracy. The user's full frozen production inputs are not present in this environment. Historical adoption and disclosed 2026 performance must be reviewed after running locally.

New Python files compile. The archive passes ZIP CRC checks and a per-file SHA-256 package manifest. It includes only new v1.9 files and does not replace earlier release files.
