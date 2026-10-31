# Pilot findings

Two seeds x all 15 seats x two strategies = 60 drafts and 30 paired comparisons. March 24, 2026 is the confirmed effective date. This is an engineering pilot and synthetic roster-construction experiment, not a 2026 outcomes backtest.

| Measure | Value baseline | Category candidate |
|---|---:|---:|
| Drafts | 30 | 30 |
| Legal 23-player active lineup | 30/30 | 30/30 |
| At least 950 projected active IP | 30/30 | 0/30 |
| Mean projected active IP | 1,239.8 | 795.4 |
| Mean historical category percentile | 62.4% | 60.2% |
| Mean categories at/above historical 80th percentile | 3.77 | 4.87 |

The category candidate fails the innings guard. Its extra categories above the benchmark must not be presented as a successful strategy. Neither its percentiles nor the baseline's prove competitive success. The baseline's legal/IP feasibility is a necessary check, not validation of weekly performance.

All 900 team rosters were checked for legal active eligibility. Every draft has 750 unique assets and 50 per team, with correct alternating snake order. Target lineups all have 14 hitters and 9 pitchers, plus 27 reserves. Repeating seed 20260324/seat 1 reproduced the full paired pick logs exactly. Active category totals were independently recomputed from assignments. Seven unit tests passed.

Single-player absence stress: 1,380 checks, 74 failures to restore all active slots. Value rosters had 50 catcher-loss failures and one 2B-loss failure; category rosters had 22 catcher-loss failures and one 1B-loss failure. These are individual loss cases, not 74 distinct rosters. Multi-position reserve eligibility is reported without double-counting assets in assignments. This reveals why a pure static-value bench needs explicit coverage constraints.

All source inputs remained unchanged. Complete final pilot outputs including stress tests and eligibility/IP gates were backed up and compared byte-for-byte. Local reproduction uses the user's equivalent corrected eligibility and 17-player watchlist; byte hashes may differ from the derived local audit inputs.

Next engineering step: enforce minimum projected active innings and configurable reserve catcher/infield/outfield coverage during drafting, then repeat paired tests against this frozen baseline. Weekly pitcher/hitter deployment and absence scenarios are still required before recommendations should rely on reserve production. These findings were not used to tune the category coefficients in this delivery.

The pilot results are delivered under outputs/dc_roster_simulator_pilot_v1_0. Start with strategy_summary.csv, simulation_audit.json, and single_absence_stress.csv.
