from __future__ import annotations

from unittest.mock import Mock

import pytest
import requests

from ingestion.api_client import ApiResponseError, WorldBankApiClient


def _record(value: float | None = 1) -> dict[str, object]:
    return {
        "country": {"id": "US", "value": "United States"},
        "countryiso3code": "USA",
        "date": "2023",
        "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
        "value": value,
    }


def _response(payload: object, raw_text: str = "raw") -> Mock:
    response = Mock()
    response.status_code = 200
    response.text = raw_text
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def test_fetch_indicator_page_returns_validated_page() -> None:
    payload = [
        {"page": 1, "pages": 3, "per_page": 1, "total": 3},
        [_record(100)],
    ]
    session = Mock()
    session.get.return_value = _response(payload, raw_text='[{"original":true}]')
    client = WorldBankApiClient("https://example.test/v2", 5, session=session)

    result = client.fetch_indicator_page(country="all", indicator="SP.POP.TOTL", page=1, per_page=1)

    assert result.page == 1
    assert result.total_pages == 3
    assert len(result.records) == 1
    assert result.raw_text == '[{"original":true}]'
    session.get.assert_called_once_with(
        "https://example.test/v2/country/all/indicator/SP.POP.TOTL",
        params={"format": "json", "page": 1, "per_page": 1},
        timeout=5,
    )


def test_fetch_indicator_page_rejects_wrong_response_shape() -> None:
    session = Mock()
    session.get.return_value = _response({"unexpected": "object"})
    client = WorldBankApiClient("https://example.test/v2", 5, session=session)

    with pytest.raises(ApiResponseError, match="two-item"):
        client.fetch_indicator_page(country="all", indicator="SP.POP.TOTL", page=1, per_page=1)


def test_fetch_indicator_page_rejects_http_failure() -> None:
    response = _response([])
    response.status_code = 404
    response.raise_for_status.side_effect = requests.HTTPError("unavailable")
    session = Mock()
    session.get.return_value = response
    client = WorldBankApiClient("https://example.test/v2", 5, session=session)

    with pytest.raises(ApiResponseError, match="HTTP 404"):
        client.fetch_indicator_page(country="all", indicator="SP.POP.TOTL", page=1, per_page=1)


def test_fetch_indicator_page_reports_timeout() -> None:
    session = Mock()
    session.get.side_effect = requests.Timeout("slow source")
    client = WorldBankApiClient("https://example.test/v2", 5, session=session, max_attempts=1)

    with pytest.raises(ApiResponseError, match="failed after 1 attempts: Timeout"):
        client.fetch_indicator_page(country="USA", indicator="SP.POP.TOTL", page=1, per_page=1)


def test_fetch_indicator_pages_requests_every_page() -> None:
    session = Mock()
    session.get.side_effect = [
        _response([{"page": 1, "pages": 2, "per_page": 1, "total": 2}, [_record(1)]]),
        _response([{"page": 2, "pages": 2, "per_page": 1, "total": 2}, [_record(2)]]),
    ]
    client = WorldBankApiClient("https://example.test/v2", 5, session=session, max_attempts=1)

    pages = list(
        client.fetch_indicator_pages(
            country="USA", indicator="SP.POP.TOTL", start_page=1, per_page=1
        )
    )

    assert [page.page for page in pages] == [1, 2]
    assert [call.kwargs["params"]["page"] for call in session.get.call_args_list] == [1, 2]


def test_fetch_indicator_page_retries_timeout_with_exponential_backoff() -> None:
    session = Mock()
    session.get.side_effect = [
        requests.Timeout("slow source"),
        _response([{"page": 1, "pages": 1, "per_page": 1, "total": 1}, [_record(1)]]),
    ]
    sleep = Mock()
    client = WorldBankApiClient(
        "https://example.test/v2",
        5,
        session=session,
        max_attempts=3,
        backoff_base_seconds=0.5,
        sleep=sleep,
    )

    page = client.fetch_indicator_page(country="USA", indicator="SP.POP.TOTL", page=1, per_page=1)

    assert page.page == 1
    assert session.get.call_count == 2
    sleep.assert_called_once_with(0.5)


def test_fetch_indicator_page_retries_retryable_http_status() -> None:
    unavailable = _response([])
    unavailable.status_code = 503
    success = _response([{"page": 1, "pages": 1, "per_page": 1, "total": 1}, [_record(1)]])
    session = Mock()
    session.get.side_effect = [unavailable, success]
    sleep = Mock()
    client = WorldBankApiClient("https://example.test/v2", 5, session=session, sleep=sleep)

    page = client.fetch_indicator_page(country="USA", indicator="SP.POP.TOTL", page=1, per_page=1)

    assert page.page == 1
    assert session.get.call_count == 2
    sleep.assert_called_once_with(1.0)


def test_fetch_indicator_page_rejects_record_schema_drift() -> None:
    invalid_record = _record()
    del invalid_record["countryiso3code"]
    session = Mock()
    session.get.return_value = _response(
        [{"page": 1, "pages": 1, "per_page": 1, "total": 1}, [invalid_record]]
    )
    client = WorldBankApiClient("https://example.test/v2", 5, session=session)

    with pytest.raises(ApiResponseError, match="missing required fields: countryiso3code"):
        client.fetch_indicator_page(country="USA", indicator="SP.POP.TOTL", page=1, per_page=1)
