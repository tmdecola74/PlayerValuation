# Remaining error-label evidence plan
Extract into PlayerValuation. Adds config/final_actuals_error_review_v1_0.csv and selection audit files. No code/data replacements.
25 games and 30 player/metric/PA leads selected from the supplied frozen PA inventory and current 35 differences. Select error-labelled PAs for remaining hitter AB differences and negative hit/type differences. Excludes already cached inventory games plus the supplied prior 25-game primary batch. The existing downloader rechecks current cache and skips any additional cached games.
These are leads, not confirmed corrections. No fallback/all-hit census is implied. Positive excess-hit differences and other non-error possibilities remain for separate review.

python download_mlb_scoring_evidence_v1_0.py --plan "config/final_actuals_error_review_v1_0.csv" --cache "data/mlb_scoring_evidence_v1_0" --scope all_review_games --max-games 25

After a failure-free run, package just these game folders and send for review. No full reconciliation rerun needed before inspection.
