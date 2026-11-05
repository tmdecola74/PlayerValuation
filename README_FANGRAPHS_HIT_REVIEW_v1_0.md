# FanGraphs hit game-log review v1.0

Extract into the outer PlayerValuation folder. Start with investigations/fangraphs_hit_review_v1_0/FINDINGS.md. The audit has already run against all ten supplied CSVs. No broad game download is needed. Five MLB feeds and the original FanGraphs exports are included.

Run tests:

```powershell
python -m unittest discover -s tests -p "test_fangraphs_hit_gamelogs_v1_0.py" -v
```

Reproduce offline into a new folder:

```powershell
python audit_fangraphs_hit_gamelogs_v1_0.py --logs "investigations/fangraphs_hit_review_v1_0/results/source_files" --prior "investigations/fangraphs_hit_review_v1_0/prior_mlb_comparison" --feeds "investigations/fangraphs_hit_review_v1_0/results/mlb_game_feeds" --output "outputs/fangraphs_hit_review_v1_0_reproduced"
```

The complete delivered investigation has a hash-verified copy under investigation_backups. Existing reference data is unchanged. This is a read-only research audit, not a source-count correction or modeling approval.
