# Supplied-data adjustment results

Fit: 2024. Validation/selection: 2025. Frozen evaluation: 2026.

45 candidates; 18 fitted; 27 insufficient fit samples; 0 accepted. All 109,065 frozen per-metric forecasts retain original baselines.

The main validation cohorts use actual PA >=300 (hitters) or IP >=40 (pitchers). Acceptance requires >=2% MAE gain and no RMSE worsening in both all-matched and main cohorts.

| Source | Metric | Overall MAE gain | Main-cohort MAE gain | Selected |
|---|---|---:|---:|---|
| Steamer | R | -1.30% | -2.70% | No |
| Steamer | HR | 2.01% | -0.41% | No |
| Steamer | RBI | 0.36% | -2.47% | No |
| Steamer | SB | -6.84% | -4.87% | No |
| Steamer | AVG | 1.56% | 0.54% | No |
| THE BAT X | R | -0.39% | -1.58% | No |
| THE BAT X | HR | 0.82% | 0.24% | No |
| THE BAT X | RBI | 0.54% | 0.72% | No |
| THE BAT X | SB | -4.05% | -3.39% | No |
| THE BAT X | AVG | -0.11% | -1.67% | No |
| ATC | W | -0.18% | 0.85% | No |
| ATC | SO | -0.10% | 0.29% | No |
| ATC | ERA | -0.81% | 2.85% | No |
| ATC | WHIP | -1.83% | 1.19% | No |
| Steamer | W | -2.50% | -0.07% | No |
| Steamer | SO | -0.64% | -0.35% | No |
| Steamer | ERA | -0.57% | 2.63% | No |
| Steamer | WHIP | -1.73% | 1.70% | No |

Positive gain means lower error. These are candidate validation results, not deployed adjustments.

Inputs were reconstructed from the uploaded physical feature tables, SQLite reference, and full-trace reconciliation using the established assembler rules. Raw pitch Parquet was not available here. All source baseline dictionaries and chronology were independently checked; rerun locally for final reproduction.

The complete result folder was backed up and every backup file hash verified. SQLite and model inputs remained unchanged. Eight tests passed, including frozen model/forecast invariance to changed holdout outcomes.

No claim of statistical significance or universal usefulness/uselessness of Statcast follows from this single validation year.
