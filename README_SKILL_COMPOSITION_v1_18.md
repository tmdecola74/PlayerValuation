# PlayerValuation v1.18: frozen composition audit

Extract this ZIP into the existing PlayerValuation project root. It adds one script and tests; it does not replace v1.17 or any accepted projection release. Requires the installed v1.17/v1.16 and their existing dependencies. No new Python packages beyond those releases.

```powershell
python -m unittest discover -s tests -p "test_skill_composition_v1_18.py" -v
python audit_skill_composition_v1_18.py
```

Default input folders:
- `outputs/statcast_incremental_v1_17`
- `outputs/training_labels_v1_0`
- `outputs/standalone_lagged_features_v1_0`

Default output: `outputs/skill_composition_audit_v1_18`. A verified complete copy is written under `backups`. Existing output folders are rejected; use `--output` with a new name to repeat. All inputs are read-only and hash-checked against the frozen experiment. No production data is bundled.

## What it traces

For every historical player-season, method and component:
1. Accepted implied skill rate versus saved raw skill rate.
2. Unconstrained counts computed from raw rates and frozen accepted workload.
3. The original v1.17 composition replay, checked against its saved final statistics.
4. Final implied rates and final differences from accepted values.
5. Eligible frozen actuals and the exact squared-error decomposition:
   `(raw error² − accepted error²) + (final error² − raw error²) = final error² − accepted error²`.

Hitter PA fractions are normalized when AB/PA + BB/PA + HBP/PA + SF/PA + SH/PA exceeds one. Hit fractions are normalized when 1B/AB + 2B/AB + 3B/AB + HR/AB exceeds one. Pitcher HR is clipped to H. Ratios are derived from components. Saves, holds and accepted workload remain exact anchors. An unsupported complete skill vector retains the accepted forecast and is reported explicitly. A historical-selected vector choosing accepted for every component retains the exact saved accepted vector.

Unconstrained vectors are diagnostic calculations, **not projection exports**. Error decomposition explains arithmetic propagation; it is not causal attribution. A better rate with actual exposure need not produce a better count under imperfect projected exposure. Changing another component can change a derived statistic without changing that statistic's originally selected rate.

## Reports

| File | Purpose |
|---|---|
| `composition_audit_report.json` | Replay, anchor and read-only checks |
| `component_reproduction_counts.csv` | New rates versus rates already reproduced by accepted forecasts |
| `component_trace.csv` | Every raw/accepted/final implied component rate, selected method and actual rate |
| `statistic_trace.csv` | Every raw count/ratio, coherence adjustment, final statistic and error decomposition |
| `composition_support.csv` | Normalization factors, clipping, unsupported-vector fallback and all-accepted selection |
| `historical_composition_scores.csv` | Year-by-year same-player raw/accepted/final error and mean error decomposition |
| `equal_season_composition_summary.csv` | Equal-season RMSE/MAE over the available reported years |
| `recent_2023_2025.csv` | Recent-season results without dropping difficult seasons |
| `transition_2021.csv` | Explicit 2021 results |
| `established_history.csv` | Prior history of two or three-plus seasons; low history remains in the full report |
| `largest_composition_changes.csv` | Top 25 nonzero adjustments per statistic, identified by MLBAM ID |
| `next_candidate_design.json` | Proposed coherent-vector historical gate; no fit, thresholds or adoption |

Cohorts also include prior role, prior age and retrospective actual exposure. Established history does not imply high current-year playing time. Summaries compare the three stages on the same eligible rows and provide membership hashes. Missing/excluded labels remain missing; zero counts remain valid. Ratio errors require positive eligible AB or OUTS. Equal-season summaries retain all available years, including 2020/2021; cohort membership can make some years unavailable, listed in `seasons`.

Rates classify as `ALREADY_REPRODUCES_ACCEPTED`, `NEW_RATE_FINAL_REPRODUCES_ACCEPTED`, `NEW_RATE_FINAL_CHANGED`, or `UNSUPPORTED_RATE`. Equality uses the inherited tolerance: 1e-9 × max(1, absolute values). The largest-change report is ranked within statistic; different statistic units are not comparable.

## Next research candidate

The proposal tests acceptance of a **complete coherent vector**, rather than promoting isolated skill-rate winners. It would use only earlier historical folds, retain frozen workload/saves/holds, and require final-statistic improvement with recent-season, established-history and low-history safeguards. This audit supplies evidence for specifying that future experiment. It does not fit it or claim that it improves projections. Thresholds must be fixed before its fit.

No 2026 forecast or holdout file is opened by this build. Previously reviewed 2026 results remain in the separate v1.17 evaluation. Neither those results nor target actual exposure should define new preseason features or selection rules.

Please return `composition_audit_report.json`, `component_reproduction_counts.csv`, `equal_season_composition_summary.csv`, `recent_2023_2025.csv`, and `transition_2021.csv` first. Keep the full player traces locally for targeted investigation.
