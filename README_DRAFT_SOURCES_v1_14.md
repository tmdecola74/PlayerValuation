# v1.14 — independently audited sources, preseason priorities and entry-branch contract

This release independently checks the v1.13 adjustment ledger before making reconciled consensus available as a **supported arithmetic export**. It also prioritizes coverage gaps using preseason information and defines a separate dated-input/historical-fold branch for prospects, international arrivals and returners.

Accepted homegrown forecasts, the v1.13 universe and all earlier releases remain unchanged. The old candidate report is not rewritten. No actual label table, 2026 evaluation score or retrospective missing-participant list determines promotion, priorities or inclusion. No new statistical model is fitted or selected.

## Install and run

Extract into the outer project folder:
`D:\JonAPythonClass\pycharm\PlayerValuation`

Retain the previous v1.11–v1.13 scripts, configs, tests and output folders. All delivered filenames are new. Existing NumPy/DuckDB dependencies suffice.

```powershell
python -m unittest discover -s tests -p "test_draft_sources_v1_14.py" -v
python build_draft_sources_v1_14.py
```

Test fitting messages come from small synthetic fixtures. The production command does not fit models.

Default output: `outputs/draft_projection_sources_v1_14`

A complete, hash-verified backup is created under `backups`. Existing output folders are not overwritten. Failed/unpublished stages are cleaned on interruption. No new 2026 evaluation run is needed: promotion changes source labels and integration metadata, not v1.13 statistical values. Existing v1.13 exposure-cohort reports remain the applicable disclosed evaluation evidence.

Default inputs:

| Argument | Default |
|---|---|
| `--source` | `outputs/preseason_coverage_v1_13` |
| `--accepted-release` | `outputs/projection_release_2026_v1_11_1` |
| `--policy` | `config/consensus_reconciliation_v1_13.json` |

Use the exact original v1.13 policy file/path; formatting changes alter its recorded fingerprint. The original fixed policy is not retuned or loosened in v1.14.

## Independent reconciliation audit

The audit derives expected results from the original snapshots without calling the v1.13 reconciliation function. It checks:

- Every available candidate identity and released component against the independent arithmetic rules.
- Exact preservation of published anchors: hitter H/AB/extra-base hits/counting categories and pitcher workload/counts, including SV and HLD.
- The fixed one-hit singles-change cap and one-PA upward budget cap.
- Positive denominators, missing versus true-zero components, rate/component identities and valid count bounds.
- Contributor replay, common source pools and normalized weights for material repairs.
- The complete ledger: original field presence, before/after values, signed deltas, change flags, policy fingerprints, duplicates and missing rows.
- Per-player case decisions, population counts, frozen inputs and byte-identical accepted homegrown exports.

`adjustment_maxima.csv` reports changed counts, maximum absolute deltas, worst player/ID, and corresponding original/candidate values. `derived_without_original` distinguishes additions such as OUTS = 3×IP from changes to an already published workload. A large number of derived OUTS rows is not a change to published IP.

### Promotion gate

Only a passing audit emits `SUPPORTED_RECONCILED_CONSENSUS_V1_14`. **Supported is a technical data-contract status, not a claim of forecasting superiority or a 2026-based model choice.** Remaining source quarantines, if any, stay excluded and disclosed. The accepted homegrown source remains separate.

If the audit fails, the output contains the audit failures/report and a registry marking reconciled consensus unavailable. Its supported tables are not written. An explicit request for that source then fails rather than silently falling back to homegrown. The unchanged homegrown export remains available.

## Draft-tool source interface

Key artifacts:

