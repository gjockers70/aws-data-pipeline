SELECT COUNT(*) AS staging_null_failures
FROM staging.world_bank_population
WHERE indicator_id IS NULL
   OR country_iso3_code IS NULL
   OR observation_year IS NULL
   OR observation_value IS NULL;

SELECT COUNT(*) AS staging_duplicate_keys
FROM (
    SELECT country_iso3_code, indicator_id, observation_year
    FROM staging.world_bank_population
    GROUP BY country_iso3_code, indicator_id, observation_year
    HAVING COUNT(*) > 1
) AS duplicates;

SELECT
    (SELECT COUNT(*) FROM staging.world_bank_population) AS staging_row_count,
    (SELECT COUNT(*) FROM core.fact_population) AS core_row_count,
    CASE
        WHEN (SELECT COUNT(*) FROM staging.world_bank_population)
            = (SELECT COUNT(*) FROM core.fact_population)
        THEN 'PASS'
        ELSE 'FAIL'
    END AS row_count_status;

SELECT COUNT(*) AS schema_drift_rows
FROM staging.world_bank_population
WHERE schema_drift = TRUE;
