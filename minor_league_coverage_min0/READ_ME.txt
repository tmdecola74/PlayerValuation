Minor league coverage update: zero-minimum exports
November 23, 2026

This package supersedes the earlier coverage package for the same 2023-2026
seasons. It prepares source data and links identities; it does not change v1.43
or apply MLB equivalencies.

COVERAGE
                         Earlier     Minimum zero     Added
Hitter source rows        15,165          21,651        6,486
Pitcher source rows       13,166          27,870       14,704
Hitter MLBAM IDs            5,556           6,551          995
Pitcher MLBAM IDs           5,880           8,888        3,008
Same-role release hitters    776             934          158
Same-role release pitchers 1,000           1,318          318

Every earlier source row appears unchanged in its corresponding new dashboard,
including multiplicities. All added hitter rows have fewer than 50 PA; all added
pitcher rows have fewer than 20 IP. The user confirmed the minimum setting of zero.
All six levels (AAA, AA, A+, A, CPX, DSL) and all four seasons are represented.
These checks remove the identified threshold gap; they do not independently
certify that Fangraphs captured every game or player.

IDENTITY
All rows contain MLBAMID, MinorMasterId and PlayerId. No MLBAM-to-multiple-
MinorMasterId or MLBAM-to-multiple-PlayerId conflicts were observed in these files.
Exact MLBAM links connect 934/1,024 release hitters and 1,318/1,487 release pitchers.
90 release hitters and 169 release pitchers have no history in the supplied
same-role exports. Absence does not establish nonparticipation. Names were not used
as a substitute for IDs. Roles remain separate, including position-player pitching.
IDs outside the release are an observed coverage pool, not an MLB roster forecast.

JOINS AND FLAGS
All standard and advanced records match. Shared source fields identify records;
where those fields collide, K% and BB% calculated from source SO/BB and PA/TBF
distinguish candidates within a 0.0000001 absolute tolerance. Rows are never
matched by order alone. All pitcher batted-ball records match.

Four hitter batted-ball assignments remain ambiguous: two Robinson Chacon KCR
DSL 2024 rows and two Adrian Silva NYM DSL 2025 rows. Their standard/advanced
records are retained, with ambiguous batted-ball values left unassigned. The four
original batted-ball rows remain in hitters_unassigned_battedball.csv. A specific
affiliate or game-level identifier is required to establish their correspondence.

1,233 hitter rows have PA greater than AB+BB+HBP+SF+SH, by 1-11 PA. These
include all previously flagged discrepancies. Keep supplied PA and counts, with
the residual flagged. Additional events or scoring evidence are needed to explain
the difference; no missing events were invented.

There are 368 hitter rows with zero PA and 51 pitcher rows with zero outs.
These remain available as source observations. Rate inputs require a positive
metric-specific denominator: e.g. PA for K%, AB for AVG, outs for ERA, TBF for
pitcher K%. A zero-out pitcher can still have positive TBF. Source zero/missing
rate values are retained verbatim, not treated as valid estimates without checking
the denominator. See zero_exposure_records.csv and missing_value_inventory.csv.

TRACKING
DSL/CPX pitch-derived statistics remain excluded from initial model use, based on
the prior documented scoring limitations and observed historical anomalies.
A through AAA pitch fields remain research-only pending validation. Batted-ball
percentages lack explicit BBE sample counts and park/affiliate context. In tiny
samples, GB%+LD%+FB% may be zero because there were no classified balls; a failed
sum diagnostic alone is not proof of erroneous source data. Missing rates stay
missing. Pitches/PA diagnostics use only rows with numeric pitch/ball/strike counts.
These are Fangraphs dashboards, not Statcast exit-velocity or barrel measurements.

Prior primary references:
https://blogs.fangraphs.com/eric-longenhagen-prospects-chat-10-3-25/
https://tht.fangraphs.com/scouting-the-minors-pitch-by-pitch-swinging-strike/

FILES
*_stints_linkable.csv: all source stints, source-row references and policy flags.
*_v1_43_coverage.csv: availability by existing same-role release player.
identity_crosswalk.csv / release_identity_links.csv: observed exact-ID links.
comparison_to_prior_exports.json: row-by-row multiset comparison and coverage.
export_thresholds.csv / tracking_diagnostics.csv: season/level diagnostics.
unresolved_PA_components.csv / unresolved_dashboard_matches.csv: retained flags.
source_manifest.json: original export and published release file hashes.
audit_summary.json: summary counts.

No source file or published release file changed. No translation factors, settings,
forecasts, workload or valuation wiring changed. No 2026 MLB outcome evaluation
files were read. 2026 minor history can support 2027; historical availability dates
are not established by these exports. The next modeling work is a component-
translation specification with league/season/park context and earlier-only testing.
