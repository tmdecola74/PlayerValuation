# v1.24 — hitter contact replay and pitcher workload audit

Extract into the PlayerValuation project root alongside the installed v1.23.1
scripts. Requires the successful v1.23 output and original training/holdout
labels. No new downloads or benchmark inventory runs are needed.

```powershell
python -m unittest discover -s tests -p "test_contact_workload_audit_v1_24.py" -v
python contact_workload_audit_v1_24.py
python contact_workload_audit_v1_24.py --evaluate
```

## Hitter experiment

The two arms replay the saved standard-recent and expanded-recent component
rates, before v1.23's hit-total normalization. This isolates the effect of
freezing HR without refitting, searching weights, or incorporating 2026 actuals.
Only 1B, 2B, and 3B can change. Accepted AB, HR, PA, BB, HBP, SF, and every
unrelated statistic are preserved exactly. Non-HR hits are proportionally
capped at AB minus HR. H, AVG, OBP, SLG and OPS are then recomputed. Missing
anchors or unsupported component rates retain the complete accepted forecast
with an explicit fallback status.

The full score pool includes fallbacks. The fitted table uses one matched pool
for all three methods, with both arms supported, eligible AVG and OPS, and
actual AB >= 30. Historical choices use earlier seasons only, with at least
three supported folds of 30 hitters and at least 1% lower equal-metric,
equal-season mean normalized MSE. AVG and OPS individually must stay within
1% of reference MSE and MAE. Guards require both latest seasons and two
supported folds in each history cohort (20 players per fold), with objective
within 1% and individual metric losses within 2%. History is established
when at least two of the preceding three seasons have positive eligible AB.
Expanded must clear both accepted and the standard contact arm. No candidate
replaces the production source.

## Pitcher audit

Pitcher forecasts are carried through unchanged, including IP, ERA, SV and HLD.
Reports provide matched IP and ERA errors (bias is forecast minus actual)
across actual exposure, prior role, actual role, and role transitions.
Exposure bands are below 20 IP, 20–99 IP, and 100+ IP, with separate zero
and unknown bands. ERA requires positive actual outs. Actual IP is outs/3.
Missing actuals are not converted to zero. Pairwise and all-source benchmark
groups use common players for each metric/cohort and record membership hashes.

Roles use eligible G and GS: starter if GS/G >= 0.50, reliever if <= 0.10,
swing otherwise. Prior role uses the immediately preceding season.
If the frozen v1.2 role run is available, its selected-role predictions are
included as a separately named diagnostic, not an assertion about which
role the final accepted workload model used. The confusion table compares
v1.2 and prior role on the same pool with both forecasts and an actual role.
If the role run is absent, the audit still reports prior/actual transitions.
Use --roles for a custom path, or --skip-roles to omit v1.2 predictions.

## Results

- Build: outputs/contact_workload_audit_v1_24
  - rolling_contact_choices.json: individual gate ratios and final historical choice.
  - historical_fitted_contact_scores.csv: matched fitted scores by year/cohort.
  - historical_contact_scores.csv: full scores, including fallbacks.
  - historical_pitcher_scores.csv and historical_pitcher_player_errors.csv:
    workload and ERA diagnostics, including benchmark scores.
- Evaluation: outputs/contact_workload_audit_v1_24_evaluation
  - evaluation_fitted_contact_scores.csv and evaluation_contact_scores.csv.
  - evaluation_pitcher_scores.csv, evaluation_pitcher_player_errors.csv,
    evaluation_role_confusion.csv.

Development never opens the holdout labels. Evaluation verifies frozen
inputs, reads the disclosed 2026 actuals and scores without any refitting or
selection. The already reviewed 2026 season is not independent validation.
The frozen inputs and accepted forecasts are not edited; each new run is
published with a verified backup. Existing output folders are refused.
For a different destination, use --output (and --run for evaluation).

Validation: six focused tests passed, plus an end-to-end synthetic v1.23
build -> v1.24 replay -> separate evaluation, including role binding,
training-only label reads during development, and backup equality.
Production accuracy requires running against your existing local outputs.
