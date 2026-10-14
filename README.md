# PlayerValuation — historical warehouse and projection accuracy

## Stage 3 historical backtest

Run `python backtest_consensus_projections_v1_0.py`. Configuration is in
`config/consensus_backtesting.json`; results are in
`outputs/consensus_backtest_v1_0/backtest_report.md`.
For another run, supply `--output outputs/consensus_backtest_run2`.
The builder protects existing nonempty results and opens the warehouse read-only.

This test calls the unchanged Stage 3 generator for 2024, 2025 and 2026,
with season-available source coverage and the configured weights. It compares
component-derived forecasts against source-statistic means and a diagnostic
common-component source pool on identical players. Actual results never enter
forecast generation or source weights. Unmatched forecasts remain in the
season exports and are excluded from accuracy, not scored as zero.

The report includes MAE, RMSE, signed bias, correlations and rank errors;
exact paired sample membership; source coverage and missing-value exclusions;
and projected-roster, disagreement, low-exposure and component-pool diagnostics.
The projected-roster cohorts require preseason consensus PA >= 300 or IP >= 40
and positive actual exposure for retrospective scoring. They are an analysis
proxy for roster relevance, not a league-specific roster definition.
Counting baselines are independently checked on the exact available-source
Stage 3 pools, which differ from Stage 2B complete-source samples.
These years informed earlier model choices, so this is retrospective validation,
not a new independent holdout. Diagnostic alternatives do not modify the
production consensus or its configuration.

## Stage 3: 2026 consensus projections

The consensus has already been generated. Start with
`outputs/consensus_2026_v1_0/audit/consensus_report.md`, then open
`hitter_consensus.csv` and `pitcher_consensus.csv` in that output folder.
To generate another build:

```powershell
python build_consensus_projections_v1_0.py --output outputs/consensus_2026_run2
```

Configuration is in `config/consensus_projections.json`. It selects season 2026
and the reviewed analytical warehouse. All analytical players are included,
including projections unmatched to actuals, prospects and low-playing-time
players. No actual-stat values enter aggregation. Names, ID namespaces, teams,
source coverage and original contributing record IDs accompany every player.
Two-way players retain one row in each applicable player-type output.

Base stats use equal weights among available sources by default. A zero value
is a real projection and participates; missing values do not. Source weights
are renormalized for every player/statistic. A single available source can
produce a consensus and is flagged as limited coverage.

For example, the following hitter override gives Steamer twice the influence
of BAT X for HR, with the other configured sources retaining their base weights:

```json
"metric_weight_overrides": {"HR": {"Steamer": 2, "THE BAT X": 1}}
```

Weights must be finite and nonnegative; zero excludes a source from that stat.
Derived-rate overrides must be applied to their components rather than setting
an unrelated AVG/ERA/WHIP weight. All contributing weights and source values are
recorded in `metric_provenance.csv`. Decimal output counts are intentional.

Rates use the exact consensus components: AVG = H/AB; OBP =
(H+BB+HBP)/(AB+BB+HBP+SF); SLG = (1B+2*2B+3*3B+4*HR)/AB; OPS = OBP+SLG;
ERA = 9*ER/IP; WHIP = (H allowed+BB)/IP. K/9, BB/9, HR/9, counting QS and
SV+HLD are included. Missing components and zero denominators yield unavailable
rates, never zeros or substitutes from actuals. CSV blanks correspond to JSON
null. FIP, BABIP and wOBA retain weighted source estimates.

The earlier blend backtest averaged source rates directly. These coherent
component-derived rates are a different aggregation. The separate historical
test is now delivered in `outputs/consensus_backtest_v1_0`; it evaluates both
accuracy and low-exposure distortions without claiming independent holdout
evidence or guaranteed improvement from this reconciliation.

Available component source pools can differ. Every difference is recorded in
`audit/mixed_component_pools.csv`; no missing component is invented to force
identical coverage. Rounded source counts, especially for tiny playing-time
projections, can yield rates that differ from supplied source skill rates.
`audit/derived_vs_source_rates.csv` highlights material differences. The player
coverage audit flags exposure below 100 PA or 20 IP for rate interpretation;
these players remain included.

`audit/high_disagreement.csv` flags coefficients of variation of at least .25
when two or more contributors exist. Source spread is descriptive disagreement,
not calibrated confidence. For derived rates the spread uses original source
rates, while formulas/components describe the actual consensus rate. Review
`audit/missing_components.csv` and `audit/player_coverage.csv` before selecting
the player pool for valuation. Original files and the warehouse are unchanged.

## Stage 2B: held-out consensus blend tests

The blend backtest has already been run. Start with
`outputs/blend_backtest_v1_0/blend_backtest_report.md`. To generate another run:

```powershell
python backtest_projection_blends_v1_0.py --output outputs/blend_backtest_run2
```

Configuration lives in `config/blend_backtesting.json`. No new dependencies or
input files are needed. The evaluator and backtester use Python's standard
library and read the resolved warehouse without modifying it.

