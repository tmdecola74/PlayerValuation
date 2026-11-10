# v1.13 — reconciliation candidate and preseason coverage

This release tests one explicit arithmetic policy and freezes a preseason universe. It preserves all original consensus values, accepted homegrown exports, earlier releases and actuals references. **It does not adopt a replacement source, fit a new skill/workload model, or use 2026 outcomes to determine inclusion.** The separate evaluator retains exposure cohorts and treats 2026 as previously reviewed evaluation data.

## Install and run

Extract into the outer project folder:
`D:\JonAPythonClass\pycharm\PlayerValuation`

Keep the installed v1.11.1, v1.11.2 and v1.12 scripts, tests, configs and frozen inputs. All delivered filenames are new. The project's existing DuckDB/NumPy dependencies are sufficient.

```powershell
python -m unittest discover -s tests -p "test_preseason_coverage_v1_13.py" -v
python build_preseason_coverage_v1_13.py
python evaluate_preseason_coverage_v1_13.py
```

The tests build small prior-release fixtures, so their fitting messages are expected. The production builder and evaluator do not fit models.

Default output folders:

- Build: `outputs/preseason_coverage_v1_13`
- Evaluation: `outputs/preseason_coverage_evaluation_v1_13`

Each receives a complete hash-verified backup under `backups`. Existing output folders are not overwritten; unpublished stages are removed on interruption. The builder validates the original projection freeze and the precise training-label, feature, warehouse and reviewed draft-input versions. If an upstream input has changed, produce/review the appropriate upstream release rather than editing fingerprints.

| Build argument | Default |
|---|---|
| `--run` | `outputs/projection_release_2026_v1_11_1` |
| `--labels` | `outputs/training_labels_v1_0` |
| `--matrix` | `outputs/standalone_lagged_features_v1_0` |
| `--warehouse` | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |
| `--draft-inputs` | `data/valuation_inputs_dc_v1_1` |
| `--policy` | `config/consensus_reconciliation_v1_13.json` |

The evaluator uses the frozen new build, `outputs/projection_evaluation_2026_v1_11_2` as `--source-evaluation`, and the same frozen labels. To repeat with a new output name, pass that new build folder to the evaluator's `--run` as well.

## Fixed consensus policy: version 1.13.0

The new source is explicitly named `CONSENSUS_RECONCILED_CANDIDATE_V1_13`. The original usable consensus, original published reference, and homegrown source remain distinct. There is no automatic blending, fallback or adoption.

For a complete hitter hit-type vector:

- Keep published H, 2B, 3B and HR.
- Derive `1B = H - 2B - 3B - HR` when the difference exceeds numerical epsilon.
- Reject a material negative derived single; do not clip it to zero.
- Reject an absolute singles change exceeding **1 hit**, subject to numerical epsilon.

For a complete PA budget:

- Keep published AB, BB, HBP, SF and SH.
- If their sum exceeds published PA beyond numerical epsilon, raise candidate PA to that sum.
- Reject an increase exceeding **1 PA**, subject to numerical epsilon.
- Leave a positive PA remainder intact; the listed terms can omit PA events such as catcher interference.

Any material hitter count repair requires the recorded weighted means to replay, a common contributor pool, and matching normalized component weights. Missing provenance, a pool/weight discrepancy, excessive change, or an unresolved component constraint leaves the row quarantined. `numerical_epsilon` is 1e-9; machine-precision cancellation retains an already nonnegative original single rather than clipping a calculated negative.

These one-stat guards are **fixed research policy assumptions**, not proof that a source difference is rounding and not values optimized against 2026 outcomes. Changing the policy JSON is rejected; a policy revision needs a distinct version. No model-selection gate compares policy variants here.

Rates are recomputed from candidate components. Published hitter H/AB/extra-base hits/counting categories and pitcher workload/counts, including saves and holds, remain anchored. Complete deterministic H-from-hit-types and OUTS/SO aliases already supported by the prior schema remain available; missing primitives are never zero-filled. Incomplete components leave their dependent rates missing. The candidate exports only the prior versioned metric schema; unexported original statistics remain in the full original snapshot.

