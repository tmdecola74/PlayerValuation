Minor league coverage branch — audit and exact-ID links
Prepared November 23, 2026

RESULT
All 15,165 hitter and 13,166 pitcher source rows are preserved in the prepared
stint tables. All standard-to-advanced matches are unique. Every pitcher batted-ball
row and 15,163 hitter batted-ball rows match uniquely through shared source fields.
The matching uses field values, not dashboard ordering or names alone.

Robinson Chacon (MLBAM 823850), KCR DSL 2024, has two separate 67-PA rows.
Different AVG values distinguish their standard/advanced records, but both have
identical shared identifiers, PA and BABIP in the batted-ball dashboard. Neither
batted-ball row can be assigned definitively. They are preserved in
hitters_unassigned_battedball.csv; the prepared rows retain standard/advanced
statistics with batted-ball fields blank and an explicit ambiguity status.
Actual affiliate/team identifiers or game-level records are needed to resolve this.
Repeated organization/level rows were not discarded or summed.

PA COMPONENTS
1,176 source rows have positive PA minus (AB+BB+HBP+SF+SH), from 1 to 11 PA.
These discrepancies remain unresolved in unresolved_PA_components.csv.
Interference or other omitted events are possible explanations, not established
facts. Keep source PA for BB%/K%; do not force the components to reconcile or
fabricate missing events. Exact reconstruction requires additional event records.

EXPORT COVERAGE
Observed minimums across every season/level cell are 50 PA and 20 IP.
These are strong evidence of export cutoffs, but the files do not preserve the
actual leaderboard filter settings. Full lower-exposure coverage requires new
exports with minimum PA/IP explicitly set to zero. Absence is not nonparticipation.
Do not use these truncated samples as complete league totals or population priors.

TRACKING POLICY
Exclude DSL/CPX pitch-derived statistics from initial model inputs. The 2023
DSL/CPX pitch totals are about two pitches per PA, with inflated swinging-strike
rates. Later seasons look different; a plausible value is not proof of completeness.
Retain these fields in raw data with exclusion labels. A through AAA pitch fields
remain research-only until definitions, coverage and predictive value are validated.
GB/LD/FB and directional rates are also research-only: these files lack explicit
batted-ball denominators, park IDs and separate affiliate IDs. These dashboards
are not Statcast exit velocity/barrel measurements.

Primary references:
https://blogs.fangraphs.com/eric-longenhagen-prospects-chat-10-3-25/
https://tht.fangraphs.com/scouting-the-minors-pitch-by-pitch-swinging-strike/
https://baseballsavant.mlb.com/statcast-search-minors

MODEL LINK
Exact MLBAMID to v1.43 mlbam_id, separated by hitter/pitcher role.
776/1,024 published hitters and 1,000/1,487 published pitchers have supplied
minor history. There are 4,780 hitter IDs and 4,880 pitcher IDs outside the current
same-role release, not necessarily new prospects or confirmed MLB roster members.
No one-to-many MLBAM-to-MinorMasterId/FG-ID conflicts were found within these
exports. This is an observed crosswalk, not external certification of every identity.
Existing same-role release IDs without these histories: 248 hitters, 487 pitchers.

FILE USE
*_stints_linkable.csv: prepared records, source row references and usage flags.
*_v1_43_coverage.csv: one row per published same-role player; availability only.
identity_crosswalk.csv: observed source identity relationships.
release_identity_links.csv: all observed minor IDs, exact same-role release links.
export_thresholds.csv / tracking_diagnostics.csv: season/level checks.
source_manifest.json: hashes of all six source files and top-level release files.
audit_summary.json: machine-readable results.

BOUNDARY
This package supersedes the preliminary joined exports in the parent outputs
folder. It is a separate prepared coverage branch, not installed in the production
model. The original exports and published v1.43 release were verified unchanged.
No MLE factors, model settings, playing time, forecasts, or valuation wiring changed.
2026 minor history is available for 2027; reviewed 2026 MLB outcomes were not
opened or used to select settings. Export snapshot/availability dates are unknown,
so these files alone do not establish historical preseason availability.

NEXT REQUIREMENTS
Zero-minimum exports for complete coverage; affiliate/game-level evidence for
unresolved rows; translation assumptions and earlier-only validation before any
projection adoption. Park/league context is still needed for defensible MLEs.
