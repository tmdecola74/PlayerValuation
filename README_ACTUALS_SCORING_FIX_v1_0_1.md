# Actuals evidence/reporting fix 1.0.1

Extract into D:\JonAPythonClass\pycharm\PlayerValuation. Replace the two
existing files actuals_scoring_v1_0.py and reconcile_statcast_actuals_v1_0.py.
The repair script, new test, audit notes and this README are additions.
Keep your existing test_actuals_scoring_v1_0.py and statcast_pipeline_v1_0.py.
No reference data, original reports, pitch files or ingestion config is replaced.

## Run the fast repair; no eleven-season rescan or download

```powershell
python -m unittest discover -s tests -p "test_actuals*.py" -v

python repair_actuals_reports_v1_0_1.py
```

Defaults:
- Source: outputs/actuals_statcast_reconciliation_v1_0_targeted
- Cache: data/mlb_scoring_evidence_v1_0
- Advisory inspection: outputs/actuals_event_inspection_v1_0/event_rows.csv
- NEW output: outputs/actuals_statcast_reconciliation_v1_0_1
- Complete verified backup: backups/<new output name>_<UTC timestamp>

If your source output has another name, use --source PATH. Output must be new;
use --output PATH for another name on reruns. Do not run ingestion or cache
downloads during repair. The command verifies all 46 originally used feed
hashes against the old usage report and copies the old output before repairing
its report layer. It does NOT scan the 7.4 million pitch rows. It checks source
report/cache hashes again before publishing and verifies the full output backup.

## Findings and fixes

1. The original comparison loop unioned keys from partial MLB boxscores into
   season-level discrepancies. That introduced 1,907 additional no-reference
   metric rows: 1,904 hitter rows for 112 extra hitter-role identities plus
   three additional pitching metrics for an already unreferenced pitcher.
   It did not establish 1,907 new numerical mismatches. Some added rows are
   sparse/zero-role records; positive partial counts also exist and are kept.

   Full-season comparisons now use reference keys and physical terminal
   baseline keys. MLB-only metrics are retained in mlb_evidence_only.csv,
   outside the season discrepancy count. The fast repair retains their original
   report columns verbatim, including positive partial counts. Future full
   reconciliation uses a compact evidence-only schema with explicit layer counts.
   Missing reference players observed in actual pitches remain review cases.

2. All ten A->B->A batter-ID patterns have corroborating MLB pinch-hit records
   at two strikes. The final Statcast ID is the outgoing batter receiving
   strikeout/AB/PA credit; it is not evidence that he re-entered the game.
   The new check requires the explicit replacement IDs/count, matching pitcher,
   complete strikeout result, matching full pitch numbering and pre/post counts,
   and the outgoing terminal-credit ID. An index match alone cannot clear review.
   Duplicate/ambiguous candidate plays do not clear review. No count or pitch
   ownership values are rewritten. The physical finishing batter is recorded
   separately in mlb_scoring_confirmation on the trace.

   The ten supplied cases satisfy these checks. Their twenty player-season
   sequence flags can clear, affecting 260 previously matching metric rows.

3. Original MLB PA exports selected player-change/no-pitch cases and omitted
   the two game_advisory PAs. The repair exports index/ID candidate matches
   for games 490101 and 490136 into advisory_outcome_candidates.csv and
   mlb_advisory_play_evidence.jsonl using the existing cache. Candidate index
   and matchup checks are shown separately. No advisory event is automatically
   reclassified or added to PA counts by this patch.

Expected report changes on the supplied run, subject to the cache checks:
- Numerical differences remain 240; no counts are recalculated by fast repair.
- Missing-reference discrepancy rows remain 994 (the existing pitch-observed
  pitcher population), with 1,907 MLB-only rows kept separately.
- All ten sequence cases confirm, eliminating 260 sequence-only review rows.
- Total discrepancy rows become 1,234 = 994 reference gaps + 240 numeric gaps.
- model_ready stays false. Unknown game_advisory remains under outcome review.

The existing ER player/team-total admission guard is unchanged. One of the 46
feeds has ER held back; this patch does not relax scoring validation or claim
full-season IP/ER reconciliation from partial game coverage. The old game fetch
plan is retained as historical context, not reprioritized. Do not launch a new
bulk evidence download from it based on this reporting repair.

## Return after running

From outputs/actuals_statcast_reconciliation_v1_0_1 attach:
- reconciliation_report.json
- discrepancies.csv
- advisory_outcome_candidates.csv
- mlb_advisory_play_evidence.jsonl

report_repair_audit.json records old report hashes, feed hashes, verification
scope and confirmation counts. Inputs_unchanged refers to the source report
folder and used cache; original pitch-integrity findings are inherited from
the original full run, not newly asserted after a rescan.

Validation: 19 distinct fixture tests plus a regression against the supplied
3,401-row discrepancy export and all ten real exported MLB play sequences.
The full report/cache directory remains on your PC, so the complete repair
must run there. The repair preserves the original folder and creates a fully
backed-up new folder. No new network requests are made.

## Confirmed reference-scope finding

The original uploaded pitcher CSV has an observed minimum of 1 IP; it contains
no 0.0/0.1/0.2-IP or other sub-1-IP seasons. Cached MLB evidence supplies one
out for José Castillo (MLBAM 620454) in 2023, whose pitcher-season is missing
from that reference. Thus zero-IP exclusions alone cannot explain all gaps.
Please re-export 2015-2026 pitching actuals with minimum IP set to 0, including
fractional and zero-IP appearances, retaining the same columns and season/IDs.
This is a new source-scope finding, not a reason to overwrite the existing
reference in place. Keep the revised CSV separate for the next reviewed import.
The fast report repair continues to use the current reference unchanged.
