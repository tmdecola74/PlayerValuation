# v1.23.1 — restrict label validation to the scoring scope

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, replacing:

- `recent_skill_inputs_v1_23.py`
- `recent_history_skills_v1_23.py`
- `evaluate_recent_history_skills_v1_23.py`
- `tests/test_recent_history_skills_v1_23.py`

The original v1.23 loader incorrectly required every eligible label in the full reference to be nonnegative, including signed metrics that this experiment never scores. For example, a valid negative K-minus-BB rate should not be treated as a negative event count.

The fix uses the explicit hitter/pitcher scoring metric lists plus G/GS. Other label metrics are ignored for fitting/scoring and recorded in a scope audit. No excluded metric is converted to zero, made into a target, or used to expand a comparison pool. Eligible scoring labels still must be finite and nonnegative. An invalid scoring label now identifies its season, role, player, metric and value in the error message. Identity, duplicate, eligibility and chronological split guards also remain in force for ignored rows.

New outputs:

- Development: `training_label_scope_audit.csv`
- Evaluation: `evaluation_label_scope_audit.csv`

Both reports retain policy version 1.23.0 and identify `build_implementation_version: 1.23.1`, with a count of ignored non-scoring label rows. Weights, estimators, selection gates, feature families and frozen workload/saves/holds policies are unchanged. No original reference, accepted forecast, manifest or input hash is edited.

All **27 tests pass** on the development runtime, including a complete historical build and separate evaluation with eligible negative, non-scoring labels in their fixtures. Regression tests verify that those labels are audited and ignored, negative HR remains rejected, ignored metrics cannot bypass duplicate/split guards, and changing an ignored label does not change the returned modeling labels. The user's full production labels are not available locally, so this does not claim a production accuracy result.

Your benchmark inventory completed successfully and does not need rerunning. The failed development build stopped before publishing an output, so no data/output directory needs deleting. Run:

```powershell
python -m unittest discover -s tests -p "test_recent_history_skills_v1_23.py" -v
python recent_history_skills_v1_23.py
python evaluate_recent_history_skills_v1_23.py
```

If a successful output exists from another run, choose a new development `--output` and give its folder to the evaluator with `--run` as usual. Do not bypass a hash error or edit source statistics to make validation pass.
