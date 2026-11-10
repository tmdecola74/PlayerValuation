# Projection release audit — v1.12.0

This build is a read-only diagnostic companion to the accepted v1.11.1 projections and disclosed v1.11.2 evaluation. It does not fit models, revise choices, repair consensus values, alter exclusions, add players to forecasts, or change saves/holds. 2026 remains previously reviewed evaluation data.

## Install and run

Extract the ZIP into the existing outer project directory:
`D:\JonAPythonClass\pycharm\PlayerValuation`

Keep the v1.11.1 and v1.11.2 scripts, tests, configs and outputs installed. All files in this package have new names. Dependencies are the project's existing DuckDB/NumPy installation; tests reuse prior delivered synthetic fixtures.

```powershell
python -m unittest discover -s tests -p "test_projection_release_audit_v1_12.py" -v
python audit_projection_release_v1_12.py
```

The tests create small historical model fixtures, so fitting messages during tests are expected. **The audit command itself does not fit or select models.** It prints progress for the three requested investigations.

Output: `outputs/projection_release_audit_v1_12`

The complete output folder receives a hash-verified backup under `backups`. Existing output directories are never overwritten. An interruption cleans the unpublished staging folder. Original input trees remain unchanged.

Default inputs:

| Argument | Folder/file |
|---|---|
| `--run` | `outputs/projection_release_2026_v1_11_1` |
| `--evaluation` | `outputs/projection_evaluation_2026_v1_11_2` |
| `--labels` | `outputs/training_labels_v1_0` |
| `--matrix` | `outputs/standalone_lagged_features_v1_0` |
| `--warehouse` | `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb` |

Use these flags only if local folder names differ. The audit verifies frozen files, the evaluation's binding to the release, label-reference fingerprints, and the precise training-label and feature versions used by the release. Moving inputs or substituting a regenerated file can break those bindings; do not edit fingerprints to bypass a mismatch.

## 1. Consensus component provenance

The audit uses the original `source_hitter_consensus.json`, `source_pitcher_consensus.json`, and `source_metric_provenance.csv` preserved in v1.11.1. It examines valid and quarantined rows; it does not rebuild or replace the established consensus.

Every primitive weighted mean is replayed from its recorded contributor values and normalized weights. Missing/derived provenance and a snapshot/provenance mismatch are explicit statuses. Counts are never invented to make an identity balance.

For hitters it examines:

- `H - (1B + 2B + 3B + HR)` as an equality.
- `PA - (AB + BB + HBP + SF + SH)` as a nonnegative budget. A positive remainder is not automatically an error: the listed terms may omit PA events such as catcher interference.

For pitchers it checks the `H - HR` nonnegative bound. It also independently checks snapshot AVG/OPS and ERA/WHIP against their components and positive denominators.

Where contributor evidence is complete, the observed equation difference is decomposed into three conserving terms:

1. **Source-pool effect:** moving each original weighted mean to the common positive-weight contributor intersection, retaining its own weights and renormalizing there.
2. **Weight effect:** moving those common-pool means to the leading metric's common-pool weights (H or PA for hitter equations).
3. **Within-source residual:** the component discrepancy remaining inside those individual sources under the same common weights.

These three terms sum to the observed difference within numerical tolerance. This is an algebraic description, **not a recommended reconciliation rule or causal attribution**. No common pool means no fabricated decomposition. Source rows include available source record IDs and the recorded component values/weights.

A fixed **0.001-stat magnitude band** separates rounding-scale differences from larger ones for review. It is not a new validity tolerance, does not prove rounding, and never releases a quarantined player. Original export precision has not been verified. Quarter-/half-hit differences can be traced to a contributor or weighting pattern, but their explanation must come from the evidence rather than their size alone.

## 2. Rate-stat exposure cohorts

The audit reads frozen player comparisons from v1.11.2 and eligible actual labels from the same frozen reference. Released homegrown/consensus values are checked against the projection freeze. No projected value is adjusted using actual exposure.

| Rate metrics | Disjoint actual-exposure bands | Additional cumulative reports |
|---|---|---|
| AVG, OPS | PA <100; 100–299; 300–499; ≥500 | PA ≥100; PA ≥300; all positive PA |
| ERA, WHIP | IP <20; 20–<40; 40–<100; ≥100 | IP ≥20; IP ≥40; all positive IP |

