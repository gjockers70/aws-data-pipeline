"""Serializable data-quality result models."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

QualityStatus = Literal["PASS", "FAIL"]


@dataclass(frozen=True)
class RuleResult:
    rule: str
    status: QualityStatus
    failures: int
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DataQualityResult:
    dataset: str
    run_id: str
    row_count: int
    rejected_row_count: int
    expected_row_count: int | None
    row_count_match: bool
    null_failures: int
    duplicate_failures: int
    invalid_type_failures: int
    missing_column_failures: int
    invalid_enum_failures: int
    schema_drift: bool
    schema_drift_rows: int
    status: QualityStatus
    evaluated_at: str
    rules: tuple[RuleResult, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
