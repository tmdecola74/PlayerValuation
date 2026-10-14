# Draft Champions calibration and values v1.1

No separate SGP workbook needs to be calculated manually. The supplied workbooks have been converted and the full valuation run completed.

Extract this small package into `D:\JonAPythonClass\pycharm\PlayerValuation`, preserving config, data and tests folders. It updates build_league_valuations_v1_0.py to support historical rate references and a Draft Champions-specific output label. The existing generic NFBC 15-team profile and its behavior are unchanged, and its ten tests still pass.

The ready-to-use inputs are in `data/valuation_inputs_dc_v1_1`. They were generated from your exact uploaded workbooks. Scripts do not overwrite those workbooks or the reference warehouse. Dependencies are the previously delivered valuation_math_v1_0.py, calibrate_league_sgp_v1_0.py, and verified consensus/warehouse helpers. openpyxl is used only for read-only Excel imports.

## Reproduce on your PC

```powershell
python -m unittest discover -s tests -p "test_dc_valuation_inputs_v1_1.py" -v
python build_dc_values_v1_1.py
```

The second command uses your default migrated DuckDB warehouse and writes `outputs/nfbc15_dc_values_2026_v1_1`. It also preserves a separately backed-up `.engine` intermediate and a full final backup containing the ADP comparison. Existing folders are never overwritten. Use --output with a new folder for later reruns.

The package also includes the results actually generated here under `results_dc_2026_v1_1`. Open `player_values_with_adp.csv` for the main ranking. No rebuild is needed simply to inspect those supplied-data results.

## Workbook parsing and SGP calibration

The standings workbook contains these COMPLETE 15-team leagues:

| Season | Leagues | Team rows |
|---|---:|---:|
|2023|323|4,845|
|2024|334|5,010|
|2025|342|5,130|
|Total|999|14,985|

The sheet-level overall rank and percentile summaries are not league standings points and are excluded. Each team row is grouped by season and league name; all fifteen draft positions must be present once. The repeated H headings are explicitly separated into hitter H and pitcher hits allowed.

IP such as 1365.2 is baseball innings, meaning 1365 plus 2/3, not 1365.2 decimal innings. AVG is rebuilt from hitter H/AB, ERA from 9*ER/IP, and WHIP from (hits allowed+BB)/IP. All original published rate values are retained. The 2025 sheet has coarser, observed two-step rounding, so reconstruction preserves component precision instead of treating displayed rounding ties as identical team performance. Published-versus-recomputed checks allow only the documented half-unit rounding bounds.

For each complete league, each category is independently sorted best-to-worst and regressed against ordinal rank points 15 to 1. This yields a statistic-units-per-point slope, not a reconstruction of official category points with every tie or penalty. League slopes are averaged within each season; the combined calibration is an equal-weight mean of the THREE annual slopes. The larger 2025 field therefore does not receive a larger season weight.

For ERA/WHIP slope fitting, an entire league is excluded if any team has fewer than 950 IP. The workbook has raw rates but not the special minimum-innings penalty points, so the importer does not fabricate those points. There are 400 such league-seasons excluded from RATE slope fitting. All 999 leagues remain in counting-stat and AVG fitting. The 950 threshold is an explicit conservative calibration filter recorded in the JSON. Other historical scoring assumptions or a different threshold should be a separately labeled sensitivity version.

Historical reference AB/H use all teams. Pitcher reference IP/ER/hits allowed/BB use the complete leagues eligible for ERA/WHIP calibration. Per-team component means are calculated per season, then averaged equally across seasons. Reference AVG/ERA/WHIP are derived from those averaged numerators and denominators, not averaged individual rates. These references replace the projection-pool iterative reference ONLY in this DC profile. All calibration years are before 2026.

The converted files include:
* dc_historical_team_stats.csv: every original team row with component-precise rates, published rates, and decimal/baseball innings.
* dc_annual_sgp_slopes.csv: all ten SGP factors for 2023, 2024 and 2025.
* dc_rate_penalty_exclusions.csv: which complete leagues were excluded from rate fitting and why.
* nfbc15_dc_sgp_calibration.json: combined slopes, annual slopes, complete league fits, and historical reference components.
* dc_input_audit.json: source-file hashes, counts, mapping methods, and full preparation backup.

## Preseason eligibility and identity mapping

The ADP workbook has 978 NFBC assets. Its Player ID is an NFBC identifier, not an MLBAM ID. Names are converted from Last, First format, normalized deterministically for accents/punctuation/suffixes, then mapped within player type. Existing MLBAM-anchored warehouse identities are preferred to unresolved RotoWire-only duplicate identities; those duplicate warehouse records are NOT merged or changed.

