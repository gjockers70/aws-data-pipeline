from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

from ingestion.identifiers import validate_run_id
from ingestion.models import LandingWriteResult


class LandingConflictError(RuntimeError):
    """Raised when a run/page key already contains different source content."""


class LocalLandingWriter:
    def __init__(self, landing_root: Path) -> None:
        self._landing_root = landing_root

    def write_raw_page(
        self,
        *,
        raw_text: str,
        indicator: str,
        page: int,
        run_id: str,
        ingested_at: datetime | None = None,
    ) -> LandingWriteResult:
        validate_run_id(run_id)
        timestamp = ingested_at or datetime.now(UTC)
        partition = (
            self._landing_root
            / "world_bank"
            / f"year={timestamp:%Y}"
            / f"month={timestamp:%m}"
            / f"day={timestamp:%d}"
            / f"run_id={run_id}"
        )
        partition.mkdir(parents=True, exist_ok=True)

        safe_indicator = indicator.lower().replace(".", "_")
        filename = f"{safe_indicator}_page_{page:05d}.json"
        destination = partition / filename
        checksum = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()

        if destination.exists():
            existing_checksum = hashlib.sha256(destination.read_bytes()).hexdigest()
            if existing_checksum != checksum:
                raise LandingConflictError(
                    f"Landing object already exists with different content: {destination}"
                )
            return LandingWriteResult(destination, checksum, "EXISTING")

        temporary = destination.with_suffix(".json.tmp")
        temporary.write_text(raw_text, encoding="utf-8")
        temporary.replace(destination)
        return LandingWriteResult(destination, checksum, "WRITTEN")
