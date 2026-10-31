# Targeted actuals evidence review 1.0

Extract into D:\JonAPythonClass\pycharm\PlayerValuation. This adds one new
inspection script, a 44-game plan under config, and review tables under audit.
It does not replace your actuals, reconciliation scripts, config JSON, or data.

Findings from your supplied reconciliation CSVs and PA traces:
- 245 numerical metric differences concern 228 player-seasons.
- 217 differences are PA (92) or pitcher TBF (125); 28 concern other counts.
- All 142 missing reference player-seasons are pitchers (994 metric rows).
  They have positive observed TBF. Zero-out appearances omitted by FanGraphs
  are a possible explanation, not a finding established by this evidence.
- Ten unresolved PA traces involve a batter-ID switch and return to the first
  ID in the same PA. Do not assume these are genuine legal substitutions or
  automatically reassign counts; MLB evidence is needed.
- The unknown event is game_advisory on two rows in 2017. Inspect the actual
  rows before reclassifying the code or adding/removing any PA.

The 44-game batch includes those ten unresolved PA games plus 34 other games
whose traces involve numerically discrepant player-seasons. The 34 links are
candidates: a shared player-season does not prove that PA caused a difference.
This is the first diagnostic batch, not a claim to resolve every discrepancy.

1. Inspect the two unknown event rows (read-only frozen source versions):

```powershell
python inspect_statcast_event_v1_0.py
```

It reads source_windows.json from outputs/actuals_statcast_reconciliation_v1_0,
checks the 2017 Parquet hashes, and writes a NEW folder:
outputs/actuals_event_inspection_v1_0. Return event_rows.csv and
inspection_report.json. It does not rerun ingestion or change event definitions.
Use --output with another name on a rerun; existing output is not overwritten.

2. Fetch ONLY the selected 44 game feeds using your installed downloader:

```powershell
python download_mlb_scoring_evidence_v1_0.py --plan "config/actuals_evidence_targets_v1_0.csv" --cache "data/mlb_scoring_evidence_v1_0" --scope player_changes --max-games 0
```

Here --max-games 0 means all games IN THIS 44-GAME FILE, not all MLB games.
Previously cached games are verified and skipped. Raw pitch downloads are
unchanged. The supplied plan uses the existing downloader's accepted priority
and includes additional explanatory columns, which it ignores.

3. Rerun comparison with the cache into a NEW output folder:

```powershell
python reconcile_statcast_actuals_v1_0.py --actuals "data/actuals_reference_v1_0" --start 2015-03-01 --end 2025-11-01 --mlb-feed-cache "data/mlb_scoring_evidence_v1_0" --output "outputs/actuals_statcast_reconciliation_v1_0_targeted"
```

Return reconciliation_report.json, discrepancies.csv, mlb_feed_usage.json and
mlb_pa_evidence.jsonl from the new output. The existing reconciler backs up
the complete new output. IP/ER and other nonterminal full-season statistics
will still be marked unsupported with only partial game coverage; this batch
is for targeted diagnosis and corroboration.

Review files under audit/actuals_reconciliation_review_v1_0 include the 245
numerical differences, the 142 missing reference pitcher seasons, trace links,
and review_summary.json. They are derived from your uploaded reports, not new
MLB findings. No projection, training label, scoring rule or source total was
changed. More targeted games may be necessary after the first results.
