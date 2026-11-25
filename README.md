# Pitcher role hybrid v1.28

Extract the package into PlayerValuation. From the project root:

```powershell
python -m unittest discover -s tests -p "test_pitcher_role_hybrid_v1_28.py" -v
python pitcher_role_hybrid_v1_28.py --evaluation-run "outputs/pitcher_workload_v1_27_evaluation"
```

Omit --evaluation-run to run history alone. Default output:
outputs/pitcher_role_hybrid_v1_28. Use --output for a new directory on repeat runs.
By default historical inputs come from the v1.27 frozen run. The optional
--historical-scores flag accepts a standalone aggregate CSV and records its hash.

The rule uses the existing preseason PRIOR_ROLE grouping. The prior year's
GS/G of at least 0.5 is STARTER and keeps accepted_ip. All others, including
UNKNOWN, use two_part_ip. Matched role groups are aggregated by player count,
and both source arms must reconcile with their overall scores. No refitting or
default changes. Historical rolling checks use earlier score years only, though
this rule was proposed after reviewing the historical period. The same gate
thresholds as v1.27 apply for overall and starter innings error. 2026 is scored
separately for innings only on known outcomes; it does not enter any gate.
The supplied historical results were computed from the uploaded score CSV.
