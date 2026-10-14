# PlayerValuation DuckDB evaluators and parity audit

Copy these files into the corresponding paths beneath D:/JonAPythonClass/pycharm/PlayerValuation. Files have distinct names; your existing scripts and configurations remain the SQLite reference. Do not overwrite originals with the DuckDB copies.

Requires the installed duckdb package. These adaptations change database access only: scoring, consensus formulas, weights, chronology, cohort rules, exports and reviewed IDs retain the supplied implementation. A small row adapter preserves named and positional access. DuckDB opens read-only; the accuracy integrity check verifies every registered Parquet hash and view row count against the migration audit.

## Verify and compare

Close any warehouse writers. Run:

```powershell
python -m unittest discover -s tests -p "test_backend_parity.py" -v
```

This uses synthetic three-season hitter data to execute all four stages against both backends. It also checks backup creation and unchanged inputs. It does not prove parity on your real pitcher/hitter data; the next command does that.

```powershell
python compare_warehouse_backends_v1_0.py --sqlite "data/warehouse_resolved/historical_projection_warehouse.sqlite" --duckdb "data/historical_duckdb_v1_0_bulk/player_valuation.duckdb" --output "outputs/backend_parity_v1_0"
```

The comparison first backs up the COMPLETE migrated folder to a new timestamped backups/ directory and verifies its copied file hashes. No source database updates occur. It recomputes reference outputs with your unchanged original scripts and DuckDB outputs with adapted copies into separate new directories. Established outputs remain untouched. Run only one comparison at a time. The output directory must not exist; use a new suffix for reruns.

Every CSV, JSON and JSONL output is compared, including nested seasonal consensus builds, forecasts, score summaries, training weights, cohort/sample IDs, diagnostics and effective configurations. Record ordering is ignored at the top level; duplicate rows are retained. Nested arrays remain ordered. JSON strings inside CSV cells are parsed for structural comparison. Differences in runtime timestamps, warehouse paths/hashes and output metadata are ignored. Floating-point comparisons allow relative 1e-10 / absolute 1e-12 tolerance. Membership, IDs and nonnumeric data otherwise compare exactly. Markdown narrative files are excluded; the underlying machine reports are compared.

Read outputs/backend_parity_v1_0/backend_comparison.json. Exit code 0 requires all comparisons and unchanged-input hashes to pass. Exit code 1 indicates differences; keep the outputs and send that report before switching your normal workflow. SQLite remains the reference. The runner compares fresh reference results; comparison to older established exports is supported by the compare_outputs() utility but is not automatically performed because their paths/versions are not yet verified.

## Separate direct commands after real parity passes

The four *_duckdb_v1_0.py scripts default to their corresponding config/*_duckdb.json files. Run them like their originals, using --config / --warehouse / --output for overrides. Configurations point to data/historical_duckdb_v1_0_bulk/player_valuation.duckdb and separate output directories. Existing nonempty output protection remains in place. The helper also accepts SQLite paths for diagnosis.

The backed-up catalog uses absolute original Parquet locations, just like the migrated catalog. A copied folder is evidence/backup; a relocation requires rebuilding/rebinding the catalog before querying it independently. Keep the entire folder, not only the .duckdb file. Exclude backups/, migrated data and generated comparison outputs from Git.

Local verification: all four stages passed SQLite/DuckDB comparison on synthetic data with unchanged input hashes and a verified backup. Real-data parity must be run on your Windows project; local copies of your databases were not supplied.
