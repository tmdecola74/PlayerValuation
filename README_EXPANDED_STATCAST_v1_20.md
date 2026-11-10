# PlayerValuation v1.20 — expanded Statcast features and availability audit

Extract this ZIP into the existing PlayerValuation project root. It adds new versioned files; it does not replace accepted projections or v1.17–v1.19 research. Existing dependencies are required: DuckDB, the installed `lagged_statcast_v1_0.py` / `lagged_io_v1_0.py`, and the standalone I/O and v1.16 diagnostic modules already used by the project. No new package is required.

```powershell
python -m unittest discover -s tests -p "test_expanded_statcast_v1_20.py" -v
python expanded_statcast_v1_20.py
```

Default input: `outputs/standalone_lagged_features_v1_0`. The builder uses **its saved `source_windows.json`**, not the current active download ledger or a new live selection. Its existing source date configuration and original raw CSV/Parquet/schedule hashes are verified. All configured frozen source windows must be present. Default output: `outputs/expanded_statcast_v1_20`, plus a verified complete backup under `backups`. Existing outputs are rejected; use a new `--output` path for repeat runs.

No data is downloaded and no source files, accepted matrix, forecasts or model selections are changed. Source seasons stop at 2025; 2026 source pitches and target outcomes are never opened. The builder uses frozen prior-history player populations from `training_features.parquet` and `holdout_features.parquet`, not target-season participant lists. Original references and scoring exclusions are preserved.

## Derived features

34 overall metric definitions are emitted for hitters and pitchers. Pitcher-side batted-ball/contact statistics describe results **allowed**. Hitter-side release/movement measures describe the pitches faced, not a hitter's own physical pitching attributes. These are candidate data, not approved model features or claims of incremental value.

| Family | Output metrics |
|---|---|
| Contact/discipline | `whiff_pct`, `chase_pct`, `zone_contact_pct`, `outside_zone_contact_pct`, `contact_pct`, `zone_swing_pct`, `outside_zone_swing_pct`, `swinging_strike_pct`, `called_strike_plus_whiff_pct` |
| Batted-ball types | `gb_pct`, `ld_pct`, `fb_pct`, `popup_pct`, `air_pct` |
| Launch angle | `launch_angle_mean`, `launch_angle_sd`, `launch_angle_p10`, `launch_angle_p50`, `launch_angle_p90`, `launch_angle_8_32_pct`, `launch_angle_below_zero_pct`, `launch_angle_ge50_pct` |
| Pull/elevation proxies | `pull_proxy_pct`, `pulled_air_proxy_per_bbe`, `pulled_air_proxy_per_air`, `pulled_barrel_proxy_per_bbe`, `pulled_barrel_proxy_per_barrel` |
| Release/movement | `release_speed_mean`, `release_spin_rate_mean`, `release_extension_mean`, `pfx_x_mean`, `pfx_z_mean`, `release_pos_x_mean`, `release_pos_z_mean` |

Pitch-type tables add `pitch_type_usage` plus release/movement, whiff/chase/contact, CSW, GB/AIR and mean launch angle. A separate `UNKNOWN` pitch-type bucket is retained; known-type usage is not renormalized to hide missing classifications. Usage sums to one across all observed type buckets before eligibility masking. Pitch types are not encoded into a fitted vocabulary; a future experiment must learn any encoding only from earlier folds.

Some measures deliberately duplicate existing features for audit: whiff/chase, outside-zone swing (= chase), velocity, spin and extension. `feature_contract.json` names their existing equivalents. Do not interpret the count of 34 as 34 genuinely new independent signals.

K%−BB% is not reconstructed from physical pitch terminal events in this build. Continue using eligible reconciled prior actual SO/BB with PA or TBF from the actuals branch; this avoids undoing the scoring-aware label work. No official outcome counts or model labels are computed here.

## Definitions and controls

All rates are fractions, not 0–100 percentages. Launch angles are degrees. Velocity is mph; spin is rpm; extension, release positions and `pfx` movement are feet. `pfx_z` is raw catcher-perspective vertical movement, **not induced vertical break**. Movement is not handedness-normalized. Tracking-era codes are inherited from the original lag builder; they do not certify cross-era comparability.

- Whiff = recognized misses / recognized swings. Contact = recognized non-miss swings / recognized swings. Contact includes fouls/foul tips and bunt contact, following the inherited event sets. Missing/unknown descriptions are audited; these are not newly certified exact Savant leaderboard definitions.
- Zone contact = in-zone recognized contact / in-zone recognized swings. Outside-zone contact uses corresponding outside-zone swings. Zone codes 1–9 are inside; 11–14 outside; 10/missing/invalid are unknown.
- Chase and outside-zone swing = recognized swings outside / recognized pitches outside. Zone swing uses the in-zone denominator. Swinging-strike and CSW use recognized recorded-pitch denominators; CSW numerator is called strikes plus inherited misses. These are archive-based research definitions, not official denominator certification.
- GB/LD/FB/PU use valid classified in-play (`type=X`) batted balls. AIR = LD + FB + PU. Missing classifications are not grounders.
- Launch-angle mean, population standard deviation and continuous 10th/50th/90th percentiles use finite angles in [-90,90]. The 8–32 band is inclusive; below-zero is `<0`; high-angle is `>=50`. A mean alone does not describe the distribution.
- Barrels use existing `launch_speed_angle=6`, with 1–6 recognized as measured batted-ball classifications. No estimated barrel formula is introduced.
- Pull uses `atan2(hc_x − 125.42, 198.27 − hc_y)` in degrees, with positive forward distance, a ±45° fair cone and a 15° pull boundary. Right-handed negative angles and left-handed positive angles beyond that boundary are classified as pulled, using **each pitch's batter stance**, including switch hitters.

