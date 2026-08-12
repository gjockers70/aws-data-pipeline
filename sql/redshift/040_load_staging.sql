DELETE FROM staging.world_bank_population;

COPY staging.world_bank_population (
    indicator_id,
    indicator_name,
    country_id,
    country_name,
    country_iso3_code,
    observation_year,
    observation_value,
    unit,
    observation_status,
    decimal_places,
    source_file,
    source_record_index,
    schema_drift,
    schema_drift_fields
)
FROM '{{warehouse_load_uri}}'
IAM_ROLE default
FORMAT AS PARQUET SERIALIZETOJSON
STATUPDATE ON;

UPDATE staging.world_bank_population
SET load_run_id = '{{load_run_id}}'
WHERE load_run_id IS NULL;
