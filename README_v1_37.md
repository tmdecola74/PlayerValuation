Extract into the PlayerValuation project root alongside the installed v1.35 and earlier dependencies. Existing releases are unchanged.

```powershell
python -m unittest discover -s tests -p "test_statcast_pull_air_v1_37.py" -v
python statcast_pull_air_v1_37.py
```

Output: outputs/2027_statcast_pull_air_v1_37 (use --output for a fresh destination). Review pull_air_comparison_deltas.csv, especially FEATURE_SUPPORTED, ALL and each projected-workload band. Negative delta_rmse or delta_mae favors the method over its comparator. XBH means 2B + 3B + HR, with HR fixed. Pitcher SO rate is per out. All four methods use the same eligible rows; even the pull-air arm requires the full feature vector for the matched experiment. Missing support leaves the baseline unchanged.

2025 fits on 2024 targets; 2026 reporting fits on 2024–2025 targets. The archive cannot currently supply an earlier compatible test fold. See development_fold_audit.json. 2025 informed this experiment's design and 2026 remains reporting only. No 2027 export is changed; the weighted skill baseline and accepted_ip stay in place, walks and WHIP remain fixed, hybrid QS stays blank, and valuations stay off.
