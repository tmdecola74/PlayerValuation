MiLB component translation pilot 0.1
November 23, 2026

DECISION: RESEARCH ONLY. DO NOT ADOPT INTO v1.43.

The component translations show a useful preliminary signal, especially for
hitters. Available source history supports only ONE trainable next-year test
origin (2025), below the existing three-fold minimum. Results are development
evidence, not independent confirmation or evidence the full model improved.

SPECIFICATION
Hitter components: BB, SO, HBP per PA; 1B, 2B, 3B, HR per AB.
Pitcher components: SO, BB, HR per TBF; H, ER, BB, SO, HR per OUTS.
Separate factors are fitted for each level, role, component and denominator.
Pitcher OUTS components align with v1.43's existing skill definitions; TBF
components provide a complementary plate-appearance basis. These are alternative
views and are not independent evidence to count twice in an adoption decision.

Additive standard counts are summed within player/year/level; separate source
stints are retained in the intake. Baseball IP is never treated as decimal IP.
No batted-ball or pitch-tracking features enter this experiment. This makes the
remaining ambiguous batted-ball assignments irrelevant to this particular fit.
Supplied PA is retained despite flagged component residuals. Missing or excluded
MLB labels remain missing; no component is filled from another source.

For matched minor and MLB observations, let w = minimum of the two denominators.
Factor = sum(w * MLB rate) / sum(w * minor rate).
Each factor requires at least 30 distinct calibration players and 1,000 paired
exposure units. These are fixed pilot support rules, not proven optimal settings.
Unsupported levels get no invented coefficient or automatic fallback factor.

Candidate rate = (minor count * factor + prior exposure * prior rate) /
                 (minor denominator + prior exposure).
The prior is pooled eligible MLB performance from 2023 through the year before
the evaluation origin. Fixed prior exposures: 200 PA/AB, 300 TBF/OUTS.
The 300 TBF setting is a new pilot assumption, not v1.43's 300-OUTS prior.
Probability rates are bounded 0-1; rates per OUTS are not bounded at 1.

These empirical bridges include year-to-year aging/development, role changes,
selection of movers and environment effects. They are not pure estimates of
competition strength. Age and source pitching role are reported, but no age,
park or role coefficients are fitted. Do not interpret a factor as universal MLE.

VALIDATION
Primary design: 2023 MiLB to 2024 MLB for calibration; 2024 MiLB to 2025 MLB
for testing. No calibration pair has a target year equal to or later than its
evaluation origin. 2024 has no earlier next-year calibration pair and is unsupported.
2026 MLB outcomes are never opened. No forecasts, workload or production settings
are changed. 2026 minor data is not needed for this historical test.

Secondary diagnostic: same-season minor/MLB pairs, calibrated in prior years
and evaluated in 2024/2025. This tests retrospective cross-level consistency,
not a preseason forecast or verified promotion order. It does not create two
additional next-season validation folds.

Comparators use identical eligible player memberships:
1. Raw unadjusted minor rate.
2. Unadjusted minor rate with the SAME prior and prior strength as the candidate.
3. Earlier-only MLB population prior.
Every score includes an exact paired-membership hash. Scores include equal-player
and target-exposure weights, MSE, RMSE, MAE and bias. Target exposure is used for
scoring only, not to assign prospective MLB playing time. Each level is evaluated
separately; a player with multiple minor levels may appear in several level tables.
These tables cannot be stacked as independent player predictions.

RESULTS: NEXT-YEAR 2025 TEST
Among level/component cells with at least 30 evaluation players:
Hitters: 21/21 cells improved versus identically regressed untranslated rates.
Pitchers: 26/32 cells improved.
Equal-cell mean MSE ratios: 0.89895 hitters, 0.98039 pitchers.
These are descriptive averages of correlated cells, not full-model accuracy gains,
statistical significance tests, or evidence each metric improves.

Selected Triple-A examples (equal-player MSE change vs identically shrunk raw):
Hitter BB/PA: -19.8%, SO/PA: -13.6%, HR/AB: -24.9%.
Pitcher SO/TBF: -8.9%, BB/TBF: +6.5%, ER/OUTS: +0.2%.
Positive means worse. Walk and earned-run translations do not uniformly help.
Some translated rates also lose to the simple MLB population prior. Both
comparisons are disclosed in validation_deltas.csv and validation_scores.csv.

Cohort labels PRIOR_MLB_EXPOSURE / NO_PRIOR_YEAR_MLB_EXPOSURE refer to positive
eligible MLB exposure in the year BEFORE the source MiLB season, not career
debut status. These are diagnostics, not a certified prospect/rookie classification.
Pitcher source-role diagnostics use GS/G >= .5 for starter, GS=0 reliever,
otherwise swing. Prior exposure, age and source role were not used to select fits.

LIMITATIONS AND ADOPTION
All target rows require observed eligible positive MLB exposure. This selects
players who reached/returned to MLB and does not evaluate non-arrivals, roster
probabilities or projected PA/IP. Factors are coarse level averages without minor
subleague, park or actual affiliate identifiers. Historical source availability
dates are unknown; this is retrospective season-ordering, not an archived
preseason-vintage backtest. No uncertainty calibration or independent validation
has been established for the fitted coefficients.

There is no blending with existing MLB history, no coherent joint hitter/pitcher
vector reconstruction, and no direct comparison against frozen v1.43 forecasts.
The original full adoption guards have not passed. More prior minor seasons,
ideally 2019-2022 for additional rolling origins and older player history, plus
subleague/park context, are needed before a defensible adoption attempt.
NPB/KBO translations remain a separate experiment.

FILES
experiment_contract.json: specification fixed before outcome label access.
transition_pairs.csv: eligible source/target components and exact IDs.
factor_support.csv: supported and unsupported level/component/origin cells.
fitted_factors.csv: experimental coefficients and latest fit target year.
validation_predictions.csv: candidate, comparators and eligible targets.
validation_scores.csv / validation_deltas.csv: paired results and cohorts.
validation_report.json: decision and summary.
source_manifest.json: hashes of source tables, labels and release CSVs.

Verified: source/release hashes unchanged; no fit sees its evaluation year;
zero denominators excluded; five synthetic/artifact checks pass, including known
factor recovery, support rejection, missing-vs-zero and independent score replay.

Method context (not published numerical factors used by this pilot):
https://library.fangraphs.com/principles/league-equivalencies/
https://www.baseballprospectus.com/news/article/7893/prospectus-toolbox-minor-league-statistics-and-eqa/
