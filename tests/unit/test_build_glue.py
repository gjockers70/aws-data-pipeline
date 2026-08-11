from __future__ import annotations

import hashlib
import zipfile

from scripts.build_glue import ZIP_TIMESTAMP, build


def test_glue_library_build_is_deterministic():
    _, first_archive = build()
    first_hash = hashlib.sha256(first_archive.read_bytes()).hexdigest()

    _, second_archive = build()
    second_hash = hashlib.sha256(second_archive.read_bytes()).hexdigest()

    assert first_hash == second_hash
    with zipfile.ZipFile(second_archive) as archive:
        assert archive.namelist() == [
            "data_quality/__init__.py",
            "data_quality/evaluator.py",
            "data_quality/models.py",
            "data_quality/s3_writer.py",
            "data_quality/world_bank.py",
            "transformations/__init__.py",
            "transformations/world_bank.py",
        ]
        assert all(item.date_time == ZIP_TIMESTAMP for item in archive.infolist())
