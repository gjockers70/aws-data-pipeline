"""AWS Glue entry point for the World Bank landing-to-processed transformation."""

from __future__ import annotations

import sys

CUSTOM_JOB_OPTIONS = [
    "JOB_NAME",
    "SOURCE_PATH",
    "PROCESSED_BASE_PATH",
    "REJECTED_BASE_PATH",
]


def run_output_path(base_path: str, job_run_id: str) -> str:
    return f"{base_path.rstrip('/')}/run_id={job_run_id}"


def main() -> None:
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext

    from transformations.world_bank import (
        read_world_bank_documents,
        transform_world_bank_documents,
        write_transform_result,
    )

    args = getResolvedOptions(sys.argv, CUSTOM_JOB_OPTIONS)
    glue_context = GlueContext(SparkContext.getOrCreate())
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    documents = read_world_bank_documents(glue_context.spark_session, args["SOURCE_PATH"])
    result = transform_world_bank_documents(glue_context.spark_session, documents)
    write_transform_result(
        result,
        run_output_path(args["PROCESSED_BASE_PATH"], args["JOB_RUN_ID"]),
        run_output_path(args["REJECTED_BASE_PATH"], args["JOB_RUN_ID"]),
    )
    job.commit()


if __name__ == "__main__":
    main()
