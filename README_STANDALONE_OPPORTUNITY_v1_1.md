# Standalone opportunity research models v1.1

Extract this ZIP directly into D:\JonAPythonClass\pycharm\PlayerValuation. It adds new scripts/config/tests and does not replace any v1.0 files. Requires the already-installed standalone v1.0 package, its test fixture, NumPy and DuckDB. Source data and v1.0 forecasts stay frozen.

## Run in order (PowerShell, project root)

```powershell
python -m unittest discover -s tests -p "test_standalone_opportunity_v1_1.py" -v
python backtest_standalone_opportunity_v1_1.py
python evaluate_standalone_opportunity_v1_1.py
```

The evaluator compares v1.0, v1.1, Steamer and OOPSY using the existing read-only warehouse. Add --skip-benchmarks to evaluate without the warehouse. All scripts support --help. If rerunning, choose a fresh --output folder; pass that build folder with --run to the evaluator. Existing folders are rejected. Both stages create complete hash-verified backups under backups/ before publication. No network calls or physical Statcast rescan.

Default inputs:
- outputs/standalone_lagged_features_v1_0
- outputs/standalone_baselines_v1_0
- data/historical_duckdb_v1_0_bulk/player_valuation.duckdb (benchmark only)

New output directories:
- outputs/standalone_opportunity_v1_1
- outputs/standalone_opportunity_evaluation_v1_1

## Models and historical testing

Opportunity models fit hitter PA and pitcher OUTS conditional on confirmed appearance; participation when supported by verified positives and negatives; pitcher G and GS/G; the probability of any saves conditional on appearance; and positive-season SV/G conditional on recording saves. Expected saves = participation probability × predicted conditional G × probability of any save given appearance × conditional positive-season SV/G.

All use fixed-penalty ridge with fold-only preprocessing inherited from v1.0. Added prior-history predictors are recent maximum/latest available volume, volume trend, observed-lag count, prior GS/G, relief G and SV/G/HLD/G. No target-year G, GS, age, team outcomes, external projections, or future measurements enter features.

Fixed role definitions: GS/G >=0.5 STARTER, <=0.1 RELIEVER, otherwise SWING; invalid/missing G/GS UNKNOWN. Expected GS = expected G × predicted start share. Role forecasts are diagnostic research outputs; a full joint role/innings/team-opportunity model is not claimed. Existing frozen G and GS fields are used. The build fails explicitly if those fields are missing, rather than guessing roles or silently substituting zeros.

Rolling origins 2019–2025 fit only earlier target seasons. At each origin, overlay choices use only earlier out-of-sample folds. The final release fits through 2025, freezes models/2026 feature-only predictions, and leaves 2026 labels to the separate evaluator.

Adoption needs two earlier qualifying folds, at least 30 paired players per fold, >=1% improvement in equal-fold mean MSE and no more than 1% MAE degradation. Saves must also pass the same gate among prior-SV>=5 pitchers, with at least 15 players per fold. Failed or insufficient gates retain v1.0. No adoption is forced. Target 2020 is excluded from opportunity fitting/selection but kept in stress-test reports; prior 2020 volumes use fixed 162/60 normalization.

Accepted volume forecasts scale the existing coherent count components while preserving AVG/OBP/SLG/OPS/ERA/WHIP. Original zero exposure cannot supply component rates: that volume overlay falls back and is flagged in diagnostics. Saves are changed only when the separate saves gate passes; rejected saves retain v1.0 even when the innings overlay changes. Other skill components remain v1.0. Probability estimates are clipped ridge predictions, not calibrated logistic probabilities. No preseason injury, contract, team bullpen competition or team save allocation is supplied.

## Participation data gate

G>0 or positive PA/OUTS confirms appearance, including pitchers with zero outs. Explicit eligible G=0 and PA/OUTS=0 confirms nonappearance. A missing actual player-season is UNKNOWN; it does not imply zero appearances.