| File | Purpose |
|---|---|
| `draft_sources_build_report.json` | Audit outcome, preservation flags, source counts and queue/branch status |
| `reconciliation_audit_report.json` | Independent audit checks and failure counts |
| `reconciliation_audit_failures.csv` | Blocking semantic failures, if any |
| `adjustment_maxima.csv` | Per-component maximum changes and derived-field counts |
| `projection_source_registry.json` | Explicit source choices, support status, date basis and policy binding |
| `homegrown_hitters_2026.csv` / `.parquet` | Unchanged accepted hitter exports |
| `homegrown_pitchers_2026.csv` / `.parquet` | Unchanged accepted pitcher exports |
| `reconciled_consensus_hitters_2026.csv` / `.parquet` | Supported reconciled hitters, only if the audit passes |
| `reconciled_consensus_pitchers_2026.csv` / `.parquet` | Supported reconciled pitchers, only if the audit passes |
| `original_consensus_records.json` | Preserved original published reference, not a valuation source |
| `original_metric_provenance.csv` | Preserved original component provenance |
| `reconciliation_adjustments.csv` | Preserved complete v1.13 adjustment list |

The registry has no automatic default or blend. Within PlayerValuation, the adapter returns the existing valuation record shape and explicit exclusions:

```python
from draft_source_registry_v1_14 import load_draft_source

players, excluded = load_draft_source(
    "outputs/draft_projection_sources_v1_14",
    source="homegrown",              # or "reconciled_consensus"
    profile="nfbc5x5",               # or "yahoo6x6"
)
```

Pass `players` to the existing valuation engine with the appropriate league configuration, SGP calibration and platform eligibility. DRAFTTOOL can consume the registry/JSON exports or wire this adapter as a project dependency. No UI or new rankings are built here.

The source-specific `*_nfbc5x5_valuation_input.json` and `*_yahoo6x6_valuation_input.json` files and corresponding exclusion CSVs are also exported. The category profiles enforce NFBC 5×5 versus Yahoo 6×6 component requirements, including Yahoo hitter OPS and pitcher QS/SV+HLD. They require canonical identity and at least 1 AB/IP. Missing components stay missing; unsupported rows are excluded from that profile, not zero-filled.

IP uses decimal innings; expected OUTS are continuous. Pitcher K is the SO alias. NFBC positions are not used as Yahoo eligibility. Correct platform eligibility, league roster depth, two-way asset treatment and valuation controls remain downstream requirements. Source readiness does not establish draft-recommendation readiness.

## Preseason coverage priorities

`nfbc_coverage_priorities.csv` includes NFBC assets missing a usable basic homegrown projection. It sorts by known **preseason ADP ascending**, then player type, projected workload descending and stable platform ID. PA and IP are not combined into one utility score. Unknown ADP sorts after known ADP.

Fixed NFBC15 DC review bands are ADP ≤150, 151–345, 346–750, >750 and unknown. They correspond to review organization, not fitted category utility or new inclusion rules.

Workload comes from **original published preseason consensus PA/IP**, with the frozen homegrown source used only if no original consensus record exists. Missing workload remains unknown. No actual PA/IP or 2026 outcomes are read. A change to reconciliation arithmetic therefore does not determine queue priority.

Nonmarket identities with preseason evidence and no usable homegrown projection are partitioned into:

- `nonmarket_workload_priorities.csv`: at least 100 projected PA or 20 projected IP, ranked separately within hitter/pitcher roles.
- `low_or_unknown_workload_review.csv`: the remaining low/unknown workload cases.

These thresholds only partition review queues. They do not remove anyone from the frozen `preseason_universe.json`, which is copied unchanged. Profiles' additional component exclusions remain separately available for league-specific review.

## Separate prospect/international/returner branch

This release defines a **contract, validated intake and rolling historical fold plan**. It does not invent minor-league translations, overseas league factors, MLB playing time, injury probabilities, roster assignments or new forecasts. Without the required dated inputs, `entry_branch_intake_report.json` reports `BRANCH_DEFINED_INPUTS_REQUIRED` and `fit_ready=false`. That is the expected first-run state.

The branch's future outputs are separated into participation/MLB workload, skill-rate/coherent components, pitcher role/workload, and saves/holds opportunity. Established projections remain benchmarks; the accepted homegrown baseline is not edited.

Four empty templates are produced:

