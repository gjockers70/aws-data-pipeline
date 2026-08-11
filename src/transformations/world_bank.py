"""Normalize World Bank API documents into processed and rejected datasets."""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from pyspark.sql import DataFrame, SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    ArrayType,
    BooleanType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)
from pyspark.sql.window import Window

EXPECTED_RECORD_FIELDS = {
    "indicator",
    "country",
    "countryiso3code",
    "date",
    "value",
    "unit",
    "obs_status",
    "decimal",
}
EXPECTED_NESTED_FIELDS = {"id", "value"}
BUSINESS_KEY = ["country_iso3_code", "indicator_id", "observation_year"]

PARSED_SCHEMA = StructType(
    [
        StructField("record_type", StringType(), nullable=False),
        StructField("source_file", StringType(), nullable=False),
        StructField("source_record_index", IntegerType(), nullable=True),
        StructField("rejection_reason", StringType(), nullable=True),
        StructField("raw_record", StringType(), nullable=True),
        StructField("indicator_id_raw", StringType(), nullable=True),
        StructField("indicator_name_raw", StringType(), nullable=True),
        StructField("country_id_raw", StringType(), nullable=True),
        StructField("country_name_raw", StringType(), nullable=True),
        StructField("country_iso3_code_raw", StringType(), nullable=True),
        StructField("observation_year_raw", StringType(), nullable=True),
        StructField("observation_value_raw", StringType(), nullable=True),
        StructField("unit_raw", StringType(), nullable=True),
        StructField("observation_status_raw", StringType(), nullable=True),
        StructField("decimal_places_raw", StringType(), nullable=True),
        StructField("schema_drift", BooleanType(), nullable=False),
        StructField(
            "schema_drift_fields",
            ArrayType(StringType(), containsNull=False),
            nullable=False,
        ),
    ]
)

REJECTED_COLUMNS = [
    "source_file",
    "source_record_index",
    "rejection_reason",
    "raw_record",
    "schema_drift",
    "schema_drift_fields",
]


@dataclass(frozen=True)
class TransformResult:
    processed: DataFrame
    rejected: DataFrame


def _string_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def _event(
    *,
    record_type: str,
    source_file: str,
    source_record_index: int | None,
    rejection_reason: str | None = None,
    raw_record: str | None = None,
    schema_drift_fields: Iterable[str] = (),
    **values: str | None,
) -> dict[str, Any]:
    drift_fields = sorted(schema_drift_fields)
    event: dict[str, Any] = {
        "record_type": record_type,
        "source_file": source_file,
        "source_record_index": source_record_index,
        "rejection_reason": rejection_reason,
        "raw_record": raw_record,
        "indicator_id_raw": None,
        "indicator_name_raw": None,
        "country_id_raw": None,
        "country_name_raw": None,
        "country_iso3_code_raw": None,
        "observation_year_raw": None,
        "observation_value_raw": None,
        "unit_raw": None,
        "observation_status_raw": None,
        "decimal_places_raw": None,
        "schema_drift": bool(drift_fields),
        "schema_drift_fields": drift_fields,
    }
    event.update(values)
    return event


def parse_world_bank_document(raw_text: str, source_file: str) -> list[dict[str, Any]]:
    """Parse one raw API response while retaining enough context for rejections."""
    try:
        payload = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError) as exc:
        return [
            _event(
                record_type="rejected",
                source_file=source_file,
                source_record_index=None,
                rejection_reason=f"MALFORMED_JSON: {exc.msg if hasattr(exc, 'msg') else exc}",
                raw_record=raw_text,
            )
        ]

    if not isinstance(payload, list) or len(payload) != 2 or not isinstance(payload[1], list):
        return [
            _event(
                record_type="rejected",
                source_file=source_file,
                source_record_index=None,
                rejection_reason="INVALID_DOCUMENT_SHAPE",
                raw_record=json.dumps(payload, separators=(",", ":"), sort_keys=True),
            )
        ]

    events: list[dict[str, Any]] = []
    for index, record in enumerate(payload[1]):
        raw_record = json.dumps(record, separators=(",", ":"), sort_keys=True)
        if not isinstance(record, dict):
            events.append(
                _event(
                    record_type="rejected",
                    source_file=source_file,
                    source_record_index=index,
                    rejection_reason="RECORD_NOT_OBJECT",
                    raw_record=raw_record,
                )
            )
            continue

        indicator = record.get("indicator")
        country = record.get("country")
        if not isinstance(indicator, dict) or not isinstance(country, dict):
            events.append(
                _event(
                    record_type="rejected",
                    source_file=source_file,
                    source_record_index=index,
                    rejection_reason="INVALID_NESTED_OBJECT",
                    raw_record=raw_record,
                )
            )
            continue

        drift_fields = {f"record.{name}" for name in record.keys() - EXPECTED_RECORD_FIELDS}
        drift_fields.update(
            f"indicator.{name}" for name in indicator.keys() - EXPECTED_NESTED_FIELDS
        )
        drift_fields.update(f"country.{name}" for name in country.keys() - EXPECTED_NESTED_FIELDS)

        events.append(
            _event(
                record_type="candidate",
                source_file=source_file,
                source_record_index=index,
                raw_record=raw_record,
                schema_drift_fields=drift_fields,
                indicator_id_raw=_string_value(indicator.get("id")),
                indicator_name_raw=_string_value(indicator.get("value")),
                country_id_raw=_string_value(country.get("id")),
                country_name_raw=_string_value(country.get("value")),
                country_iso3_code_raw=_string_value(record.get("countryiso3code")),
                observation_year_raw=_string_value(record.get("date")),
                observation_value_raw=_string_value(record.get("value")),
                unit_raw=_string_value(record.get("unit")),
                observation_status_raw=_string_value(record.get("obs_status")),
                decimal_places_raw=_string_value(record.get("decimal")),
            )
        )
    return events


