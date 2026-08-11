from __future__ import annotations

import logging
from dataclasses import dataclass
from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from ingestion.api_client import ApiResponseError
from ingestion.lambda_handler import LambdaEventError, handle_event
from ingestion.models import ApiPage


@dataclass
class StubContext:
    aws_request_id: str = "lambda-request-123"


class StubClient:
    def __init__(self, pages: list[ApiPage], failure: Exception | None = None) -> None:
        self.pages = pages
        self.failure = failure
        self.request: dict[str, object] | None = None

    def fetch_indicator_pages(self, **request):
        self.request = request
        yield from self.pages
        if self.failure:
            raise self.failure


class MemoryS3Client:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], dict[str, object]] = {}

    def put_object(self, **request):
        object_id = (request["Bucket"], request["Key"])
        if request.get("IfNoneMatch") == "*" and object_id in self.objects:
            raise ClientError(
                {"Error": {"Code": "PreconditionFailed", "Message": "already exists"}},
                "PutObject",
            )
        self.objects[object_id] = {
            "Body": bytes(request["Body"]),
            "Metadata": request.get("Metadata", {}),
        }

    def head_object(self, *, Bucket, Key):
        return {"Metadata": self.objects[(Bucket, Key)]["Metadata"]}

    def get_object(self, *, Bucket, Key):
        try:
            stored = self.objects[(Bucket, Key)]
        except KeyError as exc:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "missing"}},
                "GetObject",
            ) from exc
        return {"Body": BytesIO(stored["Body"])}


def _page(page: int, pages: int, records: int, raw_text: str) -> ApiPage:
    return ApiPage(
        raw_text=raw_text,
        metadata={"page": page, "pages": pages, "per_page": records, "total": records},
        records=[{"value": index} for index in range(records)],
    )


def _logger() -> logging.Logger:
    logger = logging.getLogger("test-lambda-handler")
    logger.handlers.clear()
    logger.addHandler(logging.NullHandler())
    return logger


def test_handle_event_uses_overrides_and_returns_counts(monkeypatch) -> None:
    monkeypatch.setenv("WORLD_BANK_API_BASE_URL", "https://example.test/v2")
    monkeypatch.setenv("LANDING_BUCKET", "test-bucket")
    client = StubClient([_page(2, 3, 2, "one"), _page(3, 3, 1, "second")])
    factory_calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def factory(*args, **kwargs):
        factory_calls.append((args, kwargs))
        return client

    result = handle_event(
        {
            "run_id": "scheduled-run-1",
            "country": "CAN",
            "indicator": "SP.POP.TOTL",
            "start_page": 2,
            "per_page": 2,
        },
        StubContext(),
        client_factory=factory,
        s3_client=MemoryS3Client(),
        logger=_logger(),
    )

    assert result == {
        "status": "COMPLETED",
        "run_id": "scheduled-run-1",
        "country": "CAN",
        "indicator": "SP.POP.TOTL",
        "pages": 2,
        "records": 3,
        "source_bytes": 9,
        "landing_status": "S3_PERSISTED",
        "manifest_uri": "s3://test-bucket/manifests/world_bank/run_id=scheduled-run-1.json",
        "replayed": False,
    }
    assert client.request == {
        "country": "CAN",
        "indicator": "SP.POP.TOTL",
        "start_page": 2,
        "per_page": 2,
    }
    assert factory_calls[0][0] == ("https://example.test/v2", 30.0)


def test_handle_event_uses_lambda_request_id_by_default(monkeypatch) -> None:
    monkeypatch.setenv("LANDING_BUCKET", "test-bucket")
    client = StubClient([_page(1, 1, 1, "payload")])

    result = handle_event(
        {},
        StubContext(),
        client_factory=lambda *_args, **_kwargs: client,
        s3_client=MemoryS3Client(),
        logger=_logger(),
    )

    assert result["run_id"] == "lambda-request-123"


@pytest.mark.parametrize(
    "event, message",
    [
        (["not", "an", "object"], "must be a JSON object"),
        ({"secret": "do-not-accept"}, "unsupported fields: secret"),
        ({"country": "USA/../../"}, "country contains unsupported"),
        ({"per_page": True}, "per_page must be a positive integer"),
    ],
)
def test_handle_event_rejects_invalid_events(event, message) -> None:
    with pytest.raises(LambdaEventError, match=message):
        handle_event(event, StubContext(), logger=_logger())


def test_handle_event_reraises_source_failure(monkeypatch) -> None:
    monkeypatch.setenv("LANDING_BUCKET", "test-bucket")
    client = StubClient([], ApiResponseError("source unavailable"))

    with pytest.raises(ApiResponseError, match="source unavailable"):
        handle_event(
            {},
            StubContext(),
            client_factory=lambda *_args, **_kwargs: client,
            s3_client=MemoryS3Client(),
            logger=_logger(),
        )
