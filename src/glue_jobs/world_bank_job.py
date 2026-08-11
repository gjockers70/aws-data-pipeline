"""AWS Glue entry point for the World Bank landing-to-processed transformation."""

from __future__ import annotations

import sys

from awsglue.context import GlueContext
from awsglue.job import Job
from awsglue.utils import getResolvedOptions
from pyspark.context import SparkContext

from transformations.world_bank import (
    read_world_bank_documents,
    transform_world_bank_documents,
    write_transform_result,
)


def main() -> None:
    args = getResolvedOptions(
        sys.argv,
        [
            "JOB_NAME",
            "JOB_RUN_ID",
            "SOURCE_PATH",
            "PROCESSED_BASE_PATH",
            "REJECTED_BASE_PATH",
        ],
    )
    glue_context = GlueContext(SparkContext.getOrCreate())
    job = Job(glue_context)
    job.init(args["JOB_NAME"], args)

    documents = read_world_bank_documents(glue_context.spark_session, args["SOURCE_PATH"])
    result = transform_world_bank_documents(glue_context.spark_session, documents)
    write_transform_result(
        result,
        f"{args['PROCESSED_BASE_PATH'].rstrip('/')}/run_id={args['JOB_RUN_ID']}",
        f"{args['REJECTED_BASE_PATH'].rstrip('/')}/run_id={args['JOB_RUN_ID']}",
    )
    job.commit()


if __name__ == "__main__":
    main()
