International identity priorities and small-sample translation assessment
November 24, 2026

DECISION
The priority review queue and separate small-sample method are built. International
estimates remain EXPERIMENTAL. No adoption threshold was lowered, and no production
projection, workload or frozen minor-history setting changed.

IDENTITY PRIORITIES
1,808 league/player-role entries have positive overseas exposure in 2025 or 2026:
P1: 4 posting-report priorities, verified against MLB.com reporting.
P2: 212 entries present by exact FanGraphs ID in supplied 2027 benchmark files.
P3: 10 additional returner-watchlist entries with eligible MLB history through 2025.
P4: 1,417 other overseas-history entries with no established MLB-arrival evidence.
P5: 165 secondary-role entries for review, deprioritized from primary role queues.
These counts are review entries, not unique people or expected MLB arrivals.

P1 posted-player review list:
Teruaki Sato — NPB hitter, FanGraphs sa3063811, Tigers.
Kaima Taira — NPB pitcher, FanGraphs sa3062990, Lions.
Hiromi Itoh — NPB pitcher, FanGraphs sa3063835, Fighters.
Si-hwan Roh — KBO hitter, FanGraphs sa3012734, Eagles.
Source league, role and overseas club are checked against supplied records.
Posting is evidence of market availability, not a signed MLB contract, future role,
probability of arrival, or guaranteed MLB playing time. This is a scoped list from
verified reports and local benchmark presence, not an exhaustive market tracker.

Posting evidence:
https://www.mlb.com/news/teruaki-sato-mlb-posting-system
https://www.mlb.com/news/kaima-taira-will-enter-mlb-posting-system
https://www.mlb.com/news/hiromi-itoh-posted-hokkaido-nippon-ham-fighters
https://www.mlb.com/news/si-hwan-roh-and-the-kbo-stars-who-could-be-mlb-bound

Three candidate MLB profile IDs were located: Sato 831664, Itoh 808955, Roh 823574.
They are REVIEW CANDIDATES, NOT accepted crosswalk overrides. Current evidence
does not establish the required explicit shared-ID or independently corroborated
biographical tie to the export ID. They remain unmerged. Taira's MLBAM link is
still unresolved. The supplied 2027 benchmark records also leave these players'
MLBAMIDs blank; exact FG IDs remain usable within the international branch.
Candidate profiles:
https://www.mlb.com/player/teruaki-sato-831664
https://www.mlb.com/player/hiromi-itoh-808955
https://www.mlb.com/player/si-hwan-roh-823574

ONE NEW EXACT LINK
Raidel Martinez, FanGraphs sa3063073 -> MLBAM 673510, appears as an identifier pair
in the supplied 2027 Steamer pitcher export. This is a documented ID co-occurrence,
recorded in new_exact_ID_links.csv, not a claim of MLB signing or arrival.
No benchmark projected statistics are used to fit factors or predict playing time.
No name-only links, candidate profiles or conflicting IDs are automatically merged.

Queue triage assigns low-exposure batting by pitchers and low-exposure pitching
by hitters to P5: <100 PA with >=30 outs pitched, or <30 outs with >=100 PA batted,
in the same league/year. This is review triage, not a model filter or a definitive
two-way/position classification. P1 stated roles are preserved. Source-2026 totals
are allowed for identity prioritization; 2026 MLB outcomes are not used.
Returner status uses known MLB history through 2025 only. A watchlist entry may
already have moved or remain overseas; verify current transaction/roster evidence
before treating it as a 2027 returner. Missing arrival evidence remains explicit.

SEPARATELY SPECIFIED SMALL-SAMPLE METHOD
The experiment contract is written before fitting. NPB and KBO are fit separately,
as are hitters/pitchers and individual components. No minor-league coefficient is
borrowed. Each fit uses the first eligible next-year transition per player within
its earlier-only calibration pool, so repeat movers are not additional independent
people. Source/target components are the previously audited eligible pairs.

Smoothed log-rate ratio:
z = log((MLB count+.5)/(MLB denominator+1))
    - log((overseas count+.5)/(overseas denominator+1)).
Assume a normal log-factor prior with mean zero and SD .35. Use fixed between-
player log SD .25. Approximate sampling variance uses inverse counts, with
binomial denominator corrections for PA/AB/TBF and conservative Poisson rate
variance for OUTS. Posterior precision is prior precision plus the observations'
inverse (sampling variance + .25 squared); posterior mean is the precision-
weighted log ratio. The factor is exp(posterior mean).