Official team abbreviations are normalized explicitly, including ARZ/ARI and CWS/CHW. A unique anchored name/type can bridge an offseason team disagreement only when that name/type identifies one NFBC asset too; the separate match method and original team are retained. Same-name NFBC assets such as the two Max Muncys and two Jacob Wilsons are not collapsed. The unmatched HOU Jacob Wilson is kept in review rather than mapped to the ATH player.

970 NFBC assets mapped, producing 971 role rows because Shohei Ohtani has UT and P eligibility. Both Ohtani roles share ONE canonical asset. The roster optimization chooses one role and never adds full-season hitting and pitching projections together. Weekly two-way switching option value is not modeled by this static valuation.

Eight source assets remain unmatched and are listed in nfbc15_dc_eligibility_review.csv. Twelve additional mapped assets fail usable projection component/exposure checks. All twenty are listed in results/unvalued_adp_watchlist.csv. Unvalued does NOT mean a zero projection or zero fantasy value. No forecast is invented for them.

## Draft Champions profile and output

config/valuation_nfbc15_dc_v1_1.json is specifically the 15-team, 50-player Draft Champions format: 23 active and 27 reserves per team, or 345 active slots and 405 league reserve selections. The original 30-player Main Event/auction profile is untouched. DC standings are not silently presented as a Main Event calibration.

The DC projection floors are PA>=1/AB>=1 and IP>=1 to preserve deep projected reserve candidates. This is an explicit deeper-pool policy; complete required category components are still mandatory. The first run values 958 unique players, selects 345 active assets and 405 reserves, and has no reserve-pool shortfall.

Draft rank uses SGP ABOVE REPLACEMENT directly, not ADP or the hypothetical dollar split. The optimizer and exact multi-position replacement chains remain unchanged. The rank is an initial static valuation, not a specific team's complete draft plan. Reserve ordering does not model weekly lineup coverage, injuries, call-up probability, category needs, or market pick availability. No individual team's minimum-IP guarantee is claimed.

The DC format is a snake draft without auction currency. Dollar columns are renamed auction_equivalent_value and scaled_marginal_value and are illustrative reference values only. The $260/67%-hitter allocation policy is retained solely for that reference; it does not determine DC draft rank. The active auction-equivalent pool sums to $3,900, with reserve dollar values zero in that allocation.

ADP is added only AFTER projections, SGP, replacement levels and ranks have been calculated. ADP_minus_value_rank is market ADP minus model rank; positive means the market typically selects later than this model's rank. This is a comparison, not a command to select that player at the model rank. The snapshot contains twenty drafts for most players and smaller samples for some late players.

## Results

* player_values_with_adp.csv: main unique-player ranking, ADP, NFBC ID, chosen role, eligibility, category contributions, replacement margin and all projection statistics.
* player_values.csv: the same valuation data before the ADP comparison.
* starter_assignments.csv: the legal aggregate 345-player active allocation.
* reserve_rankings.csv: ranked outside assets, with 405 reserve flags.
* unvalued_adp_watchlist.csv: eight unmatched and twelve mapped-but-unvalued NFBC assets.
* positional_replacement.csv: optimized slot thresholds.
* rate_reference.json: historical reference rates and team AB/IP.
* valuation_audit.json: budget/count reconciliation, complete final backup, hashes and methods.

## Reimport your source workbooks later

Save copies of the two workbooks in your project folder, then run to a NEW input folder:

```powershell
python prepare_dc_valuation_inputs_v1_1.py --adp "DCADP-pre2026.xlsx" --standings "2023-2025 DC Category Stats - Overall.xlsx" --output "data/valuation_inputs_dc_v1_1_rerun"
python build_dc_values_v1_1.py --inputs "data/valuation_inputs_dc_v1_1_rerun" --output "outputs/nfbc15_dc_values_2026_v1_1_rerun"
```

The importer uses your already prepared consensus in `outputs/nfbc15_valuation_inputs_v1_0/consensus` for canonical mapping. Override --consensus if that folder is elsewhere. Every newly prepared input folder and final output folder receives a timestamped full backup with file hashes compared.

Eight new importer tests and all ten original valuation tests pass. Full real-data checks confirm unique canonical and NFBC assets, 345 active slots, 405 reserve selections, exact auction-equivalent budget, original input hashes unchanged, and complete backup file hashes matching. No 2026 actual statistics are used to calibrate these values.

Official DC rules consulted: https://nfc.shgn.com/rules/2587 (50 rounds, 27 reserves, no free-agent pickups, and minimum-IP scoring treatment).
