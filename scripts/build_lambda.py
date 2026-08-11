from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = PROJECT_ROOT / "build" / "lambda"
STAGING_DIRECTORY = BUILD_ROOT / "package"
ARCHIVE_BASE = BUILD_ROOT / "function"


def main() -> None:
    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    STAGING_DIRECTORY.mkdir(parents=True)

    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            str(PROJECT_ROOT),
            "--target",
            str(STAGING_DIRECTORY),
            "--no-compile",
            "--quiet",
        ],
        check=True,
    )
    archive_path = shutil.make_archive(
        str(ARCHIVE_BASE),
        "zip",
        root_dir=STAGING_DIRECTORY,
    )
    print(archive_path)


if __name__ == "__main__":
    main()