| Template | Required information |
|---|---|
| `entry_branch_population_TEMPLATE.csv` | Origin, role, verified MLBAM ID, prospect/international/returner class, dated population evidence and optional birth date |
| `entry_branch_history_TEMPLATE.csv` | Prior-season minor-league/overseas/MLB primitive counts by competition, with event end, as-of date and provenance |
| `entry_branch_context_TEMPLATE.csv` | Dated roster/assignment/rotation/bullpen/injury/return/arrival observations |
| `entry_branch_cutoffs_TEMPLATE.csv` | Optional documented historical origin cutoff overrides |

Each source row requires source name, versioned source record ID, evidence reference, timezone-aware retrieval timestamp, and one of `ARCHIVED_AS_OF_CLAIM`, `USER_CONFIRMED_PRESEASON_EFFECTIVE`, or `RETROSPECTIVE_EVENT_TIME_ONLY`. These labels disclose provenance claims; the validator does not independently authenticate an archive. Unmapped foreign/prospect identities require a verified MLBAM bridge before branch intake; names are never used to guess it.

Historical primitive counts must be nonnegative integers. Use integer **OUTS**, not ambiguous baseball IP notation. Blank values remain unknown. Inputs may describe multiple minor/overseas competitions separately; the validator does not aggregate or translate them into MLB rates.

History and context cannot add players absent from their origin's registered dated population. History event seasons must precede the target origin, and event dates cannot exceed source as-of dates. Source dates must precede the relevant cutoff. Outcome-stat columns, orphan identities, duplicate records, future events and unsupported metrics are rejected. Age is calculated only from a supplied birth date and the origin cutoff.

### Chronological controls

- Population origins can cover 2016–2026; development fold origins are 2019–2025.
- Historical default cutoffs are **January 1 of each origin year**, a conservative research snapshot rather than a claimed historical draft date.
- Documented overrides may extend through February 28 in this conservative contract. Later historical snapshots require a revised contract and explicit chronology review.
- 2026 retains the user-confirmed **March 24, 2026** effective date and is evaluation-only.
- Each fold's training population origins are strictly earlier than that fold and never include 2026.
- 2020 is retained as observed; 2021 is explicitly retained. No automatic season-length rescaling or removal of unfavorable seasons occurs.
- Numeric/roster coverage counts and a minimum of three prior population origins are structural checks only. **No labels are joined and no fold is automatically fit-ready.**

Future fitting must first freeze origin-specific populations/features, then join eligible historical MLB labels with existing discrepancy exclusions. Missing rows in an actuals export are not automatically negative participation labels or zero workload: negative labels require verified complete MLB appearance coverage. Participation probability and conditional MLB workload must be evaluated separately and composed; skill-rate labels need eligible positive denominators. Existing disputed-component exclusions also apply to MLB-prior features, without cross-source backfill. Level/league/park/era translation, sample-size controls, coherent outputs, fallback rules and uncertainty need historical evaluation. Do not copy the 2026 universe backward to construct historical cohorts. Do not choose components using the reviewed 2026 evaluation.

### Validate supplied inputs later

Copy/fill the templates as local input files while preserving the exact column order. Do not fill them from the 2026 actual-participant list. For example, once the files exist:

```powershell
python validate_entry_branch_inputs_v1_14.py --population "config/entry_population.csv" --history "config/entry_history.csv" --context "config/entry_context.csv"
```

Optional `--cutoffs` supplies documented overrides. Default output is `outputs/entry_branch_intake_v1_14`, with a complete verified backup. Intake can also be attached to a new source build using `--branch-population`, `--branch-history`, `--branch-context` and `--branch-cutoffs`. Existing source builds are never overwritten.

The resulting historical fold plan remains `fit_ready=false` until the later training-label/feature/model implementation is completed and tested. Validated metadata is not evidence of forecast performance.

## Send for review

After the main build, send:

1. `draft_sources_build_report.json`
2. `reconciliation_audit_report.json`
3. `adjustment_maxima.csv`
4. `nfbc_coverage_priorities.csv`

If the audit fails, include `reconciliation_audit_failures.csv`. The entry-branch templates and intake report identify the next data-collection work without changing any current forecast.
