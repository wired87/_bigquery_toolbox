def list_rows_table(table_ref):
    return f"SELECT * FROM {table_ref}"  # Or SELECT * FROM `{project_id}.{dataset_id}.{table_id}` if you get errors with backticks
