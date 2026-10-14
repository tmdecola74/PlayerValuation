# Stage 3 delivery — 2026 consensus

The generator has already run. Start with
outputs/consensus_2026_v1_0/audit/consensus_report.md, then open
hitter_consensus.csv and pitcher_consensus.csv in the parent output folder.

* 4,376 canonical hitter rows and 5,587 canonical pitcher rows.
* All 21,813 selected 2026 source projections retained as contributors/metadata:
  6,101 matched source records and 15,712 unmatched source records included.
* Equal weights by available player/statistic, with configurable source and
  per-base-statistic overrides. Zero participates; missing is never zero-filled.
* AVG, OBP, SLG, OPS, ERA, WHIP and additional rates use exact consensus
  components. QS and saves plus holds are included.
* IDs, source record IDs, recorded names/teams and source contributors preserved.
* 1,350 unavailable metric values explicitly audited. No invalid source values.
* Source disagreement, low exposure, limited coverage, mixed component pools and
  differences between derived and supplied source rates are audited.
* Original files and warehouse unchanged; input SHA-256 verified.
* 35 tests passed, including all source player IDs/records preserved, independently
  recomputed component rates and base weights, zero/missing handling, configurable
  overrides, no actual-value substitution, and full original-file integrity checks.

Many exports round counts for players projected for very little playing time.
Their component-derived rates can differ from supplied source talent rates.
Review audit/derived_vs_source_rates.csv and player_coverage.csv before valuation.
The earlier blend backtest averaged source rates directly, so this coherent rate
reconciliation has not yet received a separate held-out performance comparison.
Formula correctness is tested; improved rate forecast accuracy is not claimed.

No player pool cuts, player valuations, auction dollars or live-season updates
are applied in this stage. Source spread is not a calibrated confidence interval.

Run a new build in a new folder:
python build_consensus_projections_v1_0.py --output outputs/consensus_2026_run2
