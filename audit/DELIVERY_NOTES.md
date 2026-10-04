# Stage 1B — owner-reviewed analytical selections

Latest results: data/warehouse_resolved/. Earlier warehouses remain historical
snapshots. Use analytical_hitter_projections.csv and
analytical_pitcher_projections.csv (or the same-named SQLite views) for Stage 2.

All 57,855 source rows remain intact, including both records in every duplicate
pair. Original source files and their hashes are unchanged.

The owner confirmed the seven identity alias groups and the duplicate selection
policy. Configuration pins each duplicate decision to the exact candidate record
IDs, selected record, reason, reviewer and date. For seven hitters the larger PA
projection is selected; for eight pitchers the larger IP projection is selected.
Greg Jones's identical core fantasy projection uses the first source row as a
representative, with wRC+, Off, Def and WAR excluded from analytical statistics.
Those four differing values remain available in the original source records.

* 16 duplicate groups resolved; 16 alternate projection rows excluded from
  analytical use, with no deletion from the warehouse.
* 53,291 analytical projection rows from 53,307 original projection rows.
* Raw projection matching totals: 13,509 matched and 39,798 unmatched.
  See validation_summary.csv for selected analytical matching counts by group.
* Zero unresolved duplicate groups; zero identity conflicts.
* Three original projection rows still lack source IDs and remain audited.
* Four unresolved advanced metric exclusions, all for Greg Jones.
* Status: passed_with_metric_exclusions.
* 17 tests passed, including complete source round-trip, unchanged hashes,
  analytical key uniqueness, owner-approved PA/IP selections, retained original
  rows, excluded Greg Jones metrics and rejection of stale record selections.

Read duplicate_resolutions.csv for the selected and alternate records and
unresolved_metric_exclusions.csv for the four advanced metric exclusions.
Unmatched players remain explicitly preserved; missing actuals are not zeroed.
