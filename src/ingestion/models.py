from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ApiPage:
    raw_text: str
    metadata: dict[str, Any]
    records: list[dict[str, Any]]

    @property
    def page(self) -> int:
        return int(self.metadata["page"])

    @property
    def total_pages(self) -> int:
        return int(self.metadata["pages"])


@dataclass(frozen=True)
class LandingWriteResult:
    path: Path | str
    sha256: str
    disposition: str


@dataclass(frozen=True)
class IngestionResult:
    run_id: str
    status: str
    page_count: int
    record_count: int
    source_bytes: int
    manifest_path: Path | str
    replayed: bool
