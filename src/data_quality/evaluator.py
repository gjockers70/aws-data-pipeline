"""Evaluate reusable PySpark data-quality rules with bounded Spark actions."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from functools import reduce

from pyspark.sql import DataFrame
from pyspark.sql import functions as F

from data_quality.models import DataQualityResult, RuleResult


@dataclass(frozen=True)
class DataQualityConfig:
    dataset: str
    required_columns: tuple[str, ...]
    business_key: tuple[str, ...]
    expected_types: Mapping[str, str]
    allowed_values: Mapping[str, frozenset[str]] = field(default_factory=dict)
    minimum_row_count: int = 1
    require_expected_row_count: bool = True
    fail_on_rejected_rows: bool = True
    maximum_schema_drift_rows: int = 0


def _rule(rule: str, failures: int, **details: object) -> RuleResult:
    return RuleResult(
        rule=rule,
        status="PASS" if failures == 0 else "FAIL",
        failures=failures,
        details=dict(details),
    )


def _combined_or(expressions: list[object]) -> object | None:
    if not expressions:
        return None
    return reduce(lambda left, right: left | right, expressions)


def evaluate_data_quality(
    processed: DataFrame,
    rejected: DataFrame,
    *,
    run_id: str,
    config: DataQualityConfig,
    expected_row_count: int | None,
    evaluated_at: datetime | None = None,
) -> DataQualityResult:
    """Evaluate schema and row rules and return one serializable run result."""
    actual_types = dict(processed.dtypes)
    missing_columns = sorted(set(config.expected_types) - set(processed.columns))
    invalid_type_columns = sorted(
        column
        for column, expected_type in config.expected_types.items()
        if column in actual_types and actual_types[column] != expected_type
    )

    required_existing = [
        column for column in config.required_columns if column in processed.columns
    ]
    null_expressions = []
    for column in required_existing:
        expression = F.col(column).isNull()
        if actual_types.get(column) == "string":
            expression = expression | (F.trim(F.col(column)) == "")
        null_expressions.append(expression)

    enum_expressions = [
        F.col(column).isNotNull() & ~F.col(column).isin(sorted(allowed))
        for column, allowed in config.allowed_values.items()
        if column in processed.columns
    ]
    schema_drift_expression = (
        F.col("schema_drift") if "schema_drift" in processed.columns else F.lit(False)
    )

    aggregate_expressions = [F.count(F.lit(1)).alias("row_count")]
    null_condition = _combined_or(null_expressions)
    enum_condition = _combined_or(enum_expressions)
    aggregate_expressions.extend(
        [
            F.coalesce(
                F.sum(F.when(null_condition, 1).otherwise(0))
                if null_condition is not None
                else F.lit(0),
                F.lit(0),
            ).alias("null_failures"),
            F.coalesce(
                F.sum(F.when(enum_condition, 1).otherwise(0))
                if enum_condition is not None
                else F.lit(0),
                F.lit(0),
            ).alias("invalid_enum_failures"),
            F.coalesce(
                F.sum(F.when(schema_drift_expression, 1).otherwise(0)),
                F.lit(0),
            ).alias("schema_drift_rows"),
        ]
    )
    metrics = processed.agg(*aggregate_expressions).first()
    row_count = int(metrics.row_count)
    if "rejection_reason" in rejected.columns:
        rejected_metrics = rejected.agg(
            F.count(F.lit(1)).alias("row_count"),
            F.coalesce(
                F.sum(F.when(F.col("rejection_reason").startswith("NULL_"), 1).otherwise(0)),
                F.lit(0),
            ).alias("null_failures"),
            F.coalesce(
                F.sum(
                    F.when(
                        F.col("rejection_reason") == "DUPLICATE_BUSINESS_KEY",
                        1,
                    ).otherwise(0)
                ),
                F.lit(0),
            ).alias("duplicate_failures"),
            F.coalesce(
                F.sum(F.when(F.col("rejection_reason").startswith("INVALID_"), 1).otherwise(0)),
                F.lit(0),
            ).alias("invalid_type_failures"),
        ).first()
    else:
        rejected_metrics = rejected.agg(F.count(F.lit(1)).alias("row_count")).first()
    rejected_row_count = int(rejected_metrics.row_count)

    business_key_exists = all(column in processed.columns for column in config.business_key)
    duplicate_failures = int(getattr(rejected_metrics, "duplicate_failures", 0))
    if business_key_exists:
        duplicate_total = (
            processed.groupBy(*config.business_key)
            .count()
            .filter(F.col("count") > 1)
            .agg(F.coalesce(F.sum(F.col("count") - 1), F.lit(0)).alias("failures"))
            .first()
        )
        duplicate_failures += int(duplicate_total.failures)

    null_failures = int(metrics.null_failures) + int(getattr(rejected_metrics, "null_failures", 0))
    invalid_enum_failures = int(metrics.invalid_enum_failures)
    schema_drift_rows = int(metrics.schema_drift_rows)
    missing_column_failures = len(missing_columns)
    invalid_type_failures = len(invalid_type_columns) + int(
        getattr(rejected_metrics, "invalid_type_failures", 0)
    )

    expected_available = expected_row_count is not None
    row_count_match = expected_available and (row_count + rejected_row_count == expected_row_count)
    row_count_failures = int(row_count < config.minimum_row_count)
    if config.require_expected_row_count or expected_available:
        row_count_failures += int(not row_count_match)

    rejected_failures = rejected_row_count if config.fail_on_rejected_rows else 0
    schema_drift_failures = max(
        0,
        schema_drift_rows - config.maximum_schema_drift_rows,
    )
    rules = (
        _rule("required_columns", missing_column_failures, missing_columns=missing_columns),
        _rule(
            "column_types",
            invalid_type_failures,
            invalid_columns=invalid_type_columns,
            expected_types=dict(config.expected_types),
        ),
        _rule(
            "row_count",
            row_count_failures,
            processed_rows=row_count,
            rejected_rows=rejected_row_count,
            expected_rows=expected_row_count,
            minimum_rows=config.minimum_row_count,
        ),
        _rule("required_nulls", null_failures, required_columns=list(config.required_columns)),
        _rule("duplicate_business_keys", duplicate_failures, key=list(config.business_key)),
        _rule(
            "allowed_values",
            invalid_enum_failures,
            columns=sorted(config.allowed_values),
        ),
        _rule(
            "schema_drift",
            schema_drift_failures,
            observed_rows=schema_drift_rows,
            maximum_rows=config.maximum_schema_drift_rows,
        ),
        _rule("rejected_rows", rejected_failures, observed_rows=rejected_row_count),
    )
    status = "PASS" if all(rule.status == "PASS" for rule in rules) else "FAIL"
    timestamp = evaluated_at or datetime.now(UTC)
    return DataQualityResult(
        dataset=config.dataset,
        run_id=run_id,
        row_count=row_count,
        rejected_row_count=rejected_row_count,
        expected_row_count=expected_row_count,
        row_count_match=row_count_match,
        null_failures=null_failures,
        duplicate_failures=duplicate_failures,
        invalid_type_failures=invalid_type_failures,
        missing_column_failures=missing_column_failures,
        invalid_enum_failures=invalid_enum_failures,
        schema_drift=schema_drift_rows > 0,
        schema_drift_rows=schema_drift_rows,
        status=status,
        evaluated_at=timestamp.isoformat(),
        rules=rules,
    )
