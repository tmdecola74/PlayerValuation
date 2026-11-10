# Validation — v1.11.0

12 tests passed using Python 3.12.14 / DuckDB 1.4.3 and 12 passed using DuckDB 1.5.0 (same NumPy environment). See the included test logs. These are synthetic end-to-end fixtures built through the preserved v1.2–v1.5 pipeline, not a run against the user's production warehouse.

Verified:

- Accepted component values reproduced exactly, with saves/holds unchanged.
- Source-separated coherent exports and typed CSV/Parquet table row counts.
- Duplicate/ambiguous identity protection, reviewed NFBC links, same-name assets.
- Nulls, zero actuals, zero-denominator ratios, and unsupported component handling.
- Cold-start/prospect-review coverage and basic valuation-adapter filtering.
- No holdout label table opened by the exporter; modified evaluation labels cannot alter projection values.
- Real read-only DuckDB benchmark extraction on a fixture warehouse and identical paired membership hashes.
- Stable explicit source loader, integrity rejection, existing-output guard, interrupted-stage cleanup, unchanged inputs, and complete backup equality.

The build and evaluation command help pages were checked. The delivery ZIP is CRC-tested and can be extracted without an extra enclosing project directory. Production results must be generated on the user's computer with the installed prior releases and frozen inputs; no production accuracy claim is made here.
