# Stage 3 historical backtest delivery

The exact Stage 3 builder was run for the supplied 2024, 2025 and 2026 seasons.
Season-specific source availability is retained; no outcomes enter forecasts.
The unchanged reviewed warehouse SHA-256 is recorded in the backtest report.

Results: 29,886 player/type/seasons, 4,385 reviewed matched player/type/seasons,
25,501 unmatched excluded from accuracy, and 48,235 evaluated player/metrics.
All 21,925 independently recomputed counting/opportunity checks passed.
The complete project test suite passes all 42 tests, including independent
forecast/export equality, paired-sample score recomputation, source disagreement
recomputation, original source conservation and warehouse read-only checks.

AVG and OPS performance is essentially unchanged for hitters projected for
at least 300 PA: MAE changes from -0.03% to +0.11% across these years.
The common-component alternative produces identical headline AVG/OPS/ERA/WHIP
forecasts. Low-exposure component-derived rates remain a material prospect
valuation concern; 68 headline player/metric review cases are exported.
2026 regular-playing-time hitter AVG/OPS errors worsen versus source-rate
averages by 7.00%/7.62% MAE, while the projected-roster cohort is virtually
unchanged. This distinction is explicitly retained in the report, not hidden
by filtering unexpected breakouts out of all accuracy calculations.

Equal weights and production consensus files have not been changed. The
next decision is a low-exposure rate policy before prospect valuation.
Earlier blend results informed the equal-weight choice, so these seasons
are retrospective validation rather than new independent holdouts.

Files: backtest_consensus_projections_v1_0.py,
config/consensus_backtesting.json, tests/test_consensus_backtest.py,
outputs/consensus_backtest_v1_0, updated README, and this audit directory.
No new dependencies or user inputs are required. The focused backtest ZIP
is intended to extend the existing PlayerValuation project; it uses that
project's reviewed warehouse and existing Stage 3 builder/evaluator modules.
