Park-aware projection challenger — frozen three-arm research test
November 24, 2026

RESULT AND DECISION
Adding translated minor league history passes the existing skill adoption guards
for both hitter and pitcher bundles on the supported historical population.
Adding park/subleague context does NOT pass the required incremental 1% objective
improvement versus the otherwise identical minor-history challenger.
Keep park context experimental. No production adoption or v1.43 changes were made.

Comparison                         Hitter MSE ratio    Pitcher MSE ratio
MLB + minor / MLB only                 0.935947             0.982016
MLB + minor + park / MLB only          0.931838             0.982799
MLB + minor + park / MLB + minor       0.995608             1.000798

These are the existing gate's equal-year/equal-primary-metric average MSE ratios,
not percentages of player projections improved, RMSE reductions, significance
claims or full-population accuracy gains. A ratio below 1 favors the candidate.
Minor history improves the primary objective by about 6.41% for hitters and 1.80%
for pitchers. Incremental park context improves hitters by only 0.44% and worsens
pitchers by about 0.08%. Both incremental park gates fail solely for insufficient
1% improvement in this run. All individual scores and guard results are retained.

1. ATTACHED CONTEXT
All 18,465 hitter and 22,973 pitcher stints at AAA/AA/A+/A in 2021-2025 match
an affiliate and supplied overall park factor. Exact join: season, normalized
parent organization and level. OAK/ATH are one organizational lineage for this
join only. Original organization labels are retained. Source-row references are
retained in stints_with_park_context.csv. 2026 and unsupported years/levels remain
explicitly without factors. No factors are backfilled or treated as neutral.
615 mapped hitter and 637 mapped pitcher stints lack supplied subleague names;
they retain UNKNOWN_SUPPLIED_LEAGUE as an explicit modeling category. Factors
remain available. This is not an externally certified affiliate or venue audit.

2. PARK MODEL SPECIFICATION
Each hitter 1B/2B/3B/HR per AB and pitcher H/ER/BB/SO/HR per OUTS has its own
level-specific translation and context coefficients. Hitter walks/HBP and other
opportunity anchors stay fixed, consistent with the published v1.43 mutable group.
Neither swinging-strike data nor batted-ball classifications enter these models.

For eligible matched source-year MiLB / next-year MLB observations:
weight = min(source denominator, target denominator).
Plain factor = sum(weight * target rate) / sum(weight * source rate).
Require 30 distinct calibration players and 1,000 paired exposure units.

Park arm starts from the SAME factor. Fit weighted residual subleague means,
shrunk toward zero by 1,000 exposure units. Then fit a weighted residual slope
on centered log(overall final PF), with fixed ridge penalty 10. This is a
predeclared sequential residual model, not a uniform park discount. Each
component can respond differently. Rates are floored at zero; hit-component
rates are bounded at one and jointly normalized only if summed H exceeds AB.

Only source-season context is used. A future MLB team's park, target-season
playing time, future league constants and future actual performance are never
predictors. These run factors remain proxies, not actual component park effects.
No half-home/road allocation is invented; actual individual venue exposure is
unavailable. Target MLB performance is not park-neutralized. Therefore context
coefficients can absorb selection, future park or role effects, not just a pure
source-stadium effect. They must not be interpreted as universal park corrections.

3. COMBINED PLAYER PROJECTIONS
MLB_ONLY reproduces the original v1.43 skill recipe with original project,
population, skill_candidate and coherence functions, using eligible training
labels and the fully validated v1.27 certified participation overlay.
All 11,946 historical player-role baseline vectors numerically reproduce the
corresponding prior v1.42 skill-arm vectors at tolerance 1e-10.

Both minor arms use exactly the same supported, mapped source stints within
the same four prior seasons. Missing/unsupported level fits exclude that stint
from BOTH arms. MLB and minor game events are disjoint; each minor stint enters
once, and dashboard rates are not summed as extra observations.
Each component combines MLB count/exposure with 0.5 * translated minor count/
exposure using original recency weights 1/2/3/4. The fixed 0.5 evidence weight is
an unoptimized research assumption. A mean weight over distinct observed seasons
normalizes exposure, avoiding multiple priors or extra season weight from multiple
levels/stints. Add the earlier-only MLB population prior ONCE: 200 AB or 300 OUTS,
subject to the original 10,000 population-exposure minimum.

