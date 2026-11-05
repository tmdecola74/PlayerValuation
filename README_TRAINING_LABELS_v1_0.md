# Frozen FanGraphs training labels v1.0

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`. This adds the builder, a private versioned label resolver, configuration and tests. It does not overwrite the existing register, references, shared resolver or warehouses.

The full corrected reference is on your PC. This package contains a tested generator, not production label tables. Validation used the actual importer schema, synthetic fixtures and a full-size older reference under an isolated test policy. The production command requires the corrected reference hashes already pinned by your register; no bypass flag is provided.

## Run

DuckDB is required and is already used by your warehouse/importer.

```powershell
python -m unittest discover -s tests -p "test_training_labels_v1_0.py" -v
python build_training_labels_v1_0.py --reference "data/actuals_reference_v1_0_min0ip" --register "outputs/discrepancy_register_v1_0_utf8" --output "outputs/training_labels_v1_0"
```

Choose a new output path on another run. Both Parquet hashes, register manifest and label-rules implementation are checked. Every registered case must reproduce the frozen FanGraphs value. Wrong snapshots, duplicates, orphan identities, invalid counts and conflicting splits fail before publication. Do not reimport or edit hashes to bypass a failure.

Every successful build verifies a complete backup under `backups`. Sources are never overwritten. Text input/output explicitly uses UTF-8. No network requests or model fitting occur. Failed output stages are removed.

## Outputs

| Files | Purpose |
|---|---|
| `training_labels.parquet` and `.csv` | Eligible scalar labels for 2015–2025 only |
| `holdout_labels.parquet` and `.csv` | Eligible scalar labels for 2026 evaluation only |
| `training_label_audit.parquet` and `.csv` | All requested training labels, eligibility, reasons, dependencies and case IDs; excluded values are null |
| `holdout_label_audit.parquet` and `.csv` | Same audit structure for 2026 only |
| `training_joint_bundles.csv` | Training component vectors with all-or-nothing eligibility; rejected vectors have no values |
| `holdout_joint_bundles.csv` | Separate 2026 component vectors |
| `label_coverage.csv` | Eligible/excluded counts by season, role and metric |
| `label_build_report.json` | Split counts, exclusions, source fingerprints and backup location |
| `register_snapshot/` | Copied policy, case register and prior build report |
| `input_hashes.json`, `output_sha256.json` | Integrity and reproduction controls |

Labels use frozen FanGraphs components without MLB/Statcast substitution. External projection systems are not inputs. Rates are recomputed from counts; IP is integer OUTS/3. Missing components and zero-denominator rates remain missing. True zero saves remain valid. Expect exclusions beyond the register's 128 rows when denominators are zero or components are missing.

Keys are season, player_type, MLBAM ID and metric. Two-way roles remain separate. The long-form source schema is the existing importer's actual_counts.parquet (season/player_type/mlbam_id/metric/value/split) and player_seasons.parquet (identity and split).

## Use and review

Fit/select models using only `training_labels`. These are outcomes, not preseason features: never use same-season actual PA/IP or label vectors as predictive inputs. Rolling-origin folds and lagged feature cutoffs remain a later integration requirement.

Use 2026 labels only after forecasts/models are frozen. A regression test changes holdout outcomes and confirms byte-identical training CSVs. For joint/coherent targets, apply the joint-bundle gate. Independent HR labels can remain usable while H/AVG or a hitting vector is excluded. Compare homegrown and external systems on identical label sources and paired eligible pools.

`model_ready: false` remains intentional. Label materialization does not certify all Statcast measurements, source reconciliation or feature chronology. The 2020 season is preserved as observed; season-length normalization belongs to modeling.

After running, check training years 2015–2025, holdout 2026, unchanged inputs and 32 registered disputed metrics. The default target list should produce 128 registered dependency exclusions; additional exclusions are separately explained. Send `label_build_report.json` and `label_coverage.csv` for review. Full label tables need not be uploaded initially.
