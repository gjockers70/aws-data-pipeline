from __future__ import annotations

import json
from unittest.mock import Mock

import pytest

from data_quality.models import DataQualityResult, RuleResult
from data_quality.s3_writer import parse_s3_uri, write_data_quality_result


def _result() -> DataQualityResult:
    return DataQualityResult(
        dataset="example_dataset",
        run_id="run_test_001",
        row_count=2,
        rejected_row_count=0,
        expected_row_count=2,
        row_count_match=True,
        null_failures=0,
        duplicate_failures=0,
        invalid_type_failures=0,
        missing_column_failures=0,
        invalid_enum_failures=0,
        schema_drift=False,
        schema_drift_rows=0,
        status="PASS",
        evaluated_at="2026-01-02T03:04:05+00:00",
        rules=(RuleResult(rule="row_count", status="PASS", failures=0),),
    )


def test_writes_encrypted_json_result_without_credentials():
    client = Mock()
    client.meta.events = Mock()

    write_data_quality_result(
        _result(),
        "s3://example.test/quality/source/run_id=run_test_001/result.json",
        s3_client=client,
    )

    request = client.put_object.call_args.kwargs
    assert request["Bucket"] == "example.test"
    assert request["Key"].endswith("/result.json")
    assert request["ServerSideEncryption"] == "AES256"
    assert "IfNoneMatch" not in request
    assert request["ContentType"] == "application/json"
    assert request["Metadata"]["status"] == "PASS"
    assert json.loads(request["Body"])["row_count"] == 2

    registration = client.meta.events.register_first.call_args
    assert registration.args[0] == "before-sign.s3.PutObject"
    assert registration.kwargs["unique_id"] == "data-quality-create-only"
    request_to_sign = Mock(headers={})
    registration.args[1](request_to_sign)
    assert request_to_sign.headers["If-None-Match"] == "*"


@pytest.mark.parametrize("uri", ["", "https://example.test/result.json", "s3://bucket-only"])
def test_rejects_invalid_s3_object_uri(uri):
    with pytest.raises(ValueError, match="Expected an S3 object URI"):
        parse_s3_uri(uri)
