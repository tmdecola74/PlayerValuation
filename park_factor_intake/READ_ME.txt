Park-factor intake and model-use assessment

Verified 750 team-season records: 30 teams x 5 seasons (2021-2025) at each of
MLB, AAA, AA, High-A and Low-A. All 25 tabs have 30 unique team names.
Blank separators and unrelated footer/league-constant rows were excluded from
the normalized park table; their original contents remain documented in audit.json.
The supplied workbooks remain unchanged; SHA-256 hashes are in source_manifest.json.

Columns include actual team name, subleague, home/road games, one-year raw factor,
three-year pooled and weighted factors, and two half-regressed variants. No stadium
or affiliate IDs, parent organization codes, or component-specific factors appear.
Some league labels are missing; retain these as missing pending a verified mapping.

Source identified from workbook footer and confirmed against official TJStats pages:
https://tjstats.ca/park-factors/
https://tjstats.ca/glossary/
The methodology defines the raw factor as combined home runs scored/allowed
per game divided by combined road runs scored/allowed per game. Here 'runs' means
total scoring, NOT home runs. Neutral = 1.0. The final value is the recency-
weighted trailing three-year factor regressed halfway toward 1.0. This is
statistical shrinkage, not a player-specific home/road exposure adjustment.
The glossary says the final factor enters TJStats wOBA+ and TJBat+ calculations.
The supplied final values agree with half-regression of the weighted column
within displayed rounding. Simple trailing 3/2/1 checks show no >.005 differences
where the same team has three supplied annual raw values. Exact reconstruction
would require the underlying runs and game counts used by the source.

MODEL USE
These are useful general run-environment controls and a source of subleague
identity. They are NOT direct home-run, hit-type, walk or strikeout factors.
Do not divide every component by the final run factor. Do not automatically
halve its effect again: regression toward 1 and home-exposure allocation are
different operations. Player exposure and the source convention need explicit
treatment in a separately validated challenger.

The existing Fangraphs stints identify parent organizations, while the park tables
identify affiliates. Build a season-specific parent/level/affiliate crosswalk before
assigning values. For full-season levels a unique mapping may be possible; verify
changes, relocations, renamed teams and any multi-venue seasons. League labels
must come from the mapped affiliate rather than guessed from organization alone.
MLB labels in the current experiment are player season totals, so traded-player
MLB park exposure likewise requires team stints or home/road/venue evidence.

No factors were assigned to players or applied to forecasts in this intake.
No 2019, 2020, 2026, CPX, DSL, R or A- park factors are supplied. Missing factors
must remain unavailable, not silently neutral. Source-season 2025 factors may
support 2026 forecasts; target-season factors cannot enter preseason predictors
for that same season. Historical yearly factors can support retrospective
neutralization, but export/revision timestamps do not certify archived vintages.

NEXT WORK
Build and audit a historical affiliate crosswalk, then measure matched coverage.
Specify an overall-environment challenger without pretending these are component
factors. Keep component-specific translations separately calibrated and validate
incremental improvement with earlier-only origins and unchanged paired samples.
The existing component pilot and v1.43 remain untouched.

Files: park_factors_as_supplied.csv, audit.json, source_manifest.json.
