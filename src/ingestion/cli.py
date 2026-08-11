from __future__ import annotations

import json
import sys

from ingestion.api_client import ApiResponseError, WorldBankApiClient
from ingestion.config import IngestionConfig
from ingestion.landing_writer import LandingConflictError, LocalLandingWriter
from ingestion.manifest_store import LocalManifestStore
from ingestion.runner import IngestionRunner, RunConflictError
from ingestion.structured_logging import configure_logging


def main() -> None:
    logger = configure_logging()
    try:
        config = IngestionConfig.from_environment()
        client = WorldBankApiClient(
            config.api_base_url,
            config.timeout_seconds,
            max_attempts=config.max_attempts,
            backoff_base_seconds=config.backoff_base_seconds,
        )
        result = IngestionRunner(
            config=config,
            client=client,
            writer=LocalLandingWriter(config.landing_root),
            manifest_store=LocalManifestStore(config.manifest_root),
            logger=logger,
        ).run()
    except (ApiResponseError, LandingConflictError, RunConflictError, ValueError) as exc:
        print(
            json.dumps(
                {
                    "event": "ingestion_stopped",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    print(
        json.dumps(
            {
                "event": "ingestion_result",
                "run_id": result.run_id,
                "status": result.status,
                "pages": result.page_count,
                "records": result.record_count,
                "manifest_path": str(result.manifest_path),
                "replayed": result.replayed,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
