# Stage 2B — held-out weighted blend tests

Equal weighting is compared with shrinkage toward equal weights using inverse training MAE, and nonnegative sum-to-one weights fitted to regularized training squared error. No test-season outcomes enter weight fitting.

Primary tests: train 2024 → test 2025; train 2024–2025 → test 2026. The additional train 2025 → test 2026 fold assesses broader recent source coverage and is excluded from primary consistency assessments.

Shared-history pools contain sources present in every training year. Expanding pools include all test-season sources; each source lacking complete training history gets an equal neutral share, while earlier-season weights divide the remaining share.

A candidate must reduce held-out MAE by at least 1.0% in both primary years, with RMSE worsening by no more than 1.0% in either year. This fixed screening rule is descriptive, not a significance test or a production guarantee.

## Hitters — regular_playing_time, expanding source pool

|Category|Method|2025 MAE gain|2026 MAE gain|Players 2025/2026|Assessment|
|---|---|---:|---:|---|---|
|AVG|Fitted weights|-0.04%|-0.01%|275/263|Retain equal|
|AVG|Error-weighted|-0.00%|-0.00%|275/263|Retain equal|
|HR|Fitted weights|-0.57%|-0.05%|275/263|Retain equal|
|HR|Error-weighted|-0.02%|-0.00%|275/263|Retain equal|
|R|Fitted weights|-0.82%|+0.12%|275/263|Retain equal|
|R|Error-weighted|-0.03%|+0.01%|275/263|Retain equal|
|RBI|Fitted weights|-0.97%|-0.05%|275/263|Retain equal|
|RBI|Error-weighted|-0.03%|-0.00%|275/263|Retain equal|
|SB|Fitted weights|+0.13%|-0.08%|275/263|Retain equal|
|SB|Error-weighted|-0.00%|-0.00%|275/263|Retain equal|

## Pitchers — substantial_innings, expanding source pool

|Category|Method|2025 MAE gain|2026 MAE gain|Players 2025/2026|Assessment|
|---|---|---:|---:|---|---|
|ERA|Fitted weights|+0.35%|+0.16%|331/337|Retain equal|
|ERA|Error-weighted|+0.01%|+0.01%|331/337|Retain equal|
|SO|Fitted weights|+0.05%|+0.03%|331/337|Retain equal|
|SO|Error-weighted|+0.00%|+0.00%|331/337|Retain equal|
|SV|Fitted weights|+0.21%|-0.21%|331/337|Retain equal|
|SV|Error-weighted|+0.01%|-0.01%|331/337|Retain equal|
|W|Fitted weights|+0.04%|+0.02%|331/337|Retain equal|
|W|Error-weighted|+0.00%|+0.00%|331/337|Retain equal|
|WHIP|Fitted weights|+0.09%|-0.01%|331/337|Retain equal|
|WHIP|Error-weighted|-0.00%|-0.00%|331/337|Retain equal|

## Saves — preseason closer candidates

This cohort requires positive actual IP and at least one participating preseason source projecting 5 or more saves. Actual saves do not determine inclusion; projected closers who finished with zero saves remain scored. Unmatched players still cannot be assigned fabricated zero actuals.

|Pool|Method|2025 MAE gain|2026 MAE gain|Players 2025/2026|Assessment|
|---|---|---:|---:|---|---|
|expanding_pool|Fitted weights|+0.67%|-0.05%|73/66|Retain equal|
|expanding_pool|Error-weighted|+0.04%|-0.00%|73/66|Retain equal|
|shared_history|Fitted weights|+0.69%|-0.06%|62/58|Retain equal|
|shared_history|Error-weighted|+0.04%|-0.00%|62/58|Retain equal|

## Recent-year sensitivity — train 2025, test 2026

These results learn from the broader 2025 source pool. They use the same 2026 outcomes as the second primary fold and therefore provide sensitivity evidence, not another independent validation season.

