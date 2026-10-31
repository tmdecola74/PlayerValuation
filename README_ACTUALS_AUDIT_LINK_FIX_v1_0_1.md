# Actuals audit link repair 1.0.1

Extract into D:\JonAPythonClass\pycharm\PlayerValuation. This updates the audit's half-inning label normalization, adds a fast report repair and regression tests, and includes the unchanged frozen scoring support. It does not change actuals, reconciliation or pitch-count logic.

The original audit compared Savant Bot with MLB bottom literally, incorrectly rejecting otherwise matching bottom-half PAs. This release normalizes Bot/bottom and preserves every other identity, pitch/count, inning and completion check. Top versus bottom still fails. Unknown outcomes remain unknown; no scoring override is introduced.

Run:
```powershell
python -m unittest discover -s tests -p "test_actuals_audit_link_fix_v1_0_1.py" -v
python repair_actuals_audit_links_v1_0_1.py
```

Default source: outputs/actuals_final_difference_audit_v1_0
New output: outputs/actuals_final_difference_audit_v1_0_1
Complete verified backup: backups/actuals_final_difference_audit_v1_0_1_<timestamp>
Use --source / --output / --backup-root if those paths differ. New output must not exist. Finish evidence downloads first.

Fast repair uses candidate_pa_evidence.jsonl plus pa_inventory.csv already in the original audit folder, verifies saved plays against the originally hashed cache feeds and metadata, and recomputes only PA-link classifications and candidate review lists. It does not reopen the raw Statcast archive or recalculate season/game counts. Every original output file is copied into the new folder; the previous report is preserved as repair_prior_audit_report.json. Source audit unchanged is verified. Original input_hashes.json records the original audit's provenance; repair_provenance.json records files verified during this repair. Raw-integrity claims are inherited from the original audit, not freshly certified.

Return audit_report.json and candidate_pa_reviews.csv from the new folder. Candidate PA evidence is updated and retained for detailed review. remaining_cases.csv changes only candidate_pa_rows, never its numerical counts. game_metric_comparisons.csv and both fetch plans are preserved byte-for-byte. The 25 uncached leads therefore remain available without another archive scan.

Tests: three new tests cover Bot/bottom equivalence while preserving Top/bottom disagreement; a full fast repair with original raw file removed, unchanged source report/counts and complete verified backup; and rejection of tampered MLB feeds. The previous ten audit tests also pass against the updated module. Full historical repair runs on your PC.
