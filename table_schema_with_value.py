

from google.cloud import bigquery

BQ=bigquery.Client()

def extract_table_schema_with_value(column_name, table_ref, column_data):
    print("Extracting values for col", column_name)
    try:
        query = f"SELECT {column_name} FROM {table_ref} WHERE {column_name} IS NOT NULL LIMIT 1"
        query_job = BQ.query(query)
        result = list(query_job.result())

        if result:
            column_data[column_name] = result[0][column_name]
        else:
            column_data[column_name] = None
    except Exception as e:
        print(f"Warning: Could not get a value for column {column_name}: {e}")
        column_data[column_name] = None