|Type|Category|Cohort|Method|Players|MAE gain|RMSE gain|
|---|---|---|---|---:|---:|---:|
|hitter|R|regular_playing_time|Error-weighted|263|+0.00%|-0.00%|
|hitter|R|regular_playing_time|Fitted weights|263|+0.03%|-0.12%|
|hitter|HR|regular_playing_time|Error-weighted|263|+0.00%|-0.00%|
|hitter|HR|regular_playing_time|Fitted weights|263|+0.06%|-0.03%|
|hitter|RBI|regular_playing_time|Error-weighted|263|+0.06%|+0.04%|
|hitter|RBI|regular_playing_time|Fitted weights|263|+1.01%|+0.59%|
|hitter|SB|regular_playing_time|Error-weighted|263|+0.00%|+0.01%|
|hitter|SB|regular_playing_time|Fitted weights|263|-0.45%|-0.21%|
|hitter|AVG|regular_playing_time|Error-weighted|263|+0.00%|-0.00%|
|hitter|AVG|regular_playing_time|Fitted weights|263|+0.06%|-0.02%|
|pitcher|W|substantial_innings|Error-weighted|337|+0.05%|+0.04%|
|pitcher|W|substantial_innings|Fitted weights|337|+0.26%|+0.25%|
|pitcher|SV|substantial_innings|Error-weighted|337|-0.03%|-0.04%|
|pitcher|SV|substantial_innings|Fitted weights|337|-0.77%|-1.14%|
|pitcher|SV|closer_candidates|Error-weighted|66|+0.03%|-0.14%|
|pitcher|SV|closer_candidates|Fitted weights|66|+0.38%|-1.79%|
|pitcher|SO|substantial_innings|Error-weighted|337|+0.07%|+0.07%|
|pitcher|SO|substantial_innings|Fitted weights|337|+0.69%|+0.95%|
|pitcher|ERA|substantial_innings|Error-weighted|337|+0.14%|+0.19%|
|pitcher|ERA|substantial_innings|Fitted weights|337|+0.84%|+1.33%|
|pitcher|WHIP|substantial_innings|Error-weighted|337|+0.11%|+0.10%|
|pitcher|WHIP|substantial_innings|Fitted weights|337|+0.17%|+0.14%|

## Outputs and interpretation

* `fold_accuracy.csv`: all methods, folds, source pools, cohorts and error/correlation/rank metrics. Positive improvement means lower error than equal weighting on the exact same held-out sample.
* `fold_weights.csv`: exact frozen weights, source provenance, training sample counts and optimizer convergence. These are fold-specific research weights, not current production weights.
* `heldout_predictions.csv`: every consensus forecast, actual value and underlying source forecasts, permitting independent recomputation.
* `sample_memberships.jsonl`: exact training player-seasons and held-out player IDs. Training/test seasons are strictly separated.
* `category_assessments.csv`: primary-fold consistency screens. The rolling fold is never counted as a third independent test.
* `skipped_training.csv`: insufficient historical samples and explicitly unavailable fits.

Models use equal total weight per training season. Inverse-MAE weights are shrunk 50% toward equal. Fitted weights use a fixed ridge strength of 0.1 relative to training equal-blend MSE, preventing tuning on the held-out results. Training cohorts and test cohorts have the same thresholds; actual-playing-time filters condition results on realized opportunity.

Primary folds with longer history restrict trained sources to complete coverage across those years. This conservatively leaves later-introduced sources at neutral shares. The recent-year sensitivity fold learns from OOPSY and RotoWire in 2025, while Depth Charts has no pre-2026 training evidence.

The ten roto categories are evaluated directly. AVG/ERA/WHIP blends are weighted source rates, not separately reconstructed counting components. A later production consensus should reconcile rates with its PA/AB/IP components.

All raw and reviewed Stage 1B rows remain unchanged. No unmatched values are zero-filled, no weights are learned from the held-out season, and Greg Jones's unresolved advanced metrics remain outside these ten categories. With only two independent test seasons, small gains are tentative and method selection requires new-season confirmation.
