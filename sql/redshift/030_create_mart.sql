CREATE OR REPLACE VIEW mart.population_yearly AS
SELECT
    country.country_iso3_code,
    country.country_name,
    indicator.indicator_id,
    indicator.indicator_name,
    fact.observation_year,
    fact.population_value,
    fact.population_value
        - LAG(fact.population_value) OVER (
            PARTITION BY fact.country_key, fact.indicator_key
            ORDER BY fact.observation_year
        ) AS annual_change,
    ROUND(
        100.0 * (
            fact.population_value
            - LAG(fact.population_value) OVER (
                PARTITION BY fact.country_key, fact.indicator_key
                ORDER BY fact.observation_year
            )
        ) / NULLIF(
            LAG(fact.population_value) OVER (
                PARTITION BY fact.country_key, fact.indicator_key
                ORDER BY fact.observation_year
            ),
            0
        ),
        4
    ) AS annual_growth_percent
FROM core.fact_population AS fact
JOIN core.dim_country AS country ON country.country_key = fact.country_key
JOIN core.dim_indicator AS indicator ON indicator.indicator_key = fact.indicator_key;

CREATE OR REPLACE VIEW mart.population_decade_summary AS
SELECT
    country_iso3_code,
    country_name,
    (observation_year / 10) * 10 AS decade_start_year,
    MIN(population_value) AS minimum_population,
    MAX(population_value) AS maximum_population,
    AVG(population_value) AS average_population,
    MAX(population_value) - MIN(population_value) AS population_range
FROM mart.population_yearly
GROUP BY country_iso3_code, country_name, (observation_year / 10) * 10;

CREATE OR REPLACE VIEW mart.population_latest_kpi AS
SELECT
    country_iso3_code,
    country_name,
    observation_year,
    population_value,
    annual_change,
    annual_growth_percent
FROM mart.population_yearly
QUALIFY ROW_NUMBER() OVER (
    PARTITION BY country_iso3_code
    ORDER BY observation_year DESC
) = 1;
