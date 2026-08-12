"""World Bank dataset quality policy."""

from data_quality.evaluator import DataQualityConfig

WORLD_BANK_QUALITY_CONFIG = DataQualityConfig(
    dataset="world_bank_population",
    required_columns=(
        "indicator_id",
        "country_iso3_code",
        "observation_year",
        "observation_value",
    ),
    business_key=("country_iso3_code", "indicator_id", "observation_year"),
    expected_types={
        "indicator_id": "string",
        "indicator_name": "string",
        "country_id": "string",
        "country_name": "string",
        "country_iso3_code": "string",
        "observation_year": "int",
        "observation_value": "double",
        "unit": "string",
        "observation_status": "string",
        "decimal_places": "int",
        "source_file": "string",
        "source_record_index": "int",
        "schema_drift": "boolean",
        "schema_drift_fields": "array<string>",
    },
    allowed_values={
        "indicator_id": frozenset({"SP.POP.TOTL"}),
        "country_iso3_code": frozenset({"USA"}),
    },
)


class DataQualityFailure(RuntimeError):
    """Raised after a failing result has been persisted for investigation."""
