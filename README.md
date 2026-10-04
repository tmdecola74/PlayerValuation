# PlayerValuation — Stage 1B

The latest delivered build is `data/warehouse_resolved/`. It includes the seven
identity groups and 16 duplicate selections confirmed by the project owner on
October 4, 2026. Earlier builds are retained as historical snapshots. Review the latest
build's `audit/validation_report.md` or the project-level `audit/` reports.

For Stage 2 use `analytical_hitter_projections` and
`analytical_pitcher_projections` in SQLite or the corresponding CSV exports.
They contain one selected row per analytical key. All input rows and statistics
remain in the original projections tables. `record_selection` and the audit's
`duplicate_resolutions.csv` document every choice. The 15 playing-time pairs use
the larger PA/IP row. Greg Jones uses the first source row as a representative
of the identical core fantasy statistics; WAR, wRC+, Off and Def are omitted
from analytical statistics because their correct versions remain unresolved.
Empty analytical CSV cells mean unavailable, not zero.

`config/duplicate_resolutions.json` pins each owner-confirmed selection to the
exact record IDs of that duplicate group. Changing the original input file
changes its fingerprint and record IDs, so a stale selection stops the build
before outputs are created. Unreviewed duplicate groups are retained in source
tables but excluded from analytical views. `passed_with_metric_exclusions`
means key checks pass while explicitly listed advanced metrics remain excluded.

Build a historical preseason projection warehouse with lossless source fields,
canonical player identities and explicit projection-to-actual matching. Stage 2
accuracy calculations are deliberately outside this build.

## Run in PyCharm or a terminal

Use Python 3.10 or newer. Install the XLSX reader:

```powershell
python -m pip install -r requirements.txt
python build_historical_projection_warehouse_v1_0.py
python -m unittest discover -s tests -v
```

The default configuration reads your original folders at
`D:/JonAPythonClass/pycharm/last3yrsproj` and
`D:/JonAPythonClass/pycharm/EOYstatistics`. Inputs are opened read-only.
The actual-stat files are CSVs, as found on disk. The 2025 RotoWire input is XLSX.
Edit `config/warehouse.json` to change locations or add a future season. Each
file is explicitly declared; absent source/year combinations are not fabricated.
JSON avoids another configuration dependency. Relative input roots resolve
against the project folder. File paths resolve against their configured root.

The default output is `data/warehouse/`. Subsequent builds require a new or
empty destination; existing builds are never overwritten:

```powershell
python build_historical_projection_warehouse_v1_0.py --output data/warehouse_review2
```

Exit 0 means ingestion and analytical key checks passed; exit 2 means the complete warehouse
was built but conflict, duplicate canonical key, invalid season or numeric
parsing issues require review. Missing identifiers and unmatched rows remain
visible in audits even if the ingestion status is passed. Missing inputs and
malformed file widths abort before output creation. A passed build is not a
guarantee that all name matches have been independently verified.

## Files and database

`historical_projection_warehouse.sqlite` contains:

* `players`, `player_id_crosswalk`, `player_aliases`
* `ingestion_runs` and the `projection_runs` view
* `hitter_projections`, `pitcher_projections`
* `hitter_actuals`, `pitcher_actuals`
* `metric_registry`, `source_field_map`, `record_selection`
* `analytical_hitter_projections`, `analytical_pitcher_projections` views

Stats tables retain one record per input row with `record_id`, file/run ID,
physical row number, source, season, canonical player ID, matching status,
`actual_record_id`, `metrics_json` and **all** source columns in `raw_json`.
Canonical fields and registry-derived rates are exported to wide CSVs for
inspection. SQLite is the authoritative lossless warehouse. JSON can be queried
with SQLite `json_extract(metrics_json, '$.HR')`.

The intended analytical key is Season × Source × Player for projections and
Season × Player for actuals (separately for hitters/pitchers). These are indexed
but intentionally not enforced as unique: duplicate input rows must survive and
be audited. A projection joins an actual only when exactly one actual row exists
for the same Season × Player × PlayerType. Multiple projection runs for the
same analytical key require cohort selection before Stage 2.

## Identity policy

FanGraphs, MLBAM and RotoWire IDs have separate namespaces. Populated IDs are
strings (including FanGraphs prospect IDs); trailing spreadsheet `.0` is removed.
ID co-occurrence establishes crosswalk edges. The configured FanGraphs alias
policy accepts a prospect `sa...` ID and one numeric ID only when they share
exactly one MLBAM anchor and all recorded names normalize identically.
These transitions are listed in `verified_id_aliases.json` (verification refers
to internal evidence, not an external identity service). Other components with
multiple IDs in the same namespace are isolated and cannot match actuals.
`config/reviewed_aliases.json` records owner-confirmed exceptions to the exact
name rule. An exception applies only to the exact complete set of namespace/ID
pairs listed in the review. It still requires one MLBAM anchor, one numeric
FanGraphs ID and prospect IDs matching the configured pattern. It does not
authorize other merges, and all original names remain in the source records.
Names are Unicode-normalized with punctuation and whitespace removed.
An exact normalized name can bridge an unlinked identity to a FanGraphs identity
only if there is exactly one candidate across the complete corpus and the name
identifies only one player within each source namespace. No fuzzy
matching or team-only disambiguation is performed. Traded players remain
matchable by ID despite different teams. All bridge matches are explicitly
marked `unique_name_bridge`; review them before using their data in backtesting.

`config/identity_overrides.json` accepts reviewed crosswalk edges:

```json
[{"from_namespace":"rotowire","from_id":"123",
  "to_namespace":"mlbam","to_id":"456"}]
```

Override edges remain subject to namespace-conflict checks. Changes to the
identity graph can change canonical IDs; freeze and version the crosswalk used
for any published analysis. IDs are deterministic for the same input graph.
Records without identifiers receive isolated keys unless safely name-bridged.

## Metrics and preservation

Mappings and ID columns live in configuration profiles. K/SO map to canonical
SO; source K remains in raw JSON. Metric metadata classifies opportunity, skill,
fantasy outcome, market, uncertainty and other context; skill rates can also be
fantasy categories. Source-specific fields without registry entries are retained
and listed in source_field_map with a blank canonical metric. Registry coverage
can be extended without editing ingestion code.

Percentage strings ending in `%` are converted to fractions; bare numeric
percentages in these files are already fractions. IP is configured as decimal
innings for these exports; future baseball-notation inputs must explicitly set
`ip_notation` to `baseball` (e.g. 10.2 means 10⅔). Repeated actual pitcher headers
are preserved as `HR/FB`, `HR/FB__2`, `FB%`, `FB%__2`: only the first is mapped
unless an explicit mapping is added. AB is absent from hitter actuals and is
not reconstructed from potentially incomplete components. No zero-denominator
derived rates or fabricated missing stats are generated.

## Audits

The warehouse's `audit/` folder contains validation summary CSV/JSON/Markdown,
every unmatched projection, duplicate rows, numeric/season issues and identity
conflict components. Counts are row counts; duplicate counts include all rows
participating in a collision, not merely excess rows. Missing key means missing
source ID or season; missing names are reported separately. Unmatched does not
prove a player accumulated zero MLB statistics. Effective configuration,
registry, overrides and source SHA-256 fingerprints accompany each build.

The project-level `audit/` folder contains the delivered run's audit copy and
test results. Generated data and original sources are ignored by Git; code,
configuration and reviewed audit reports can be committed. No Git commits or
remote publication are performed by the builder.
