# PlayerValuation v1.21 — supplemental leaderboard intake and lag features

Extract this ZIP into the existing PlayerValuation project root. **The 13 selected CSV inputs are included**, unedited, under `data/statcast_leaderboards_v1_21/source_files`; no manual copy is needed. The expanded low-minimum hitter batted-ball file is named `hitter_batted-ball2023-2026_min1.csv` in this new folder. Its bytes match the supplied `(1)` export. The earlier restricted hitter export is not imported or deleted. No accepted projection, reference, matrix or previous release is replaced.

Requires the existing project dependencies (DuckDB and standalone I/O/v1.16 diagnostic modules). No new Python package is needed.

```powershell
python -m unittest discover -s tests -p "test_statcast_leaderboards_v1_21.py" -v
python import_statcast_leaderboards_v1_21.py
```

Default inputs:
- Supplied CSVs: `data/statcast_leaderboards_v1_21/source_files`
- Source registry: `config/statcast_leaderboards_v1_21.json`
- Frozen base population: `outputs/standalone_lagged_features_v1_0`
- Frozen expanded archive summaries: `outputs/expanded_statcast_v1_20`

Default output: `outputs/statcast_leaderboards_v1_21`. A verified complete copy is written under `backups`. Existing output folders are rejected; use a new `--output` for reruns. Source hashes are registered in the configuration. Do not edit the CSVs in Excel; an intentional new export should have a separately recorded source version rather than silently replacing this one.

## Scope and source preservation

This is **data preparation, not a model replacement**. It performs no fitting, imputation, shrinkage, feature selection, label replacement or forecasting. It does not read target labels. Counts and source percentages are preserved even when their relationships need review. Every input is copied byte-for-byte into `source_snapshots`, checked against its registered hash, and retained alongside normalized tables.

The source registry explicitly declares family, role, expected/allowed years and, for yearless exit-velocity exports, season. It does not guess season from a filename at import time. The supplied files were inspected when preparing that registry. Unknown retrieval timestamps and filter settings remain unknown; the new registration timestamp is not claimed to be the original download date or a preseason archive.

Joins use MLBAM ID + role + source season. Names are display/provenance only. Duplicate family/role/player-season rows are rejected, including ambiguous team splits; they are never automatically summed or merged. The importer rejects multi-year baserunning rows. Hitter and pitcher records for the same MLBAM ID are legitimate distinct role observations.

## Chronological separation

- Source years 2023–2025 go to `historical/leaderboard_features.csv` and `.parquet`.
- Source year 2026 goes to **`quarantine_2026/leaderboard_features.csv` and `.parquet`**.
- The importer necessarily reads the supplied mixed-year files to separate them. This is explicitly reported as `source_2026_rows_read_and_quarantined: true`.
- Historical and target-2026 lag add-ons read only the historical normalized table. 2026 source values cannot enter either add-on or determine populations, thresholds or definitions.
- No 2027 forecasting is performed. The quarantined data can be separately registered as prior history for a future 2027 release.

**Do not glob all output folders or source snapshots as model inputs.** Mixed-year raw snapshots and the quarantine table contain 2026 data. Use only the explicitly named historical/lag tables. Sample controls and the feature registry are fixed before any modeling. This release makes no model choices from any year.

## Normalization and eligibility

Every normalized row retains original text, original numeric value, normalized value, candidate `value`, units, source ID/row, sample basis, denominator, sample eligibility, definition eligibility and review reason. Percentages in exit-velocity exports are divided by 100; batted-ball and bat-tracking rates already use fractions. Original values are not edited.

Fixed research sample controls are 30 BBE, 100 competitive swings, 30 competitive contacts, or 20 recorded movements. These are not tuned or claimed sufficient for every future model. `eligible` does not certify historical measurement comparability, scope completeness, archive authenticity or predictive value. Coverage remains null where the leaderboard does not supply enough information to measure it; it is never fabricated as 100%.

