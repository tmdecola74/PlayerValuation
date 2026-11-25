2027 minor-history research release and international identity/status closeout
November 24, 2026

DELIVERY STATUS
This is a separate research release. Production v1.43 remains intact.
All four priority international identity ties are corroborated, ten priority
returners have been reviewed against current public records, and unsupported
international performance remains visible as coverage exceptions.

2027 PROJECTIONS
                                Hitters       Pitchers
Original frozen player count      1,024          1,487
Supported minor-history update      931          1,316
Updates using 2026 minor history    548            790
Recent international gap flags       39             79

Same player-role population and playing-time anchors as v1.43. No new prospect
or overseas arrival is given invented MLB PA/IP. Unsupported minor groups fall
back to the complete v1.43 vector. All inherited source exceptions and workload
limitations remain, even for players whose current roster status is uncertain.
These are conditional skill projections, not certification of MLB employment.

The changed-cell ledger contains 17,591 numeric changes versus v1.43. Counts of
supported updates do not mean every player's forecast or every metric improved.
The earlier historical gate improvements remain development evidence, not an
untouched test or a guarantee about 2027 accuracy.

FROZEN METHOD AND 2026 BOUNDARY
The active arm is the historically successful MLB_PLUS_MINOR method. Park effects
and international translation coefficients remain inactive. Same component groups,
0.5 minor evidence weight, four-year 1/2/3/4 recency weights, complete-group fallback,
and single population prior are retained. Hitter groups update 1B/2B/3B/HR and
derived H/AVG/OBP/SLG/OPS. Pitcher groups update H/ER/BB/SO/HR and derived ERA/WHIP.
All other original fields, including workload, saves/holds and counting anchors
outside those groups, are checked unchanged.

The original final MINOR_vs_MLB gates passed both role bundles through 2025.
The original source contract/gates, final translation factors and population priors
were frozen BEFORE reading 2026 MLB player history. Final minor factors use only
eligible next-year MLB calibration outcomes through 2025. The original v1.42
population priors through 2025 remain frozen; they are not refitted using 2026.
Only after publication_freeze.json was written was 2026 MLB history loaded for
the 2027 player histories. Original certified G/OUTS supplements were validated
and applied as player history. No 2026 forecast errors, fitting, parameter choices
or validation scores are used to select this research release.

ELIGIBILITY CLARIFICATION, REPLAYED BEFORE RELEASE
The historical park comparison required PF availability so its three arms shared
the same samples. The adopted NON-PARK arm does not use the PF value. Its release
eligibility uses verified season/organization/AAA-AA-A+-A affiliate membership,
not a PF predictor. Historical 2021-2025 membership is unchanged. All 11,946 prior
historical minor-arm vectors replayed within 1e-10 under that clarification before
the release was generated. This permits mapped 2026 full-season minor stints to
enter the 2027 non-park arm even though 2026 park factors are absent. No neutral
park factor is fabricated. Unsupported rookie/short-season levels remain excluded.

The full 2,511-player v1.43 2027 baseline numerically replayed before blending.
New projections are coherent and retain the exact original workload/opportunity
anchors. These source checks do not establish that those anchors are appropriate
for the player's current club, injury, retirement or future participation status.

FOUR CORROBORATED IDENTITIES
Player             FanGraphs ID     MLBAM ID    Home registry ID
Teruaki Sato       sa3063811          831664     NPB 41045153
Kaima Taira        sa3062990          838343     NPB 31035136
Hiromi Itoh        sa3063835          808955     NPB 51355153
Si-hwan Roh        sa3012734          823574     KBO 69737

The home-league profiles and source stat fingerprints identify the exported
players. Official MLB API biography records independently agree on full identity,
date of birth and position. All four direct official biography responses are
included. Taira required the international sportIds=51 directory; default MLB-only
name searches returning empty results did not establish that an ID was absent.
No speculative ID or name-only override was applied.

Dates of birth: Sato 1999-03-13; Taira 1999-11-15; Itoh 1997-08-31;
Roh 2000-12-03. Roh's English KBO date format was ambiguous; the Korean official
record explicitly confirms December 3. Taira's MLB biography says bats R while
NPB says bats L. That non-identifier field conflict is retained and not used.
The validated identity joins are observational branch files; no production
crosswalk or identity configuration was overwritten.

