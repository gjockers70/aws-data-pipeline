CREATE TABLE IF NOT EXISTS staging.world_bank_population (
    indicator_id VARCHAR(32) NOT NULL,
    indicator_name VARCHAR(256) NOT NULL,
    country_id VARCHAR(16),
    country_name VARCHAR(128) NOT NULL,
    country_iso3_code CHAR(3) NOT NULL,
    observation_year INTEGER NOT NULL,
    observation_value DOUBLE PRECISION NOT NULL,
    unit VARCHAR(64),
    observation_status VARCHAR(64),
    decimal_places INTEGER,
    source_file VARCHAR(2048) NOT NULL,
    source_record_index INTEGER NOT NULL,
    schema_drift BOOLEAN NOT NULL,
    schema_drift_fields SUPER,
    load_run_id VARCHAR(128),
    loaded_at TIMESTAMP NOT NULL DEFAULT GETDATE()
)
DISTSTYLE AUTO
SORTKEY AUTO;

CREATE TABLE IF NOT EXISTS audit.warehouse_load (
    load_run_id VARCHAR(128) NOT NULL,
    source_uri VARCHAR(2048) NOT NULL,
    load_status VARCHAR(16) NOT NULL,
    staged_row_count BIGINT,
    core_row_count BIGINT,
    started_at TIMESTAMP NOT NULL DEFAULT GETDATE(),
    completed_at TIMESTAMP,
    error_message VARCHAR(4096),
    PRIMARY KEY (load_run_id)
)
DISTSTYLE AUTO
SORTKEY AUTO;
