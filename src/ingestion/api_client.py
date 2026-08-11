from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

from ingestion.models import ApiPage


class ApiResponseError(RuntimeError):
    """Raised when the API returns an unusable response."""


RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})


class WorldBankApiClient:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        session: requests.Session | None = None,
        max_attempts: int = 3,
        backoff_base_seconds: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if max_attempts <= 0:
            raise ValueError("max_attempts must be greater than zero")
        if backoff_base_seconds <= 0:
            raise ValueError("backoff_base_seconds must be greater than zero")

        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = session or requests.Session()
        self._max_attempts = max_attempts
        self._backoff_base_seconds = backoff_base_seconds
        self._sleep = sleep

    def fetch_indicator_pages(
        self,
        *,
        country: str,
        indicator: str,
        start_page: int,
        per_page: int,
    ) -> Iterator[ApiPage]:
        requested_page = start_page

        while True:
            api_page = self.fetch_indicator_page(
                country=country,
                indicator=indicator,
                page=requested_page,
                per_page=per_page,
            )
            if api_page.page != requested_page:
                raise ApiResponseError(
                    f"Requested page {requested_page}, but the API returned page {api_page.page}"
                )

            yield api_page
            if api_page.page >= api_page.total_pages:
                return
            requested_page += 1

    def fetch_indicator_page(
        self,
        *,
        country: str,
        indicator: str,
        page: int,
        per_page: int,
    ) -> ApiPage:
        url = f"{self._base_url}/country/{country}/indicator/{indicator}"
        response = self._get_with_retries(
            url,
            params={"format": "json", "page": page, "per_page": per_page},
        )

        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            raise ApiResponseError(f"World Bank API returned HTTP {response.status_code}") from exc

        try:
            payload: Any = response.json()
        except requests.JSONDecodeError as exc:
            raise ApiResponseError("World Bank API returned invalid JSON") from exc

        metadata, records = _validate_payload(payload)
        return ApiPage(raw_text=response.text, metadata=metadata, records=records)

    def _get_with_retries(self, url: str, *, params: dict[str, Any]) -> requests.Response:
        for attempt in range(1, self._max_attempts + 1):
            try:
                response = self._session.get(
                    url,
                    params=params,
                    timeout=self._timeout_seconds,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt == self._max_attempts:
                    raise ApiResponseError(
                        "World Bank API request failed after "
                        f"{self._max_attempts} attempts: {type(exc).__name__}"
                    ) from exc
                self._sleep(self._backoff_seconds(attempt))
                continue
            except requests.RequestException as exc:
                raise ApiResponseError("World Bank API request failed") from exc

            if response.status_code not in RETRYABLE_STATUS_CODES:
                return response
            if attempt == self._max_attempts:
                return response

            self._sleep(self._backoff_seconds(attempt))

        raise AssertionError("retry loop completed without a response")

    def _backoff_seconds(self, failed_attempt: int) -> float:
        return self._backoff_base_seconds * (2 ** (failed_attempt - 1))


def _validate_payload(payload: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not isinstance(payload, list) or len(payload) != 2:
        raise ApiResponseError("Expected a two-item World Bank response array")

    metadata, records = payload
    if not isinstance(metadata, dict):
        raise ApiResponseError("Expected response metadata to be an object")
    if not isinstance(records, list):
        raise ApiResponseError("Expected response records to be an array")

    missing_metadata = {"page", "pages", "per_page", "total"} - metadata.keys()
    if missing_metadata:
        missing = ", ".join(sorted(missing_metadata))
        raise ApiResponseError(f"Response metadata is missing fields: {missing}")
    if any(not isinstance(record, dict) for record in records):
        raise ApiResponseError("Expected every response record to be an object")

    _validate_metadata_numbers(metadata)
    for index, record in enumerate(records):
        _validate_record(record, index)

    return metadata, records


def _validate_metadata_numbers(metadata: dict[str, Any]) -> None:
    for field in ("page", "pages", "per_page", "total"):
        try:
            value = int(metadata[field])
        except (TypeError, ValueError) as exc:
            raise ApiResponseError(f"Response metadata field {field} must be an integer") from exc
        minimum = 0 if field == "total" else 1
        if value < minimum:
            raise ApiResponseError(f"Response metadata field {field} must be at least {minimum}")


def _validate_record(record: dict[str, Any], index: int) -> None:
    required = {"country", "countryiso3code", "date", "indicator", "value"}
    missing = required - record.keys()
    if missing:
        fields = ", ".join(sorted(missing))
        raise ApiResponseError(f"Record {index} is missing required fields: {fields}")

    for field in ("country", "indicator"):
        nested = record[field]
        if not isinstance(nested, dict) or not isinstance(nested.get("id"), str):
            raise ApiResponseError(f"Record {index} field {field} must contain a string id")
        if not isinstance(nested.get("value"), str):
            raise ApiResponseError(f"Record {index} field {field} must contain a string value")

    if not isinstance(record["countryiso3code"], str) or not record["countryiso3code"]:
        raise ApiResponseError(f"Record {index} field countryiso3code must be a non-empty string")
    if not isinstance(record["date"], str) or not record["date"]:
        raise ApiResponseError(f"Record {index} field date must be a non-empty string")
    value = record["value"]
    if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
        raise ApiResponseError(f"Record {index} field value must be numeric or null")