The full component ledger records original field presence, original/candidate values, exact numerical deltas, change flags, reason, player identity and policy fingerprint. This includes changes to derived rates. A rejected row remains in the case/quarantine files and full original snapshot; it is not silently assigned zeros.

### Build artifacts

| File | Purpose |
|---|---|
| `original_consensus_records.json` | Complete original records and every original metric value |
| `original_metric_provenance.csv` | Unchanged original source values, weights and provenance |
| `candidate_projection_records.json` | Coherent available candidate rows |
| `reconciled_consensus_hitters_2026.csv` / `.parquet` | Separate candidate hitter table |
| `reconciled_consensus_pitchers_2026.csv` / `.parquet` | Separate candidate pitcher table |
| `reconciliation_component_ledger.csv` | Every exported component, including unchanged values |
| `reconciliation_adjustments.csv` | Changed components only |
| `reconciliation_cases.csv` | Per-player decision and provenance checks |
| `remaining_consensus_quarantine.csv` | Cases the policy cannot resolve |
| `policy_frozen.json` | Exact fixed policy |
| `homegrown_hitters_2026.csv` / `.parquet` | Byte-for-byte copies of the accepted hitter exports |
| `homegrown_pitchers_2026.csv` / `.parquet` | Byte-for-byte copies of the accepted pitcher exports |

The two `reconciled_consensus_*_valuation_candidate.json` files use the existing valuation record shape. They are explicit candidate inputs, not default replacements. Their basic readiness gate covers known canonical identity, category components and at least 1 AB/IP. League position eligibility, roster constraints and Yahoo-specific OPS/QS/SV+HLD completeness still require the downstream league checks. No SGP values or draft recommendations are recalculated here.

## Preseason universe and coverage

The builder unions only information available in the permitted source layers:

1. The user-confirmed 2026 preseason projection snapshot.
2. Reviewed NFBC preseason ADP/eligibility assets.
3. Frozen homegrown forecasts and prior-history feature identities.
4. Historical reference identities from seasons 2015–2025.
5. Optional dated preseason evidence described below.

It never reads the target-season label table or the 298-player retrospective missing list during construction. Historical-only identities remain visible but are explicitly marked as having no current preseason evidence; universe membership does not mean active-roster status. The evaluated actual-only population cannot append new universe rows.

Identity uses canonical IDs/unique MLBAM links; names are display fields, not matching rules. Unmapped NFBC assets remain separate NFBC identities. Multi-position/platform assets stay listed separately in asset coverage, while a canonical player's hitter and pitcher roles remain separate universe rows. No current Yahoo position feed is inferred from NFBC eligibility.

Preseason strata distinguish prior MLB role history, older-history returner candidates, other-role review, unresolved identities and unclassified cold-start candidates. **A player with no prior MLB reference history is not automatically called a prospect, international arrival or debut.** Those categories require evidence. The layer supplies coverage and review status, not a new playing-time or skill forecast for that player.

### Optional dated evidence

A first build works without additional files. It creates:

- `preseason_classification_review.csv`: identities needing class/returner/role review.
- `preseason_evidence_TEMPLATE.csv`: an empty exact-schema input template.

To add documented classifications or additional preseason identities, copy the template to a local input file and fill it. Supported `preseason_class` values are `prospect`, `international_arrival`, `returner`, `established_mlb`, and `unknown`.

Each row requires 2026, hitter/pitcher role, an exact canonical or MLBAM identity, effective date, evidence-as-of date, source, source record ID, evidence reference and a date basis. Both dates must be **on or before 2026-03-24**. Allowed date bases are `ARCHIVED_AS_OF_CLAIM` and `USER_CONFIRMED_PRESEASON_EFFECTIVE`. Canonical/MLBAM conflicts, future dates, duplicates and outcome-stat columns are rejected. Conflicting declared classes remain review cases.

