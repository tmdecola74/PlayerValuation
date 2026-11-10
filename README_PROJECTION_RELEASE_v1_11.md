# Consolidated standalone projections — v1.11

This is the principal **2026 projection export**, not another candidate-fitting release. It publishes the accepted v1.5 composition: historically selected hitter workload change and pitcher probability workloads, prior frozen skill components, unchanged saves, and the historically selected holds component/fallback. It replays the earlier historical gates and verifies full frozen vectors before exporting. It never adopts v1.6–v1.10 research overlays, retrains a model, or changes a choice using 2026 outcomes. The multiyear SB candidate remains in its existing research release.

The established consensus remains a separate selectable source. There is **no blending, hidden fallback, or replacement of a missing homegrown forecast with consensus**.

## Install and run

Extract the ZIP **into the outer project directory**:
`D:\JonAPythonClass\pycharm\PlayerValuation`

The Python files go alongside the existing scripts; the new test goes into `tests` and the new JSON goes into `config`. No older files are replaced. Existing v1.0–v1.5 standalone modules, configs, tests, and output folders must remain installed; the fixture tests reuse those prior test builders. Requirements are the project's existing NumPy and DuckDB dependencies.

From the activated project virtual environment:

```powershell
python -m unittest discover -s tests -p "test_projection_release_v1_11.py" -v
python build_projection_release_v1_11.py
python evaluate_projection_release_v1_11.py
```

The **build** writes:
`outputs/projection_release_2026_v1_11`

The separate **evaluation** writes:
`outputs/projection_evaluation_2026_v1_11`

Both commands require new output directories and create complete, hash-verified backups under `backups`. Prior releases, SQLite/DuckDB references, consensus snapshots, labels, and original Statcast files remain unchanged. If interrupted, an unpublished staging folder is cleaned. To repeat, select another output name; pass that name to the evaluation's `--run` argument.

## Required input locations

| Argument | Default |
|---|---|
| `--run15` | `outputs/standalone_holds_attribution_v1_5` |
| `--run14` | `outputs/standalone_combined_v1_4` |
| `--source` | `outputs/standalone_workload_experiments_v1_3` |
| `--matrix` | `outputs/standalone_lagged_features_v1_0` |
| `--baseline` | `outputs/standalone_role_workload_v1_2` |
| `--labels` | `outputs/training_labels_v1_0` |
| `--consensus` | `outputs/nfbc15_dc_values_2026_v1_1_reviewed_reportingfix/consensus` |
| `--warehouse` | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |
| `--draft-inputs` | `data/valuation_inputs_dc_v1_1` |

Change only the path arguments when local folder names differ. `--consensus` must point to the subfolder containing `hitter_consensus.json`, `pitcher_consensus.json`, and `metric_provenance.csv`. Its 2026 rows are consumed as a frozen snapshot; the established consensus algorithm is not rebuilt or reweighted. All consumed files are fingerprinted. Warehouse migration Parquet fingerprints and canonical MLBAM ownership are verified.

## Projection tables

| File in the release folder | Purpose |
|---|---|
| `homegrown_hitters_2026.csv` / `.parquet` | One row per homegrown hitter/MLBAM identity |
| `homegrown_pitchers_2026.csv` / `.parquet` | One row per homegrown pitcher/MLBAM identity |
| `consensus_hitters_2026.csv` / `.parquet` | Separate established consensus hitters |
| `consensus_pitchers_2026.csv` / `.parquet` | Separate established consensus pitchers |
| `component_provenance.csv` | Per-player, per-metric frozen source, model/forecast references, hashes, overlay choice, dependencies; original consensus metric provenance |
| `draft_pool_coverage.csv` | NFBC asset × projection-source coverage, reviewed identity, ADP, playing time, unsupported components |
| `exceptions.csv` | Missing projections, unsupported values, identity gaps, possible cold starts/prospects, and playing-time review flags |
| `accepted_component_choices.json` | Frozen final historical decisions |
| `projection_release_report.json` | Counts, coverage, limitations, source/date disclosures |
| `forecast_freeze.json` / `output_sha256.json` | Projection freeze and full output integrity manifests |
| `export_schema.json` | Keys, units, null policy, source selection and adapter contract |

Hitters include PA, AB, hit types, H, HR, R, RBI, SB, BB/HBP/SF/SH, AVG/OBP/SLG/OPS. Pitchers include continuous expected OUTS, decimal IP, H/ER/BB/SO/HR, W/SV/HLD/QS, ERA/WHIP/SV+HLD. Pitcher `K` is an exact alias of `SO` for downstream use. This release does not invent unsupported G/GS, CS, hitter SO, or other unavailable outputs.

