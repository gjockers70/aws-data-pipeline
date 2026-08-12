from glue_jobs.world_bank_job import CUSTOM_JOB_OPTIONS, run_output_path


def test_reserved_job_run_id_is_not_registered_as_custom_option():
    assert "JOB_RUN_ID" not in CUSTOM_JOB_OPTIONS


def test_quality_output_path_is_required_by_the_job():
    assert "QUALITY_BASE_PATH" in CUSTOM_JOB_OPTIONS


def test_warehouse_output_path_is_required_by_the_job():
    assert "WAREHOUSE_BASE_PATH" in CUSTOM_JOB_OPTIONS


def test_output_path_is_isolated_by_job_run_id():
    assert run_output_path("s3://example.test/processed/", "jr_example") == (
        "s3://example.test/processed/run_id=jr_example"
    )
