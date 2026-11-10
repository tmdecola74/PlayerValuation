# PlayerValuation v1.22 — targeted denominator and measurement-scope audit

Extract this package into `D:\JonAPythonClass\pycharm\PlayerValuation`. It adds new files only. Preserve v1.20, v1.21 and the accepted projection release.

Run from the project root in the existing virtual environment:

```powershell
python -m unittest discover -s tests -p "test_statcast_scope_v1_22.py" -v
python audit_statcast_scope_v1_22.py
```

Defaults:

| Input/output | Folder |
| --- | --- |
| Frozen leaderboard intake | `outputs/statcast_leaderboards_v1_21` |
| Frozen source-window manifest | `outputs/standalone_lagged_features_v1_0` |
| Expanded archive summaries | `outputs/expanded_statcast_v1_20` |
| New audit | `outputs/statcast_scope_audit_v1_22` |
| Complete verified backup | `backups/statcast_scope_audit_v1_22_<timestamp>` |

If a prior audit output already exists, choose a new folder:

```powershell
python audit_statcast_scope_v1_22.py --output "outputs/statcast_scope_audit_v1_22_run2"
```

Existing `standalone_io_v1_0.py` and DuckDB are required. No download or model fit is performed. No accepted forecast file is opened or edited.

## What is audited

1. Verify registered v1.21 historical tables, original 2023–2025 EV source snapshots, v1.20 bindings and the matrix's frozen manifest. Check every configured March 1–November 1 window for 2023–2025; verify saved CSV, Parquet and schedule hashes. Old and 2026 manifest entries are skipped before their source files are opened.
2. Reconstruct physical BBE counts, hard-hit/barrel numerators, finite-EV and classification denominators, launch-angle means/sweet spots and coordinate pull proxies from frozen Parquet. Enforce regular-season game type, physical keys, row/date totals and unique in-play outcomes. The reconstructed values must reproduce the existing reconciliation; otherwise publication stops.
3. Compare exported counts directly with reconstructed numerators. Report rates over **measured observations**, **archive total BBE**, and **exported BBE** independently. Equal total BBE is not called equal measured denominators. No rate is corrected or substituted.
4. Reproduce the prior hard-hit accounting residual cohort and historical normalization flags. The production reports supplied for this build contain 52 and 100, respectively; these numbers are not hard-coded as acceptance criteria. Unsupported flag types fail explicitly rather than being dropped.
5. Trace all unresolved count/rate/BBE cases and normalization cases. Also trace the top five beyond-tolerance differences for each source year, role and metric with at least 100 exported BBE: mean EV, mean LA, sweet-spot rate, pull rate and pulled-air rate. Selection uses measurement disagreements, never player outcomes.
6. Write an eligibility overlay for every historical v1.21 metric/player-season. Previously masked rows remain held. Accounting-resolved rates/counts can be marked research eligible with explicit definitions; EV/LA/sweet-spot measurement scope remains held, direction stays separate from the archive proxy, and bat tracking remains a short-history research branch. No new fitted-model input or projection source is promoted.

The event trace includes game/date/PA/pitch keys, both player IDs, source Parquet filename, unedited finite physical measurements, raw classification/coordinates, valid-LA/class flags, numerator membership and geometry flags. Missing measurements and unknown numerator membership remain blank, not zero. Original CSV/Parquet hashes and paths are in the source-window bridge.

## Review these outputs first

| File | Purpose |
| --- | --- |
| `scope_audit_report.json` | Totals, classifications, source guards and limitations |
| `denominator_count_audit.csv` | Both counts and all three explicitly named rate denominators |
| `hardhit_prior_residuals.csv` | The previously identified 52 accounting residuals on these inputs |
| `historical_normalization_flag_audit.csv` | The separate 100 historical exported count/rate flags |
| `target_scope_comparisons.csv` | Original player-level export/archive differences for trace targets |
| `target_event_trace.csv` | Exact underlying physical events and measurement membership |
| `target_game_bridge.csv` | Game/date counts and sums for locating events |
| `target_subgroup_summary.csv` | Overlapping measured/missing, contact-type, low-EV and bunt-description diagnostics |
| `metric_eligibility_summary.csv` | Counts by metric, role and audit decision |
| `feature_eligibility_decisions.csv` | Player-level decision overlay, original eligibility and reason |

Additional outputs: `archive_replay.csv`, `exposure_scope_summary.csv`, `target_player_seasons.csv`, `physical_value_exceptions.csv`, verified EV snapshot and source-window inventories, a fixed audit contract and input/output hashes.

## Interpreting the result

- A matching numerator with a total-BBE-only rate match is an accounting explanation. It does **not** identify how the leaderboard handles each unmeasured event.
- A measured-only match can explain an exported count/rate flag, but v1.21's original mask is not automatically released.
- Integer denominators compatible with displayed rounding are reported as a range/count. They are investigation leads, not inferred official sample membership.
- The classic barrel denominator inherits its original `launch_speed_angle BETWEEN 1 AND 6` definition. Noninteger/invalid classifications are reported separately; this audit does not silently rewrite the old definition. Expanded LA uses its original valid range and pull uses the fixed v1.20 coordinate geometry.
- EV below 50 mph and descriptions containing `bunt` are predefined diagnostic groups. They are **not** a claimed leaderboard exclusion rule; the description does not identify every bunt. Subgroups overlap and must not be summed as disjoint totals.
- We do not possess an official event-membership list for each leaderboard metric. Tracing an EV/LA/pull disagreement to saved events can narrow its scope, but cannot alone prove which events the leaderboard excluded, a tracking revision, or a scoring revision.
- `research eligible` means definition/accounting controls allow a separate historical experiment. It does not establish incremental predictive value, long-history coverage, era comparability or model approval. Existing minimum sample controls remain in force. These decisions concern the supplemental v1.21 metrics; they do not replace v1.20's feature contract.
- Combined metadata reports may contain quarantined-2026 row descriptions. No 2026 normalized feature table, EV snapshot, pitch file, actual label or evaluation outcome is opened. 2026 remains previously reviewed reporting data for later frozen experiments.

On any failure, do not edit original evidence to make the audit pass. Keep the traceback and the named mismatch. Successful output is staged, backed up completely, hash-verified and published to a new folder. Interrupted builds remove their unpublished staging folder.

## After this audit

Review denominator classifications and scope traces before defining any new model candidate. Preserve the accepted workload, saves, holds and projection source. Any subsequent feature experiment must use earlier historical folds, retain 2021, keep missingness/sample controls explicit, and freeze decisions before separate disclosed 2026 reporting.