Homegrown numeric values must equal the accepted frozen v1.5 vector, including saves and holds. Consensus primitive components remain intact; derived rates are recomputed from components. Inconsistent complete component vectors stop publication rather than silently changing counts. Missing components stay null. Partial consensus hit-type vectors cannot support SLG, while a published H and AB can still support AVG. Numeric output is not rounded or capped.

**Units:** IP is decimal innings, not baseball `.1`/`.2` notation. Forecast OUTS are continuous expectations, not rounded integer outs. AVG = H/AB; ERA = 27×ER/OUTS; WHIP = 3×(H+BB)/OUTS. A zero denominator produces null. R/RBI/W/SV/HLD remain model estimates, not identities reconstructed from a game simulation.

## Coverage and playing-time reviews

Player joins use canonical IDs and uniquely owned MLBAM IDs, never names. Reviewed eligibility links supersede old ADP links. NFBC IDs remain separate platform assets; identical names are not merged. Canonical two-way identities retain separate hitter/pitcher rows; the existing valuation engine still prevents counting one canonical identity twice in its global roster assignment. No Yahoo position eligibility is inferred from NFBC eligibility.

Review flags use fixed, versioned thresholds: PA <50 or >750, IP <10 or >220, or a prior-year change exceeding 300 PA / 240 OUTS. They **do not alter forecasts**. The basic valuation adapter requires complete 5×5 category components, a canonical ID, and at least 1 AB or 1 IP. Position eligibility, roster depth and league-specific rules remain later valuation gates.

An asset absent from the homegrown prior-history universe is flagged as a **possible cold start/prospect requiring review**. It is not automatically classified as a prospect, assigned a zero forecast, or supplied a prospect projection. An unmapped player cannot be identified as a cold start without evidence. Players with no NFBC listing can still appear in source projection tables.

## Player-level evaluation and benchmarks

The evaluator opens the separate 2026 eligible FanGraphs labels only after verifying the exported forecast freeze. It requires the same frozen reference and warehouse as the release. No count or label exclusions are changed. Missing actual records are not interpreted as zero participation.

| File in the evaluation folder | Purpose |
|---|---|
| `player_comparisons.csv` | Individual projected/actual values, signed/absolute errors, eligibility status and source record IDs |
| `matched_benchmark_scores.csv` | MAE/RMSE/bias by metric, source and comparison group |
| `matched_benchmark_pairs.csv` | Exact player-level paired comparisons against Steamer/OOPSY and consensus |
| `comparison_coverage.csv` | Eligible/forecast/matched counts and membership hashes |
| `largest_homegrown_errors.csv` | Largest 25 absolute errors per role/metric; retrospective review only |
| `actual_participants_without_homegrown.csv` | Observed participants missing from the frozen homegrown universe, never added back into projections |
| `benchmark_identity_exceptions.csv` | 2026 benchmark records that cannot be joined safely |
| `projection_evaluation_report.json` | Evaluation scope, counts, source availability and disclosures |

Each matched group uses identical eligible players **within each metric**. Homegrown–Steamer and homegrown–OOPSY results are reported separately, with an additional all-source common pool. An empty benchmark pool remains visible as n=0 with null scores. Do not compare unpaired all-eligible scores as though their player pools were identical. True zero labels are retained; disputed/missing labels are excluded. Benchmark components remain their published/available metrics with existing analytical exclusions.

**2026 was already reviewed.** These are disclosed retrospective evaluations, not a newly untouched holdout. Projections/ADP use March 24, 2026 as the user-confirmed effective date; retrieval occurred later and archived-as-of vintages have not been independently established. No claim of historical timestamp certification is made.

## Valuation/draft-tool interface

The four `*_valuation_input.json` files hold the record shape accepted by the existing `value_players` / `candidate_records` APIs. The loader verifies integrity and selects one source explicitly:

```python
from projection_release_v1_11 import load_valuation_source
players = load_valuation_source(
    "outputs/projection_release_2026_v1_11", "homegrown"
)
# Choose "consensus" separately for an independent valuation run.
# Pass players to the existing value_players with the reviewed league profile,
# eligibility and SGP calibration. No league configuration is changed here.
```

The adapter includes only rows passing basic component/exposure/identity gates. All other projections remain available in the full tables and exception audit. This build does not run new SGP rankings, dollar allocations, weekly lineups, or draft recommendations. It provides their stable projection input while keeping established consensus available independently.

## Review next

Send `projection_release_report.json`, `projection_evaluation_report.json`, `matched_benchmark_scores.csv`, `exceptions.csv`, and `draft_pool_coverage.csv` after the production run. The player comparisons and largest-error files support deeper investigation afterward.

Research remains separate: retain the multiyear SB candidate; prioritize historically available pitcher role/availability/return information over further general multiplier tuning. Any new candidate must use historical folds for selection and disclose 2026's prior review.