Three methods are fixed before evaluation: equal weighting, inverse training
MAE shrunk 50% toward equal weights, and nonnegative sum-to-one weights fitted
to regularized training squared error. The ridge strength is fixed at 0.1 times
training equal-blend MSE. No held-out outcomes enter fitting or parameter tuning.
Training seasons receive equal total weight, irrespective of player counts.
The optimizer uses feasible pairwise coordinate transfers on a convex objective
and requires convergence before emitting fitted weights.

The primary chronological tests train 2024 to predict 2025 and train 2024–2025
to predict 2026. A separate train-2025/test-2026 fold examines newer source
coverage; it does not count as a third independent validation year. Source pools
are explicit: shared-history uses sources present in every training year;
expanding pools assign each incomplete-history source a neutral equal share,
then distribute the remaining share using the trained sources' relative weights.
For example, a new source among four gets 25%; trained sources divide 75%.

All methods score exactly the same held-out players within each comparison.
The default hitter cohorts require positive actual PA or at least 300 PA;
pitcher cohorts require positive actual IP or at least 40 IP. A separate saves
cohort selects closer candidates using at least one participating source's
preseason projection of five or more saves. It never filters on actual saves,
so projected closers who finished with zero saves are scored. Unmatched players
remain excluded rather than being assigned zero. Actual-playing-time thresholds
condition the evaluation on realized opportunity and are not deployable player
selection rules.

The consistency screen asks for at least 1% MAE improvement in both primary
years with no more than 1% RMSE deterioration in either. This is a fixed,
descriptive screen, not statistical proof. Comparing methods on these tests
and choosing one afterward still needs confirmation on a new season. The
delivered fold weights are research artifacts, not final production weights.
Individual player aggregation and coherent rate/count reconciliation belong in
the subsequent consensus builder.

`fold_weights.csv`, `heldout_predictions.csv` and `sample_memberships.jsonl`
allow independent verification of every weight, forecast and earlier-season
training sample. `fold_accuracy.csv` gives MAE/RMSE/bias, correlations, rank
errors, and improvement against the same-sample equal baseline.

## Stage 2: first accuracy report

Stage 2 has been run against the resolved warehouse. Start with
`outputs/accuracy_v1_0/accuracy_report.md` and `common_player_accuracy.csv`.
No rerun is needed to review the delivered results. To generate a new run:

```powershell
python evaluate_historical_projection_accuracy_v1_0.py --output outputs/accuracy_run2
```

The evaluator uses only the Python standard library. It opens the warehouse
read-only and records its SHA-256 hash. Thresholds, metric groups, warehouse
location and output folder live in `config/accuracy_evaluation.json`.
Relative configured paths resolve against the project folder. Optional
`--warehouse` and `--output` paths resolve against the terminal's current folder.
Existing outputs are never overwritten.

The three hitter cohorts require positive actual PA, then thresholds of
0, 100 or 300 PA. Pitcher cohorts similarly require positive actual IP with
thresholds of 0, 40 or 100 IP. These are research cohorts, not a guarantee of
fantasy relevance; the 100-IP cohort favors starters. Projected playing-time
floors are configurable and default to zero. For fair comparisons, a player
must satisfy every participating source's projected floor.
Actual-threshold cohorts condition on observed playing time. They describe
players who appeared in MLB, rather than the full preseason pool or the risk
of never appearing. Compare the all-matched and higher-threshold results when
assessing injuries and playing-time misses.

Each season/metric/cohort has separate individual-source, all-source common
player and pairwise source samples. All-source comparisons include every source
with a finite projection for that metric in that season, before cohort filters.
Metric-unavailable sources are shown in `metric_availability.csv` and omitted
only for that metric. If a capable source has no eligible players, the common
sample is empty rather than quietly removing that source. Uneven historical
source coverage is preserved, and seasons are not pooled.

Every comparison requires complete projected and actual values. Unmatched
players never enter scoring and are never assigned zero actual statistics.
All reviewed duplicate exclusions and Greg Jones's unresolved advanced metrics
carry through from Stage 1B. Actual OPS is derived from OBP + SLG where absent;
every derivation is logged. Existing source values are not replaced. Skill
metrics such as HR/PA and K/9 are separate from opportunity and counting stats.
Rate outcomes such as AVG, ERA and WHIP also appear in the fantasy group.

Bias is **projection minus actual**, so positive means overprojection. MAE and
RMSE retain metric units. Percentage metrics are fractions: an error of .02
means two percentage points. Scores are equally weighted by player. No pooled
AVG, ERA or WHIP is calculated, and missing hitter AB is not invented for rate
weighting. Pearson and Spearman correlations, average tied ranks, absolute rank
error and normalized rank error require 30 observations; constant-series
correlations are unavailable. Lowest-MAE labels also require at least 30 pairs
and are descriptive, without statistical significance claims.

`evaluation_pairs.csv` stores linked player-level values/errors. Exact common
samples are saved in `cohort_memberships.jsonl` under `sample_id`; summary and
pairwise outputs reference that ID. `input_coverage.csv` accounts for every
selected projection. `missing_metric_pairs.csv` records missing-value exclusions.
Start future consensus work only after reviewing these results. This evaluator
fits no weights: optimized consensus requires earlier-season training and a
held-out season for testing.

## Stage 1B: reviewed warehouse

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
