# Validation — v1.23.0

The development runtime uses Python 3.12, NumPy 2.3.5 and DuckDB 1.4.3. Tests use a self-contained synthetic warehouse, frozen accepted forecasts, complete label/feature source shapes and Windows-style manifest keys. Full production matrices and the user's local warehouse are not available in this runtime; production results are not claimed.

All **24 automated tests pass**. The packaged test log records the full run. Both development and evaluation command-line entry points were checked with `--help`.

The test suite covers:

- Exposure-weighted recency, finite zero rates and missing observations remaining unknown.
- Strict three-year 2026 feature windows, no fourth-lag use and role-appropriate feature blocks.
- Exact preservation of accepted primitives outside the registered coherent groups.
- Missing required components yielding explicit accepted-group fallbacks.
- Historical-only selection, insufficient-support rejection and bat arms never being selectable.
- A known synthetic predictive signal, earlier-target fitting and test-year changes not affecting fitted preprocessing.
- Identical preprocessing for common features between paired feature arms.
- Eligibility masking before preprocessing and rejection of unmasked/future add-on values.
- Invalid rate denominators excluded while zero numerators remain valid.
- A full pipeline with complete backup equality and immutable original references.
- Matching bat/control fitting memberships and short-history source restrictions.
- Identical historical and benchmark scoring memberships within paired groups.
- Benchmark season inventory, preserved source metric exclusions and unopened 2027 raw files.
- Explicit ambiguous benchmark identity handling without name matching.
- A separate evaluator with no fitting, unchanged forecast files and complete backup equality.
- Unreadable/mutated 2026 outcome files leaving frozen development choices, models and forecasts unchanged.
- No-overwrite/configuration guards, interruption cleanup and rejection of tampered forecast freezes.

The fixed configuration is packaged before any production experiment runs. No accepted projection set or 2027 forecast is generated or promoted during tests.
