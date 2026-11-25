v1.42 — two separate experiments and one 2027 core research release

Extract into D:\JonAPythonClass\pycharm\PlayerValuation alongside prior versions.
Run from the project root:
  python -m unittest discover -s tests -p "test_projection_phase_v1_42.py" -v
  python projection_phase_v1_42.py

Output: outputs/projection_phase_v1_42; choose a fresh --output if it already exists.
Complete timestamped backups go under backups.
Requires the completed v1.41 audit and its original input bindings.
No new downloads, 2022 leaderboard intake or benchmark systems required.
This can take longer than an export-only build: it reconstructs historical forecasts.

1. SKILL REGRESSION
Four prior seasons weighted 1/2/3/4, just like the weighted baseline.
Hitter 1B/2B/3B/HR per AB are regressed toward pooled earlier eligible component rates.
AB and PA stay fixed, as do R/RBI/SB/BB/HBP/SF/SH.
H/AVG/OBP/SLG/OPS are recomputed coherently.
Pitcher H/ER/BB/SO/HR per OUTS are regressed; OUTS/IP/W/G/GS/QS/SV/HLD stay fixed.
ERA/WHIP are recomputed coherently. This separate pitcher skill experiment intentionally
permits BB and WHIP changes; the published default preserves their existing values.
These are standard-statistic reliability tests, with no extra Statcast or external
projection input.

Prior strengths are fixed BEFORE running: 200 AB for hitters, 300 OUTS for pitchers.
Season-weighted sample totals are divided by the mean available recency weight
before adding that prior. A recent observation is not four independent observations.
Population priors require 10,000 paired exposure units, and use only the four source
seasons before the historical forecast origin. Every primitive has its own eligible
sample. No missing primitive is filled with a population-only estimate.
A complete primitive group is required; otherwise the whole candidate falls back.
Hits normalize only if total H exceeds AB; pitcher H remains at least HR.

2. WORKLOAD RELIABILITY — SEPARATE ARM
Fits a conservative exposure multiplier by prior role and freshness state:
RECENT_POSITIVE, KNOWN_ZERO_RECENT or UNKNOWN_RECENT.
Pitcher roles use prior-year GS/G: >=.5 STARTER; GS=0 RELIEVER; other known ratios
SWING; missing information UNKNOWN. Hitters have one role group.
Each group's earlier observed target exposure / earlier forecast exposure is
shrunk toward multiplier=1 using 50 group-average projected exposures.
The multiplier is bounded 0–1, so this first candidate can reduce exposure but
does not model returner growth. That limitation remains explicit.
No group evidence => unchanged forecast.
Unknown target exposure is excluded, never treated as zero.
Pitcher historical certified zeros come from the frozen v1.27 overlay.
Hitter nonparticipation coverage is incomplete and stays disclosed.

Hitter counting statistics scale with PA; hitter rates stay fixed.
Pitcher workload-based counts scale with IP; skill rates stay fixed except that
zero IP has undefined ERA/WHIP. Saves/holds stay fixed anchors and are not inferred
from an innings cut. Workload-candidate QS is blank, not inferred from IP.
Group outcomes never enter the fit for their own origin.

3. CHRONOLOGICAL TESTING
Origins 2019–2025; 2020 and 2021 retained.
Historical player populations use positive prior MLB exposure, not target
appearance lists. Each retrospective baseline uses its own previous four years;
these are reconstructed forecasts, not archived preseason releases.
Population coefficients are learned only from source seasons before origin.
Workload coefficients use completed earlier historical forecast/outcome rows only.
Skill and workload candidates never use one another's changes.

