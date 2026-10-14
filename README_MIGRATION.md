# Reviewed historical warehouse migration

Copy the script to your PlayerValuation root and the test file into tests/. Existing code/configurations remain unchanged. Requires duckdb from the earlier requirements installation.

Run tests from the project root:

```powershell
python -m unittest discover -s tests -p "test_sqlite_duckdb_migration.py" -v
```

Close warehouse writers. Find the reviewed database with this read-only command:

```powershell
Get-ChildItem .\data -Filter historical_projection_warehouse.sqlite -Recurse | Select-Object FullName
```

If your reviewed database is in data/warehouse_resolved, run:

```powershell
python migrate_sqlite_warehouse_to_duckdb_v1_0.py --sqlite "data/warehouse_resolved/historical_projection_warehouse.sqlite" --output "data/historical_duckdb_v1_0"
```

Otherwise substitute the actual reviewed database path. Output must not already exist. Do not automatically pick an older/unreviewed database. Do not run the simpler foundation ingestion over this migration.

The migration copies all user tables AND view results, preserving original record IDs, JSON metrics/raw records, crosswalks, selections/exclusions, aliases and run provenance. All views become immutable snapshot Parquet views in DuckDB. No ID rematching or stat renormalization occurs. SQLite is opened read-only and hash-checked. Every object is compared by full row values and audited. Temporary output is removed on failure; publication occurs after checks pass. It also saves a byte-identical SQLite snapshot, allowing schema/constraints and view definitions to be retained for reference.

DuckDB is a snapshot query layer here: original constraints are not recreated, and original SQL view logic is materialized, not dynamically recalculated. Existing evaluators still use SQLite; redirecting them requires a separate, tested change. Missing-vs-zero and reviewed metric exclusions are preserved. Later Statcast datasets should be added separately, joined via the retained crosswalk.

All records for one table/view are currently loaded into memory. This is appropriate for the existing approximately 58k-row warehouse; pitch-level ingestion will require streaming. Absolute Parquet paths mean moving the output folder requires rebuilding into a new location. Back up the complete output directory. Do not commit database/Parquet/source snapshots to Git.

After running, send migration_audit.json. No target-data migration has been run in this environment. Local tests use synthetic SQLite data.
