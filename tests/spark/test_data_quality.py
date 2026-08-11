from __future__ import annotations

import json
from datetime import UTC, datetime

from pyspark.sql.types import (
    BooleanType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)

from data_quality import DataQualityConfig, evaluate_data_quality
from data_quality.world_bank import WORLD_BANK_QUALITY_CONFIG
from transformations.world_bank import (
    expected_world_bank_row_count,
    transform_world_bank_documents,
)

QUALITY_CONFIG = DataQualityConfig(
    dataset="example_dataset",
    required_columns=("entity_id", "year"),
    business_key=("entity_id", "year"),
    expected_types={
        "entity_id": "string",
        "year": "int",
        "category": "string",
        "schema_drift": "boolean",
    },
    allowed_values={"category": frozenset({"VALID", "UNKNOWN"})},
)

PROCESSED_SCHEMA = StructType(
    [
        StructField("entity_id", StringType(), nullable=True),
        StructField("year", IntegerType(), nullable=True),
        StructField("category", StringType(), nullable=True),
        StructField("schema_drift", BooleanType(), nullable=False),
    ]
)
REJECTED_SCHEMA = StructType([StructField("reason", StringType(), nullable=False)])
REJECTION_REASON_SCHEMA = StructType(
    [StructField("rejection_reason", StringType(), nullable=False)]
)
EVALUATED_AT = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def _evaluate(spark, rows, *, rejected=(), expected_row_count=None, config=QUALITY_CONFIG):
    processed = spark.createDataFrame(rows, schema=PROCESSED_SCHEMA)
    rejected_frame = spark.createDataFrame(rejected, schema=REJECTED_SCHEMA)
    return evaluate_data_quality(
        processed,
        rejected_frame,
        run_id="run_test_001",
        config=config,
        expected_row_count=expected_row_count,
        evaluated_at=EVALUATED_AT,
    )


def test_quality_passes_complete_unique_rows(spark):
    result = _evaluate(
        spark,
        [
            ("entity-1", 2023, "VALID", False),
            ("entity-1", 2024, "UNKNOWN", False),
        ],
        expected_row_count=2,
    )

    assert result.status == "PASS"
    assert result.row_count == 2
    assert result.row_count_match is True
    assert result.null_failures == 0
    assert result.duplicate_failures == 0
    assert result.invalid_enum_failures == 0
    assert result.schema_drift is False
    assert result.evaluated_at == "2026-01-02T03:04:05+00:00"


def test_quality_detects_null_enum_and_schema_drift(spark):
    result = _evaluate(
        spark,
        [(None, 2024, "INVALID", True)],
        expected_row_count=1,
    )

    assert result.status == "FAIL"
    assert result.null_failures == 1
    assert result.invalid_enum_failures == 1
    assert result.schema_drift is True
    assert result.schema_drift_rows == 1


def test_quality_detects_duplicates_rejections_and_row_count_mismatch(spark):
    duplicate = ("entity-1", 2024, "VALID", False)
    result = _evaluate(
        spark,
        [duplicate, duplicate],
        rejected=[("INVALID_TYPE",)],
        expected_row_count=4,
    )

    assert result.status == "FAIL"
    assert result.duplicate_failures == 1
    assert result.rejected_row_count == 1
    assert result.row_count_match is False
    assert next(rule for rule in result.rules if rule.rule == "row_count").status == "FAIL"


def test_quality_detects_missing_columns_and_invalid_spark_types(spark):
    incomplete = spark.createDataFrame([(123, 2024)], ["entity_id", "year"])
    rejected = spark.createDataFrame([], schema=REJECTED_SCHEMA)

    result = evaluate_data_quality(
        incomplete,
        rejected,
        run_id="run_test_002",
        config=QUALITY_CONFIG,
        expected_row_count=1,
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "FAIL"
    assert result.missing_column_failures == 2
    assert result.invalid_type_failures == 2


def test_quality_classifies_transformation_rejection_reasons(spark):
    processed = spark.createDataFrame(
        [("entity-1", 2024, "VALID", False)],
        schema=PROCESSED_SCHEMA,
    )
    rejected = spark.createDataFrame(
        [
            ("NULL_ENTITY_ID",),
            ("DUPLICATE_BUSINESS_KEY",),
            ("INVALID_OBSERVATION_VALUE",),
        ],
        schema=REJECTION_REASON_SCHEMA,
    )

    result = evaluate_data_quality(
        processed,
        rejected,
        run_id="run_test_003",
        config=QUALITY_CONFIG,
        expected_row_count=4,
        evaluated_at=EVALUATED_AT,
    )

    assert result.row_count_match is True
    assert result.null_failures == 1
    assert result.duplicate_failures == 1
    assert result.invalid_type_failures == 1
    assert result.status == "FAIL"


def test_world_bank_metadata_total_must_be_present_and_consistent(spark):
    consistent = spark.createDataFrame(
        [
            ("page-1", '[{"total":66},[]]'),
            ("page-2", '[{"total":66},[]]'),
        ],
        ["source_file", "raw_text"],
    )
    inconsistent = spark.createDataFrame(
        [
            ("page-1", '[{"total":66},[]]'),
            ("page-2", '[{"total":67},[]]'),
        ],
        ["source_file", "raw_text"],
    )

    assert expected_world_bank_row_count(consistent) == 66
    assert expected_world_bank_row_count(inconsistent) is None


def test_world_bank_transformation_passes_dataset_quality_policy(spark):
    records = [
        {
            "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
            "country": {"id": "US", "value": "United States"},
            "countryiso3code": "USA",
            "date": str(year),
            "value": value,
            "unit": "",
            "obs_status": "",
            "decimal": 0,
        }
        for year, value in [(2023, 334017321), (2024, 336806231)]
    ]
    raw_text = json.dumps([{"page": 1, "pages": 1, "total": 2}, records])
    documents = spark.createDataFrame(
        [("s3://example.test/page-1.json", raw_text)],
        ["source_file", "raw_text"],
    )

    transformed = transform_world_bank_documents(spark, documents)
    result = evaluate_data_quality(
        transformed.processed,
        transformed.rejected,
        run_id="run_test_world_bank",
        config=WORLD_BANK_QUALITY_CONFIG,
        expected_row_count=expected_world_bank_row_count(documents),
        evaluated_at=EVALUATED_AT,
    )

    assert result.status == "PASS"
    assert result.row_count == 2
    assert result.row_count_match is True