historical_scores.csv includes paired baseline/candidate membership hashes,
MSE/RMSE/MAE/bias by year, experiment and cohort:
ALL; LOW_HISTORY/ESTABLISHED; LOW_SAMPLE/ESTABLISHED_SAMPLE (skill);
prior role/freshness/returner-like cohort and known participation status (workload).
Actual-exposure bands are retrospective skill diagnostics only, never gate features.
Low sample means minimum component sample below 200 AB or 300 OUTS.
Workload SO/W and hitter HR/R/RBI/SB are additional eligible-count diagnostics;
known zero OUTS does not manufacture missing counting labels.
historical_label_coverage.csv reports known-positive/zero/unknown target exposure
and supported forecasts for each origin/role.

rolling_research_choices.csv evaluates each candidate with EARLIER folds only.
frozen_choices.json records final historical eligibility through 2025.
At least 3 supported folds and 30 rows per fold are required.
Primary objective: equal-weight average MSE ratio across years and primary metrics
must improve by at least 1%. Individual metrics cannot degrade >2%.
Each of the last two supported years cannot degrade >2% on its objective average.
Low-history guard requires supported cohorts with at least 15 rows and no >2%
average degradation. Unsupported guards reject rather than silently disappear.
Skill count guards require no >2% average degradation in resulting eligible counts.
These are fixed research gates, not significance tests or untouched validation.
Previously inspected historical folds remain development evidence.

Defaults DO NOT automatically change, even if historical gates pass.
This implements the user's requirement to keep weighted_actuals / accepted_ip.
No combined arm is selected or exported; combination would need its own test.

4. 2027 RELEASE CHECK
Choices and all fitted coefficients are staged before the first 2026 actual-label
file is opened. No 2026 forecast-error table is read or scored.
2026 actuals then enter only as prior player history for 2027; population coefficients
and workload models stay frozen through 2025.
Original v1.31 baseline numbers must replay from those bound source labels.
Release verifies finite nonnegative values, hits/AB, PA components, ratios,
OUTS=3*IP, GS<=G, QS<=GS and SV+HLD. Missing values remain explicit exceptions.

Main default files:
  default_2027_hitters.csv
  default_2027_pitchers.csv
These contain one row per frozen v1.40 player-role, name, standard metric columns,
source/method metadata, history context, release_status and exception flags.
They preserve weighted baseline values, INCLUDING flagged extreme rates.
They are a useful CORE RESEARCH release, not certification that every row is
draft-ready. Unresolved names, sparse/stale history and unsupported metrics are
not dropped, fabricated or silently filled from a benchmark.
Hybrid QS is blank and valuation_enabled=False.

Separate research files:
  research_candidates_2027_hitters.csv
  research_candidates_2027_pitchers.csv
Contain baseline__, skill_regression__ and freshness_workload__ metric columns,
support status and workload multiplier. They are not default sources.
skill_regression_component_trace_2027.csv records sample sizes, priors and rates.
release_exceptions.csv is ranked by projected PA/IP within role.
release_report.json summarizes gates, counts, checks and remaining limitations.

Other reports:
historical_player_predictions.csv (player-level outcomes and predictions),
historical_population_priors.json, historical_workload_models.json,
experiment_contract.json, input_hashes.json, output_sha256.json.

Defaults:
--audit outputs/baseline_reliability_v1_41
--review outputs/projection_review_v1_40
--baseline outputs/homegrown_2027_v1_31
--labels outputs/training_labels_v1_0
--overlay outputs/participation_label_overlay_v1_27
--research outputs/recent_history_skills_v1_23
--evaluation outputs/pitcher_evaluation_v1_29

Local validation: 11 tests including complete historical synthetic replay,
2026 outcome-mutation invariance, no-lookahead fits/selection, missing-vs-zero,
component shrinkage/coherence, frozen anchors, source immutability, staged freeze
before 2026 label access, complete output/backup equality and tamper/no-overwrite.
The publication test isolates the prior releases' data adapters with fixture data;
the production label/parquet paths must be run in your local project.

No valuations, no prospect/minor/overseas expansion, no dated availability model.
Those remain a separate coverage branch. No guarantee a research candidate wins.
