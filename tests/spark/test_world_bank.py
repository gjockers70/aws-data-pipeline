from __future__ import annotations

import json
import os

import pytest

from transformations.world_bank import (
    read_world_bank_documents,
    transform_world_bank_documents,
    write_transform_result,
)


def _record(**overrides):
    record = {
        "indicator": {"id": "SP.POP.TOTL", "value": "Population, total"},
        "country": {"id": "XT", "value": "Example Territory"},
        "countryiso3code": "XTS",
        "date": "2024",
        "value": 12345,
        "unit": "people",
        "obs_status": "",
        "decimal": 0,
    }
    record.update(overrides)
    return record


def _document(*records):
    metadata = {"page": 1, "pages": 1, "per_page": 50, "total": len(records)}
    return json.dumps([metadata, list(records)])


def _documents_frame(spark, *documents):
    return spark.createDataFrame(documents, ["source_file", "raw_text"])


def test_flattens_nested_fields_and_casts_types(spark):
    documents = _documents_frame(spark, ("s3://example.test/page-1.json", _document(_record())))

    result = transform_world_bank_documents(spark, documents)
    row = result.processed.first()

    assert row.indicator_id == "SP.POP.TOTL"
    assert row.country_iso3_code == "XTS"
    assert row.observation_year == 2024
    assert row.observation_value == 12345.0
    assert row.schema_drift is False
    assert result.rejected.count() == 0


def test_rejects_malformed_and_invalid_records(spark):
    invalid_value = _record(value="not-a-number")
    documents = _documents_frame(
        spark,
        ("s3://example.test/malformed.json", "{bad-json"),
        ("s3://example.test/invalid-value.json", _document(invalid_value)),
    )

    result = transform_world_bank_documents(spark, documents)
    reasons = {row.rejection_reason for row in result.rejected.collect()}

    assert result.processed.count() == 0
    assert any(reason.startswith("MALFORMED_JSON:") for reason in reasons)
    assert "INVALID_OBSERVATION_VALUE" in reasons


def test_deduplicates_business_key_and_records_schema_drift(spark):
    first = _record(new_source_field="unexpected")
    duplicate = _record(value=99999)
    documents = _documents_frame(
        spark,
        ("s3://example.test/page-1.json", _document(first)),
        ("s3://example.test/page-2.json", _document(duplicate)),
    )

    result = transform_world_bank_documents(spark, documents)
    processed = result.processed.first()
    rejected = result.rejected.first()

    assert processed.observation_value == 12345.0
    assert processed.schema_drift is True
    assert processed.schema_drift_fields == ["record.new_source_field"]
    assert rejected.rejection_reason == "DUPLICATE_BUSINESS_KEY"


@pytest.mark.skipif(
    os.name == "nt",
    reason="Local Spark file I/O on Windows requires Hadoop's optional winutils binary",
)
def test_reads_whole_json_and_writes_partitioned_parquet(spark, tmp_path):
    input_path = tmp_path / "landing"
    input_path.mkdir()
    (input_path / "page-1.json").write_text(_document(_record()), encoding="utf-8")

    documents = read_world_bank_documents(spark, str(input_path))
    result = transform_world_bank_documents(spark, documents)
    processed_path = tmp_path / "processed"
    rejected_path = tmp_path / "rejected"
    write_transform_result(result, str(processed_path), str(rejected_path))

    persisted = spark.read.parquet(str(processed_path))
    assert persisted.first().country_iso3_code == "XTS"
    assert "observation_year=2024" in str(next(processed_path.glob("observation_year=*")))
