from datetime import UTC, datetime

import pytest

from ingestion.landing_writer import LandingConflictError, LocalLandingWriter


def test_write_raw_page_preserves_payload_in_date_partition(tmp_path) -> None:
    raw_text = '[{"metadata":true},[{"value":1}]]'
    ingested_at = datetime(2026, 8, 11, 15, 4, 5, tzinfo=UTC)

    result = LocalLandingWriter(tmp_path).write_raw_page(
        raw_text=raw_text,
        indicator="SP.POP.TOTL",
        page=1,
        run_id="test-run-1",
        ingested_at=ingested_at,
    )

    assert result.path.parent == (
        tmp_path / "world_bank" / "year=2026" / "month=08" / "day=11" / "run_id=test-run-1"
    )
    assert result.path.name == "sp_pop_totl_page_00001.json"
    assert result.path.read_text(encoding="utf-8") == raw_text
    assert result.disposition == "WRITTEN"
    assert len(result.sha256) == 64


def test_write_raw_page_is_idempotent_for_matching_content(tmp_path) -> None:
    writer = LocalLandingWriter(tmp_path)
    arguments = {
        "raw_text": '[{"same":true}]',
        "indicator": "SP.POP.TOTL",
        "page": 1,
        "run_id": "replay-run",
        "ingested_at": datetime(2026, 8, 11, tzinfo=UTC),
    }

    first = writer.write_raw_page(**arguments)
    second = writer.write_raw_page(**arguments)

    assert first.disposition == "WRITTEN"
    assert second.disposition == "EXISTING"
    assert first.sha256 == second.sha256


def test_write_raw_page_rejects_different_content_for_same_run_page(tmp_path) -> None:
    writer = LocalLandingWriter(tmp_path)
    common = {
        "indicator": "SP.POP.TOTL",
        "page": 1,
        "run_id": "conflict-run",
        "ingested_at": datetime(2026, 8, 11, tzinfo=UTC),
    }
    writer.write_raw_page(raw_text='[{"version":1}]', **common)

    with pytest.raises(LandingConflictError, match="different content"):
        writer.write_raw_page(raw_text='[{"version":2}]', **common)
