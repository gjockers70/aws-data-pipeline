from unittest.mock import Mock

from transformations.world_bank import write_warehouse_load_result


def test_warehouse_output_keeps_all_columns_inside_parquet_files():
    processed = Mock()
    processed.write.mode.return_value = processed.write

    write_warehouse_load_result(
        processed,
        "s3://example.test/warehouse/world_bank/run_id=run_test",
    )

    processed.write.mode.assert_called_once_with("errorifexists")
    processed.write.parquet.assert_called_once_with(
        "s3://example.test/warehouse/world_bank/run_id=run_test"
    )
    processed.write.partitionBy.assert_not_called()
