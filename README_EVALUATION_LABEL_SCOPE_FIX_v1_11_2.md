# v1.11.2 — evaluator-only label scope fix

The v1.11.1 projection build completed successfully and backed up its outputs. Keep that folder. No projection rebuild is required.

The evaluator incorrectly applied a nonnegative-value requirement to every eligible label, even metrics outside the projection release. The full actuals reference can contain legitimate signed metrics such as K-BB%. The traceback does not identify its offending metric, so this patch both corrects scope handling and adds an actionable error for any genuinely invalid scored label.

## Run

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, keeping the v1.11.1 scripts and config installed. The files in this patch have new names.

```powershell
python -m unittest discover -s tests -p "test_projection_release_v1_11_2.py" -v
python evaluate_projection_release_v1_11_2.py
```

Default source: `outputs/projection_release_2026_v1_11_1`

New evaluation output: `outputs/projection_evaluation_2026_v1_11_2`

A complete verified backup is created under `backups`. No models, choices, projections, consensus snapshots, actual counts, eligibility exclusions or previous outputs are changed. 2026 remains previously reviewed evaluation data.

## Scope policy

- The scored metric allowlist is the existing released hitter/pitcher metric schema.
- Labels outside that allowlist are not scored or used to construct missing-player coverage. Their player IDs, original metric, value, and eligibility are preserved in `label_scope_audit.csv`.
- True zero values and existing exclusions retain their previous behavior.
- Eligible scored metrics must still be finite and nonnegative. Failures now name season, role, MLBAM ID, metric and value. No invalid count is silently skipped or changed.
- Identity, duplicate, reference fingerprint and split checks remain active.

The evaluation report includes implementation version 1.11.2, source projection-release version 1.11.1, and counts of the out-of-scope label rows and metrics. Matched player pools are still identical within each metric/comparison group. The existing consensus quarantine count and its restricted comparison scope remain disclosed.

## Production build review

The supplied log reports 911 homegrown hitters and 1,302 pitchers. Of 979 draft assets, 872 have available homegrown projections, 102 lack source projections, and five lack confirmed identities. Basic valuation adapters contain 889 hitters and 1,260 pitchers; these counts do not establish league eligibility or recommendation readiness.

The consensus side requires investigation: 1,676 source rows were quarantined, affecting 497 draft assets. This is a substantial coverage restriction, not a clean consensus release. This evaluator patch does not resolve it or assume all differences are rounding.

Please provide:

- `outputs/projection_release_2026_v1_11_1/consensus_component_exceptions.csv`
- `outputs/projection_evaluation_2026_v1_11_2/projection_evaluation_report.json`
- `outputs/projection_evaluation_2026_v1_11_2/matched_benchmark_scores.csv`

The first file is needed to quantify H/component differences and examine source/component weighting before any consensus repair. If evaluation still rejects a scored label, the new message identifies the exact record to investigate.

## Validation

17 tests passed on synthetic end-to-end fixtures with DuckDB 1.4.3. New tests cover a legitimate negative out-of-scope label, preservation of strict validation for invalid scored labels, and invariance of matched scores and frozen projection files when the signed label is added. The 14 prior projection-release tests remain included. This is not a production evaluation run against the user's files.
