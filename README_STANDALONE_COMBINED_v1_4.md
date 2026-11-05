# Standalone combined projections v1.4

This release combines the historically selected hitter-change and pitcher-probability workload components from v1.3. It preserves prior-role classification and exact saves forecasts. It does not fit another model, retune a gate, change a reference, or overwrite v1.0–v1.3.

## Install and run

Extract this ZIP into `D:\JonAPythonClass\pycharm\PlayerValuation` so the new Python files are in the project root. Existing standalone v1.0, v1.1, v1.2 and v1.3 scripts and completed output folders are prerequisites. Keep their test files to run the integration fixtures. No new dependency is required beyond NumPy and DuckDB from the earlier releases.

From the project root in the activated environment:

```powershell
python -m unittest discover -s tests -p "test_standalone_combined_v1_4.py" -v
python build_standalone_combined_v1_4.py
python evaluate_standalone_combined_v1_4.py
```

The evaluator includes read-only Steamer/OOPSY comparisons by default. If that warehouse is unavailable, use `--skip-benchmarks`; the report will explicitly state that benchmarks were not run. Use `--help` for alternate input/output paths. An existing destination is rejected. Choose a new `--output` folder for a rerun; do not delete a prior release to run this one.

Default inputs:

| Input | Folder |
|---|---|
| Frozen v1.3 experiments | `outputs/standalone_workload_experiments_v1_3` |
| Frozen v1.2 reference forecasts | `outputs/standalone_role_workload_v1_2` |
| Lagged matrix | `outputs/standalone_lagged_features_v1_0` |
| Frozen labels and exclusions | `outputs/training_labels_v1_0` |
| Benchmark warehouse | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |

## Composition and chronology

| Component | Combined policy |
|---|---|
| Hitter workload | v1.3 `selected_change_experiment` |
| Pitcher workload | v1.3 `selected_probability_experiment` |
| Pitcher hard role label | Frozen prior-role label for every player |
| Saves | Exact v1.2 forecast, which retains the accepted v1.1 saves model |
| Pitcher-change candidate | Separate research file, never used by combined forecasts |
| Unsupported or rejected component | Existing v1.3 frozen-baseline fallback |

The builder replays historical selection gates from the v1.3 workload forecasts and frozen training PA/OUTS, using only earlier origins. It verifies the replay against the saved rolling and final choices. It checks model fit chronology and the original probability streams, then validates every selected full-statistic source row. A missing forecast row, duplicate row, altered freeze, wrong input binding or nonchronological choice prevents publication.

For an origin such as 2024, the combined backtest uses the components selected before 2024. It never applies the final 2026 selections to all past years. Development origins are 2019–2025, with target 2020 excluded from selection and fitting and retained only as a stress report. Existing fixed source-2020 normalization remains inherited from v1.3.

The builder reads only historical labels and 2026 feature-only inputs. It does not open either 2026 label table or the outcome-bearing holdout matrix. Hash verification can read file bytes for integrity, but no evaluation outcomes are parsed. The evaluator opens the separate eligible 2026 label table only after verifying the frozen composition. It never fits or selects anything.

2026 has already been reviewed in earlier releases. It is disclosed evaluation data, not a fresh untouched holdout. All sources remain retrospective rather than independently archived preseason vintages. Steamer and OOPSY are benchmarks only.

## Statistical coherence

Hitter PA changes scale the existing AB, hit types, walks, HBP, SF, SH, R, RBI and SB components together. The builder verifies H equals singles + doubles + triples + HR, H does not exceed AB, and the PA components do not exceed PA. The remaining PA mass is not assigned a fabricated event type.

Pitcher OUTS changes scale IP, H, ER, BB, SO, HR, W, HLD and QS together. Saves stay exactly fixed because their separate opportunity model is preserved. Saves are not assumed proportional to innings. No integer rounding is performed.

Ratios are checked against the inherited vectors and recomputed:

- AVG = H / AB.
- OBP = (H + BB + HBP) / (AB + BB + HBP + SF).
- SLG = (1B + 2×2B + 3×3B + 4×HR) / AB.
- OPS = OBP + SLG.
- IP = OUTS / 3, with OUTS in integer-out units but forecasts allowed fractional expectations.
- ERA = 27×ER / OUTS.
- WHIP = 3×(H + BB) / OUTS.
- Saves-plus-holds = SV + HLD when both projected components exist.

