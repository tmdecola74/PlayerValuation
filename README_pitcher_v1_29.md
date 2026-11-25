# PlayerValuation v1.29

Extract into the PlayerValuation root. Requires the existing v1.24, v1.26.1 and
v1.27 dependencies and the frozen v1.27 run.

```powershell
python -m unittest discover -s tests -p "test_pitcher_v1_29.py" -v
python pitcher_evaluation_v1_29.py --download
```

Default output: outputs/pitcher_evaluation_v1_29. MLB responses are cached in
cache/pitcher_appearance_mlb. On rerun specify a new --output path. Remove
--download to run from the cache alone. Keep the audit and scores together.

The audit verifies the complete MLB regular-season schedule against standings,
then verifies all boxscores, counts official pitching appearances (including
zero-out appearances), sums integer outs, and reconciles existing eligible G
and OUTS labels. Certification fails closed on missing games or conflicting
labels; details are in coverage_issues.csv. Missing identities remain unknown.
Only certified absences with exact MLBAM identity confirmation receive zero
games and zero outs. Known positive boxscore counts can fill missing evaluation
outcomes. Neither the historical overlay nor the holdout Parquet is edited.

Use report.json to check season_certified and complete_pool_scored. All three
methods are scored on exactly the same known outcomes overall, by appearance,
prior role, and their intersection. The frozen v1.28 rule keeps accepted_ip for
prior starters; all other roles use two_part_ip. Scores include total squared
error so the appearance and non-appearance contributions can be compared.
The 2026 outcomes are reporting only: no fitting, selection, or default changes.

## 2027 pitcher export (independent)

Fill the included CSV template from the approved **2027 preseason** projection
source. Use decimal innings (e.g. 100.666667 for 100 and two-thirds), not MLB
boxscore notation. The file requires accepted innings, strikeouts, wins,
quality starts and starts. Challenger innings and starts are optional.
Do not copy the 2026 holdout rows into this input.

```powershell
python pitcher_baseline_export_2027_v1_29.py --input "data/pitcher_preseason_2027.csv"
```

Default output: outputs/pitcher_baseline_2027_v1_29. The baseline file preserves
accepted IP/SO/W/QS/GS. The separate sensitivity file shows illustrative
strikeouts and wins at the accepted per-inning rates, and quality starts at the
accepted per-start rate if challenger starts are supplied (capped at IP/6).
These are diagnostics, not replacement projections: wins depend on role and
team context, and innings alone do not determine quality starts. No valuation
integration is performed. This is a pitcher workload/counting-stat export,
not a new model or a complete fantasy projection feed.
