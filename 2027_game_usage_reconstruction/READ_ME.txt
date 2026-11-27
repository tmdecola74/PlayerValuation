GAME-LEVEL USAGE RECONSTRUCTION AND HITTER PARTICIPATION CERTIFICATION

{
  "status": "RECONCILED_WITH_EXPLICIT_EXCEPTIONS",
  "years": [
    2019,
    2020,
    2021,
    2022,
    2023,
    2024,
    2025,
    2026
  ],
  "completed_games": 17904,
  "batting_stat_rows": 395620,
  "all_MLB_game_team_player_rows": 527198,
  "pitching_outings": 154798,
  "label_comparisons": 77749,
  "remaining_label_mismatches": 3,
  "lineup_slot_exceptions": 0,
  "historical_cohort_player_seasons": 10951,
  "historical_certified_MLB_nonappearances": 4868,
  "historical_certified_zero_PA_exposure": 6701,
  "historical_zero_PA_with_MLB_appearance": 1833,
  "game_files_bound_to_original_hashes": 17904,
  "source_files_changed": false,
  "baseline_changed": false,
  "adoption_guards_changed": false,
  "models_fitted": false,
  "forecast_errors_scored": false,
  "proposed_label_overlay_applied": false
}

SCOPE
All cached completed MLB regular-season games for 2019–2026 were read and hash-bound to the original season certificates. Schedules reconcile to standings team-game counts. Every game validates official pitcher lists/credited appearances and outs, player batting counts to team batting totals, and initial batting-order slots. No new statistics were downloaded and no original label, model, guard or forecast was edited.

GAME DEFINITIONS
Annual source G counts credited MLB games, including pitching-only games. Batting-only gamesPlayed is a different quantity. Canonical hitter_game_usage files use the union of credited batting and pitching game/team/player records and retain BATTING_G, CREDITED_PITCHING_G and PITCHING_ONLY_G. The original batting-only extraction is preserved in batting_stat_game_usage files. PA and other batting counts are not altered. A pitching-only appearance contributes G but no PA. Zero PA is not proof of no MLB appearance. Starting batting-order code and substitute order are retained separately; final team battingOrder is not treated as the starting lineup.

PITCHER SPLITS
Each credited outing has gamesStarted 0/1 and observed outs. Seasonal GS+GR=G and START_OUTS+RELIEF_OUTS=OUTS hold exactly. IP is decimal OUTS/3, with original baseball innings notation retained per outing. Zero-out/no-pitch credited appearances remain. Mixed-role innings are split from observed outings rather than season IP divided by GS.

HITTER COHORT AND ZERO CERTIFICATES
For target Y, freeze exact IDs with positive eligible MLB PA in Y-4 through Y-1. This matches the baseline history window, intentionally including pitchers with prior batting exposure. It is not a complete prospective MLB roster or a prospect-arrival universe. A certified MLB nonappearance requires complete season coverage, no credited MLB appearance and no conflicting eligible source label. Zero-PA exposure is certified separately for players who pitched or otherwise appeared without PA. Proposed overlays are separate and are NOT applied to baseline/training labels. Future model design must distinguish primary hitter opportunity from secondary pitcher batting records, without silently changing the registered comparison sample.

HISTORICAL VERSUS 2027 HISTORY
2019–2025 tables are historical adapter/certification evidence. The 2026 season is published in separate quarantine/history tables for 2027 inputs only. No 2026 forecast errors were calculated or used. Last60 features use the last60 completed games of each source team, retain trades/game identities and store source season; they become predictors only for later target years. Actual target-year roles, availability or workloads must never become preseason features.

LIMITATIONS
Retrospective source vintages remain. Games/starts/lineup position are observed usage, not evidence of health or a guaranteed future roster role. Historical preseason depth charts are still required for chart-dependent validation. This reconstruction does not fit a workload model or demonstrate adoption improvement. Remaining source discrepancies, if any, are explicit and quarantined; no target count is silently repaired.

NEXT BUILD
After reviewing remaining exceptions and the appearance-versus-positive-PA label definition, register the executable usage-transition model and support/fallback rules before historical scoring. Keep the current baseline and rejected workload/Statcast methods unchanged.


INDEPENDENT CHECKS AND EXCEPTION DISPOSITION
All eight seasons passed an independent check of unique game/team/player keys, exactly nine credited initial batting-order starters per team/game, valid appearance flags and exact pitching outing partitions. Josh Walker's credited zero-out appearance is preserved. Danny Jansen's 2024 game 746942 contains separate Toronto and Boston records; both are retained. The frozen annual source still reports 94 G versus 92 reconstructed G, so his 2024 hitter usage remains quarantined. No unsupported correction is applied.

The two 2026 PA differences are localized to Ryan Jeffers in game 823732 (April 3) and Sean Keys in game 824784 (September 23). Each official boxscore reports 4 PA while AB/BB/HBP/SF/SH/CI account for 3. The original season labels match the smaller annual tally. Archived event traces are supplied as evidence, but no unverified cause or substitute PA is assigned. These player-seasons remain quarantined from the new usage inputs; 2026 is history-only, never a scoring target.

Annual and last60 files carry source_reconciliation_status. historical_source_reconciled_season_usage.csv excludes the one unresolved historical player-season. It is a source-reconciled dataset, not authorization to fit or change the comparison sample silently. The next model contract must explicitly define shared supported memberships, role-state labels, secondary pitcher batting treatment and fallbacks before scoring.
