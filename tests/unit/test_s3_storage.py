from __future__ import annotations

import json
from datetime import UTC, datetime
from io import BytesIO

import pytest
from botocore.exceptions import ClientError

from ingestion.landing_writer import LandingConflictError
from ingestion.s3_storage import S3LandingWriter, S3ManifestStore


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
            "ContentType": request.get("ContentType"),
            "ServerSideEncryption": request.get("ServerSideEncryption"),
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


def test_s3_landing_writer_uses_partitioned_encrypted_immutable_key() -> None:
    client = MemoryS3Client()
    writer = S3LandingWriter(client, "test-bucket")
    timestamp = datetime(2026, 8, 11, 12, 30, tzinfo=UTC)

    result = writer.write_raw_page(
        raw_text='[{"metadata":true},[{"value":1}]]',
        indicator="SP.POP.TOTL",
        page=2,
        run_id="s3-run-1",
        ingested_at=timestamp,
    )

    key = "landing/world_bank/year=2026/month=08/day=11/run_id=s3-run-1/"
    key += "sp_pop_totl_page_00002.json"
    stored = client.objects[("test-bucket", key)]
    assert result.path == f"s3://test-bucket/{key}"
    assert result.disposition == "WRITTEN"
    assert stored["ContentType"] == "application/json"
    assert stored["ServerSideEncryption"] == "AES256"
    assert stored["Metadata"] == {"sha256": result.sha256}


def test_s3_landing_writer_replays_matching_content_and_rejects_conflict() -> None:
    client = MemoryS3Client()
    writer = S3LandingWriter(client, "test-bucket")
    common = {
        "indicator": "SP.POP.TOTL",
        "page": 1,
        "run_id": "immutable-run",
        "ingested_at": datetime(2026, 8, 11, tzinfo=UTC),
    }

    first = writer.write_raw_page(raw_text='[{"version":1}]', **common)
    replay = writer.write_raw_page(raw_text='[{"version":1}]', **common)

    assert first.disposition == "WRITTEN"
    assert replay.disposition == "EXISTING"
    with pytest.raises(LandingConflictError, match="different content"):
        writer.write_raw_page(raw_text='[{"version":2}]', **common)


def test_s3_manifest_store_returns_none_then_round_trips_manifest() -> None:
    client = MemoryS3Client()
    store = S3ManifestStore(client, "test-bucket")
    manifest = {"run_id": "manifest-run", "status": "COMPLETED", "record_count": 3}

    assert store.load("manifest-run") is None
    uri = store.write(manifest)
    loaded = store.load("manifest-run")

    assert uri == "s3://test-bucket/manifests/world_bank/run_id=manifest-run.json"
    assert loaded == manifest
    stored = client.objects[("test-bucket", "manifests/world_bank/run_id=manifest-run.json")]
    assert stored["ServerSideEncryption"] == "AES256"
    assert json.loads(stored["Body"].decode("utf-8")) == manifest