Positive exposure and eligible rate/exposure labels are required. Missing/excluded exposure never becomes zero. Boundary values enter the next band (e.g. exactly 40 IP enters 40–<100). Rate errors are in their original units, not multiplied by exposure.

Each comparison group uses identical eligible players within metric/cohort: homegrown alone, consensus alone, homegrown/consensus matched, Steamer matched, OOPSY matched, and all sources matched. Coverage counts and membership hashes accompany scores. A group with no matching players remains n=0 with null errors.

The disjoint bands also report their shares of paired players and squared error. Their membership counts and squared-error sums must reconstruct the corresponding all-positive-exposure pool. Cumulative cohorts overlap; do not add them together or average their RMSEs.

Actual PA/IP define **retrospective diagnostic cohorts only**, never preseason predictors or model-selection gates.

## 3. Participants absent from the homegrown universe

The missing population is independently reconstructed from eligible 2026 released-metric labels and frozen homegrown identities, then required to match the existing evaluation's missing-player file and count. On the supplied production evaluation that count is 298; the script does not hardcode 298.

The review checks all prior reference seasons available in the frozen training labels, the original 2026 feature population, opposite-role history, and warehouse MLBAM ownership. Classifications include:

- Feature row present but forecast absent: forecast-coverage review.
- Prior same-role reference row within 2023–2025 but no feature row: feature/source-coverage review.
- Older same-role history only: returner outside the three-year lag window.
- Other-role history/homegrown presence only: role-transition review.
- No prior reference history: cold-start candidate.

Identity status is a separate field: uniquely mapped canonical MLBAM, ambiguous/nonunique ownership, or no warehouse MLBAM mapping. Thus an identity problem is not silently called a debut. Positive prior G/PA/OUTS evidence is reported separately from mere reference-row existence; zero-out pitchers are not automatically treated as having no history.

**No prior history in this reference is not proof of an MLB debut.** History before the reference window, minor-league/prospect information, and an official career/debut reference are not supplied. Debuts/prospect status remain uncertified. The audit names available canonical identities and preserves MLBAM IDs where names cannot be resolved. It does not guess by name or generate missing-player projections.

## Output files

| File | Use |
|---|---|
| `projection_audit_report.json` | Scope, frozen-status flags, counts, diagnostic limitations |
| `consensus_driver_summary.csv` | Compact grouping of quarantined equation cases by scale, provenance status, pool/weight differences and arithmetic result |
| `consensus_equation_audit.csv` | Player-level equation differences and conserving decomposition |
| `consensus_source_residuals.csv` | Contributor-level values, weights, source differences and available record IDs |
| `consensus_primitive_replay.csv` | All primitive contributor replay results and unavailable provenance statuses |
| `consensus_ratio_audit.csv` | Snapshot rates versus component-derived rates |
| `exposure_cohort_scores.csv` | Matched n, MAE/RMSE/bias and squared-error sums by metric/cohort/source |
| `exposure_error_partition.csv` | Disjoint exposure-band shares of players and squared errors |
| `exposure_cohort_pairs.csv` | Exact player-level cohort comparisons |
| `exposure_cohort_coverage.csv` | Missing exposure, nonpositive exposure, available forecasts and common pools |
| `exposure_cohort_outliers.csv` | Largest 10 absolute errors within each metric/cohort/group/source |
| `missing_universe_review.csv` | History, identity, feature membership and classification for each absent participant |

`consensus_driver_summary.csv` groups **equation rows**, so one quarantined hitter can appear under both H and PA equations. The report's quarantined-player count remains separate.

## Send for review

Please send these four files from `outputs/projection_release_audit_v1_12`:

1. `projection_audit_report.json`
2. `consensus_driver_summary.csv`
3. `exposure_cohort_scores.csv`
4. `missing_universe_review.csv`

`exposure_error_partition.csv` is also useful for reviewing low-exposure influence. Detailed source residuals and player pairs remain local until needed.

The audit is research evidence only. Any subsequent consensus reconciliation requires an explicit component policy preserving originals. Any new forecasting candidate must be developed/selected on historical folds, with 2026 kept as disclosed evaluation data.
