# NFBC 15-team league valuation engine v1.0

Extract into `D:\JonAPythonClass\pycharm\PlayerValuation`, preserving config and tests folders. This adds five scripts and two profiles; it does not replace prior builders or change the SQLite reference. It reuses the existing build_consensus_projections_duckdb_v1_0.py, evaluate_historical_projection_accuracy_duckdb_v1_0.py, and warehouse_readonly_v1_0.py from the verified backend-adaptation build. DuckDB is needed when reading the migrated catalog.

## First commands

```powershell
python -m unittest discover -s tests -p "test_league_valuations_v1_0.py" -v
python build_league_valuations_v1_0.py --prepare-inputs
```

This creates `outputs/nfbc15_valuation_inputs_v1_0` containing coherent consensus statistics, eligibility and SGP input templates, exclusions, and input requirements. The complete folder is backed up with every file hash verified. The default read-only source is `data/historical_duckdb_v1_0_bulk/player_valuation.duckdb`; override --warehouse to point to the SQLite reference if needed. DuckDB integrity verification also checks migration Parquet hashes, and the external payloads are fingerprinted before and after the run.

Once authoritative eligibility and SGP calibration are supplied:

```powershell
python build_league_valuations_v1_0.py
```

Outputs go to `outputs/nfbc15_values_2026_v1_0` with a complete timestamped backup. Existing output folders are never overwritten; reruns require --output with a new name. --eligibility and --calibration override the profile's input paths.

## Profile and source choices

config/valuation_nfbc15_v1_0.json defines 15 teams, C x2, 1B/2B/3B/SS x1, CI/MI x1, OF x5, UT x1, P x9, and seven bench slots. Pitchers are unrestricted P slots. Both snake draft rankings and $260-per-team active-auction-equivalent values are produced. The seven reserve rounds are separate from the auction budget. The 67% hitter budget share is an editable initial allocation policy, not an empirical calibration or optimizer result. This is distinct from the $1,000 in-season FAAB budget.

config/valuation_consensus_v1_0.json preserves the established consensus source and component weights. No Statcast adjustments were validated, so none are applied. This build does not select weights using 2026 outcomes.

Minimum projection floors are PA>=100 and AB>=50 for hitters, IP>=20 for pitchers. All category numerators and denominators must be present and valid. Excluded candidates are reported, never given invented zero statistics. Change these thresholds in the profile when a deeper prospect/bench pool is needed.

The general roster and budget code can use a different team count with a matching calibration profile, but v1 supports standard 5x5 only. Yahoo OPS/QS/SV+HLD requires separately specified rate/category rules; this version rejects such a profile rather than silently applying 5x5 weights.

NFBC official rules consulted:
* https://nfc.shgn.com/rules/2571 (15 teams, 14 hitters/9 pitchers, seven bench slots)
* https://nfc.shgn.com/faq/baseball (2026 eligibility based on 2025 games, plus platform rulings)
* https://nfc.shgn.com/rules/2755 (active $260 auction budget and separate reserve draft)

## Position eligibility

The warehouse has no position columns. Supply an authoritative archived 2026 preseason NFBC eligibility export or ADP export containing positions. Do not use current 2026 eligibility that includes ten-game in-season gains. The user's earlier MEADP.csv or DCADP.csv may be useful if their columns include the official preseason positions.

Option A: complete the prepared nfbc15_eligibility_TEMPLATE.csv and save it as `data/valuation_inputs/nfbc15_eligibility.csv`. Required populated fields are player_id, player_type, positions, eligibility_season=2026, eligibility_basis_season=2025, and source. Name and MLBAM IDs are provided as references. Blank positions are omitted from the value pool. Pitcher eligibility must also be explicit, avoiding unsupported assumptions about two-way players.

Option B: import an official CSV after inspecting its headings. Example with explicitly supplied column names:

```powershell
python import_valuation_eligibility_v1_0.py --csv "your_preseason_NFBC_export.csv" --name-column "Player" --position-column "Position" --season 2026 --basis-season 2025 --source "NFBC preseason 2026 eligibility"
```

