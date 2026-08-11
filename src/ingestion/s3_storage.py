from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from botocore.exceptions import ClientError

from ingestion.identifiers import validate_run_id
from ingestion.landing_writer import LandingConflictError
from ingestion.models import LandingWriteResult


class S3LandingWriter:
    def __init__(self, s3_client: Any, bucket: str, prefix: str = "landing") -> None:
        self._client = s3_client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

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
        safe_indicator = indicator.lower().replace(".", "_")
        key = (
            f"{self._prefix}/world_bank/year={timestamp:%Y}/month={timestamp:%m}/"
            f"day={timestamp:%d}/run_id={run_id}/{safe_indicator}_page_{page:05d}.json"
        )
        body = raw_text.encode("utf-8")
        checksum = hashlib.sha256(body).hexdigest()

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
                ServerSideEncryption="AES256",
                Metadata={"sha256": checksum},
                IfNoneMatch="*",
            )
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if error.get("Code") not in {"PreconditionFailed", "412"}:
                raise
            existing = self._client.head_object(Bucket=self._bucket, Key=key)
            existing_checksum = existing.get("Metadata", {}).get("sha256")
            if existing_checksum != checksum:
                raise LandingConflictError(
                    f"Landing object already exists with different content: s3://{self._bucket}/{key}"
                ) from exc
            return LandingWriteResult(f"s3://{self._bucket}/{key}", checksum, "EXISTING")

        return LandingWriteResult(f"s3://{self._bucket}/{key}", checksum, "WRITTEN")


class S3ManifestStore:
    def __init__(self, s3_client: Any, bucket: str, prefix: str = "manifests") -> None:
        self._client = s3_client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    def path_for(self, run_id: str) -> str:
        return f"s3://{self._bucket}/{self._key_for(run_id)}"

    def load(self, run_id: str) -> dict[str, Any] | None:
        key = self._key_for(run_id)
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if error.get("Code") in {"NoSuchKey", "404", "NotFound"}:
                return None
            raise

        payload = json.loads(response["Body"].read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise TypeError(f"Manifest must contain a JSON object: s3://{self._bucket}/{key}")
        return payload

    def write(self, manifest: dict[str, Any]) -> str:
        key = self._key_for(str(manifest["run_id"]))
        body = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType="application/json",
            ServerSideEncryption="AES256",
        )
        return f"s3://{self._bucket}/{key}"

    def _key_for(self, run_id: str) -> str:
        validate_run_id(run_id)
        return f"{self._prefix}/world_bank/run_id={run_id}.json"
