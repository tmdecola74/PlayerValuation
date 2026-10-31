# Actuals importer and scoring-aware Statcast reconciliation 1.0

## Install and run

Extract this ZIP into:
`D:\JonAPythonClass\pycharm\PlayerValuation`

It contains new scripts/tests, a complete imported reference under
`data/actuals_reference_v1_0`, and its complete verified backup under `backups/`.
It does not include or replace your existing statcast_pipeline_v1_0.py,
ingestion config, projection databases, or previous model code. Keep those.
Do not overlay a manually edited existing actuals_reference_v1_0 folder; choose
another folder for that existing package before extracting if it exists.

The actuals import has ALREADY been run on your two updated FanGraphs exports.
You do not need to re-import or locate the original uploads for the first run.
Dependencies: Python 3.10+ and your existing DuckDB installation.

```powershell
python -m unittest discover -s tests -p "test_actuals_scoring_v1_0.py" -v

python reconcile_statcast_actuals_v1_0.py --actuals "data/actuals_reference_v1_0" --start 2015-03-01 --end 2025-11-01 --output "outputs/actuals_statcast_reconciliation_v1_0"
```

Use a NEW output name on reruns. The audit hashes all selected raw, Parquet and
schedule files, then scans one season at a time. It prints yearly progress.
Hash verification can be quiet and take time. Do not run ingestion/refreshes
simultaneously. Working disk space is needed for one season of selected pitch
columns plus output and its complete backup. DuckDB memory limit is 2 GB.

Return these first:
- reconciliation_report.json
- reconciliation_summary.csv
- discrepancies.csv
- reference_player_coverage.csv
- unknown_events.csv
- invalid_pa_sequences.csv

For individual discrepancy review, also use discrepancy_pa_links.csv and
pa_scoring_trace.jsonl. Those link a player-season to game/PA/pitch IDs and
incoming counts, terminal owners, proposed scored owners, and reasons for any
withheld attribution. Original physical pitch rows remain unchanged.

## What was imported

9,835 hitter seasons and 9,684 pitcher seasons from 2015-2026, keyed by
(season, player_type, MLBAMID). Source CSVs are copied byte-for-byte into
source_files/hitters.csv and source_files/pitchers.csv, including duplicate
Season headings. Those duplicate values were checked for agreement.

Counts are nonnegative integers. Hit components must sum to hits. Innings use
baseball notation: 146.1 -> 439 outs, NOT 146.1 decimal innings. ERA/WHIP and
AVG/OBP/SLG are independently derived from components, with null for undefined
zero-denominator rates. The raw published values and all other source columns
remain in source_rows.csv/Parquet/DuckDB and the original CSV copies.

The reference package provides:
- actuals_reference.duckdb, with materialized player_seasons, actual_counts,
  derived_rates, source_rows and separate historical_counts / holdout_counts views;
- matching CSV/Parquet tables;
- import_report.json, import_review.csv and reference_cross_role_totals.csv.

2026 records carry split=holdout. They are preserved for later evaluation,
never used in the default 2015-2025 reconciliation. A model must still enforce
feature_season < prediction_season in its own loader. This package does not
train a model or promise that a consumer's query is chronology-safe.

All supplied integer components and published comparable rates passed internal
consistency checks. The 459 PA residual review rows are PA minus
AB+BB+HBP+SF+SH; positive residuals can reflect interference/obstruction.
They are NOT silently allocated or rejected.

There are 60 season/metric cross-role total differences (out of 72 comparisons)
between hitter and pitcher exports. Differences are small, but real. There
are no zero-OUTS pitchers in the supplied file. Missing zero-out appearances
are one possible source-scope explanation, not a confirmed finding. FanGraphs
reference totals are not treated as independently certified MLB totals.
Use reference_player_coverage.csv and MLB evidence to identify missing IDs.
Do not repair source totals merely to make them agree with Statcast.

## Scoring logic

The terminal-outcome layer counts one completed PA per recognized terminal
event. Hitter PA/AB, H/1B/2B/3B/HR, BB/IBB/SO/HBP/SF/SH and pitcher
TBF/H/HR/BB/IBB/SO/HBP are compared. Interference consumes PA but not AB.
Runner-only events and truncated PAs do not manufacture completed PAs.
Unknown event codes and inconsistent terminal sequences remain review cases.

The rule layer uses pre-pitch substitution counts for these limited rules:
- OBR 9.15(b): inherited two-strike strikeouts credit the outgoing batter's
  strikeout, AB and PA. Other completed outcomes credit the terminal batter.
- OBR 9.16(h): a completed walk at an incoming count of 2-0, 2-1, 3-0, 3-1 or
  3-2 credits the outgoing pitcher with the walk and batter faced. Other
  outcomes, including strikeouts and HBP, credit the terminal pitcher.

