# Verification

Seven integration tests passed on 2026-10-06. Synthetic fixtures only; local user data has not been tested.

- python: 3.12.14
- duckdb: 1.5.6
- polars: 2.0.0
- PyYAML: 6.0.3
- openpyxl: 3.1.5

Covered CSV/Excel roundtrip, unchanged rerun, active replacement without double counting, duplicate rejection preserving the previous version, FanGraphs fallback, bad numeric rejection, innings conversion, raw-file tamper detection, read-only inspection and empty/missing mapping rejection.