Date compliance validates metadata claims; it does not independently certify an archive or prove when a retrospectively retrieved file existed. Do not populate this input from 2026 results or from the retrospective missing-player list.

Example rerun after creating a properly documented input file:

```powershell
python build_preseason_coverage_v1_13.py --preseason-evidence "config/preseason_universe_evidence_v1_13.csv" --output "outputs/preseason_coverage_v1_13_with_evidence"
python evaluate_preseason_coverage_v1_13.py --run "outputs/preseason_coverage_v1_13_with_evidence" --output "outputs/preseason_coverage_evaluation_v1_13_with_evidence"
```

Additional build artifacts:

| File | Purpose |
|---|---|
| `preseason_universe.csv` / `.json` | Frozen population, inclusion reasons, history, class evidence and source coverage |
| `draft_asset_coverage.csv` | NFBC asset-level homegrown/candidate coverage |
| `preseason_coverage_exceptions.csv` | Preseason-supported identities missing homegrown forecasts or requiring identity/class review |
| `preseason_classification_review.csv` | Cold-start, returner and role classifications requiring evidence |
| `dated_preseason_evidence_used.csv` | Explicit dated evidence actually used |
| `preseason_coverage_build_report.json` | Counts, source/date disclosures, immutable homegrown hashes and candidate-only status |

## Separate disclosed 2026 evaluation

The evaluator verifies the candidate and universe freeze before opening eligible 2026 labels. Existing label exclusions remain intact; missing actuals are not treated as zero participation.

It compares:

- Accepted homegrown forecasts.
- Previously usable, coherent original consensus rows.
- **Published original consensus reference**, including quarantined rows as an evaluation-only reference with their original published values. It is not certified coherent or offered as a valuation source.
- The new reconciled candidate.
- Frozen Steamer and OOPSY forecasts from the original evaluation.

`published_vs_reconciled_matched` compares the same eligible players directly before/after arithmetic changes, including recovered quarantined rows. `original_vs_reconciled_common` is limited to the old usable consensus pool. Candidate-all scores can also reflect coverage expansion; do not mistake that population change for a pure accuracy improvement.

Named source pairs and homegrown/candidate/benchmark triple pools preserve identical membership within each metric/cohort. Pairs and triples may differ in membership from one another.

The same fixed AVG/OPS PA bands and ERA/WHIP IP bands from v1.12 remain, with positive exposure, boundary checks, cumulative cohorts and a conserving disjoint-band squared-error partition. Actual exposure is a retrospective diagnostic only. No 2026 result adopts the policy or selects a model.

| Evaluation file | Purpose |
|---|---|
| `matched_scores.csv` | All-eligible per-metric MAE/RMSE/bias with matched memberships |
| `matched_pairs.csv` | Streamed exact player-level comparisons, including cohort pairs |
| `exposure_cohort_scores.csv` | Retained fixed rate-stat cohorts |
| `exposure_error_partition.csv` | Band shares of players and squared error |
| `comparison_coverage.csv` | Eligible/cohort/source/matched counts |
| `universe_coverage_evaluation.csv` | Post-freeze actual-participant coverage, with no retroactive additions |
| `original_missing_homegrown_coverage.csv` | Whether the original missing-homegrown cases were represented by permitted preseason evidence |
| `preseason_coverage_evaluation_report.json` | Evaluation disclosure, coverage and no-adoption/no-modification flags |

## Research boundary and next review

No new skill or workload candidate is introduced in this build. Any later fitted candidate must construct its population and preprocessing inside historical folds; do not reuse the 2026 universe as a historical population. Keep the multiyear SB candidate and prior pitcher experiments as separate research evidence. Accepted saves/holds and homegrown forecasts stay frozen.

After running, send:

- `preseason_coverage_build_report.json`
- `preseason_coverage_evaluation_report.json`
- `matched_scores.csv`
- `exposure_cohort_scores.csv`
- `remaining_consensus_quarantine.csv`

The adjustment ledger and preseason classification review support the next targeted investigation if needed.
