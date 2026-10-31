# V1.2 validation: requested roster split

Reused all five original seeds (20260324-20260328), all 15 draft seats and both strategies. No broader seed search, outcome-based tuning or changes to v1.0/v1.1.

- 150/150 rosters satisfy the requested ranges. All happened to select 23 pitchers and 27 hitters; 22/28 is also legal and unit-tested.
- 150/150 satisfy the normal active lineup's 950 projected IP minimum.
- All 3450 single-active-player absence checks restore legal positional assignments.
- No active or bench statistics were invented for market-only assets.
- 112500 chronological picks, unique assets, target pick-by-pick type caps, final counts, category totals and complete backups were independently verified.
- 15 v1.2 tests passed. The frozen 10 v1.1 and 7 v1.0 tests also passed.

| Strategy | Mean active saves in v1.1 | Mean active saves in v1.2 | V1.2 rosters meeting 70.33 saves |
|---|---:|---:|---:|
| Value | 15.47 | 15.47 | 0/75 |
| Category | 100.98 | 100.98 | 70/75 |

The requested type split does NOT improve the value baseline's active saves in this static model. It caps reserve pitchers and shifts late reserve picks toward hitters, but the same nine active pitching choices retain their saves/volume tradeoff. This is evidence against assuming roster counts alone solve category balance. Reserve saves remain separate projection inventory, not usable incremental team saves.

The user's confirmed saves 80th-percentile figures of 71 for 2024 and 66 for 2025 match the supplied historical data. 2023 is 74, giving the unchanged prior-season equal-year target of 70.33 for the 2026 preseason exercise. The user's reported 2026 result of 67 is documented as retrospective context only and is not used in draft selection. See SAVES_BENCHMARK_PROVENANCE.json.

Next modeling work must address reliever selection/active pitching utility and weekly deployment. Do not claim the new roster split itself improves projected saves, real standings, or winning probability. All comparisons remain synthetic static-roster experiments.

Output files are delivered under outputs/dc_roster_simulator_v1_2_validation. The local baseline summary used for comparison was reconstructed from the user's uploaded v1.1 comparison report, preserving exact per-seed/seat/strategy IP and percentile values. On the user's PC the default reads the original v1.1 team_results.csv directly. Equivalent reviewed local identity/eligibility inputs may differ in serialization hashes; their player assets and roles are unchanged.
