# Validation

Ten end-to-end tests passed under DuckDB 1.4.3 and DuckDB 2.0.0. They check exact lag/label separation, historical-age derivation, no future-window access, 2026 outcome/age invariance, missing measurements, fixed sample gates, prior-label masks, cold-start population independence, tampered manifests, source hashes, duplicate physical pitches, Windows CP1252 defaults, immutable references, output guards and verified complete backups.

Schemas were inspected in the existing Statcast ingestion/feature builders, the actual FanGraphs importer and the 2,706-window historical manifest. The full corrected label tables and physical Statcast files reside on the user's PC. No production matrix run is claimed from this environment. Use the README command to build and audit those data locally.

This stage does not fit models or claim measurement comparability, historical archived-as-of availability or complete preseason-roster coverage.
