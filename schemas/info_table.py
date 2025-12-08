from google.cloud import bigquery

INFO_TABLE_SCHEMA = [
    bigquery.SchemaField("dataset", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("info", "STRING", mode="NULLABLE"),
    bigquery.SchemaField("graph_conv", "BOOL", mode="NULLABLE", default_value_expression="FALSE")
]