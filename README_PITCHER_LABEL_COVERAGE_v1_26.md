# Historical pitcher label coverage audit v1.26.1

Extract into PlayerValuation with v1.24 and the v1.23.1 dependencies installed.
The audit reads the same frozen v1.23 historical forecasts and training labels
as the v1.25 experiment. It never opens 2026 outcomes, changes labels, or fits models.

```powershell
python -m unittest discover -s tests -p "test_pitcher_label_coverage_v1_26.py" -v
python pitcher_label_coverage_v1_26.py --seasons 2025 --download --output "outputs/pitcher_label_coverage_2025"
```

Start with one season; a full-length season needs roughly 2,430 boxscore responses.
Downloads run sequentially and are cached under cache/pitcher_appearance_mlb.
For another season change --seasons and --output. Omit --seasons to audit 2019–2025;
omit --download for a cache-only run. To retry missing responses run with
--download and a new --output path. If an existing cached response is reported
invalid, inspect it, move just that file aside, and rerun. Do not run two
downloaders against the same cache simultaneously. Keep the cache local.

For each season the program reconciles completed regular-season schedule games
with all 30 official team standings totals. It collapses matching final duplicates
and skips cancelled/postponed placeholders. It verifies every scheduled boxscore:
both team IDs, pitcher lists, corresponding individual pitching lines, and team
innings totals. An individual line counts only if MLB credits gamesPitched=1, even at 0.0 IP. A zero-activity placeholder with gamesPitched=0 is excluded. Official
source base: https://statsapi.mlb.com/api/v1/ (schedule, standings,
game/{gamePk}/boxscore, and people).

The program cross-checks existing eligible pitcher G labels and positive OUTS
against the boxscores. A discrepancy blocks all new zeros in that season and
is reported for review. For a pitcher absent from the complete appearance index,
it also requires exact MLBAM identity confirmation from the official people
endpoint. This builds on the existing frozen forecast MLBAM crosswalk; it does
not infer IDs from names or attempt to correct upstream ID mappings. An unresolved
identity or incomplete source produces no proposed zero. A verified positive
appearance on a partial season is shown, but its final G is withheld.

Outputs:
- report.json: coverage and statuses per season, with team-level reconciliation.
- pitcher_label_coverage.csv: one row per frozen forecast pitcher-season, including
  existing G/OUTS, observed boxscore G, certification and proposed G. Only verified
  non-appearances have proposed OUTS=0.
- coverage_issues.csv: missing/invalid sources, identity lookup failures, conflicts.
- input_hashes.json and output_sha256.json: source/cache provenance and output hashes.

Review the report before proposing any label migration. 2026–27 offseason news
does not enter the audit. A successful command can still report incomplete
coverage; check season_certified and the issues file.

For a v1.26.0 rerun, extract over the prior script and use a fresh output
directory with the existing cache. Use --download to allow only missing requests,
including identity lookups previously skipped because of reconciliation conflicts.