CURRENT P1 MARKET STATUS AS OF NOVEMBER 24
Sato: Cubs agreement reported; formal roster transaction not independently confirmed.
Taira: Toronto agreement reported; formal roster transaction not independently confirmed.
Itoh: posting/free-agent evidence; no later agreement independently verified.
Roh: posting/free-agent evidence; no later agreement independently verified.

Sources:
https://www.mlb.com/news/teruaki-sato-cubs-contract
https://www.mlb.com/news/kaima-taira-profile-blue-jays
https://www.mlb.com/news/mlb-rumors-and-2026-27-free-agent-news-november-21
https://www.mlb.com/news/mlb-free-agents-2026-2027
Full home-league and official API evidence is in P1_corroborated_identity_and_status.csv.
Reported agreement, official registration, verified identity, projected skill and
MLB playing time remain separate concepts; one does not establish the others.

TEN RETURNER REVIEWS
Lewin Diaz: Samsung's official 2026 KBO registration; 2027 contract unverified.
Jon Duplantier: official Yokohama 2026 roster, pitcher. Earlier source-role/team
labels conflict and are flagged rather than treated as current hitter status.
Elvis Luciano: official Yomiuri 2026 roster; 2027 contract unverified.
Luis Liberato: Aguilas Cibaenas winter affiliation verified; summer 2027 unverified.
Andrew Stevenson: Campeche assignment verified; summer 2027 unverified.
Estevan Florial: Chihuahua's 2027 Mexican League announcement verified.
Maikel Franco: Licey winter affiliation; newer secondary MLB claim unconfirmed.
Elier Hernandez: Licey winter affiliation; summer 2027 unverified.
Jordan Diaz: same-day signed/released primary entries are ambiguous; 2027 unverified.
Edward Olivares: Margarita winter affiliation; summer 2027 unverified.

Each review has dated primary evidence and official MLB API profile/transaction
receipts through November 24. MLB currentTeam can retain inactive or outdated
affiliations: for example it retains old North American clubs for some players
listed in current NPB records. API active/currentTeam values are preserved as
evidence, not mistaken for MLB roster guarantees. Winter clubs are not summer
contracts, and no absence of a new transaction is treated as proof of free agency.
The ledger explicitly distinguishes checked-but-unverified status from confirmed
non-MLB destination. It does not certify all ten current 2027 rosters.

INTERNATIONAL EXCEPTIONS
P1_international_coverage_only.csv contains four identity-resolved placeholders
with blank PA/IP and no skill forecasts. international_coverage_exceptions.csv
retains positive 2026 international histories and their original identity status.
Use the new P1 identity ledger for the four verified joins; the original source
audit remains an immutable historical snapshot. Neither minor coefficients nor
the small-sample experimental international factors enter these projections.
Recent international-history flags on existing model players indicate omitted
evidence, not a successful translation or a newly certified MLB opportunity.

VERIFICATION
Seven checks pass: exact frozen population/workload/coherence and whole-vector
fallback; freeze hash and original numeric replays; independent reconstruction of
all final minor coefficients from <=2025 labels; four official identity/DOB ties;
international placeholders and ten status reviews; 2026 minor eligibility/source
separation; unchanged original source and production file hashes.
source_manifest.json binds original v1.43 files, input histories and source design.
output_sha256.json binds this finalized research package, including status notes.

FILES TO REVIEW
research_2027_hitters.csv / research_2027_pitchers.csv: separate skill projections.
v1_43_to_research_changes.csv: every changed numeric metric.
component_trace_2027.csv / frozen_minor_factors.csv: evidence and fixed factors.
minor_stint_eligibility.csv: included/excluded levels, years and mapping provenance.
research_exceptions.csv: numeric branch limitations; inherited v1.43 exceptions
also remain in each forecast's original exceptions column. Role/status flags are
additional columns in the forecast files and the reviewed status ledger.
P1_corroborated_identity_and_status.csv / official_MLB_identity_responses.json:
accepted identity ties and non-identifier conflicts.
priority_returner_status_review.csv / official_returner_metadata_responses.json:
dated roster/transaction evidence with explicit uncertainty.
P1_international_coverage_only.csv / international_coverage_exceptions.csv:
unsupported international performance and missing opportunity.
publication_freeze.json / release_report.json / identity_status_review.json:
decision boundary and checks. This package is reviewable, not production enabled.