| Family | Handling |
|---|---|
| Batted ball | Official fractions retain their all-BBE denominator, including Pull AIR. Low-minimum players remain in the import; sample eligibility masks small samples. |
| Bat tracking | Per-contact and per-swing measures retain separate denominators. Average bat speed, fast-swing rate and swing length use the competitive-swing sample. 2023 is explicitly partial, with exact start not claimed from these files. Pitcher-side values describe opposing hitters, not the pitcher's own swing. |
| Exit velocity | Uses exported BBE as a **sample proxy**, not a certified count of every measured EV/contact subset. Hitter EV50 is the hardest half; pitcher EV50 is the softest half allowed. |
| Baserunning | Negative values are valid and preserved. Recorded movements are not all running opportunities. Values are not stolen-base counts; no attempt rate is invented. This branch remains definition-review-only. |

Unsupported denominators remain explicit. `brl_pa`, EV means on FB/LD or GB, and average HR distance are retained but not enabled without their required PA/subset denominators. `percent_swings_competitive` lacks an exported all-swings count and is not reverse-engineered into one. Bat run value/swords and all baserunning model values stay masked for definition review. Counts and signed raw context remain available in the audit tables.

Count/rate relationships are audited without replacing either value. Rounded EV percentages get a ±0.0005001 fraction tolerance (approximately half a tenth of a percentage point). Differences can reflect measurement/sample scope rather than bad data. Affected rates are held with `SOURCE_RELATIONSHIP_REVIEW_REQUIRED`. Batted-ball partition and bat-tracking cross-denominator discrepancies are also held for review. No missing value or omitted player becomes zero.

## Reconciliation

The importer verifies that v1.20 is bound to the same frozen source manifest as the base matrix. It compares only historical 2023–2025 leaderboard measurements with:
- v1.20 batted-ball fractions, pull proxies, mean launch angle and the 8–32-degree angle band.
- The registered original lag-builder audit for average EV, hard-hit rate and barrel rate, when available. An unregistered loose CSV is never substituted.

The detailed report keeps official normalized value, archive value, both sample counts, archive coverage and their difference. It separates missing matches, denominator/scope mismatches, rounding-scale matches and proxy-review cases. A matching pull proxy is labeled `PROXY_MATCH_NOT_CERTIFICATION`; it is not automatically promoted to an official definition. A different denominator is not automatically treated as a scoring revision or missing archive data.

Only sample scope is compared here; matching BBE totals do not prove matching dates, filters or measurement treatment. The review tolerance for pull proxies is two percentage points and is an investigation threshold, not an adoption gate. Original counts and accepted references remain untouched.

This build also writes a corrected copy of the earlier bat-tracking field inventory, excluding `bat_score`, `bat_score_diff` and `bat_win_exp`. These are game-context fields. The v1.20 report itself is preserved unchanged.

## Lag add-ons and coverage

`training_leaderboard_features.parquet` and `holdout_leaderboard_features.parquet` are **long-format** additions to the unchanged frozen base feature populations. They join lag 1/2/3 only, with source season strictly before target season and no source later than 2025. Historical targets remain 2016–2025; target 2026 gets its own prior-history add-on.

Absent players, unavailable earlier years, small samples and unsupported definitions remain null with explicit reasons. No leaderboard participant or 2026 outcome expands the old universe. `outside_frozen_population.csv` identifies supplements absent from the next-season base population for later identity/coverage investigation. It does not merge names or fabricate projections. Raw and normalized audit values are withheld from the model-facing add-ons to prevent bypassing sample/definition masks.

Recent bat-tracking history and the selected baserunning export population are not treated as long historical evidence. A later model must fit preprocessing within earlier folds, keep low-history coverage explicit and preserve 2021. This release supplies inputs, not an adoption decision.

## Reports to return first

- `leaderboard_build_report.json`
- `source_coverage.csv`
- `reconciliation_summary.csv`
- `normalization_review.csv`
- `lag_availability.csv`
- `outside_frozen_population.csv`

Other local artifacts: `source_inventory.json`, `feature_contract.json`, `historical_eligibility_summary.csv`, `reconciliation_details.csv`, `frozen_population_audit.csv`, corrected inventory reports, source snapshots, historical/quarantine normalized CSVs and Parquets, and the two lag add-ons. Keep large normalized/lag tables locally unless a specific trace is requested.

The included validation checks the supplied CSV intake. Production reconciliation results require the user's local frozen v1.20/base matrices; they have not been run here. After reviewing those results, a separate experiment can test approved feature families against the unchanged accepted projections.
