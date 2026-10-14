# Statcast model inputs and PA attribution audit v1.0

Extract this ZIP into `D:\JonAPythonClass\pycharm\PlayerValuation`, preserving the config and tests subfolders. These are new files. Requires the existing statcast_pipeline_v1_0.py, its tests, Python, and DuckDB. No original warehouse, feature builder, configuration, or projection evaluator is replaced.

Run from that project folder:

```powershell
python -m unittest discover -s tests -p "test_statcast_model_inputs_v1_0.py" -v
python statcast_model_inputs_v1_0.py
```

The defaults use the reviewed SQLite reference, the completed 2026-target feature folder, and the existing Statcast ingestion configuration. Override --sqlite, --features, --feature-audit, --ingestion-config, --config, --output, or --backup-root if needed. Output must not already exist. A later rerun can use --output "outputs/statcast_model_inputs_2026_v1_0_rerun".

The full run verifies the original source_windows.json against the ingestion journal, verifies file hashes via the established pipeline, then reads the registered 2023–2025 pitch Parquet. It makes no downloads. The uploaded feature DuckDB's raw views have Windows-specific external paths; this script instead uses the journal's verified pitch paths.

## What the PA trace does

Groups pitches by game_pk/at_bat_number and orders by pitch_number. It records every observed hitter/pitcher change with incoming PRE-pitch balls/strikes and a full short sequence. A two-strike replacement hitter's subsequent strikeout stays with the preceding credited hitter (OBR 9.15(b)). A walk after a pitcher change stays with the preceding credited pitcher at incoming counts 2-0, 2-1, 3-0, 3-1, or 3-2 (OBR 9.16(h)). Other completed outcomes belong to the final hitter/pitcher. Repeated changes are chained. Missing/invalid substitution counts are flagged, not silently credited. Nonterminal player-change PAs are logged separately and do not create completed PAs.

These are candidate scoring-rule attributions. They are confirmed for a player-season only when exposure, SO, and BB all reconcile exactly with selected warehouse actuals. Residual discrepancies remain UNRESOLVED_DIFFERENCE. Physical pitch/swing/contact ownership is unchanged. The old feature database remains intact.

Source: MLB Official Baseball Rules, 9.15(b), 9.16(h): https://content.mlb.com/documents/2/2/4/305750224/2019_Official_Baseball_Rules_FINAL_.pdf

## Model inputs

* projection_baselines.jsonl: every analytical 2024–2026 projection record, original metrics and metric exclusions intact. Separate sources remain separate. No new blend, consensus, forecasts, or valuations are calculated.
* model_players.jsonl: one row per type/season/canonical player, source record references, usable-feature list, and fallback status.
* model_features.csv: one row per player/season/feature. Newest adequate prior-season sample within three years is used. Below-threshold/missing values are null, never filled with zero. Older adequate history is explicitly labeled.
* model_team_context.csv: source-specific projected team joined to newest matching prior historical team context, never a target-season context row. Explicit MLB abbreviation aliases are documented in code. Missing/ambiguous teams remain null.
* training_labels.jsonl: 2024/2025 actual outcome labels, kept separate. The 2026 actuals tables are never queried for labels.
* historical_team_context.csv: historical reference context; additional consumers must filter its season below the relevant prediction year.
* player_count_reconciliation.csv: observed versus official versus rule-attributed PA/BF, SO and BB, with status and provenance.
* pa_player_changes.jsonl: complete pitch sequences for completed player-change PAs. Unresolved substitutions are retained.
* nonterminal_player_changes.jsonl: player changes without a completed PA event.
* attributed_player_season.csv: candidate scoring-rule totals and unresolved-count flags.
* model_input_audit.json: counts, gates, hashes, chronology, trace status, fallbacks, and backup location.

Official historical PA/TBF/SO/BB components are preferred for scored K/BB features when available. For 2023, where the reference has no actuals, rule-attributed rates have explicit unverified-official provenance. Without a pitch trace they remain null. Observed terminal-row rates are not substituted for scored rates.

Initial controls in config/statcast_model_inputs_v1_0.json: >=100 swings or out-of-zone pitches, >=200 thrown/known-zone pitches, >=30 measured contact events, >=100 velocity measurements, >=50 scored PA/BF. Reliability is n/(n+prior); these are configurable initial controls, not fitted coefficients or accuracy claims. Features are selected independently, so a missing barrel measurement need not discard a valid swing feature. Players without any usable features use PROJECTION_ONLY. Baseline values are never adjusted by these reliability scores.

There are no 2023 projection labels in the reference. For 2024 training, features stop at 2023; for 2025 training, they stop at 2024; for 2026 holdout prediction, they stop at 2025. 2026 features and outcome labels stay outside this run. Data was retrieved retrospectively, so this is not a reconstruction of source availability at the historical prediction dates. The default feature controls support the pre-2026 measurement era only; future 2027 modeling needs explicit handling of 2026 measurement changes.

## Backup and verification

The complete new folder is copied to backups/statcast_model_inputs_2026_v1_0_TIMESTAMP and every file hash is compared before publishing the output folder. SQLite and feature DuckDB are opened read-only; input hashes are checked again before publication. Feature-catalog and SQLite file hashes differ because they are different backends: canonical MLBAM identities are checked directly instead.

The included tests cover inheritance counts, replacement hitter outcomes, chained changes, missing-count quarantine, count conservation, sample gates, older-season fallback, read-only input hashes, complete backup, and target-outcome leakage. They also run the existing 11 Statcast pipeline tests.

## Preliminary uploaded-file audit

preliminary_uploaded_file_audit contains the feature-table-only reconciliation and summary produced here from your uploaded files. Its trace status is NOT_RUN: the original pitch Parquet was not uploaded. It does NOT prove that substitutions explain the real differences. It is not a replacement for your full local run.

Upload your full run's model_input_audit.json, player_count_reconciliation.csv, and pa_player_changes.jsonl next. Do not fit a valuation adjustment until residual discrepancies have been reviewed.
