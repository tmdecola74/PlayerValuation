# Final actuals difference audit 1.0

Extract this ZIP into `D:\JonAPythonClass\pycharm\PlayerValuation`.
It adds a new audit, its frozen scoring-support module, and tests. It does not replace any existing scripts, source data, projection warehouse, or reconciliation reports.

## Run

```powershell
python -m unittest discover -s tests -p "test_actuals_final_difference_audit_v1_0.py" -v

python audit_actuals_final_differences_v1_0.py `
    --reconciliation "outputs/actuals_statcast_reconciliation_v1_0_remaining_pa_evidence" `
    --mlb-feed-cache "data/mlb_scoring_evidence_v1_0" `
    --output "outputs/actuals_final_difference_audit_v1_0"
```

Python standard library only; no new dependencies. Stop ingestion, refreshes and evidence downloads while this audit runs. The source manifest's original Windows paths must still exist. This reads the frozen RAW CSV files, not the live ingestion ledger; it does not rescan the projection warehouse or rebuild reconciliation. It scans relevant seasons once, then verifies source hashes again. Progress prints every 100 files; final hashing can be quiet. The whole archive is on your PC, so full-data execution has not been performed here.

The default baseline currently has 41 numerical differences across 29 player-season roles, all one count. The audit selects its cases from discrepancies.csv rather than hardcoding those players or assuming the answer. 2026 and future target seasons are rejected. Reuse requires a NEW output folder.

## What the audit does

1. Reads baseline discrepancies, reconciliation report and source_windows.json, retaining SHA256 fingerprints.
2. Verifies frozen raw CSV hashes and source-row counts, uses one game/PA/pitch key, collapses exact field-equivalent duplicate pitches and rejects conflicting duplicates. Retains complete recorded PA sequences involving the target players.
3. Reconstructs terminal and existing scoring-rule counts for both hitter and pitcher targets using a separately named frozen copy of the established 1.0.1 scoring support. No external projection system is used.
4. Verifies relevant saved MLB feeds, game identity, season, regular-season type, completion state, and both team/player metric sums before admitting a game-level comparison. Missing/failed metric blocks are never zeros.
5. Uses PA index only to nominate a candidate. Both player identities, pitch numbers, full pre-pitch ball/strike counts and available inning/half information must agree before an outcome-label disagreement is called aligned. Player-change or incomplete sequences remain review cases.
6. Distinguishes aligned missing outcomes, extra reconstructed outcomes, hit/error or hit-type differences, other label differences, and unknown outcomes. Runner-only events do not manufacture completed PA/TBF. A source disagreement is NOT proof that a historical scoring revision occurred; dated archived scoring evidence is still needed.
7. Reproduces the baseline's terminal/rule/evidence totals and reports any failure explicitly. If you added cached feeds after reconciliation, an evidence-total bridge mismatch may reflect that change; no baseline row is rewritten and no approval is inferred.
8. Nominates uncached games where complementary same-sign hitter/pitcher residuals meet in a recorded PA, plus unknown-event leads. These are leads only. Other uncached observed games are retained in a separate fallback plan. Neither plan downloads automatically.
9. Writes a new folder, copies the COMPLETE folder to backups, verifies every backup file hash, then publishes the output. On interruption/error, staging files are removed. A completed backup may remain if publication itself fails.

## Files to return first

From `outputs/actuals_final_difference_audit_v1_0`:

- `audit_report.json`
- `remaining_cases.csv`
- `game_metric_comparisons.csv`
- `candidate_pa_reviews.csv`

If detailed PA review is needed, `candidate_pa_evidence.jsonl` contains the associated slim Statcast pitch sequences and original cached MLB plays. No need to send it initially if large.

## Other outputs

| File | Purpose |
|---|---|
| pa_inventory.csv | Every recorded target PA/metric association, including matches and uncached cases |
| unknown_outcome_reviews.csv | Unknown labels retained without reclassification |
| mlb_rejected_metric_blocks.csv | Game/role/metric blocks that did not pass completeness/sum checks |
| unmatched_mlb_plays.jsonl | MLB target plays without a nominated raw PA group; no index-only credit transfer |
| primary_game_fetch_plan.csv | Narrow uncached complementary-residual or unknown-outcome leads |
| fallback_observed_games_fetch_plan.csv | Remaining uncached games with a physical target observation; review before using |
| baseline_discrepancies.csv | Exact copy of input cases |
| source_windows.json | Exact copy of frozen source-version manifest |
| input_hashes.json | Source, evidence and audit-code fingerprints |
| audit_report.md | Short interpretation guide |

Download plans have the existing downloader's columns, priority PLAYER_SEASON_DIFFERENCE, and should use --scope all_review_games if later authorized. Do not use player_changes scope with these plans. Empty plans contain headings only. Do not download fallback games automatically.

## Interpretation

- `baseline_reproduced: true` means the audit agrees with the existing reconciliation totals. It does not mean those totals match FanGraphs.
- `ALIGNED_HIT_OR_ERROR_CLASSIFICATION_DIFFERENCE` establishes a disagreement between the two supplied sources under the strict link checks, not which archived source was correct at a particular time.
- `ALIGNED_EXTRA_RECONSTRUCTED_OUTCOME` flags a Statcast completed-outcome label against a recognized MLB runner-only label. The game-level metric comparison remains separate.
- Unknown game_advisory labels remain unknown even if pitch alignment succeeds.
- A residual pairing cannot identify the responsible PA by itself. It only reduces which games to inspect.
- Partial game evidence does not certify season IP/ER, all played games, measurement comparability, or model readiness. `model_ready` remains false.
- No raw pitch, actuals reference, cached feed or baseline count is changed. No correction file or model-input override is produced.

## Validation

The included tests cover read-only input preservation, complete verified backups, raw/cache tampering, output guard, holdout exclusion, exact versus conflicting duplicates, identity/count alignment, unknown versus runner-only treatment, paired residual leads, rejected boxscore metrics and cache changes relative to the baseline. Full historical execution must run on your PC.
