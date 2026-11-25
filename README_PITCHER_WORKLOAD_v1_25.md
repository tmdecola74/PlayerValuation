# Pitcher workload research v1.25

Extract into PlayerValuation with v1.24 and its v1.23.1 dependencies installed. The
frozen v1.24 build and the same v1.23 parent and training label directories are
required. The v1.24 evaluation folder is not required. NumPy and DuckDB are used.

```powershell
python -m unittest discover -s tests -p "test_pitcher_workload_v1_25.py" -v
python pitcher_workload_v1_25.py
python pitcher_workload_v1_25.py --evaluate
```

An optional dated preseason availability file can be supplied on the build command:
`python pitcher_workload_v1_25.py --availability "data/pitcher_preseason_availability.csv"`.
Copy the header-only template, then provide at most one final documented status per
target season and MLBAM pitcher ID. Valid statuses are AVAILABLE, LIMITED and
UNAVAILABLE. Supply a source URL or archival reference and the original publication
date. Use a consistent preseason snapshot cutoff across comparable seasons; the
validator requires a cutoff January 1 through March 1 of the target year and
publication on or after October 1 of the preceding year and strictly before cutoff.
Do not use retrospective injury or roster information. A missing record is UNKNOWN.
No availability file is assumed or downloaded; the build reports how many forecast
rows have supplied documentation. Historical documentation is needed to learn
availability effects; a 2026-only CSV cannot establish them.

## Targets and comparisons

- Participation means any MLB pitching appearance: positive games or outs confirms
  participation, and an explicit eligible G=0 confirms non-participation. Known zero
  outs count as zero innings even when appearance status is ambiguous. A pitcher
  who appeared without recording an out remains a participant. Missing actual rows
  are never zero-filled.
- Fit a penalized logistic participation model and compare Brier score with the
  earlier-fold observed participation rate. Fit ridge innings on known participants
  and separately on all known innings (direct IP control). Two-part expected innings
  is probability times conditional innings. The conditional scores also show the
  accepted IP forecast on the same participants as a reference; it is not a
  conditional forecast. Each fit has independent support requirements.
- Predictors: frozen preseason accepted IP, previous three seasons' workload and
  appearance evidence with missing flags, prior-season role, and dated availability.
  Preprocessing and coefficients use earlier forecast folds only. All scored players
  come from the accepted forecast pool with supported preseason IP.
- The selection gate uses equal-weight historical season MSE ratios and at least three
  supported folds. Either arm must improve overall IP MSE by 1% and avoid degrading
  the prior-starter cohort by more than 1%. The two-part arm must also improve
  participation Brier by 1%, avoid worsening conditional innings MSE versus the
  direct arm, and improve expected innings MSE versus the direct arm by 1%.
  Early unsupported folds retain the accepted forecast. No tuning or promotion.
- Actual innings bands, actual role transitions, stable starters, and role changes
  are retrospective diagnostic cohorts. They never enter features or selection.
  G=0 does not imply a role. Participation scores cover known outcomes only and
  may not represent the whole preseason universe when true zero appearances
  are missing from the label source.
- ERA, saves, and holds are carried through unchanged for audit. The output is an
  innings experiment, not a full statline: no counting stats or rates are rescaled.

## Outputs

Build: outputs/pitcher_workload_v1_25, including historical_scores.csv,
historical_coverage.csv, historical_player_audit.csv, rolling_choices.json,
models.json, frozen_2026_workload.csv and report.json. The report identifies
origins supporting the participation fit, and models.json includes sample counts
for non-appearances and each innings fit.

Evaluation: outputs/pitcher_workload_v1_25_evaluation, including
evaluation_scores.csv, evaluation_coverage.csv, evaluation_player_audit.csv and
report.json. The separate evaluator verifies the freeze, opens the 2026 labels, and
does not fit or select. 2026 was previously reviewed and is disclosed reporting only.

Both runs write new output folders and verified backups. Use a new --output path
to rerun. If writing the build to a custom path, pass it to evaluation via --run.
