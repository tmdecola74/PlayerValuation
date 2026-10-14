# PlayerValuation Statcast ingestion and features v1.0

This package adds new files to the PlayerValuation root, config/ and tests/. Copy its contents into D:/JonAPythonClass/pycharm/PlayerValuation preserving those folders. It does not replace your existing projection warehouse, scripts or configuration. Uses the already installed duckdb package; HTTP, CSV and the download ledger use Python's standard library. I used the file-saving skill to provide this reusable package.

## Archive 2023–2026, test 2026 without leaking 2026 outcomes

The archive includes all four seasons. For 2026 valuations use 2026 PRESEASON projections and 2023–2025 historical skills/team context. The feature CLI defaults to target-season 2026 and forces end <= 2025-12-31. Downloaded 2026 pitches remain available for 2027 feature builds. A design contract is in config/valuation_backtest_plan_v1_0.json; the valuation/model engine itself is not implemented in this package.

For supervised projection-residual training, 2024 targets use 2023 skills and 2025 targets use 2023–2024 skills. 2026 is the untouched outcome holdout after settings freeze. Do not use all 2023–2025 skills for EVERY earlier target row. All preseason roster/role/team opportunity data and SGP/market assumptions must also reflect the forecast date. Present-day corrected historical downloads reconstruct past seasons, not exact historical publication vintages. Download timestamps are preserved and must not be mislabeled as past availability.

## Start with tests and one live day

From the project terminal:

```powershell
python -m unittest discover -s tests -p "test_statcast_pipeline_v1_0.py" -v
python statcast_pipeline_v1_0.py --plan
python statcast_pipeline_v1_0.py --start 2023-03-30 --end 2023-03-30
python validate_statcast_ingestion_v1_0.py --start 2023-03-30 --end 2023-03-30
```

Send the terminal output and data/statcast_v1_0/latest_download_report.json after the first live day, before launching four full seasons. Local integration tests use synthetic responses; live Baseball Savant/MLB endpoints have not been validated in this restricted environment. Failures retain source bytes and an explanation; do not weaken validation to force completion.

A smoke feature build is optional:

```powershell
python build_statcast_features_v1_0.py --start 2023-03-30 --end 2023-03-30 --target-season 2026 --output "outputs/statcast_smoke_20230330"
```

Its sparse one-day results are for pipeline validation, not player valuation.

## After live smoke validation

Historical download for the initial 2026 backtest:

```powershell
python statcast_pipeline_v1_0.py --start 2023-03-01 --end 2025-11-01
python validate_statcast_ingestion_v1_0.py --start 2023-03-01 --end 2025-11-01
python download_team_context_v1_0.py --seasons 2023 2024 2025
python build_statcast_features_v1_0.py --target-season 2026 --output "outputs/statcast_features_for_2026_v1_0"
```

Then archive 2026 separately:

```powershell
python statcast_pipeline_v1_0.py --start 2026-03-01 --end 2026-11-01
python download_team_context_v1_0.py --seasons 2026
```

Future dates are clamped to yesterday, so incomplete future dates are not marked complete. Run again later to append remaining days. Use --refresh with an explicit date range to fetch source corrections; old bytes/Parquet versions stay intact and only the successful new version becomes active. A failed refresh retains the prior active version. Team supplements are immutable season snapshots in this version; defer a full 2026 supplement until the season is final, or use a different ingestion root for a later corrected supplement.

For future 2027 inputs, after all required 2026 windows complete:

```powershell
python build_statcast_features_v1_0.py --target-season 2027 --output "outputs/statcast_features_for_2027_v1_0"
```

This is a feature snapshot, not a 2027 valuation until 2027 projections/context are available.

## Resume behavior and file layout

Each CSV window is exactly one day, regular season only. Sequential requests use bounded retries and pacing. Expected completed-game IDs come from an archived MLB schedule response. Empty days complete only when no final regular-season games are expected. Daily presence checks do not prove official pitch/PA totals. Suspended games/date conventions or endpoint schema changes may require investigation; mismatches fail visibly.

- data/statcast_v1_0/raw/<season>/<day>/<version>/ preserves original CSV, schedule JSON and audits/failures.
- data/statcast_v1_0/parquet/season=YYYY/month=MM/day=DD/<version>/pitches.parquet uses ZSTD compression.
- download_ledger.sqlite stores the active daily versions, hashes, rows, URLs, errors and retrieval timestamps. This small SQLite file is an ingestion journal, not the analytical warehouse.
- features are partitioned by season beneath the requested output, with review CSVs and statcast_features.duckdb.

Reruns verify hashes and skip complete windows. --max-windows N caps NEW/retried windows per invocation; existing successful windows are still verified. Missing windows block feature construction. Exact duplicate raw rows are deduplicated and counted; conflicting duplicate pitch keys are rejected, including cross-window conflicts. Unknown columns remain preserved; missing optional metrics remain null; numeric parsing failures are rejected rather than silently turned into zero.

Run one downloader at a time. Ctrl+C releases the lock and leaves completed days resumable; an unfinished attempt is not registered as complete. After an OS crash, confirm no downloader remains before removing pipeline.lock. Large raw archives are intentionally retained; ensure disk space, back up the ledger and entire data/output directories, and exclude these from Git. Keep the original SQLite/projection DuckDB references untouched. Views contain absolute paths, so relocating data requires rebuilding the feature catalog.

## Feature outputs and limits

See FEATURE_DICTIONARY.md for exact definitions. Implemented: hitter/pitcher contact and discipline, arsenal usage/velocity/spin/movement/extension, platoon splits, contiguous-season changes, schedule-derived team results, inning deployment and opportunity proxies. Official team SB/CS/SV/HLD fields are downloaded separately when exposed by the MLB team endpoint; unavailable fields remain null. Supplements are included only for a complete configured season window, never a partial snapshot.

The team supplement endpoint must be tested on your PC. Missing fields are audited; a missing holds field is not zero holds. xERA, official full-PA xwOBA, xSLG, sprint speed, top-90%-swing bat speed, detailed bullpen hold/save shares, and actual steal-event denominators need additional leaderboard/play-by-play adapters. Raw available bat-tracking columns are retained for that work. No learned Statcast bonuses or fantasy values are applied yet.

Player features retain MLBAM IDs and map through the existing reviewed player_id_crosswalk by ID only. Unmapped players are exported in player_identity_coverage.csv. No fuzzy-name matching or automatic identity replacement occurs.