**Pull metrics are coordinate-based research proxies, not certified matches to Savant's official pull classifications.** Their denominators include only jointly measured relevant events. Pulled-air per BBE uses direction+type-classified BBE; per air conditions on measured air balls. Pulled-barrel per BBE uses direction+barrel-classified BBE; per barrel conditions on measured barrels. Missing coordinates, stance or required classifications remain unknown. Reconcile against official player-season exports before a model adopts these proxies. No `hit_location` guess substitutes for coordinates.

Fixed, non-optimized eligibility controls: minimum 30 measured BBE, 100 swings, 50 conditioned zone swings, 100 pitches for pitch/release measures, or 10 measured barrels for the conditional pulled-barrel rate. Measurement coverage must be at least 50%. Invalid physical ranges become missing and are counted in `numeric_value_audit.csv`; extreme values are not silently clipped into plausible measurements.

`denominator` records the actual statistic's observed denominator. `coverage_observations` / `coverage_opportunities` record measurement coverage separately; a rare conditioning event is not itself missing data. Conditional air/barrel proxies require broad joint BBE measurement coverage, and discipline coverage is limited by recognized description coverage. `raw_value` remains in the season audit even below controls, but the model-facing `value` becomes null. Raw values/numerators are withheld from lag add-ons so an estimator cannot trivially bypass masking. No imputation, shrinkage, scaling, model fitting or outcome-driven thresholds are applied.

## Outputs

| File | Purpose |
|---|---|
| `expanded_feature_report.json` | Integrity, scope, counts and limitations |
| `schema_availability.csv` | Optional field presence by source year, in original CSV headers versus Parquet schemas |
| `numeric_value_audit.csv` | Finite measurements, fixed-range exclusions and original extrema |
| `feature_availability_by_season.csv` | Eligible player coverage, sample and measurement counts by year/role/metric |
| `training_lag_availability.csv`, `holdout_lag_availability.csv` | Availability in the unchanged prior-history forecast populations |
| `transition_2021_availability.csv` | Explicit 2021 source-year availability; no season removed |
| `player_season_context.csv` | Physical pitches, unknown descriptions, BBE/classification and direction sample counts |
| `bat_tracking_field_inventory.csv` | Detected bat-related Parquet fields, data types, non-null and finite counts; no inferred squared-up features |
| `supplemental_download_plan.csv` | Bat-tracking exports and official batted-ball references to obtain or validate |
| `expanded_features_season.csv` / `.parquet` | Detailed overall source-season features and audit values |
| `pitch_type_features_season.csv` / `.parquet` | Detailed source-season pitch-type profiles and usage |
| `training_expanded_features.parquet` | Long-format lag-1/2/3 feature add-on for historical target years |
| `holdout_expanded_features.parquet` | Separate long-format prior-history add-on for target 2026 |
| `feature_contract.json` | Frozen definitions, existing-feature aliases and future model-use restrictions |

`RAW_ONLY_SCHEMA_RECOVERY_CANDIDATE` means the original CSV header contains a field absent from Parquet. It does **not** prove nonmissing usable raw values. Investigate a versioned raw recovery before downloading again. `PARQUET_AVAILABLE` likewise means schema presence; finite/eligible counts determine actual usability. An empty bat inventory is valid, not an error.

The long lag table preserves each target/role/MLBAM ID/lag/metric even when source history is absent. Values stay null with `NO_SOURCE_PLAYER_SEASON`; no target outcomes expand the population. Raw source seasons beyond 2025 are skipped before their file paths are accessed. Pitch-type season profiles are supplied separately; fitting a stable pitch-type lag representation is later research.

## Supplemental bat tracking

The builder does not fetch anything or invent squared-up values from exit velocity. First inspect stored CSV/Parquet field availability. If verified swing/contact counts and competitive-swing definitions are missing, use Baseball Savant's Bat Tracking leaderboard to export:

1. Separate hitter and pitcher player-level regular-season CSVs for 2023, 2024 and 2025. Use all available players rather than qualified-only if the export allows it; retain the applied minimum and selection filters.
2. MLBAM IDs, competitive swing and contact counts, squared-up counts/rates per contact and per swing, bat speed, fast-swing rate, blasts and swing length where available.
3. Exact season/date interval and player-role scope. **2023 starts in the second half**, so do not label it full-season coverage. Different metric denominators/coverage must remain explicit.
4. Source URL/filter settings, original unedited CSV, actual download timestamp and file hash. Historical event dates and present retrieval dates are different facts. Do not claim archived preseason availability.

Keep these exports in a new supplemental-input folder, separate from accepted references. This build provides the plan; it does not yet import or join them. For the current 2026 forecast exercise, source seasons stop at 2025; no 2026 outcomes should select features. A future 2027 build can separately register 2026 feature history.

Official references checked during development:
- https://baseballsavant.mlb.com/csv-docs — pitch fields, units and batted-ball classifications.
- https://baseballsavant.mlb.com/leaderboard/batted-ball — AIR and official batted-ball profile definitions.
- https://baseballsavant.mlb.com/leaderboard/bat-tracking — bat-tracking history and distinct swing/contact rate denominators.

## What to return

Please attach `expanded_feature_report.json`, `schema_availability.csv`, `feature_availability_by_season.csv`, `training_lag_availability.csv`, `bat_tracking_field_inventory.csv`, and `supplemental_download_plan.csv`. Keep the large feature CSVs/Parquets locally. Their production availability results determine the next focused historical experiment; accepted workload/saves/holds and projection sources stay frozen.
