# Compatibility recovery

Extract this archive into a temporary folder, then copy the three Python files to the corresponding paths in D:/JonAPythonClass/pycharm/PlayerValuation.

- build_historical_projection_warehouse_v1_0.py: uploaded original, restored byte-for-byte. Replace the new wrapper with this file.
- build_duckdb_projection_warehouse_v1_0.py: distinct entry point for the new foundation, using the existing src/warehouse/core.py from the earlier package.
- tests/test_duckdb_warehouse.py: the seven foundation tests with a distinct filename.

The original tests/test_warehouse.py was also replaced by the first package. Recover that file from Git or PyCharm Local History; do not replace it with test_duckdb_warehouse.py. test_accuracy.py calls WarehouseTests.fixture from the original test_warehouse.py. The foundation test file has no such fixture. Upload the recovered original tests/test_warehouse.py so we can verify compatibility. Do not delete or weaken accuracy tests to hide the issue.

After recovering the original test_warehouse.py, run:

```powershell
python -m unittest discover -s tests -v
```

The DuckDB tests alone can be run with:

```powershell
python -m unittest discover -s tests -p "test_duckdb_warehouse.py" -v
```

Do not rerun the legacy builder just to fix test imports: its default output must be empty, and your existing SQLite data should be retained. No database migration is performed here. Keep initialization and DuckDB ingestion on hold while project mappings/configuration and existing outputs are reconciled. Do not recopy the first ZIP's same-named builder or test_warehouse.py.

Verification: original builder SHA-256 matches uploaded bytes; original build(config_path, output_root=None) and read_rows(path, spec) exports checked; legacy CSV reader tested with duplicate headings and numbered row tuples. Seven DuckDB integration tests passed. Full legacy suite cannot be run here without original fixture tests, evaluator scripts, configuration and delivered datasets.
