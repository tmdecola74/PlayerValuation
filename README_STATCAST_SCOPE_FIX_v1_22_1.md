# v1.22.1 — Windows manifest-path compatibility fix

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, replacing these two files:

- `audit_statcast_scope_v1_22.py`
- `tests/test_statcast_scope_v1_22.py`

The existing v1.22 configuration and commands stay the same:

```powershell
python -m unittest discover -s tests -p "test_statcast_scope_v1_22.py" -v
python audit_statcast_scope_v1_22.py
```

The original manifest lookup used `historical/leaderboard_features.parquet` literally, while Windows-generated manifests use `historical\leaderboard_features.parquet`. This caused a false hash/path failure before the pipeline tests could run.

The fix normalizes manifest separators in memory for lookup only. It does not rewrite any existing manifest, change a hash or skip verification. Ambiguous duplicate normalized paths, drive/absolute paths, traversal components and actual content tampering remain rejected. The resolved file must remain inside the source folder.

The audit policy/configuration version stays 1.22.0; successful reports additionally identify `build_implementation_version: 1.22.1`. Measurement definitions, cohort selection and eligibility decisions are unchanged. Accepted forecasts and original references remain untouched.

Validation: all 22 tests pass on the development runtime. New tests cover a complete build using Windows-style manifest keys, lookup with either separator, continued hash rejection after tampering, and rejection of ambiguous/unsafe paths. This emulates Windows manifest formatting; it is not a claim of running the development tests on Windows.

No existing data or output folder needs to be removed for this test-fixture failure. If a successful audit output already exists from another run, choose a new `--output` folder as usual.
