import re
from pathlib import Path

SQL_ROOT = Path(__file__).resolve().parents[2] / "sql" / "redshift"


def _sql(name: str) -> str:
    return (SQL_ROOT / name).read_text(encoding="utf-8")


def test_layer_schemas_and_tables_are_declared():
    schemas = _sql("001_create_schemas.sql").lower()
    staging = _sql("010_create_staging.sql").lower()
    core = _sql("020_create_core.sql").lower()
    mart = _sql("030_create_mart.sql").lower()

    for name in ("staging", "core", "mart", "audit"):
        assert f"create schema if not exists {name}" in schemas
    assert "staging.world_bank_population" in staging
    assert "core.dim_country" in core
    assert "core.dim_indicator" in core
    assert "core.fact_population" in core
    assert "mart.population_yearly" in mart
    assert "mart.population_decade_summary" in mart
    assert "mart.population_latest_kpi" in mart


def test_copy_uses_role_authentication_and_complete_parquet_column_order():
    load = _sql("040_load_staging.sql")
    expected_order = [
        "indicator_id",
        "indicator_name",
        "country_id",
        "country_name",
        "country_iso3_code",
        "observation_year",
        "observation_value",
        "unit",
        "observation_status",
        "decimal_places",
        "source_file",
        "source_record_index",
        "schema_drift",
        "schema_drift_fields",
    ]

    positions = [load.index(column) for column in expected_order]
    assert positions == sorted(positions)
    assert "{{warehouse_load_uri}}" in load
    assert "{{load_run_id}}" in load
    assert "IAM_ROLE default" in load
    assert "FORMAT AS PARQUET SERIALIZETOJSON" in load
    assert "ACCESS_KEY_ID" not in load
    assert "SECRET_ACCESS_KEY" not in load


def test_core_merge_contains_deduplicated_dimensions_and_fact_joins():
    merge = _sql("050_merge_core.sql").lower()

    assert merge.count("merge into") == 3
    assert merge.count("select distinct") == 2
    assert "join core.dim_country" in merge
    assert "join core.dim_indicator" in merge
    assert "when matched then update" in merge
    assert "when not matched then insert" in merge


def test_validation_sql_covers_required_failure_modes():
    validation = _sql("060_validate_load.sql").lower()

    assert "staging_null_failures" in validation
    assert "staging_duplicate_keys" in validation
    assert "row_count_status" in validation
    assert "schema_drift_rows" in validation


def test_redshift_sql_contains_no_account_or_static_credentials():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in SQL_ROOT.glob("*.sql"))

    assert re.search(r"\b\d{12}\b", combined) is None
    assert "AKIA" not in combined
    assert "ASIA" not in combined
