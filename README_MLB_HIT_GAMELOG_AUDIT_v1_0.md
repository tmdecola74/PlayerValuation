# Targeted MLB hit/type game-log audit v1.0.0

Extract this ZIP into the outer PlayerValuation project folder. It adds a new script, tests, and a self-contained investigation folder; it does not overwrite existing reconciliation builds.

The delivered investigation contains actual retrieved MLB responses and their SHA-256 metadata. See `investigations/mlb_hit_gamelog_audit_v1_0/results/season_comparisons.csv` and `FINDINGS.md`. The complete results folder also has an independently copied, hash-verified backup in the investigation directory.

## Verification

```powershell
python -m unittest discover -s tests -p "test_mlb_hit_gamelogs_v1_0.py" -v
```

## Reproduce from the bundled cache without network requests

```powershell
python audit_mlb_hit_gamelogs_v1_0.py --discrepancies "investigations/mlb_hit_gamelog_audit_v1_0/results/baseline_discrepancies.csv" --game-totals "investigations/mlb_hit_gamelog_audit_v1_0/game_metric_comparisons.csv" --cache "investigations/mlb_hit_gamelog_audit_v1_0/results/source_responses" --output "outputs/mlb_hit_gamelog_audit_v1_0_reproduced"
```

Choose a new output path for each run. `--download` fetches only missing request entries; existing responses are verified and never refreshed. The script defaults to the current reconciliation and prior final-audit game totals on your PC. Every selected baseline terminal/rule/evidence season total must reproduce before MLB comparisons begin.

MLB game-log sums are checked against separately requested MLB season totals. Season gamesPlayed can differ from the number of role-specific log entries, so this is reported explicitly rather than used to claim every appearance was downloaded. Selected H/1B/2B/3B/HR sums must agree exactly. Missing game entries remain unknown, not zero. FanGraphs totals are preserved. No event, projection, or training label is corrected, and model readiness remains false.

The game plan contains only games needing further comparison. An empty plan means no additional MLB game download was justified by this comparison; FanGraphs game-level evidence would be needed to explain the different season totals.
