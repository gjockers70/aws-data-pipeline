from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest


@pytest.fixture(scope="session")
def spark():
    if "JAVA_HOME" not in os.environ:
        local_jdk = Path(__file__).parents[2] / ".tools" / "temurin17" / "jdk-17.0.20+8"
        if local_jdk.exists():
            os.environ["JAVA_HOME"] = str(local_jdk)
    os.environ["PYSPARK_PYTHON"] = sys.executable
    os.environ["PYSPARK_DRIVER_PYTHON"] = sys.executable

    pyspark = pytest.importorskip("pyspark")
    session = (
        pyspark.sql.SparkSession.builder.master("local[2]")
        .appName("aws-data-pipeline-tests")
        .config("spark.ui.enabled", "false")
        .config("spark.sql.shuffle.partitions", "2")
        .config("spark.pyspark.python", sys.executable)
        .config("spark.pyspark.driver.python", sys.executable)
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()
