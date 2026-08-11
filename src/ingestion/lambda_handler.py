from __future__ import annotations

import logging
import re
from collections.abc import Callable, Mapping
from typing import Any
from uuid import uuid4

from ingestion.api_client import WorldBankApiClient
from ingestion.config import IngestionConfig
from ingestion.identifiers import validate_run_id
from ingestion.structured_logging import configure_logging, log_event

ALLOWED_EVENT_FIELDS = frozenset({"run_id", "country", "indicator", "start_page", "per_page"})
COUNTRY_PATTERN = re.compile(r"^[A-Za-z0-9;]{2,64}$")
INDICATOR_PATTERN = re.compile(r"^[A-Za-z0-9.]{2,64}$")


class LambdaEventError(ValueError):
    """Raised when an invocation event violates the supported contract."""


def lambda_handler(event: object, context: object) -> dict[str, Any]:
    return handle_event(event, context)


def handle_event(
    event: object,
    context: object,
    *,
    client_factory: Callable[..., WorldBankApiClient] = WorldBankApiClient,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    active_logger = logger or configure_logging()
    try:
        invocation = _validate_event(event)
        config = IngestionConfig.from_environment()
    except (LambdaEventError, ValueError) as exc:
        log_event(
            active_logger,
            "lambda_event_rejected",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise

    run_id = invocation.get("run_id") or getattr(context, "aws_request_id", None) or str(uuid4())
    validate_run_id(run_id)
    country = invocation.get("country", config.country)
    indicator = invocation.get("indicator", config.indicator)
    start_page = invocation.get("start_page", config.page)
    per_page = invocation.get("per_page", config.per_page)

    _validate_source_identifiers(country, indicator)
    start_page = _positive_event_integer("start_page", start_page)
    per_page = _positive_event_integer("per_page", per_page)

    client = client_factory(
        config.api_base_url,
        config.timeout_seconds,
        max_attempts=config.max_attempts,
        backoff_base_seconds=config.backoff_base_seconds,
    )
    page_count = 0
    record_count = 0
    source_bytes = 0

    log_event(
        active_logger,
        "lambda_run_started",
        run_id=run_id,
        country=country,
        indicator=indicator,
    )
    try:
        for api_page in client.fetch_indicator_pages(
            country=country,
            indicator=indicator,
            start_page=start_page,
            per_page=per_page,
        ):
            page_records = len(api_page.records)
            page_count += 1
            record_count += page_records
            source_bytes += len(api_page.raw_text.encode("utf-8"))
            log_event(
                active_logger,
                "lambda_page_validated",
                run_id=run_id,
                page=api_page.page,
                records=page_records,
            )
    except Exception as exc:
        log_event(
            active_logger,
            "lambda_run_failed",
            run_id=run_id,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
        raise

    result = {
        "status": "COMPLETED",
        "run_id": run_id,
        "country": country,
        "indicator": indicator,
        "pages": page_count,
        "records": record_count,
        "source_bytes": source_bytes,
        "landing_status": "DEFERRED_TO_PHASE_3",
    }
    log_event(
        active_logger,
        "lambda_run_completed",
        run_id=run_id,
        pages=page_count,
        records=record_count,
        source_bytes=source_bytes,
    )
    return result


def _validate_event(event: object) -> dict[str, Any]:
    if event is None:
        return {}
    if not isinstance(event, Mapping):
        raise LambdaEventError("Lambda event must be a JSON object")

    invocation = dict(event)
    unknown = invocation.keys() - ALLOWED_EVENT_FIELDS
    if unknown:
        fields = ", ".join(sorted(unknown))
        raise LambdaEventError(f"Lambda event contains unsupported fields: {fields}")
    return invocation


def _validate_source_identifiers(country: object, indicator: object) -> None:
    if not isinstance(country, str) or not COUNTRY_PATTERN.fullmatch(country):
        raise LambdaEventError("country contains unsupported characters")
    if not isinstance(indicator, str) or not INDICATOR_PATTERN.fullmatch(indicator):
        raise LambdaEventError("indicator contains unsupported characters")


def _positive_event_integer(name: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise LambdaEventError(f"{name} must be a positive integer")
    return value
