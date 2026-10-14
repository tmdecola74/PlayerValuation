# Architecture and next stages

## Storage responsibilities

| Layer | Storage | Responsibility |
|---|---|---|
| Original evidence | data/raw/<hash>/<filename> | Byte-identical source archive |
| Normalized bulk records | data/parquet/<dataset>/season=<year>/<version>/ | Typed immutable snapshots |
| Catalog and queries | data/database/player_valuation.duckdb | Active-version registry and views |
| Modeling features, future | data/parquet/features/ | Reproducible cutoff-specific features |
| Review/export | audit/, output/ | Human-readable diagnostics, later Excel/UI |

The active-version registry is essential: a glob over all historical versions would double count replaced datasets. Each catalog view includes only registered active paths. v1.0 uses one file per modest projection/actuals source; raw pitch ingestion should be a separate streaming path.

## Planned data contracts

| Dataset | Grain/key | Implementation |
|---|---|---|
| projection_hitter/pitcher | player × target season × system, active snapshot | v1.0 |
| actual_hitter/pitcher | player × season, season totals | v1.0 |
| player_identifier | identifier system × external ID → canonical player | Next; verified crosswalk, no name-only auto merges |
| statcast_pitch | game_pk × at_bat_number × pitch_number | Planned; season/month partitions, regular season filter |
| hitter_statcast_season | MLBAM × season × cutoff | Planned |
| hitter_bat_tracking_season | MLBAM × season × cutoff | Planned; coverage flags by year |
| pitcher_arsenal_season | MLBAM × season × pitch type × cutoff | Planned |
| team_context_season | MLB team ID × season × cutoff | Planned |
| team_bullpen_usage | MLBAM × team × season × cutoff | Planned; retain team stints |
| team_running_tendency | team × season × speed group × cutoff | Planned |
| model_features | player × target season × prediction cutoff | Planned |

## Download design

Download pitch-level data in resumable date windows. Record date boundaries, request parameters, game type, download time, hashes, schema and row counts. Write temporary files, validate keys/completeness and publish only successful windows. Deduplicate overlapping windows by pitch key. Keep a failed-window ledger, bounded retries and pacing. Regular-season games and postseason must remain distinct. Empty windows need explicit successful completion records. Source corrections should create new versions.

Pitch-level files often contain batted-ball events already; use a derived batted-ball view before introducing redundant storage. Keep original movement units and document derived inches/sign conventions. Preserve measurement-era flags for historical comparisons, including 2026 location/zone changes; verify exact source definitions during adapter implementation.

## Modeling guardrails

The goal is to improve projection residuals, not assume every metric adds value. Join prior-season Statcast/team context to next-season preseason projections using verified availability dates. Use rolling season holdouts, not random player-row splits. 2024–2026 supplies few independent year transitions; avoid claiming robust validation from sample size alone. Do not tune on the final holdout.

Keep talent, playing time, team context and bullpen role separate. Save opportunities and blown saves need source-specific definitions; team holds are events and can occur multiple times in a game. Save and hold shares are not interchangeable. SB opportunities require an explicit eligible-state denominator; attempt rate must be conditioned on player speed/opportunity to estimate manager/team tendency. Use projected upcoming-team environment, not leaked target-season actual wins.

## Next work on the PC

1. Inspect local inventory and configure every 2024–2026 projection/actuals input.
2. Run ingestion and review reconciliations; confirm season-total rows, rates and innings conventions.
3. Import a verified FanGraphs–MLBAM crosswalk with conflicts/unmapped audit.
4. Add resumable Statcast download/streaming ingestion and derive player/arsenal aggregates.
5. Add team/role/opportunity tables with clear denominators and availability dates.
6. Construct consensus and leakage-safe residual datasets; backtest incremental value.

No migration of a prior warehouse is performed without reading its real schema and mappings first.
