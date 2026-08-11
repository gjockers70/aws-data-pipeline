from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

import pytest

from ingestion.api_client import ApiResponseError
from ingestion.config import IngestionConfig
from ingestion.landing_writer import LocalLandingWriter
from ingestion.manifest_store import LocalManifestStore
from ingestion.models import ApiPage
from ingestion.runner import IngestionRunner, RunConflictError

FIXED_TIME = datetime(2026, 8, 11, 12, 0, tzinfo=UTC)


def _config(tmp_path, *, run_id: str = "test-run", country: str = "USA") -> IngestionConfig:
    return IngestionConfig(
        api_base_url="https://example.test/v2",
        country=country,
        indicator="SP.POP.TOTL",
        page=1,
        per_page=1,
        timeout_seconds=5,
        max_attempts=1,
        backoff_base_seconds=1,
        run_id=run_id,
        landing_root=tmp_path / "landing",
        manifest_root=tmp_path / "manifests",
    )


def _page(page: int, total_pages: int, raw_text: str) -> ApiPage:
    return ApiPage(
        raw_text=raw_text,
        metadata={"page": page, "pages": total_pages, "per_page": 1, "total": total_pages},
        records=[{"value": page}],
    )


class StubClient:
    def __init__(self, pages: list[ApiPage], failure: Exception | None = None) -> None:
        self.pages = pages
        self.failure = failure
        self.calls = 0

    def fetch_indicator_pages(self, **_kwargs):
        self.calls += 1
        yield from self.pages
        if self.failure:
            raise self.failure


def _runner(config: IngestionConfig, client: StubClient) -> IngestionRunner:
    logger = logging.getLogger(f"test-runner-{id(client)}")
    logger.addHandler(logging.NullHandler())
    return IngestionRunner(
        config=config,
        client=client,  # type: ignore[arg-type]
        writer=LocalLandingWriter(config.landing_root),
        manifest_store=LocalManifestStore(config.manifest_root),
        logger=logger,
        clock=lambda: FIXED_TIME,
    )


def test_runner_writes_completed_manifest_and_skips_completed_replay(tmp_path) -> None:
    config = _config(tmp_path)
    first_client = StubClient([_page(1, 2, "page-one"), _page(2, 2, "page-two")])

    first = _runner(config, first_client).run()
    replay_client = StubClient([], failure=AssertionError("API should not be called"))
    replay = _runner(config, replay_client).run()

    manifest = json.loads(first.manifest_path.read_text(encoding="utf-8"))
    assert first.status == "COMPLETED"
    assert first.page_count == 2
    assert first.record_count == 2
    assert manifest["status"] == "COMPLETED"
    assert len(manifest["objects"]) == 2
    assert all(len(item["sha256"]) == 64 for item in manifest["objects"])
    assert replay.replayed is True
    assert replay_client.calls == 0


def test_runner_records_failure_and_reuses_matching_page_on_replay(tmp_path) -> None:
    config = _config(tmp_path, run_id="failed-then-replayed")
    failed_client = StubClient([_page(1, 2, "page-one")], ApiResponseError("page two failed"))

    with pytest.raises(ApiResponseError, match="page two failed"):
        _runner(config, failed_client).run()

    store = LocalManifestStore(config.manifest_root)
    failed_manifest = store.load("failed-then-replayed")
    assert failed_manifest is not None
    assert failed_manifest["status"] == "FAILED"
    assert failed_manifest["error"]["type"] == "ApiResponseError"

    replay_client = StubClient([_page(1, 2, "page-one"), _page(2, 2, "page-two")])
    result = _runner(config, replay_client).run()
    completed_manifest = store.load("failed-then-replayed")

    assert result.status == "COMPLETED"
    assert result.replayed is True
    assert completed_manifest is not None
    assert [item["disposition"] for item in completed_manifest["objects"]] == [
        "EXISTING",
        "WRITTEN",
    ]


def test_runner_rejects_run_id_reuse_with_different_configuration(tmp_path) -> None:
    original = _config(tmp_path, run_id="fixed-run", country="USA")
    _runner(original, StubClient([_page(1, 1, "page-one")])).run()
    changed = _config(tmp_path, run_id="fixed-run", country="CAN")

    with pytest.raises(RunConflictError, match="different source configuration"):
        _runner(changed, StubClient([_page(1, 1, "other")])).run()
