# PlayerValuation warehouse foundation v1.0

This is a standalone foundation package for the existing PlayerValuation project. It has not been run against your Windows files. No existing scripts or data are included or overwritten automatically. Compare any same-named files before copying into your project.

## What works now

- CSV/TSV and explicit-sheet XLSX ingestion for preseason hitter/pitcher projections and season-total hitter/pitcher actuals.
- Immutable raw archives keyed by SHA-256; versioned compressed Parquet; DuckDB views selecting active versions.
- Dataset/season/source replacement: one active snapshot per combination, with old files and catalog versions retained.
- Identical active inputs and mapping configuration skip ingestion. Failed normalization leaves the previous active version untouched.
- Missing mapped headings, invalid numbers, missing IDs, duplicate players and empty inputs are rejected. Rejection details are in audit/<run>/issues.json.
- Read-only source inventory and validation JSON/CSV; MLBAM coverage and per-stat null counts are reported.

DuckDB can query Parquet directly; the catalog stores file locations and version metadata rather than duplicating all records. See https://duckdb.org/docs/stable/data/parquet/overview and https://duckdb.org/docs/stable/clients/python/overview .

## Setup on your PC

Extract the ZIP to a temporary folder. Merge its PlayerValuation contents into `D:\JonAPythonClass\pycharm\PlayerValuation` after comparing existing files. In the PyCharm project terminal:

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python initialize_warehouse_v1_0.py
python inventory_local_sources_v1_0.py "D:\JonAPythonClass\pycharm\last3yrsproj" "D:\JonAPythonClass\pycharm\EOYstatistics" > source_inventory.jsonl
```

Send the inventory when ready. It includes file paths, headings and the first four rows of each Excel sheet. We can then finish exact mappings. The configuration intentionally contains no guessed filenames or sheet names.

Copy `examples/data_sources.example.yaml` to `config/data_sources.local.yaml`. Replace every placeholder and confirm each source's headings, season, export date, sheet and innings convention. Add an entry per projection system/season/player type and actuals season/player type. `source` must be consistent across versions of the same dataset.

```powershell
python build_historical_projection_warehouse_v1_0.py --sources config/data_sources.local.yaml --inspect
python build_historical_projection_warehouse_v1_0.py --sources config/data_sources.local.yaml
python validate_historical_projection_warehouse_v1_0.py
```

Validation exit code 0 means the implemented checks pass; 1 means failure. Review MLBAM coverage and nulls even when validation passes. An initialized empty warehouse fails validation by design.

## Important interpretation details

FanGraphs IDs are retained as `FG:<id>` when MLBAM is missing. These records are unresolved, not silently joined to Savant. `dim_player` is currently an observed-identity view, not an authoritative player master. A verified crosswalk and conflict handling are the next identity step. Two-way players are separated by dataset. Actuals must be season totals; multiple team-stint rows are rejected rather than summed with a total row.

`SO` is the canonical strikeout column for both hitters and pitchers. Pitcher hits/walks allowed are `HA`/`BBA`; hitter hits/walks are `H`/`BB`. Missing statistics stay null, never zero. `IP` defaults to decimal innings; explicitly set `ip_format: baseball` for displays such as 10.1/10.2. Percent conversion applies to AVG/OBP/SLG/OPS only. Use fractional rates by default.

Snapshot and availability dates are source metadata. Do not invent them. Missing dates are permitted for archival ingestion but those rows must not enter a time-safe training dataset until dates are verified. The model layer is not implemented yet. In particular, predicting 2026 preseason residuals must use 2025-or-earlier skill/team information available at the preseason cutoff, never 2026 end-of-season skills.

## Operations and backups

Use a single ingestion process at a time. Each source commits independently: if a later source fails, earlier successful sources remain committed. Original local inputs are never modified. A crash between file publication and transaction commit can leave an unreferenced version directory; it is harmless and must not be included via broad file globs.

Back up the complete `data` folder, configurations and source inventory together after closing writers. The database currently stores absolute paths. After moving the project, rebuild the catalog by ingesting configured sources at the new location; copying only the DuckDB file is insufficient. Keep large raw/Parquet/database/output files out of Git. Code, mappings without private paths, SQL, docs and tests belong in Git.

## Scope still to implement

Savant downloading/resumable windows, streamed pitch ingestion, crosswalk import, Statcast features, team context, consensus construction, residual modeling and Excel reporting are designed in docs/ARCHITECTURE.md but not implemented by this package. No MLB downloads run automatically. Dependencies use bounded major-version ranges; tests were run with versions listed in docs/TEST_RESULTS.md, not on your Windows Python 3.13 environment.
