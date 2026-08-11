from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Protocol

from ingestion.models import LandingWriteResult


class LandingWriter(Protocol):
    def write_raw_page(
        self,
        *,
        raw_text: str,
        indicator: str,
        page: int,
        run_id: str,
        ingested_at: datetime | None = None,
    ) -> LandingWriteResult: ...


class ManifestStore(Protocol):
    def path_for(self, run_id: str) -> Path | str: ...

    def load(self, run_id: str) -> dict[str, Any] | None: ...

    def write(self, manifest: dict[str, Any]) -> Path | str: ...
