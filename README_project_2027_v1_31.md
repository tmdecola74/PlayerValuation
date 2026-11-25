# Homegrown 2027 v1.31
Extract into PlayerValuation alongside v1.30. Reuses the same local manifests,
frozen models, audited labels and benchmark snapshots. Run from project root:

```powershell
python -m unittest discover -s tests -p "test_project_2027_v1_31.py" -v
python project_2027_v1_31.py
```

Outputs go to outputs/homegrown_2027_v1_31. The v1.30 folder is unchanged.
Use --output for a fresh directory on subsequent runs.

- Zero projected starts imply zero baseline QS. Unknown starts/rate evidence
  can still produce missing baseline QS. Hybrid QS stays unmodeled.
- largest_pitcher_cuts.csv ranks hybrid IP reductions. Names come from
  Depth Charts, then Steamer, on exact MLBAM matches; unmatched names stay blank.
  Prior-year workload columns use 2026 actual IP, G and GS.
- ranked_coverage_gaps.csv ranks benchmark-only players by PA or IP separately
  for each benchmark and player type.
- historical_weighted_ip_scores.csv compares the weighted baseline against its
  hybrid on identical rows overall, by prior role and by participation.
  For each 2023–2026 fold, construct the baseline from exactly the trailing four
  seasons with the same 1:2:3:4 weights, missing-value policy and history-based
  player pool used for 2027. Replay each origin's frozen v1.27 coefficients with
  weighted baseline IP in place of their original baseline input. Keep baseline
  IP for prior starters. The 2027 challenger still uses the frozen 2026 model.
- historical_weighted_ip_coverage.csv reports exclusions; unknown outcomes are
  never imputed as zeros. The matched cohort can differ from prior experiments.
  2026 is a separate reporting-only diagnostic and not used for selection.
  This replay examines shifted inputs; it does not refit models or validate an
  automatic switch. No promotion, default change, or valuation wiring.
