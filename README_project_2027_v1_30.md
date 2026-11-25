# Homegrown 2027 research forecasts

Extract into the PlayerValuation project. Requires the existing v1.23.1, v1.24,
v1.27 and v1.29 modules/dependencies and their frozen local outputs. This package
includes the four dated benchmark snapshots under data/benchmarks_2027.

```powershell
python -m unittest discover -s tests -p "test_project_2027_v1_30.py" -v
python project_2027_v1_30.py
```

The runner verifies input hashes, records the frozen 2026 evaluation and
historical decisions, then generates independent forecasts for 2027.
Historical and holdout label files remain read-only. 2026 is a reporting-only
year for the frozen experiment; its actuals become lagged inputs for 2027.
Benchmarks never enter forecast calculations.

This is a new, unvalidated weighted-actuals prototype, not a replay of the
accepted 2026 model stack. Fixed weights 1:2:3:4 across 2023–2026 were not
selected on 2026 outcomes. Accepted innings remains the default policy:
for this prototype the baseline IP is the weighted actuals estimate.
The hybrid reuses frozen v1.27 coefficients and protects prior starters.
Using provisional IP as a model input is a distribution shift. No coefficients
are refitted and neither projection arm is enabled for valuations.

Output defaults to outputs/homegrown_2027_v1_30. Use --output for another run.
The two player CSVs retain exposure history and distinguish nulls from audited
zero exposures. Coverage and differences compare sources separately by MLBAM
ID and player type. Players without positive exposure history are not forecast.
Large differences use fixed screening thresholds, not evidence of accuracy.
The counting-stat review shows strikeouts and wins at unchanged rates and
an innings-based QS ceiling, not a QS forecast. Challenger starts and QS stay
blank. The report counts missing components; source files remain unchanged.
