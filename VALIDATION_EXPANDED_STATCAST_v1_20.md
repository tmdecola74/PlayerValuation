# Validation

21 tests passed using Python, DuckDB 1.4.3 and NumPy in the development environment.

Tests cover handedness/switch-stance pull geometry, both pulled-barrel denominators, AIR/launch distribution calculations, zone/outside-zone contact, whiff/chase, conditional measurement coverage, pitch-type usage summation and missing-type normalization, movement units, fixed-range invalids, valid measured zeros, absent optional columns, duplicate physical pitches and multiple in-play outcomes, raw-only geometry recovery flags, bat fields audited without guessed metrics, exact source hashes, lag chronology and absent-history nulls, no labels/future-archive reads, fixed configuration/output guards, verified complete backups and interruption cleanup.

End-to-end synthetic fixture: three frozen daily windows (2020, 2021, 2025), 2,160 physical pitches, both roles, 34 overall metric definitions, separate pitch-type features and historical/2026 prior-history add-ons. Includes an absent-history identity and a deliberately inaccessible 2026 archive path. Frozen manifest/schema shape matches the retrieved original v1.0 lagged-feature package. Existing files remain unchanged.

The user's production archive is on their PC and has not been scanned here. Synthetic checks establish software behavior, not production field coverage, official leaderboard agreement, measurement comparability or predictive benefit. Pull definitions remain explicit research proxies. The build performs no model fitting or selection and changes no accepted forecasts.
