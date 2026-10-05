# Stage 2B delivery: equal versus weighted blends

No additional inputs were required. The backtest has already run against the
resolved warehouse. Start with outputs/blend_backtest_v1_0/blend_backtest_report.md.

Three methods are compared: equal weighting, training inverse-MAE weights
shrunk toward equal, and nonnegative sum-to-one fitted ridge-MSE weights.
Only earlier seasons enter fitting. Primary tests train 2024/test 2025 and
train 2024–2025/test 2026. A train-2025/test-2026 sensitivity fold is separate.
It is not a third independent test season. Sources without complete training
history receive neutral equal shares in expanding-pool comparisons.

The run produced 378 fold/method results, 126 exact sample sets, and 164,178
held-out consensus predictions. All samples and weights are reproducible from
sample_memberships.jsonl, fold_weights.csv and heldout_predictions.csv.

Result: neither weighted method cleared the preset consistency screen across
both primary seasons for any of the ten roto categories in the headline cohorts.
Equal weighting remains the supported default under these tested rules.
For example, fitted ERA weights improved MAE by about 0.35% in 2025 and 0.16%
in 2026. Those gains are small. The recent-year sensitivity fold showed about
1.01% RBI MAE improvement in 2026, which warrants monitoring rather than claiming
an independently confirmed advantage.

Saves were also evaluated on preseason closer candidates: at least one source
in the comparison must project five or more saves; actual saves never determine
selection. Players with zero actual saves remain in that sample. Unmatched
players are excluded, never zero-filled. The closer results also favor retaining
equal weighting under the primary consistency screen.

The warehouse is read-only and its hash is verified before and after evaluation.
All original sources, duplicate selections and identity reviews remain unchanged.
29 tests pass, including a test that changes held-out actuals and confirms learned
weights cannot change, optimizer constraints, source-neutral allocations,
forecast recomputation, identical evaluation player sets and chronological folds.

The screen requires at least 1% MAE improvement in both primary years with no
more than 1% RMSE deterioration in either year. It is descriptive, not statistical
proof that weighted blending cannot help. These are fixed-method research tests,
not final production weights. New-season data would strengthen the evidence.

Run another backtest in a new output folder:
python backtest_projection_blends_v1_0.py --output outputs/blend_backtest_run2
