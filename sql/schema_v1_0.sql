CREATE TABLE IF NOT EXISTS dataset_version (
 version_id VARCHAR PRIMARY KEY,
 dataset VARCHAR NOT NULL, season INTEGER NOT NULL, source VARCHAR NOT NULL,
 source_hash VARCHAR NOT NULL, fingerprint VARCHAR NOT NULL,
 raw_path VARCHAR NOT NULL, parquet_path VARCHAR NOT NULL, parquet_hash VARCHAR NOT NULL,
 source_rows BIGINT NOT NULL, normalized_rows BIGINT NOT NULL,
 ingested_at TIMESTAMPTZ NOT NULL, active BOOLEAN NOT NULL
);
