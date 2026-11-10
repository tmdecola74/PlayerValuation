# v1.11.1 — consensus component exception handling

The v1.11 tests passed, but the production consensus contains at least one row where H differs from 1B + 2B + 3B + HR beyond the existing tolerance. The fixture had consistent hit components and did not expose this export failure. This patch adds regression coverage and a row-level exception policy rather than changing any source counts.

## Install and run

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`. All delivered Python/test filenames are new. Retain the original v1.11 files, its installed config, and the prior standalone releases.

```powershell
python -m unittest discover -s tests -p "test_projection_release_v1_11_1.py" -v
python build_projection_release_v1_11_1.py
python evaluate_projection_release_v1_11_1.py
```

New default folders:

- `outputs/projection_release_2026_v1_11_1`
- `outputs/projection_evaluation_2026_v1_11_1`

The failed v1.11 run does not need to be deleted. New outputs receive complete hash-verified backups under `backups`. Existing-output guards and interrupted-stage cleanup remain active. Use the new evaluator with the new release.

## What changes

An inconsistent **consensus** row is quarantined. Other valid rows and all accepted homegrown forecasts export normally. The source row is never silently repaired, zero-filled, or substituted with homegrown data. The same policy covers conflicting pitcher IP/OUTS, invalid count bounds, and the existing consensus component validation failures. Homegrown coherence and frozen-forecast validation remain strict; a homegrown error still stops publication.

The original source consensus JSON files and source metric provenance are copied unchanged into the new release, as before. No warehouse, earlier projection release, consensus input, model choice, saves forecast, holds forecast, or actuals reference is modified.

New audit artifacts in the release folder:

| File | Contents |
|---|---|
| `consensus_component_exceptions.csv` | Player identity, validation message, H, summed hit types, H minus hit types, PA component checks, original metrics, disposition |
| `quarantined_consensus_records.json` | Complete original source records for quarantined players |

Quarantined rows are omitted from coherent consensus projection tables, consensus valuation adapters, and consensus evaluation forecasts. They remain visible in `exceptions.csv`; affected draft assets receive `QUARANTINED_INCOHERENT_SOURCE_COMPONENTS` in `draft_pool_coverage.csv` instead of an inaccurate missing-projection reason. Homegrown tables remain independent.

`projection_release_report.json` now reports source consensus row counts and quarantine counts. A nonzero quarantine count produces `EXPORTED_WITH_CONSENSUS_QUARANTINE_REVIEW_REQUIRED`, explicitly signaling a partial usable consensus export. The evaluator carries this count and disclosure forward. Matched consensus scores use the remaining valid consensus rows; comparison coverage and matched membership hashes remain explicit. Steamer/OOPSY matched comparisons remain separate and use their existing published metric policies.

This patch **does not establish why** a production row differs. Mixed source/component pools or source inconsistencies require the new diagnostics and original metric provenance to investigate. No tolerance was loosened and no preferred total was chosen.

## Outputs and next review

The projection/evaluation table names and units are unchanged from v1.11. In the new release folder, open `homegrown_hitters_2026.csv` and `homegrown_pitchers_2026.csv` for the accepted homegrown projections. The corresponding consensus tables contain only valid rows. The stable loader is now imported from `projection_release_v1_11_1`:

```python
from projection_release_v1_11_1 import load_valuation_source
players = load_valuation_source(
    "outputs/projection_release_2026_v1_11_1", "homegrown"
)
```

Please send `consensus_component_exceptions.csv` and `projection_release_report.json` after building. Those identify the affected players and magnitude of the differences without needing another broad data export.

2026 remains previously reviewed evaluation data. All model choices remain frozen and historical-only.