Zero-centered log prior is NUMERICAL REGULARIZATION TOWARD NO CHANGE, not evidence
that NPB or KBO performance equals MLB performance. SD .35 and heterogeneity .25
are predeclared assumptions, not estimated or tuned winners. Sensitivities use
prior SD .20 and .50, reported alongside the primary fit without winner selection.
Three distinct movers suffice to CALCULATE AN EXPLORATORY FIT only. The original
30-player/1,000-exposure calibration and 30-row/three-fold adoption rules remain.

Conditional 95% factor intervals come from the assumed posterior normal variance.
They are NOT empirically calibrated prediction intervals for an individual player,
and omit uncertainty about the prior, heterogeneity, aging, parks, changing roles,
selection into MLB and incomplete identity coverage. They must not be presented
as validated floor/ceiling forecasts.

CHRONOLOGICAL DIAGNOSTICS
Origins 2021-2025 fit only transitions with earlier target years. MLB labels stop
at 2025. Candidate rates are compared with identically regressed untranslated
rates and the earlier-only MLB population prior on identical metric memberships.
Fixed prior exposure: 200 PA/AB or 300 TBF/OUTS. These are component diagnostics,
not complete coherent projections or direct comparisons against v1.43.

The package contains 498 model rows across origins/components/prior settings and
1,599 diagnostic prediction rows. These rows are correlated repeated analyses,
not independent players. No evaluation cell satisfies the unchanged adoption
sample requirements, so there is no international adoption case from this test.

The hitter fits remain fragile. For example, the primary NPB HR/AB factor from
the through-2025 sample is about .742; leaving Seiya Suzuki out changes it to
about .876. Its conditional factor interval is roughly .517-1.063. That interval
and influence calculation illustrate limited evidence; neither is a published
universal MLE. Factor sensitivities and every leave-one-player-out result are
retained, including pitcher/component alternatives. Do not stack correlated
denominators or prior settings as extra validation folds.

2027 PRIORITY RATE SCENARIOS
priority_rate_scenarios.csv uses 2023-2026 international counts weighted 1/2/3/4
with factors fitted only through 2025. It produces 1,718 unaged source-history
component-rate scenarios for P1-P3 entries with supported exploratory factors.
These are NOT 2027 player forecasts, coherent stat vectors, MLB workloads,
roster probabilities or official adopted MLB equivalencies. Factor interval
scenarios are NOT full player prediction intervals. Candidate identity links are
not applied; rows retain FG ID and unresolved-ID flags. No MLB PA/IP is invented.
The successful minor branch is not blended with this experimental branch.

PROTECTION AND VERIFICATION
Original international/prepared source tables, all v1.43 release files and the
entire protected park/minor challenger output directory are hash-verified unchanged.
No 2026 MLB actual-label or evaluation file is opened or used for fitting/selection.
Current posting reports are used for identity prioritization only, not performance
coefficients. Benchmark files supply IDs/presence only. No external projection
values or current MLB performance results enter the statistical fit.

Seven checks pass: priority/candidate separation and exact new ID pair; strict
earlier-year fitting; valid posterior factor intervals and all sensitivity settings;
paired scoring memberships and unchanged sample requirements; distinct-player
calibration counts; immutable source/minor/production hashes; independent MSE replay.

FILES
priority_1_to_3.csv: focused 226-entry review queue.
priority_identity_queue.csv: all 1,808 entries, including low-priority/secondary roles.
new_exact_ID_links.csv: new observed exact bridge, not a production override.
posting_evidence.json: four P1 source reports and candidate profile references.
experiment_contract.json: separate statistical design and unchanged adoption limits.
experimental_factor_models.csv: factors, assumed conditional intervals, sample sizes.
chronological_diagnostic_predictions.csv / chronological_diagnostic_scores.csv:
earlier-only paired comparisons at all three prior strengths.
leave_one_player_out_influence.csv: single-mover influence on final research factors.
priority_rate_scenarios.csv: labeled source-history scenarios only.
assessment_report.json / source_manifest.json / verification.txt: results and integrity.

NEXT ACTION
Finish independently corroborated identity ties for the four P1 players and verify
current roster/posting status for priority returners. Keep international estimates
as explicitly unvalidated coverage until an independently justified prior or more
historical transition evidence supports a new test. The already validated minor-
history 2027 research release can proceed with these international exceptions
visible. No minor coefficient or weaker threshold should silently fill the gap.