Only a single relevant observed substitution with a known count and no pitch
gap is automatically attributed. Multiple relevant substitutions, incomplete
starts and missing counts remain review cases. Aggregate reference differences
are never used to choose an owner. scoring_conservation.csv verifies that
credit transfers preserve all role/season/metric totals.

Source rules (consulted directly; no rulebook text bundled):
- https://img.mlbstatic.com/mlb-images/image/upload/mlb/hhvryxqioipb87os1puw.pdf
  OBR 9.15(b), 2022 edition.
- https://img.mlbstatic.com/mlb-images/image/upload/mlb/atcjzj9j7wrgvsm8wnjq.pdf
  OBR 9.16(h), 2021 edition.

Outputs distinguish terminal_count, rule_count, evidence_count and each
corresponding difference. The rule layer is a supported attribution candidate;
an exact match is reference corroboration, not independent event certification.
A missing player is unknown, not an observed zero. A participant who appears
in pitches can legitimately have zero completed PA/TBF.

## Optional MLB game evidence, after the first review

The first reconciliation is offline. It also writes game_fetch_plan.csv with
all observed regular-season games and priorities. Start with a small batch of
player-change games:

```powershell
python download_mlb_scoring_evidence_v1_0.py --plan "outputs/actuals_statcast_reconciliation_v1_0/game_fetch_plan.csv" --cache "data/mlb_scoring_evidence_v1_0" --scope player_changes --max-games 25
```

Repeat the same command to resume; cached games are hash-checked and skipped.
The limit counts new games, not cached ones. --max-games 0 downloads all games
in the chosen scope. Scope all_review_games includes games involving
unresolved player-season differences. Scope all_games downloads the entire
selected game's census and can be much larger. No new pitch download occurs.
Three bounded retries, a one-second pause, and a cache lock are used.
Do not remove a download.lock unless you have confirmed no downloader runs.

Rerun reconciliation into a new output, adding:

```powershell
python reconcile_statcast_actuals_v1_0.py --actuals "data/actuals_reference_v1_0" --start 2015-03-01 --end 2025-11-01 --mlb-feed-cache "data/mlb_scoring_evidence_v1_0" --output "outputs/actuals_statcast_reconciliation_v1_0_mlb"
```

The cache keeps raw MLB /api/v1.1/game/{gamePk}/feed/live JSON, URL, retrieval
time and SHA256. Game ID, season, regular-season type and completed status are
verified before use. A game/role/metric block is admitted only if both teams'
player counts sum exactly to their supplied team totals; missing fields are
not zeros. Admitted blocks replace only the corresponding game/role/metric in
a separate evidence layer, without changing Statcast or rule-count layers.

For Statcast-supported metrics, this can resolve credit or missing no-pitch
outcomes at game level. For other fields (pitcher OUTS, R/ER and hitter
R/RBI/SB/CS, for example), full-season metric totals are reported only when
EVERY selected game has an admitted block. With partial coverage, partial
counts are explicitly labeled and no full-season comparison is claimed.
G/GS/W/L/SV/HLD/QS are retained in the reference but not reconstructed in
this release. These are NOT filled with zeros.

mlb_feed_usage.json lists admitted and rejected metrics. mlb_pa_evidence.jsonl
preserves candidate matching plays and completed no-pitch plays. An MLB
atBatIndex+1 is a candidate index link only; it never moves credit by itself.
Game-level boxscore corroboration is separate from exact PA identity proof.

## Limits, exit codes and preservation

A successful run (exit 0) means reports were built, NOT that all counts match.
Read status, discrepancies, unknown events and unsupported metrics. Integrity
exceptions fail without publishing a partial output. model_ready remains false
until scoring discrepancies, reference scope, advanced-feature comparability
and model fallback rules have been reviewed separately.

The ingestion ledger is opened read-only. Saved schedules, registered active
versions and file hashes are checked. Obsolete refresh versions are excluded.
The ledger, actuals Parquet and ingestion config hashes are checked again at
completion. The source files and reference/projection warehouses are not
modified. Every complete new output folder is copied to backups and verified
file-by-file before publication. No symbolic links or external-data DuckDB
views are required by the imported reference database.

To re-import later exports (optional; output must be new):
```powershell
python import_fangraphs_actuals_v1_0.py --hitters "data/actuals_reference_v1_0/source_files/hitters.csv" --pitchers "data/actuals_reference_v1_0/source_files/pitchers.csv" --output "data/actuals_reference_v1_0_reimport"
```

Validation: 15 synthetic tests, including read-only preservation, backups,
holdout exclusion, inherited-count rules, duplicate rejection, partial/full
boxscore support and resumable cache checks. The full supplied CSV import was
run here. The 7.4-million-pitch archive is on your PC, so full reconciliation
must run there. MLB network retrieval has not been exercised against live
feeds in this environment; schema variation is reported rather than guessed.
