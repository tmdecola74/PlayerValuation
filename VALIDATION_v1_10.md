# Validation

All 14 supplied tests pass on Python 3.12.14 / NumPy 2.5.4 with DuckDB 1.4.3 (12.130 seconds) and DuckDB 2.0.0 (13.110 seconds).

Tests cover the independently calculated exposure-weighted formula; valid zero last-season rate; missing histories versus population-only forecasts; missing proxy fallback; earlier-only population membership including zero-SB observations and excluded components; raw 2020 lag exposure reliability; required historical gates against both accepted and last-season comparators; retained 2021 and excluded stress/future targets; recorded workload drops, normalization, missing histories and prior-role transitions; retrospective return/actual-role separation; missing versus known source branch ranges; hitter non-SB preservation; all-origin frozen forecast reproduction; unchanged v1.9 evidence; complete verified backups; no default holdout-outcome parsing; no new pitcher fit; no population refit during evaluation; disclosed-label changes cannot alter frozen forecasts/choices; identical comparison pools; unchanged full pitcher vectors; source tamper rejection; output guards and interrupted-stage cleanup.

The end-to-end fixture builds the earlier release chain before the new build and evaluation. These are synthetic correctness tests, not evidence of production accuracy. Full frozen production inputs are on the user's PC. Historical adoption and disclosed 2026 results require running the supplied commands locally.

All new Python files compile. The archive passes CRC and per-member SHA-256 verification. Only new v1.10 files are included; earlier releases are not overwritten.
