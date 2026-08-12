"""AWS Glue entry point for the World Bank landing-to-processed transformation."""

from __future__ import annotations

import sys

CUSTOM_JOB_OPTIONS = [
    "JOB_NAME",
    "SOURCE_PATH",
    "PROCESSED_BASE_PATH",
    "REJECTED_BASE_PATH",
    "QUALITY_BASE_PATH",
    "WAREHOUSE_BASE_PATH",
]


def run_output_path(base_path: str, job_run_id: str) -> str:
    return f"{base_path.rstrip('/')}/run_id={job_run_id}"


def main() -> None:
    from awsglue.context import GlueContext
    from awsglue.job import Job
    from awsglue.utils import getResolvedOptions
    from pyspark.context import SparkContext
    from pyspark.storagelevel import StorageLevel

    from data_quality import evaluate_data_quality
    from data_quality.s3_writer import write_data_quality_result
    from data_quality.world_bank import WORLD_BANK_QUALITY_CONFIG, DataQualityFailure
    from transformations.world_bank import (
        expected_world_bank_row_count,
        read_world_bank_documents,
        transform_world_bank_documents,
        write_transform_result,
        write_warehouse_load_result,
    )

    args = getResolvedOptions(sys.argv, CUSTOM_JOB_OPTIONS)
    glue_context = GlueContext(SparkContext.getOrCreate())
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    documents = read_world_bank_documents(
        glue_context.spark_session,
        args["SOURCE_PATH"],
    ).persist(StorageLevel.MEMORY_AND_DISK)
    expected_row_count = expected_world_bank_row_count(documents)
    result = transform_world_bank_documents(glue_context.spark_session, documents)
    result.processed.persist(StorageLevel.MEMORY_AND_DISK)
    result.rejected.persist(StorageLevel.MEMORY_AND_DISK)

    quality_result = evaluate_data_quality(
        result.processed,
        result.rejected,
        run_id=args["JOB_RUN_ID"],
        config=WORLD_BANK_QUALITY_CONFIG,
        expected_row_count=expected_row_count,
    )
    quality_uri = f"{run_output_path(args['QUALITY_BASE_PATH'], args['JOB_RUN_ID'])}/result.json"
    write_data_quality_result(quality_result, quality_uri)

    processed_path = run_output_path(args["PROCESSED_BASE_PATH"], args["JOB_RUN_ID"])
    rejected_path = run_output_path(args["REJECTED_BASE_PATH"], args["JOB_RUN_ID"])
    warehouse_path = run_output_path(args["WAREHOUSE_BASE_PATH"], args["JOB_RUN_ID"])
    if quality_result.status == "FAIL":
        result.rejected.write.mode("errorifexists").json(rejected_path)
        raise DataQualityFailure(
            f"Data quality failed for run {args['JOB_RUN_ID']}; see {quality_uri}"
        )

    write_warehouse_load_result(result.processed, warehouse_path)
    write_transform_result(result, processed_path, rejected_path)
    job.commit()


if __name__ == "__main__":
    main()
