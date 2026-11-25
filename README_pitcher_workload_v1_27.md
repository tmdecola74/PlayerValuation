# PlayerValuation v1.27 participation overlay

Extract into the existing PlayerValuation project. This adds two scripts and a test
file; the v1.23, v1.24, v1.25 and v1.26.1 packages remain unchanged. Existing project
dependencies (NumPy and DuckDB) and the v1.23/v1.24 frozen outputs are required.

Run from the project root in PowerShell:

```powershell
python -m unittest discover -s tests -p "test_pitcher_workload_v1_27.py" -v
python participation_label_overlay_v1_27.py
python pitcher_workload_v1_27.py
python pitcher_workload_v1_27.py --evaluate
```

Stop if any command fails. The overlay reads the seven certified audit directories
under outputs. For 2023 it uses pitcher_label_coverage_2023_corrected; for all
other years it uses pitcher_label_coverage_<year>_v1_26_1. Each directory must retain
report.json, pitcher_label_coverage.csv, input_hashes.json, and output_sha256.json.
Use --audits-root to point to a different common parent. No network is needed.

The overlay checks audit output hashes, upstream bindings, certification, season
coverage, and the exact pitcher membership from the frozen forecast. It writes
8,461 metric rows: G=0 and OUTS=0 for each of the 4,230 verified non-appearances,
plus one G=14 correction with expected frozen G=13 for Josh Walker (MLBAM 677020).
Positive audit rows verify coverage and are not copied into the overlay.
The original frozen Parquet and audits are read-only. The overlay report lists
each source, its checksum, and the documented Walker correction.

Outputs:

- outputs/participation_label_overlay_v1_27: overlay CSV, report, input/output hashes.
- outputs/pitcher_workload_v1_27: chronological scores, coverage, rolling choices,
  and a frozen 2026 forecast. Models and selection use only earlier years;
  the earliest historical year is available for training later folds.
- outputs/pitcher_workload_v1_27_evaluation: separately scored 2026 outcomes.
  This command does not refit or select. Missing 2026 participation outcomes
  stay unknown. If there are no confirmed 2026 non-appearances, participation
  scores describe known positives only and do not measure performance on the
  full forecast pool. Historical audited folds supply the primary comparison.

Each command creates a new directory and a backup. For reruns use a fresh
--output path. For non-default paths, the workload build takes --overlay and
evaluation takes --run to locate its frozen model output.