If either participation class has fewer than 20 verified historical examples for a role, its status is PARTICIPATION_BLOCKED_NO_VERIFIED_CLASS_SUPPORT. Its neutral multiplier is 1, leaving a conditional-on-appearance forecast. No misleading Brier score is published for unsupported models. The playing-time and role models still run. Expect this gate to remain blocked with the current positive-appearance reference until verified nonappearance evidence is provided.

Optional: --participation-evidence FOLDER accepts a reviewed, immutable historical evidence package. Do not create negatives by merely subtracting FanGraphs export rows. Required contents:

1. confirmed_nonappearance.csv with columns season,player_type,mlbam_id,status,source,evidence_file. status must be CONFIRMED_NO_MLB_APPEARANCE. Only 2016–2025 identities already in the prior-history matrix are allowed.
2. Each cited evidence_file beneath the package folder: authoritative season appearance evidence, or a reviewed complete-scope reconciliation that establishes no MLB appearance in that role. source must explain the provenance. Hash checks do not independently certify a human review decision.
3. output_sha256.json mapping every package file except itself to SHA-256. Every cited evidence file must be registered.

Duplicate/future cases, changed hashes, unregistered evidence, path escapes and conflicts with observed appearances fail. The package is snapshotted into the new release; original labels remain unchanged. Historical participation evaluation joins only that frozen snapshot. Missing 2026 outcomes remain unknown. Evidence additions require a new output release, never edits to frozen v1.0 or v1.1.

A full verified participant universe and prospect/non-return labels remain separate future work. This package does not invent that universe or claim an unconditional production participation model when the gate is blocked.

## Files to review

Build folder:
- opportunity_build_report.json: model statuses, blocked participation support, final historical choices and disclosure.
- historical_scores.csv and historical_paired_predictions.csv: identical eligible pools for v1_0 and v1_1.
- candidate_scores.json, rolling_choices.json: candidate results, earlier-fold selection evidence and saves-relevant gate.
- fit_chronology.json: actual fit years and status for every model/origin.
- opportunity_diagnostics.csv: conditional/expected volume, support status, G/GS, roles and saves-hurdle components. Historical actual G/GS/SV are diagnostic fields only. No 2026 actuals are read by the builder.
- frozen_models.json, frozen_2026_forecasts.csv, freeze_manifest.json.

Evaluation folder:
- opportunity_evaluation_report.json and evaluation_2026_scores.csv.
- cohort_scores.csv: all eligible; actual PA>=100/300; actual IP>=40/100; prior exposure; actual/prior pitcher roles; actual/prior SV>=5. Actual-exposure/actual-role cohorts are retrospective diagnostics, not known preseason cohorts.
- pitcher_role_predictions.csv, role_scores.csv and role_confusion.csv: individual G/GS, G/GS RMSE, overall role accuracy and class confusion counts.
- saves_hurdle_predictions.csv and saves_hurdle_scores.csv: Brier scores for any saves conditional on observed appearance.
- participation_predictions.csv and participation_scores.csv: supported models only, with explicit class counts.
- benchmark_scores.csv, benchmark_paired_predictions.csv, benchmark_coverage.csv and identity_review.csv: common eligible pools by source/metric/year, source record IDs and unresolved identities. Steamer/OOPSY enter only after freezing. Analytical exclusions retained; no name guessing.

Please send opportunity_build_report.json, historical_scores.csv, opportunity_evaluation_report.json, evaluation_2026_scores.csv, cohort_scores.csv, role_scores.csv, saves_hurdle_scores.csv and benchmark_scores.csv after running. Full-data performance and adoption counts must be determined on your PC; synthetic tests are not accuracy evidence.

## 2026 disclosure

2026 was reviewed during v1.0 development before v1.1 was designed. It is a disclosed evaluation set, NOT a new untouched holdout. No 2026 labels enter fitting, preprocessing, scaling or selection. Repeated evaluation does not establish independent validation; further development must use historical folds and future frozen prospective forecasts. Retrospective source vintages and historical measurement limitations remain. No statistical significance or production-readiness claim is made.
