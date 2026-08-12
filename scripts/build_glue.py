"""Build the AWS Glue entry script and transformation library archive."""

from __future__ import annotations

import shutil
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = PROJECT_ROOT / "build" / "glue"
ENTRY_SOURCE = PROJECT_ROOT / "src" / "glue_jobs" / "world_bank_job.py"
LIBRARY_SOURCES = sorted(
    [
        *(PROJECT_ROOT / "src" / "data_quality").glob("*.py"),
        *(PROJECT_ROOT / "src" / "transformations").glob("*.py"),
    ]
)
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def _write_deterministic_file(
    archive: zipfile.ZipFile,
    source: Path,
    destination: Path,
) -> None:
    entry = zipfile.ZipInfo(destination.as_posix(), date_time=ZIP_TIMESTAMP)
    entry.compress_type = zipfile.ZIP_DEFLATED
    entry.external_attr = 0o644 << 16
    archive.writestr(entry, source.read_bytes())


def build() -> tuple[Path, Path]:
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    entry_target = BUILD_DIR / "world_bank_job.py"
    library_target = BUILD_DIR / "transformations.zip"

    shutil.copyfile(ENTRY_SOURCE, entry_target)
    with zipfile.ZipFile(library_target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in LIBRARY_SOURCES:
            _write_deterministic_file(
                archive,
                source,
                source.relative_to(PROJECT_ROOT / "src"),
            )

    return entry_target, library_target


if __name__ == "__main__":
    entry_script, library_archive = build()
    print(f"Built {entry_script}")
    print(f"Built {library_archive}")
