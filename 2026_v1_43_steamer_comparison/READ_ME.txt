2026 V1.43 / STEAMER / ACTUALS HISTORICAL COMPARISON
Steamer snapshot: March 25, 2026 (user supplied).
Open comparison_report.html for the readable report.
Finding: Steamer has lower MAE on all 39 scored statistics in the broad matched samples. This is descriptive, not a claim of statistical significance.
Forecast agreement: 929 hitters / 1,308 pitchers matched.
Accuracy among actual participants: 550 hitters / 660 pitchers, with 549 eligible batting-rate rows.
Pitcher innings including certified nonparticipants: 1,172 matched players.
No fresh holdout or model adoption decision.
Wide hitter_player_comparison.csv and pitcher_player_comparison.csv provide the matched player-level three-way values.
MAE and RMSE: lower is better. Bias: forecast minus actual.
All accuracy comparisons use identical eligible players per metric/cohort.
No projection, playing-time, prior, coefficient or production files changed.
The 2027 minor-history challenger is not part of this comparison.

[
  {
    "role": "hitter",
    "raw_Steamer_rows": 4186,
    "valid_Steamer_IDs": 4185,
    "our_forecasts": 1052,
    "matched_forecast_players": 929,
    "actual_positive_players": 662,
    "actual_positive_with_both_forecasts": 550,
    "actual_positive_missing_our_forecast": 112,
    "actual_positive_missing_Steamer": 3,
    "our_forecast_participation_unknown": 502,
    "our_forecast_certified_zero_pitching": 0
  },
  {
    "role": "pitcher",
    "raw_Steamer_rows": 5162,
    "valid_Steamer_IDs": 5161,
    "our_forecasts": 1512,
    "matched_forecast_players": 1308,
    "actual_positive_players": 868,
    "actual_positive_with_both_forecasts": 660,
    "actual_positive_missing_our_forecast": 181,
    "actual_positive_missing_Steamer": 61,
    "our_forecast_participation_unknown": 206,
    "our_forecast_certified_zero_pitching": 619
  }
]

ACTUAL >=200 PA OR >=100 IP DIAGNOSTIC COHORT
hitter PA n=333: MAE v1.43 141.15344; Steamer 128.30410; difference +10.0%; RMSE 181.90548 vs 157.79941
hitter HR n=333: MAE v1.43 6.24977; Steamer 6.07784; difference +2.8%; RMSE 8.45758 vs 7.70605
hitter R n=333: MAE v1.43 20.27770; Steamer 18.83454; difference +7.7%; RMSE 25.62938 vs 22.91627
hitter RBI n=333: MAE v1.43 20.60912; Steamer 18.89586; difference +9.1%; RMSE 26.26915 vs 23.36670
hitter SB n=333: MAE v1.43 4.43544; Steamer 3.91593; difference +13.3%; RMSE 6.55460 vs 5.81834
hitter AVG n=333: MAE v1.43 0.02292; Steamer 0.02034; difference +12.7%; RMSE 0.02918 vs 0.02622
hitter OPS n=333: MAE v1.43 0.06833; Steamer 0.06264; difference +9.1%; RMSE 0.08731 vs 0.07907
pitcher IP n=135: MAE v1.43 55.58098; Steamer 31.52423; difference +76.3%; RMSE 67.07744 vs 42.42738
pitcher SO n=135: MAE v1.43 56.00356; Steamer 36.39356; difference +53.9%; RMSE 69.83441 vs 46.71376
pitcher W n=135: MAE v1.43 4.45577; Steamer 3.24943; difference +37.1%; RMSE 5.36886 vs 3.90738
pitcher SV n=135: MAE v1.43 0.38540; Steamer 0.32854; difference +17.3%; RMSE 1.58021 vs 1.36134
pitcher HLD n=135: MAE v1.43 0.86774; Steamer 0.64397; difference +34.7%; RMSE 2.71439 vs 2.04718
pitcher ERA n=135: MAE v1.43 0.74124; Steamer 0.67142; difference +10.4%; RMSE 0.96173 vs 0.85218
pitcher WHIP n=135: MAE v1.43 0.12552; Steamer 0.11821; difference +6.2%; RMSE 0.16205 vs 0.15071