from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from ingestion.api_client import WorldBankApiClient
from ingestion.config import IngestionConfig
from ingestion.models import IngestionResult
from ingestion.storage import LandingWriter, ManifestStore
from ingestion.structured_logging import log_event


class RunConflictError(RuntimeError):
    """Raised when an existing run ID is reused with different source configuration."""


class IngestionRunner:
    def __init__(
        self,
        *,
        config: IngestionConfig,
        client: WorldBankApiClient,
        writer: LandingWriter,
        manifest_store: ManifestStore,
        logger: logging.Logger,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._config = config
        self._client = client
        self._writer = writer
        self._manifest_store = manifest_store
        self._logger = logger
        self._clock = clock

    def run(self) -> IngestionResult:
        run_id = self._config.run_id or str(uuid4())
        fingerprint = self._config_fingerprint()
        existing = self._manifest_store.load(run_id)

        if existing:
            if existing.get("config_fingerprint") != fingerprint:
                raise RunConflictError(f"run_id {run_id} belongs to different source configuration")
            if existing.get("status") == "COMPLETED":
                log_event(self._logger, "run_skipped", run_id=run_id, reason="already_completed")
                return self._result_from_manifest(existing, replayed=True)
            started_at = datetime.fromisoformat(str(existing["started_at"]))
            replayed = True
        else:
            started_at = self._clock()
            replayed = False

        manifest = self._new_manifest(run_id, fingerprint, started_at, replayed)
        manifest_path = self._manifest_store.write(manifest)
        log_event(
            self._logger,
            "run_started",
            run_id=run_id,
            country=self._config.country,
            indicator=self._config.indicator,
            replayed=replayed,
        )

        try:
            for api_page in self._client.fetch_indicator_pages(
                country=self._config.country,
                indicator=self._config.indicator,
                start_page=self._config.page,
                per_page=self._config.per_page,
            ):
                landed = self._writer.write_raw_page(
                    raw_text=api_page.raw_text,
                    indicator=self._config.indicator,
                    page=api_page.page,
                    run_id=run_id,
                    ingested_at=started_at,
                )
                page_source_bytes = len(api_page.raw_text.encode("utf-8"))
                manifest["pages_expected"] = api_page.total_pages
                manifest["pages_landed"] += 1
                manifest["record_count"] += len(api_page.records)
                manifest["source_bytes"] += page_source_bytes
                manifest["objects"].append(
                    {
                        "page": api_page.page,
                        "record_count": len(api_page.records),
                        "source_bytes": page_source_bytes,
                        "path": str(landed.path),
                        "sha256": landed.sha256,
                        "disposition": landed.disposition,
                    }
                )
                self._manifest_store.write(manifest)
                log_event(
                    self._logger,
                    "page_landed",
                    run_id=run_id,
                    page=api_page.page,
                    records=len(api_page.records),
                    disposition=landed.disposition,
                )
        except Exception as exc:
            manifest["status"] = "FAILED"
            manifest["completed_at"] = self._clock().isoformat()
            manifest["error"] = {"type": type(exc).__name__, "message": str(exc)}
            self._manifest_store.write(manifest)
            log_event(
                self._logger,
                "run_failed",
                run_id=run_id,
                error_type=type(exc).__name__,
                error_message=str(exc),
            )
            raise

        manifest["status"] = "COMPLETED"
        manifest["completed_at"] = self._clock().isoformat()
        self._manifest_store.write(manifest)
        log_event(
            self._logger,
            "run_completed",
            run_id=run_id,
            pages=manifest["pages_landed"],
            records=manifest["record_count"],
            manifest_path=str(manifest_path),
        )
        return self._result_from_manifest(manifest, replayed=replayed)

    def _config_fingerprint(self) -> str:
        source_config = {
            "api_base_url": self._config.api_base_url,
            "country": self._config.country,
            "indicator": self._config.indicator,
            "page": self._config.page,
            "per_page": self._config.per_page,
        }
        encoded = json.dumps(source_config, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _new_manifest(
        self,
        run_id: str,
        fingerprint: str,
        started_at: datetime,
        replayed: bool,
    ) -> dict[str, Any]:
        return {
            "run_id": run_id,
            "dataset": "world_bank_indicator",
            "status": "RUNNING",
            "started_at": started_at.isoformat(),
            "completed_at": None,
            "country": self._config.country,
            "indicator": self._config.indicator,
            "start_page": self._config.page,
            "per_page": self._config.per_page,
            "config_fingerprint": fingerprint,
            "replayed": replayed,
            "pages_expected": None,
            "pages_landed": 0,
            "record_count": 0,
            "source_bytes": 0,
            "objects": [],
            "error": None,
        }

    def _result_from_manifest(self, manifest: dict[str, Any], *, replayed: bool) -> IngestionResult:
        run_id = str(manifest["run_id"])
        return IngestionResult(
            run_id=run_id,
            status=str(manifest["status"]),
            page_count=int(manifest["pages_landed"]),
            record_count=int(manifest["record_count"]),
            source_bytes=int(manifest.get("source_bytes", 0)),
            manifest_path=self._manifest_store.path_for(run_id),
            replayed=replayed,
        )
