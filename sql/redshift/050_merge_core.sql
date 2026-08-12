MERGE INTO core.dim_country
USING (
    SELECT DISTINCT country_iso3_code, country_id, country_name
    FROM staging.world_bank_population
) AS source
ON core.dim_country.country_iso3_code = source.country_iso3_code
WHEN MATCHED THEN UPDATE SET
    country_id = source.country_id,
    country_name = source.country_name,
    updated_at = GETDATE()
WHEN NOT MATCHED THEN INSERT (country_iso3_code, country_id, country_name)
VALUES (source.country_iso3_code, source.country_id, source.country_name);

MERGE INTO core.dim_indicator
USING (
    SELECT DISTINCT indicator_id, indicator_name, unit, decimal_places
    FROM staging.world_bank_population
) AS source
ON core.dim_indicator.indicator_id = source.indicator_id
WHEN MATCHED THEN UPDATE SET
    indicator_name = source.indicator_name,
    unit = source.unit,
    decimal_places = source.decimal_places,
    updated_at = GETDATE()
WHEN NOT MATCHED THEN INSERT (indicator_id, indicator_name, unit, decimal_places)
VALUES (source.indicator_id, source.indicator_name, source.unit, source.decimal_places);

MERGE INTO core.fact_population
USING (
    SELECT
        country.country_key,
        indicator.indicator_key,
        staging.observation_year,
        CAST(ROUND(staging.observation_value) AS BIGINT) AS population_value,
        staging.observation_status,
        staging.source_file,
        staging.source_record_index,
        staging.load_run_id
    FROM staging.world_bank_population AS staging
    JOIN core.dim_country AS country
        ON country.country_iso3_code = staging.country_iso3_code
    JOIN core.dim_indicator AS indicator
        ON indicator.indicator_id = staging.indicator_id
) AS source
ON core.fact_population.country_key = source.country_key
AND core.fact_population.indicator_key = source.indicator_key
AND core.fact_population.observation_year = source.observation_year
WHEN MATCHED THEN UPDATE SET
    population_value = source.population_value,
    observation_status = source.observation_status,
    source_file = source.source_file,
    source_record_index = source.source_record_index,
    load_run_id = source.load_run_id,
    loaded_at = GETDATE()
WHEN NOT MATCHED THEN INSERT (
    country_key,
    indicator_key,
    observation_year,
    population_value,
    observation_status,
    source_file,
    source_record_index,
    load_run_id
) VALUES (
    source.country_key,
    source.indicator_key,
    source.observation_year,
    source.population_value,
    source.observation_status,
    source.source_file,
    source.source_record_index,
    source.load_run_id
);
