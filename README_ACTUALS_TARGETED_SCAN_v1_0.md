# Targeted actuals scan 1.0
Extract into the PlayerValuation project root. Adds one standalone standard-library script and tests. No existing scripts are replaced.

Run:
```powershell
python -m unittest discover -s tests -p "test_actuals_targeted_scan_v1_0.py" -v
python scan_actuals_discrepancies_v1_0.py
```
Default source: outputs/actuals_statcast_reconciliation_v1_0_min0ip
Default output (must not exist): outputs/actuals_targeted_scan_v1_0
Default selection: three largest absolute hitter PA differences, with deterministic ties.

Uses raw CSV paths and SHA256 hashes from source_windows.json, never current active ledger selection. Validates all selected daily raw versions before accepting output and verifies hashes again at completion. Scans only selected seasons, sequentially, one daily file at a time. No DuckDB dependency and no network calls. Original source/reconciliation files and all counts remain unchanged. Copies the complete new output to backups and verifies file hashes before publication.

Return scan_report.json and candidate_pas.csv. The two game plans are for later evidence retrieval: candidate_game_fetch_plan.csv is the narrow unusual-event set; all_target_games_fetch_plan.csv is the broader recorded target-appearance census. Neither is proof of causation. Do not automatically download the broader plan. A target PA missing entirely from Statcast is not detectable from recorded appearances alone; separate game evidence may be necessary. No claim of full game/season census or scoring reconciliation is made by this diagnostic.

Use --output with a new folder on reruns; --top changes the number of hitter PA discrepancies selected. Windows paths in the frozen manifest must still exist on your PC.
