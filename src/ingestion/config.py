from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class IngestionConfig:
    api_base_url: str
    country: str
    indicator: str
    page: int
    per_page: int
    timeout_seconds: float
    max_attempts: int
    backoff_base_seconds: float
    run_id: str | None
    landing_root: Path
    manifest_root: Path

    @classmethod
    def from_environment(cls) -> IngestionConfig:
        return cls(
            api_base_url=os.getenv("WORLD_BANK_API_BASE_URL", "https://api.worldbank.org/v2"),
            country=os.getenv("WORLD_BANK_COUNTRY", "USA"),
            indicator=os.getenv("WORLD_BANK_INDICATOR", "SP.POP.TOTL"),
            page=_positive_int("WORLD_BANK_PAGE", "1"),
            per_page=_positive_int("WORLD_BANK_PER_PAGE", "25"),
            timeout_seconds=_positive_float("WORLD_BANK_TIMEOUT_SECONDS", "30"),
            max_attempts=_positive_int("WORLD_BANK_MAX_ATTEMPTS", "3"),
            backoff_base_seconds=_positive_float("WORLD_BANK_BACKOFF_BASE_SECONDS", "1"),
            run_id=os.getenv("INGESTION_RUN_ID") or None,
            landing_root=Path(os.getenv("LANDING_ROOT", "local_data/landing")),
            manifest_root=Path(os.getenv("MANIFEST_ROOT", "local_data/manifests")),
        )


def _positive_int(name: str, default: str) -> int:
    value = int(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value


def _positive_float(name: str, default: str) -> float:
    value = float(os.getenv(name, default))
    if value <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return value
