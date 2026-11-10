# Validation

19 tests pass under Python 3.12, DuckDB 1.4.3 and NumPy. The tests cover:

- Exact accepted PA/OUTS/IP/SV/HLD/SV+HLD preservation, coherent counts/ratios, complete verified backups and unchanged source trees.
- Identical target-specific training memberships and common-feature preprocessing across arms.
- Role-appropriate physical features and absence of Statcast features/history flags from the standard arm.
- Registered measurement masking, unknown values, zero-exposure rates, unsupported-vector fallback and insufficient-guard rejection.
- A known synthetic Statcast signal improving paired skill predictions with the same estimator.
- Matched rate/statistic comparison pools, including asymmetric missing-rate support.
- Chronological fitting and decisions, current-origin label invariance, future predictor rejection, 2021 retention, and 2026 outcome mutation invariance.
- Source hash failure before publication, existing-output protection and interruption cleanup.
- Separate evaluation without fitting or changing source forecasts/choices.

An additional check generated the earlier standalone v1.0–v1.5/consolidated release's real synthetic artifact formats and ran both new commands against them. The experiment generated 7,469 historical rate-score rows and 16,100 statistic-score rows; separate evaluation generated 980 rate-score rows and 2,090 statistic-score rows. The validation fixture fitted older synthetic releases to construct its input artifacts; production accepted releases are not refitted by the new commands.

No production dataset was available for fitting during this build. No empirical Statcast improvement, accepted component change, significance claim or independently archived-vintage claim is made. Real acceptance results must come from the user's local historical run. The release is a separately labeled experiment; successful skill gates do not automatically promote a new full projection source.

The build learns new paired historical skill models and freezes 2026 research forecasts before any 2026 evaluation. The evaluator reads previously reviewed 2026 labels only for reporting. Statcast value and measurement metadata enter together, so effects of physical values alone are not isolated. Unsupported full-vector cases remain explicit, with fitted-only reports provided.
