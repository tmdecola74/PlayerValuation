# Findings: the 15 hit/type differences

Completed 31 October 2026. Downloaded 20 targeted MLB player-stat responses (game log plus season for ten player-season roles), compared 929 game/metric rows, then inspected only three MLB game feeds. No broad game batches were downloaded.

All 15 selected reconstructed season totals equal both the current MLB game-log sums and the separately retrieved MLB season totals. All overlapping game/metric counts agree. The supplied FanGraphs totals remain different by one. These results support a source-total disagreement; they do not prove a scoring revision, establish its date, or justify overwriting either source.

## Season comparison

| Season | Player / role | Metric | Supplied FanGraphs | Reconstructed | MLB log sum / season |
|---|---|---|---:|---:|---:|
| 2016 | Adam Wainwright / hitter | H | 14 | 13 | 13 |
| 2016 | Adam Wainwright / hitter | 2B | 8 | 7 | 7 |
| 2016 | Chase Headley / hitter | H | 117 | 118 | 118 |
| 2016 | Chase Headley / hitter | 1B | 84 | 85 | 85 |
| 2016 | Charlie Culberson / hitter | H | 19 | 20 | 20 |
| 2016 | Charlie Culberson / hitter | 1B | 15 | 16 | 16 |
| 2016 | Aaron Altherr / hitter | H | 40 | 39 | 39 |
| 2016 | Aaron Altherr / hitter | 1B | 30 | 29 | 29 |
| 2016 | Ryan Vogelsong / pitcher | H | 81 | 80 | 80 |
| 2016 | Jim Henderson / pitcher | H | 35 | 34 | 34 |
| 2016 | Madison Bumgarner / pitcher | H | 178 | 179 | 179 |
| 2016 | Robbie Ross Jr. / pitcher | H | 46 | 47 | 47 |
| 2022 | Luis González / hitter | H | 79 | 78 | 78 |
| 2022 | Luis González / hitter | 1B | 56 | 55 | 55 |
| 2022 | Duane Underwood Jr. / pitcher | H | 58 | 57 | 57 |

## Three appearances inspected

The comparison found six missing-game rows (H and 1B for each of three Culberson games). They are appearances outside the reconstructed batting-game inventory, not observed nonzero hit discrepancies:

| Date | Game | Charlie Culberson role | MLB PA | MLB AB | MLB H |
|---|---:|---|---:|---:|---:|
| 2016-04-08 | 446916 | Third-base substitute | 0 | 0 | 0 |
| 2016-04-24 | 447137 | Pinch runner | 0 | 0 | 0 |
| 2016-09-05 | 448909 | Shortstop substitute | 0 | 0 | 0 |

Each feed has no batter play for Culberson, and player hit sums match team hits. These zero-PA appearances do not account for the one-hit difference. No missing reconstructed entry was converted to zero or inserted into Statcast.

Adam Wainwright's MLB season G is 34 while the hitting game log contains 32 entries. Both selected hit totals still reconcile exactly. This participation-count difference is exposed in the CSV; the audit does not certify every role appearance.

## What remains

The season-level hit/type discrepancies are not explained by missing nonzero hits in the reconstructed game totals versus current MLB logs. Locating the dates behind the supplied FanGraphs differences now requires FanGraphs player game logs matching the supplied season exports, especially H, 2B, 3B and HR (hits allowed for pitchers). Start with these ten player-season roles, not additional broad MLB downloads. If those FanGraphs game logs sum to a newer season total instead, retain the source-vintage discrepancy explicitly.

No correction, scoring-revision claim or model-readiness approval is issued. The original reconciliation's 32 numerical differences remain unchanged. The raw MLB requests, retrieval times, hashes, game inspections and input bridge are included for review.
