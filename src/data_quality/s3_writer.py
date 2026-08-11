"""Write one immutable data-quality result object to Amazon S3."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

import boto3

from data_quality.models import DataQualityResult


def parse_s3_uri(uri: str) -> tuple[str, str]:
    parsed = urlparse(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.lstrip("/"):
        raise ValueError(f"Expected an S3 object URI, got {uri!r}")
    return parsed.netloc, parsed.path.lstrip("/")


def write_data_quality_result(
    result: DataQualityResult,
    destination_uri: str,
    *,
    s3_client: Any | None = None,
) -> None:
    bucket, key = parse_s3_uri(destination_uri)
    client = s3_client or boto3.client("s3")
    body = json.dumps(result.to_dict(), indent=2, sort_keys=True).encode("utf-8")
    client.put_object(
        Bucket=bucket,
        Key=key,
        Body=body,
        ContentType="application/json",
        ServerSideEncryption="AES256",
        IfNoneMatch="*",
        Metadata={
            "dataset": result.dataset,
            "run-id": result.run_id,
            "status": result.status,
        },
    )
