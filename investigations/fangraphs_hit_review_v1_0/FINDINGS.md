# FanGraphs hit/type game-log review

All 15 metric differences across ten player-season roles have been located in five games. Every new FanGraphs game-log sum equals its supplied original season total. The identified game differences fully account for each season residual. Newly retrieved MLB boxscores agree with the frozen MLB game logs for all 15 compared metrics. No reference or pitch counts were modified.

| Date | Game | Hitter / opposing pitcher | FanGraphs game H: hitter / allowed | MLB game H: hitter / allowed | Relevant MLB play candidate |
|---|---:|---|---:|---:|---|
| 2016-09-27 | 449213 | Chase Headley / Robbie Ross Jr. | 0 / 1 | 1 / 2 | Headley single to shortstop, play index 65 |
| 2016-09-30 | 449258 | Charlie Culberson / Madison Bumgarner | 0 / 8 | 1 / 9 | Culberson single to shortstop with runner out at third, play index 14 |
| 2016-10-02 | 449292 | Aaron Altherr / Jim Henderson | 1 / 3 | 0 / 2 | Altherr reaches on pitcher field error, play index 64 |
| 2016-10-02 | 449294 | Adam Wainwright / Ryan Vogelsong | 1 / 5 | 0 / 4 | Wainwright reaches on third-base field error and reaches second, play index 32 |
| 2022-08-13 | 662110 | Luis González / Duane Underwood Jr. | 1 / 1 | 0 / 0 | González reaches on third-base field error, play index 45 |

Wainwright's FanGraphs game log also contains one double on October 2. MLB records zero doubles. The other four hitters' differences involve singles. Together these account for five hitter H rows, five additional hitter hit-type rows, and five pitcher H rows: 15 metric rows from five paired game differences.

## Evidence interpretation

The game dates and opposing-player pairings are established by the logs. The current MLB feeds identify the play candidates above. The FanGraphs game totals and MLB outcomes are consistent with hit/error classification disagreements. FanGraphs play-by-play evidence has not been supplied, so these candidates are not claimed as confirmed cross-provider play alignments. They are not proof that a historical scoring revision occurred, or when it occurred.

For Culberson, the MLB single also includes an out on the bases. That makes hit versus another play classification a specific review point; this audit does not reclassify it. Full MLB plate-appearance descriptions for each target hitter are retained, including non-candidate outcomes, in mlb_target_batter_plays.csv.

## Remaining scope details

Two zero-hit Wainwright game-log entries (May 12 and June 27, 2016) lack entries in the frozen MLB hitting game log. They remain unmatched, rather than inserted as MLB zeros. González's September 8, 2022 doubleheader is compared as a date aggregate: both logs contain two appearances and zero H/1B in total. No game-order assignment is guessed. Neither issue contributes to the 15 season differences.

The pitching CSVs contain duplicate unused GS headings. They remain intact in the source files. H is unique and is the only selected pitching comparison metric.

## Next evidence

For confirmation of individual cross-provider play labels, obtain FanGraphs Play Logs for these five hitters and dates only. They should show inning, batter, pitcher, play description and any scoring notes. Do not alter the actuals importer, Statcast outcomes, or reference season counts based on paired residuals. An explicit source policy will be required before modeling; the original 32 reconciliation differences remain unchanged.