The resulting rates are applied to the SAME baseline AB or OUTS anchors. H, AVG,
OBP, SLG, OPS, ERA and WHIP are recomputed consistently. PA/AB/R/RBI/SB/BB/HBP/
SF/SH for hitters and IP/OUTS/G/GS/QS/W/SV/HLD/SV+HLD for pitchers remain fixed
where they are outside the original mutable skill group. Pitcher BB is mutable.
Every vector passes original coherence checks; every immutable anchor is checked.

Unsupported complete-group evidence yields whole-vector MLB_ONLY fallback for
BOTH minor arms. Prospects without a positive prior MLB baseline are recorded
in prospect_coverage_only.csv. No population-only baseline or new PA/IP forecast
is invented for them. This test does not solve international-arrival/prospect
opportunity, promotion or participation prediction.

4. VALIDATION AND ADOPTION GUARDS
Forecasts are generated for 2022-2025 from pre-origin populations, never target
appearance lists. 2022 has no earlier supported park-calibration sample and is
entirely fallback. Supported comparisons use 2023, 2024 and 2025, with calibration
target years strictly earlier than each origin. Scores exclude ineligible target
metrics; missing values and unknown nonappearance are not fabricated as zero.

All three arms have identical player eligibility and paired-membership hashes
for each metric/cohort. Supported samples for AVG: 422, 460, 506 hitters by year;
for ERA: 525, 594, 633 pitchers. Other metrics can have different eligible samples.
Scores for fallback players are also included separately, not mixed into adoption
evidence to dilute failures. Low-history cohorts come from original context code.

The ORIGINAL gate function runs unmodified for all three pairwise comparisons:
MINOR_vs_MLB, PARK_vs_MLB and PARK_vs_MINOR. Its method labels are adapted solely
to identify the two arms being compared. The original primary metrics are AVG/
OPS for hitters and ERA/WHIP/SO per OUTS/HR per OUTS for pitchers. Required gates:
at least three supported folds, >=30 rows per fold, >=1% aggregate MSE improvement,
no >2% individual-metric average regression, recent-two-year checks, supported
low-history guard with >=15 rows, and original coherent-count guards. Rolling
decisions use earlier folds only. Final gates cover outcomes through 2025.

MINOR_vs_MLB and PARK_vs_MLB pass both role bundles. PARK_vs_MINOR fails both.
Passing development guards supports further review; it does not authorize automatic
publication or establish untouched out-of-sample confirmation. These historical
seasons were previously inspected and are disclosed development evidence.

5. PROTECTION AND VERIFICATION
The contract was written before model scoring. No 2026 MLB actuals, evaluation
files or holdout labels were opened. Historical-label loading enforces <=2025.
The 2026 origin shown in adoption_gates is the decision cutoff after 2025 outcomes,
not a scored 2026 forecast. No 2027 challenger projections were published.
Input/production CSV/code hashes remain unchanged. Source inputs and all published
v1.43 CSV files are covered by source_manifest.json. Original overlay validation
checks all provenance and old/new values rather than silently replacing labels.

Seven tests pass: 11,946-vector baseline replay; original vector coherence and
unchanged anchors/fallbacks; paired scoring memberships; earlier-only calibration
and immutable sources; synthetic factor/context recovery and support thresholds;
original-gate outcomes; and independent recomputation of a supported AVG MSE.

6. FILES
experiment_contract.json: fixed design and original gate contract.
stints_with_park_context.csv / park_mapping_coverage.csv: joins and coverage flags.
fitted_context_models.csv: per-origin component coefficients, fit year and sample.
historical_forecasts.csv: all three coherent historical vectors, including fallback.
component_trace.csv: merged evidence, distinct seasons and prior/exposure details.
historical_scores.csv / paired_score_deltas.csv: paired errors, cohorts and deltas.
adoption_gates.json / adoption_gates.csv: rolling and final unchanged gate results.
coverage_by_player.csv / prospect_coverage_only.csv: scope and missing opportunity.
report.json / source_manifest.json / verification.txt: results and integrity.

NEXT DECISION
Advance translated minor-history integration for review, keeping park context
inactive under this fixed design. Any new blend weight, park specification or
production population change requires a separately declared experiment. A later
2027 research release can use 2026 as player history only AFTER choices are frozen;
it must preserve workload anchors and make uncovered prospects explicit. This
package does not modify or replace v1.43.
