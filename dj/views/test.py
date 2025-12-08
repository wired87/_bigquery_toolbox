from _bq_core.bq_handler import BQCore

if __name__ =="__main__":
    bqc = BQCore(
        dataset_id="QCOMPS"
    )

    # Access db_manager however it's available, e.g. via self.db_manager
    bqc.bq_insert(
        table_id="TEST_RUN_ID",
        rows=[{"test2": 1}],
    )