If that export has MLBAM IDs, add --mlbam-column with the exact heading. The importer prioritizes that identity anchor. Without it, it accepts only a unique normalized name within the supplied player type, records the method, and retains ambiguous or unmatched rows in a review CSV. It never infers a position from a name. User-supplied source and basis year declare that this is a preseason eligibility export; the importer cannot independently validate the date or authority of an arbitrary local CSV.

Position tokens may be separated with /, comma, semicolon, | or spaces. DH maps to UT, LF/CF/RF to OF, SP/RP to P. CI and MI are roster slots, not natural eligibility tokens. A 1B/OF player can fill 1B, CI, OF, or UT. A DH-only player can fill UT only.

One canonical player is one draft asset, even if both hitter and pitcher projections exist. The assignment chooses at most one eligible role for that asset. NFBC's official eligibility file should determine whether a two-way projection role belongs in the player pool. Formats with separate platform identities for two roles require an explicit platform-specific identity model.

## SGP calibration

The user's sgpcalcs.xlsx was confirmed to be 2026 in-season calibration for the FAAB system. It is intentionally excluded from this 2026 preseason valuation build.

Supply completed 2024 or 2025 15-team 5x5 final category standings. A rank grid is sufficient; actual team H/AB/IP components are not required for the slope fit. Each league-season must include ranks 1–15 once, with points=16-rank and these columns:

season,league_id,rank,points,R,HR,RBI,SB,AVG,W,SV,K,ERA,WHIP

Each category's rank grid must be independently sorted best-to-worst (ERA/WHIP ascending, other categories descending), as in the earlier SGP workbook. These rows are category rank order, not necessarily the same fantasy team across columns. AVG is a fraction such as .250. Missing, unordered, zero-slope, incomplete or 2026/future grids are rejected.

```powershell
python calibrate_league_sgp_v1_0.py --standings "data/valuation_inputs/historical_rank_grid.csv" --source "Completed NFBC 2025 15-team league standings" --full-season
```

The output is `data/valuation_inputs/nfbc15_sgp_calibration.json`. It fits statistic against ordinal rank points within each complete league-season and averages slope magnitudes equally across league-seasons. ERA/WHIP slopes retain signed diagnostic fits but use positive magnitudes in the favorable-direction contribution formulas. The output preserves source, seasons, league fits, and the standings-file hash. This is a full-season calibration; an in-season grid cannot be rescaled automatically.

Alternatively, provide already-calibrated positive slopes in the prepared calibration JSON template with named source, completed seasons before 2026, full_season=true, matching team count and target year. No placeholder slope is automatically accepted.

## Coherent category math

The consensus is a weighted available-source mean of base components, using the established builder's exact provenance and exclusions. AVG=H/AB; OBP=(H+BB+HBP)/(AB+BB+HBP+SF); SLG=(1B+2*2B+3*3B+4*HR)/AB; OPS=OBP+SLG; ERA=9*ER/IP; WHIP=(H+BB)/IP. Missing components or nonpositive denominators remain unavailable. Mixed source/component pools retain the existing consensus audit.

Counting category SGP is the projected count divided by that category's statistic-units-per-standing-point slope.

Linear rate SGP uses excess numerators at a COMMON projected full-roster team denominator:

* AVG: (H - reference_AVG * AB) / (team_AB * AVG_slope)
* ERA: (reference_ERA * IP - 9 * ER) / (team_IP * ERA_slope)
* WHIP: (reference_WHIP * IP - H_allowed - BB) / (team_IP * WHIP_slope)

A low ERA/WHIP contributes positively; exposure weights the contribution. This avoids treating equal rates at 20 IP and 180 IP as equivalent. These contributions are a linear approximation at the stated common team denominator, not additive exact changes in a team rate.

