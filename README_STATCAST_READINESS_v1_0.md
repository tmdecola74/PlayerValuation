# Historical Statcast readiness audit 1.0

Extract the new audit script and tests into the PlayerValuation project root.
Keep the existing statcast_pipeline_v1_0.py and config unchanged. Requires the
existing DuckDB Python dependency. No network downloads or warehouse writes.

Run:

```powershell
python -m unittest discover -s tests -p "test_statcast_readiness_v1_0.py" -v
python audit_statcast_readiness_v1_0.py --start 2015-03-01 --end 2025-11-01 --output "outputs/statcast_readiness_2015_2025_v1_0"
```

Audit 2026 separately:

```powershell
python audit_statcast_readiness_v1_0.py --start 2026-03-01 --end 2026-10-27 --output "outputs/statcast_readiness_2026_v1_0"
```

Select the actual last completed date. Existing days() caps dates at yesterday;
the report records effective_first_day and effective_last_day. Configured gaps
between annual season windows are not required. Output must be a NEW directory
outside data/statcast_v1_0. Use a new output name for reruns. Do not run while
refreshing ingestion. Audit time includes hashing all raw files and Parquet;
it can be substantially longer than the original daily downloads' skip checks.

Outputs:
- readiness_report.json: integrity status, explicit cutoff and limitations.
- season_summary.csv: expected/verified windows, rows, duplicate keys and PA
  groups containing multiple batter or pitcher IDs.
- window_checks.csv: active row counts and saved-schedule game coverage.
- measurement_coverage.csv: finite observations / eligible rows per field/year.
  Contact denominator is type=X; swing denominator uses explicit descriptions.
  This is measurement availability, not a blanket pass/fail threshold.
- issues.csv: blocking integrity problems (empty means none detected).
- terminal_event_counts.csv: diagnostic H, HR, BB (includes intentional), SO
  attributed to IDs on terminal event rows. Sparse positive counts only.
- official_comparison.csv: optional supplied-reference comparison.

Exit code 1 means integrity failures; code 0 means integrity checks passed.
Neither means model-ready. model_ready is deliberately false until separate
scoring-aware PA/AB/IP reconciliation, player ages/identity completeness,
historical era controls and feature fallback approval are completed.

Optional official comparison accepts a long-format CSV with columns:
season,player_type,mlbam_id,metric,value
Allowed roles hitter/pitcher; metrics H/HR/BB/SO. Supply full regular-season,
all-team player totals for the selected years, not team splits. No source is
fetched automatically. Supply provenance separately. Add --official-counts PATH
to the audit command. Only supplied rows are compared; missing reference rows
are not evidence of completeness. Partial-season references must match the
selected date range. Differences need review, especially inherited-count
walks/strikeouts when batters or pitchers change mid-PA. PA, AB, pitching outs,
ER, saves and official attribution are NOT reconciled by this version.

The tool reads SQLite with mode=ro, checks active source file hashes and saved
schedule/game presence, checks dependency versions/hashes, and aggregates pitch
keys across all selected active partitions. Old refresh versions are excluded.
Schedule snapshots themselves are not independently refreshed. It creates only
new audit output files and never edits source ledgers, projection warehouses,
or existing feature outputs. The source ledger hash is checked before/after.
No output backup is needed for a new directory; retain the audit folder with
other local output backups.

Validation: four synthetic tests passed on DuckDB. The user's full 2015-2026
pitch archive is not present here and has not been run by the author. Return
readiness_report.json, season_summary.csv, measurement_coverage.csv and
issues.csv after running locally. No need to upload raw pitch data.
