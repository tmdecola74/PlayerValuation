# Discrepancy register and modeling-label policy v1.0

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`. This adds new scripts/configurations and a self-contained evidence snapshot. It does not edit the SQLite/DuckDB warehouses, actuals importer output, Statcast files, or earlier review releases.

The delivered build is already under `outputs/discrepancy_register_v1_0`. Its complete folder has a separately hash-verified copy under `backups`.

## Results

- 32 stable case IDs retain every original FanGraphs, terminal, scoring-rule and admitted-evidence count.
- 12 hit/type rows document FanGraphs play text agreeing with MLB but differing from FanGraphs exported game/season totals.
- 3 rows document the González/Underwood single-versus-error difference between providers.
- 17 PA/TBF rows retain their original review status. This hit investigation does not newly certify their prior evidence or classify them as missing pitches.
- User-confirmed historical years are recorded separately from the original workbook's 2026 values. This is user confirmation, not an independently archived timestamp. Converted score cells are not used.
- 128 direct/dependent metric exclusions are listed. They are exclusions, not 128 independent discrepancies or deleted players.

## Source policy

**Primary season labels: the frozen FanGraphs actual-counts reference.** It supplies a consistent component source and the existing season/baseline comparison contract. This choice does not claim that FanGraphs is correct in every disputed play. MLB game logs/scoring feeds and reconstructed Statcast remain independent evidence and research comparison layers.

For every registered discrepancy, exclude the affected metric and dependent targets from fitting and scoring. Do not substitute MLB values into a FanGraphs target row. Keep source counts visible in the register; do not convert exclusions to zero. Benchmarks against Steamer/OOPSY and the homegrown model must use the same label source, exclusions and common eligible player pool.

Examples:

| Disputed component | Labels excluded by dependency | Labels not automatically excluded |
|---|---|---|
| Hitter H / hit types | The disputed counts, derived singles where affected, AVG/OBP/SLG/OPS/ISO/BABIP as dependencies require | Independent HR, R, RBI, SB counts unless directly disputed |
| Hitter PA | PA and K%, BB%, HR/PA, SB/PA | Unaffected standalone counting targets |
| Pitcher H | H and WHIP | ERA if ER and OUTS are otherwise eligible |
| Pitcher TBF | TBF and K%, BB%, K-BB% | Per-inning rates if their own components are eligible |

All model labels must come from the primary snapshot. Rate labels are recomputed from its components, with integer OUTS for pitching exposure. Zero-denominator rates stay missing. Missing counts stay missing; true zero saves remain zero. Unknown label metrics fail closed. For any joint/coherent target vector, if one component is excluded, exclude that vector through `resolve_bundle`.

The 2015–2025 training cutoff is enforced. 2026 is available only under an explicit holdout-evaluation purpose. Changing labels or exclusion policy after viewing results requires a new version and fresh reporting; do not tune source choices to favor a model.

## Important scope

`modeling_labels_v1_0.py` is a consumable label-resolution API. `build_discrepancy_register_v1_0.py` creates the register and exclusion plan without network requests. The complete actuals-reference Parquet files are on your PC, not in this delivery. Their expected hashes are pinned from the existing reconciliation report. This build therefore publishes **no full training-label table** and does not rewire or rerun a training model.

A candidate unregistered metric is eligible under this discrepancy policy only; that does not certify global readiness. Coverage, unknown events, identity checks, feature cutoffs, historical measurement availability and IP/ER reconciliation retain their own gates. The 128-row exclusion plan covers affected player-season roles. It is not a complete table of all labels.

## Commands

From the project root:

```powershell
python -m unittest discover -s tests -p "test_discrepancy_register_v1_0.py" -v
python build_discrepancy_register_v1_0.py --output "outputs/discrepancy_register_v1_0_local"
```

Choose a new output path for another run. Existing folders are rejected. Each successful run copies all supplied evidence into the new output, verifies a complete backup, and records input/output hashes. Case IDs use season, role, MLBAM ID and metric, so they remain stable across releases; classifications, policy and evidence snapshots are versioned separately.

Start review with `discrepancy_register.csv`, `label_exclusion_plan.csv`, `modeling_label_policy.json` and `build_report.json` in the output folder. `register_events.jsonl` records the initial transition from the prior reconciliation status. The original `UNRESOLVED_DIFFERENCE` status remains preserved; documented source disagreement does not become an exact numeric match.

## API contract for the next training build

Read the actual counts from the verified file itself; do not pass counts from another source alongside a copied hash. Keys are season, player_type and MLBAM ID. `counts` contains nonnegative integer primitive components for that player-season, using OUTS rather than baseball-format IP.

```python
import json
from modeling_labels_v1_0 import verified_reference_sha256, resolve_label, resolve_bundle

policy = json.load(open("outputs/discrepancy_register_v1_0/modeling_label_policy.json"))
register = json.load(open("outputs/discrepancy_register_v1_0/discrepancy_register.json"))
reference_hash = verified_reference_sha256(
    "data/actuals_reference_v1_0_min0ip/actual_counts.parquet", policy
)
# Load `counts` for the requested player-season from that same verified reference.
# result = resolve_label(season, role, mlbam_id, metric, counts,
#                        register, policy, reference_hash)
# A training consumer must check result['eligible'] before using result['value'].
```

The next integration step is to load the full frozen reference on the PC, call this API for each target and write the eligible/masked label dataset with the policy version and source hashes. Neither physical source is overwritten.
