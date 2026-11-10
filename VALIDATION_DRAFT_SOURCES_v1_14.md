# Validation — v1.14.0

16 tests passed using Python 3.12.14 and DuckDB 1.4.3. These are synthetic end-to-end fixtures, not the production ledger audit. The build and intake command help pages were checked.

Verified independent arithmetic replay, exact published anchors, maximum changes/count caps, provenance mean/pool/weight guards, complete ledger coverage and policy fingerprints, corrupt delta rejection, preserved homegrown bytes and earlier trees, complete backups, explicit source/profile loading without fallback, independent unmapped-identity exclusions, ADP-first ordering using published preseason workload, preserved universe membership, chronology/schema/identity checks for dated inputs, unknown counts not zero-filled, strictly earlier fold populations with 2026 excluded and 2021 retained, output/tamper guards and interrupted-stage cleanup.

A rehashed corrupt-producer fixture fails the semantic audit and cannot publish a supported reconciled source. The homegrown source remains available independently. No production outcome table is read by the main build. The entry branch never claims fit readiness or generates forecasts; dated inputs, eligible label joins and empirical translation/workload/skill development remain future work. The ZIP is CRC-checked.