def _parse_partition(rows: Iterator[Any]) -> Iterator[dict[str, Any]]:
    for row in rows:
        yield from parse_world_bank_document(row.raw_text, row.source_file)


def read_world_bank_documents(spark: SparkSession, input_path: str) -> DataFrame:
    """Read each source object as one UTF-8 document instead of line-delimited JSON."""
    return (
        spark.read.format("binaryFile")
        .option("recursiveFileLookup", "true")
        .load(input_path)
        .select(F.col("path").alias("source_file"), F.decode("content", "UTF-8").alias("raw_text"))
    )


def transform_world_bank_documents(
    spark: SparkSession,
    documents: DataFrame,
) -> TransformResult:
    """Flatten, cast, validate, and deduplicate raw World Bank API documents."""
    required_columns = {"source_file", "raw_text"}
    missing_columns = required_columns - set(documents.columns)
    if missing_columns:
        raise ValueError(f"Documents DataFrame is missing columns: {sorted(missing_columns)}")

    parsed = spark.createDataFrame(documents.rdd.mapPartitions(_parse_partition), PARSED_SCHEMA)
    parser_rejected = parsed.filter(F.col("record_type") == "rejected").select(*REJECTED_COLUMNS)

    candidates = (
        parsed.filter(F.col("record_type") == "candidate")
        .withColumn("indicator_id", F.trim("indicator_id_raw"))
        .withColumn("indicator_name", F.trim("indicator_name_raw"))
        .withColumn("country_id", F.upper(F.trim("country_id_raw")))
        .withColumn("country_name", F.trim("country_name_raw"))
        .withColumn("country_iso3_code", F.upper(F.trim("country_iso3_code_raw")))
        .withColumn("observation_year", F.col("observation_year_raw").cast("int"))
        .withColumn("observation_value", F.col("observation_value_raw").cast("double"))
        .withColumn("unit", F.trim("unit_raw"))
        .withColumn("observation_status", F.trim("observation_status_raw"))
        .withColumn("decimal_places", F.col("decimal_places_raw").cast("int"))
    )

    validation_reason = (
        F.when(F.col("indicator_id").isNull() | (F.col("indicator_id") == ""), "NULL_INDICATOR_ID")
        .when(
            F.col("country_iso3_code").isNull() | (F.col("country_iso3_code") == ""),
            "NULL_COUNTRY_ISO3_CODE",
        )
        .when(F.col("observation_year_raw").isNull(), "NULL_OBSERVATION_YEAR")
        .when(F.col("observation_year").isNull(), "INVALID_OBSERVATION_YEAR")
        .when(F.col("observation_value_raw").isNull(), "NULL_OBSERVATION_VALUE")
        .when(F.col("observation_value").isNull(), "INVALID_OBSERVATION_VALUE")
        .when(
            F.col("decimal_places_raw").isNotNull() & F.col("decimal_places").isNull(),
            "INVALID_DECIMAL_PLACES",
        )
    )
    candidates = candidates.withColumn("validation_reason", validation_reason)

    validation_rejected = (
        candidates.filter(F.col("validation_reason").isNotNull())
        .withColumn("rejection_reason", F.col("validation_reason"))
        .select(*REJECTED_COLUMNS)
    )
    valid = candidates.filter(F.col("validation_reason").isNull())

    duplicate_window = Window.partitionBy(*BUSINESS_KEY).orderBy(
        F.col("source_file"), F.col("source_record_index")
    )
    ranked = valid.withColumn("duplicate_rank", F.row_number().over(duplicate_window))
    duplicate_rejected = (
        ranked.filter(F.col("duplicate_rank") > 1)
        .withColumn("rejection_reason", F.lit("DUPLICATE_BUSINESS_KEY"))
        .select(*REJECTED_COLUMNS)
    )

    processed = ranked.filter(F.col("duplicate_rank") == 1).select(
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
    )
    rejected = parser_rejected.unionByName(validation_rejected).unionByName(duplicate_rejected)
    return TransformResult(processed=processed, rejected=rejected)


def write_transform_result(
    result: TransformResult,
    processed_path: str,
    rejected_path: str,
    *,
    mode: str = "errorifexists",
) -> None:
    """Write analytics-ready Parquet and inspectable JSON rejection records."""
    result.processed.write.mode(mode).partitionBy("observation_year").parquet(processed_path)
    result.rejected.write.mode(mode).json(rejected_path)