A missing required component or zero denominator produces a missing ratio, never zero. Negative, nonfinite or inconsistent forecasts are rejected. A zero-OUTS forecast with positive separately preserved saves is flagged in the coherence audit rather than silently changing either forecast. This release provides coherent component expectations, not a full game-event simulation, GS/G forecast, or weekly lineup model.

## Category evaluation

Both the historical builder and evaluator score individual-player statistics. Standard 5×5 categories are R, HR, RBI, SB, AVG, W, SV, SO (K), ERA and WHIP. Additional outputs cover OPS, OBP, SLG, QS, HLD, SV+HLD, exposures and component counts.

Every metric uses an identical eligible comparison pool across:

1. Frozen v1.2.
2. Selected probability experiment.
3. Selected change experiment.
4. Combined v1.4.

External comparisons separately add Steamer, OOPSY, or all available sources. Availability and pool membership hashes are reported. A zero-player pool remains visible; no missing source or missing actual is turned into zero. The source record ID is retained in paired rows.

Only explicitly eligible frozen labels are scored. Missing or excluded labels, including missing SV+HLD labels, are never reconstructed from other labels. External SV+HLD may be derived only when both published components are non-excluded and the combined metric is not excluded. Analytical warehouse selections and identity mappings remain read-only. No name matching is introduced.

MAE, RMSE and signed bias use each statistic's native units. Pitcher workload is available in both OUTS and IP; SO is the canonical name for strikeouts. Rate diagnostics also show actual 100/300-PA hitter cohorts and actual 40/100-IP pitcher cohorts. Those are retrospective diagnostics, not preseason selection rules. Rates are individual-player errors, not team standings estimates. Errors across different category units are not added into one winner score.

## Output folders

Build: `outputs/standalone_combined_v1_4`

| File | Purpose |
|---|---|
| `combined_build_report.json` | Build integrity, policy and frozen historical choices |
| `frozen_composition.json` | Source bindings and final composition policy |
| `historical_forecasts.csv` | All four methods, chronological historical forecasts |
| `frozen_2026_forecasts.csv` | All four methods, frozen disclosed-evaluation forecasts |
| `pitcher_change_research_only.csv` | Unselected pitcher-change candidate, kept separate |
| `component_lineage.csv` | Player-season component choice and workload change |
| `coherence_audit.csv` | Component checks and exact-save checks |
| `classification_and_probability_inputs.csv` | Unchanged v1.3 role/probability evidence |
| `rolling_choices.json` | Replayed earlier-fold choices |
| `historical_category_scores.csv` | Historical category errors, no 2026 outcome scores |
| `historical_category_coverage.csv` | Historical actual/forecast/common-pool coverage |
| `historical_category_pairs.csv` | Historical paired predictions |

Evaluation: `outputs/standalone_combined_evaluation_v1_4`

| File | Purpose |
|---|---|
| `combined_evaluation_report.json` | Evaluation disclosure and integrity report |
| `category_scores.csv` | All statistics, cohorts and internal/external comparisons |
| `fantasy_category_scores.csv` | Compact standard 5×5 and additional Yahoo category subset |
| `category_coverage.csv` | Missing-data and identical-pool counts |
| `category_pairs.csv` | Detailed predictions, actuals and source record IDs |
| `identity_review.csv` | Unresolved benchmark identities |

Both output folders include integrity manifests and input hashes. Every successful build/evaluation creates a complete, hash-verified copy under `backups`. Inputs remain unchanged. Interrupted unpublished output stages are cleaned up. The pair CSVs can be large because they retain every method and comparison group; they are streamed to disk.

## Review after your full-data run

Send these files first:

- `combined_build_report.json`
- `combined_evaluation_report.json`
- `fantasy_category_scores.csv`
- `category_coverage.csv`

Use `category_scores.csv` for detailed rate/cohort reviews and `component_lineage.csv` for individual players. Local tests verify mechanics with synthetic fixtures; no full-data category-accuracy result is claimed in this package. Review historical category tradeoffs before production promotion or draft recommendations. Do not retune this release on the disclosed 2026 results.
