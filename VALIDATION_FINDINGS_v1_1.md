# V1.1 validation findings

March 24, 2026 effective inputs. Frozen five-seed v1.0 outputs supplied by the user were compared with v1.1 on seeds 20260324-20260328, every draft seat, both strategies. This is 150 matched drafts and 75 paired strategy comparisons, with no broader seed search or outcome-based tuning.

| Check | Frozen v1.0 | V1.1 |
|---|---:|---:|
| Legal target active lineups | 150/150 | 150/150 |
| Target lineups below 950 projected IP | 68 | 0 |
| Single-active-player absence failures | 149/3450 | 0/3450 |
| All constraint gates passed | Not published as a combined metric | 150/150 |

Only the first three rows should be used for direct gate-count comparisons; v1.0 did not publish one combined coverage/IP count. V1.1's combined gate independently checks full legal active assignment, at least 950 projected active IP and legal restoration after each single active absence.

| Strategy | V1.0 mean IP | V1.1 mean IP | V1.0 mean historical percentile | V1.1 mean historical percentile |
|---|---:|---:|---:|---:|
| Value | 1270.2 | 1244.0 | 63.1% | 63.3% |
| Category | 828.9 | 971.3 | 59.5% | 56.6% |

Minimum active IP across the 75 value rosters: 951.010105. Minimum category IP: 950.11082. The feasibility guard made at most nine mandatory picks for value and five for category; there were no recorded completion failures. The pitching solver maximizes raw SGP subject to the innings floor rather than treating innings as another category bonus.

Separate reports show mean active saves of 15.47 for value and 100.98 for category. Feasibility does not mean category balance: the value strategy still has a saves weakness, while category retains lower total benchmark utility. Reserve IP/saves are reported as a separate inventory and never used to inflate active results. No claim of strategic superiority or real-world win probability is justified.

Validation: ten v1.1 tests passed, including a brute-force pitching optimality check and a case where ten pitchers sum to 1000 IP but no legal nine can reach 950. All seven frozen v1.0 tests passed. Independent checks verified all 112500 chronological picks, 750 unique assets per draft, 50 assets per team, 150 legal constrained target lineups with 27 reserves each, component-derived category totals and all 3450 replacement checks. In the two v1.0 pilot seeds with full pick logs available locally, all 20700 picks before the round-24 guard matched the frozen market paths exactly.

Input hashes, including frozen v1.0 script and user baseline results, stayed unchanged. Complete result-folder backup contents were compared byte-for-byte. The supplied outputs are under outputs/dc_roster_simulator_v1_1_validation. The README explains equivalent local input serializations and reproduction on the user's PC.

Remaining scope: the after-absence gate ensures eligibility, not an additional 950-IP guarantee for each absence lineup. There is no simultaneous-absence model or weekly deployment model. This version repairs roster feasibility; it does not convert full-season reserve inventory into usable season production.
