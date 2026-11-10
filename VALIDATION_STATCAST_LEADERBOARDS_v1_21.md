# Validation

21 tests passed with DuckDB 1.4.3 in the development environment.

Coverage includes percentage-versus-fraction units; role-specific EV50; competitive swing/contact denominators; partial-2023 flags; missing values, valid zeros and small samples; signed baserunning context; unsupported denominators; count/rate holds without count replacement; source IDs and explicit years; duplicate/tampered sources; complete backups and snapshot immutability; paired archive reconciliation with no automatic proxy certification; frozen population joins and future-context rejection; no label reads; interruption cleanup; and invariance of both lag add-ons to changes in 2026 source values.

All 13 bundled supplied CSVs passed schema/ID/duplicate-key intake. The preferred updated hitter batted-ball export is used. The importer normalized 216,608 historical metric rows and quarantined 74,315 source-2026 metric rows. It flagged 171 hard-hit count/rate relationships outside simple rounding: 100 historical and 71 quarantined. Those flags do not establish source errors; measurement denominators may differ. Values/counts are preserved and affected candidate rates are masked for review.

An additional end-to-end test used all supplied exports with synthetic archive summaries and a small synthetic prior-history population. It completed CSV/Parquet normalization, quarantine, reconciliation machinery, lag writing and verified backup. Its reconciliation/coverage figures are not production findings because the user's actual frozen archive/matrices are on their PC.

No model was fitted, projection generated, accepted source replaced, actual count changed or target label read. Original uploaded CSV bytes are included under a new versioned input directory with registered SHA-256 hashes. 2026 descriptive source data is explicitly read and quarantined; it never feeds historical or target-2026 lag add-ons.