The reference starts from an exposure-ranked eligible projection seed. The engine solves the league roster, recomputes weighted reference rates and per-team AB/IP from that selected active pool, and repeats until they agree. On the converged selected active pool, each rate category's summed excess contribution is zero. Cycles or nonconvergence stop publication rather than selecting an arbitrary iteration. Projection pool references use no target actuals.

For an exact roster swap, team_category_impact_v1_0.py recomputes BOTH team numerators and denominators:

```powershell
python team_category_impact_v1_0.py --roster-json "your_active_roster.json" --add-player-json "your_add_player.json" --drop-player-id "canonical_player_id" --calibration "data/valuation_inputs/nfbc15_sgp_calibration.json" --output "outputs/exact_category_swap.json"
```

Roster JSON is a list of objects with player_id, player_type, and metrics, as in the consensus JSON; the add JSON is one such object. Supply active players only. IP must be decimal innings from the warehouse, not baseball .1/.2 notation. The helper computes statistical contribution, not an automatic legal-lineup or FAAB recommendation.

## Replacement and draft/auction values

The assignment maximizes summed raw category SGP while filling all 345 league active slots and allowing only one slot per canonical player. It is an exact min-cost-flow optimization with natural, flex, and multi-position eligibility.

For a selected player, SGP above replacement is the loss in the optimal full-roster objective if that player is removed. The optimizer accounts for all resulting position swaps and the best outside replacement. This is more accurate than independently sorting catcher, OF, CI and UT lists and counting one multi-position player twice.

For an undrafted player, the marginal inclusion gain is the loss versus the optimal roster when forcing that canonical asset into the pool. The engine chooses the best eligible role and explicitly preserves a nonpositive outside-pool value. Positional thresholds are marginal entry thresholds from the optimized residual roster network. If there is no replacement path for a selected player, the eligibility pool is too shallow and publication stops.

The $3,900 aggregate active-auction budget first covers $1 for each of 345 slots. Hitter and pitcher discretionary budgets are allocated in proportion to positive marginal SGP within each group, using the editable 67/33 allocation. Largest-remainder cent rounding preserves the league and group budgets exactly. These are valuation amounts, not executable bids or a promise that any particular team can draft every recommended player for $260.

Draft rank orders the unique active assets by auction-equivalent value, then the undrafted pool by its budget-scaled marginal utility. The next 105 outside assets are marked reserve selections. They are a league-wide reserve ranking, not team-specific bench needs, and receive $0 in the ACTIVE auction allocation. Marginal replacement values are joint roster opportunity costs, not additive utilities for a specific team.

## Output and audit

* player_values.csv: unique-player draft ranks, eligibility, chosen role/slot, all projection statistics, per-category SGP, raw SGP, replacement margin, active/reserve flags, and auction values.
* starter_assignments.csv: exactly 345 legally assigned league active slots.
* reserve_rankings.csv: outside-pool rankings and 105 reserve selections when sufficient depth exists.
* positional_replacement.csv: slot capacities and optimized marginal entry thresholds.
* rate_reference.json: weighted AVG/ERA/WHIP and per-team AB/IP, with convergence iterations.
* effective_calibration.json: slope source and prior-season fits.
* candidate_exclusions.csv: missing metrics, exposure floors, and missing eligibility.
* valuation_audit.json: status, input hashes, budget reconciliation, reference method, and backup location.
* consensus folder: exact existing consensus statistics, source records, formulas and provenance.

All new outputs are backed up with file hashes compared. Both input databases and source payloads are read-only and fingerprinted. No final rankings or dollar values are published while calibration/eligibility is missing.

## Lightweight replacement package

This replacement contains the five engine scripts, two profiles, tests and instructions. Large generated consensus and demonstration files are omitted. Run --prepare-inputs on your PC to regenerate consensus and templates from your warehouse.

Ten tests previously passed, including exact multi-position replacement comparisons, rate denominators, budget conservation, and future-calibration rejection. A full-size synthetic test filled 345 active slots and 105 reserves and allocated $3,900 exactly. Real player values still require authoritative preseason position eligibility and completed prior-season SGP calibration.
