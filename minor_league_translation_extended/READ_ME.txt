Extended minor league translation research — 2019-2025 validation
Prepared November 23, 2026

RESULT
The added history expands chronological next-season validation from one year to
four (2022, 2023, 2024, 2025). With 2020 MLB calibration pairs excluded, there are
three supported years (2023-2025). Hitter translation results remain encouraging;
pitcher gains are component-specific. Production v1.43 remains unchanged.

INTAKE
2019-2022 exports: 19,128 hitter and 21,350 pitcher stints per dashboard.
Represented seasons: 2019, 2021, 2022. The 2020 absence is expected; that minor
league season was cancelled. No missing season is filled with zero performance.
Official reference: https://www.milb.com/news/2020-season-cancellation
Old labels R and A- remain distinct from CPX, DSL and A. The 2019 R category
is heterogeneous and must not be assigned a universal modern rookie translation.
The same A/A+ tier labels span organizational changes; separate subleague and
park context is still unavailable.

All older standard-to-advanced records match, using shared fields and calculated
SO/BB rates to resolve collisions where needed. Four older pitcher batted-ball
assignments remain ambiguous, preserved separately. They do not affect this
experiment, which uses only standard counting components. The old files have
536 PA-component discrepancies, including one negative residual; no repairs or
missing events were invented. The prior newer exports have 1,233 such rows.
R/CPX/DSL pitch-derived information is not used in any fitted translation.

Combined supplied history (2019-2026):
Hitters: 40,779 stints, 11,088 MLBAM IDs; 990/1,024 existing model hitters linked.
Pitchers: 49,220 stints, 12,998 MLBAM IDs; 1,350/1,487 model pitchers linked.
These are observed exact same-role ID links, not roster or workload forecasts.

EXPERIMENT
The original component definitions, multiplicative bridge estimator, minimum
support of 30 calibration players/1,000 paired exposure units and regression
strengths remain unchanged. The pooled MLB prior window now begins in 2019,
matching the extended source era, and ends before each forecast origin.
This is a declared prior-window extension, not a numerical replay of the earlier
2023-only pilot. No hyperparameters were tuned using these results.

For each level and component, factor is the ratio of pooled MLB to minor rates
in matched movers, weighted by min(source denominator, target denominator).
Hitter components: BB/SO/HBP per PA, 1B/2B/3B/HR per AB.
Pitcher components: SO/BB/HR per TBF, H/ER/BB/SO/HR per OUTS.
200 PA/AB or 300 TBF/OUTS prior exposure is added identically to candidate and
untranslated comparator. Source stints aggregate only within player/year/level.
Different level predictions remain separate, never counted as independent players
in a combined forecast. TBF- and OUTS-based views are correlated alternatives.

Primary chronology: minor season s predicts MLB s+1. Fit uses only matched target
years earlier than the evaluation year. There is no 2020 minor source season, no
2021 next-year test sample, and no supported earlier fit for the 2020 test year.
Primary 2022 calibration draws on 2019-minor/2020-MLB observations; these are
retained but explicitly tested by an alternative run excluding target year 2020
from calibration. That sensitivity first supports next-season testing in 2023.
The sensitivity is a robustness check, not a newly selected winning model.

Same-year diagnostics are separately labeled and never counted as forecast folds.
Only eligible historical MLB labels through 2025 are used. 2026 minor history
contributes to coverage only, not this validation. 2026 MLB outcomes are not read.

RESULTS
Among primary level/component/year cells with at least 30 test observations,
hitters improve in 91/94 cells and pitchers in 101/131 against identically regressed
untranslated rates. Equal-cell mean MSE ratios: 0.89577 and 0.96975 respectively.
These are descriptive averages of correlated tests, not full-model accuracy gains.
Excluding 2020 calibration: hitters improve in 72/73 and pitchers in 84/102 cells;
mean MSE ratios 0.88967 and 0.97021. Gains are not dependent on 2020 calibration.

Triple-A primary mean MSE ratios over four years, vs same-prior untranslated:
Hitter 1B/AB .93285; 2B/AB .89791; 3B/AB .91255; HR/AB .81771;
BB/PA .84127; SO/PA .87617; HBP/PA .97587.
Pitcher SO/TBF .89843; SO/OUTS .94556.
Pitcher BB/TBF .99888; BB/OUTS .99782; HR/TBF 1.00251;
HR/OUTS .99688; H/OUTS .99145; ER/OUTS .99342.
Ratios below 1 favor translation. Small gains do not meet the fixed 1% screen.

PRELIMINARY ROLLING SCREEN
component_rolling_screen.csv checks >=3 years with >=30 rows each, mean MSE
ratio <=.99, and no >2% degradation in either last two supported years, separately
by level/component. Primary: 21 hitter and 19 pitcher cells pass; sensitivity:
21 hitter and 17 pitcher cells pass. Failures include insufficient folds as well
as inadequate improvement or recent deterioration. All seven Triple-A hitter
components pass in both runs. Triple-A pitcher SO passes in both denominator
views; other components generally do not. H/OUTS passes only in the sensitivity.

This is a necessary exploratory screen, NOT the complete original adoption gate.
It does not implement the original full joint objective, coherent count-vector
guards, low-history protections or comparison against the actual v1.43 model.
No automatic component selection, blending or promotion is authorized by passing.
Per-origin scores include equal-player and target-exposure-weighted MSE/RMSE,
MAE and bias; every comparator uses exactly paired memberships. Comparisons to
raw minor rates and the earlier-only MLB population prior are also included.

LIMITATIONS
Conditional on players with eligible positive MLB exposure; non-arrival and future
playing time are not evaluated. Aging, selection, role changes and park/subleague
effects are mixed with league-strength differences. Retrospective export dates
do not certify archived preseason availability. Prior-MBL cohort labels refer to
the year BEFORE the minor source season, not verified career rookie status.
No confidence intervals, coefficient uncertainty calibration or untouched test set
is established. No new player forecasts, NPB/KBO factors or valuations are produced.

FILES
experiment_contract.json: earlier-only specification, declared era extension.
factor_support.csv / fitted_factors.csv: supported and unsupported cells/factors.
transition_pairs.csv / validation_predictions.csv: auditable pairs and predictions.
validation_scores.csv / validation_deltas.csv: all comparisons and cohorts.
component_rolling_screen.csv: primary and sensitivity necessary screens.
combined_source_coverage.csv / combined_release_ID_links.csv: combined intake links.
extended_review.json: coverage and verification; validation_report.json: research status.
source_manifest.json: unchanged input and published-release hashes.
Package folders also retain older intake audit, prior pilot documentation,
reproducible experiment script and the complete no-2020-calibration sensitivity.

NEXT MODEL STEP
Freeze the translation design and test a coherent translated-history challenger
against an MLB-history-only challenger for the same pre-origin population, with
explicit fallback and separate prospect/returner coverage. Keep workload fixed
where a baseline exists; do not invent MLB PA/IP for new players. Complete the
original adoption guards before changing production. Park/subleague information
would strengthen the interpretation of the translation coefficients.

Verification passed in both runs: missing-2020 handling, exact next-year pairing,
strict earlier-year fitting, identical comparator memberships, and unchanged
source/release hashes. Prior synthetic estimator tests also remain applicable.
