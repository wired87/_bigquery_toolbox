import pandas as pd
from typing import List

from google.cloud import bigquery  # Import BigQuery library

def dataframe_to_bigquery_schema(df: pd.DataFrame) -> List[bigquery.SchemaField]:
    """
    Converts a Pandas DataFrame to a BigQuery schema.

    Args:
        df: The Pandas DataFrame.

    Returns:
        A list of bigquery.SchemaField objects representing the BigQuery schema.
        Returns an empty list if the input DataFrame is empty or None.
        Raises a ValueError if a column type cannot be mapped to a BigQuery type.
    """

    if df is None or df.empty:
        return []

    schema = []

    for col_name in df.columns:
        # Determine the most common type (or handle multiple types appropriately).
        # In this simplified version, we'll just take the first non-NaN type we find.
        # For more robust type detection, you could analyze the entire column.
        bq_type = None
        mode = "NULLABLE"  # Default mode

        for value in df[col_name]:  # Iterate through the column values
            if pd.isna(value):  # Handle missing values
                continue  # Skip to the next value

            val_type = type(value)

            if val_type is str:
                bq_type = "STRING"
                break  # Found the type, exit loop
            elif val_type is int:
                bq_type = "INTEGER"
                break
            elif val_type is float:
                bq_type = "FLOAT64"
                break
            elif val_type is bool:
                bq_type = "BOOLEAN"
                break
            elif pd.Timestamp == val_type:
                bq_type = "DATETIME"
                break
            elif pd.Timedelta == val_type:
                bq_type = "TIME"  # or "INTERVAL"
                break
            elif val_type is list:
                bq_type = "ARRAY"
                # You'll likely need to analyze the list elements for a more
                # accurate ARRAY type (e.g., ARRAY<STRING>, ARRAY<INTEGER>, etc.)
                break
            elif val_type is dict:
                bq_type = "STRUCT"  # or "RECORD"
                # Similar to ARRAY, you'd need to analyze the dictionary structure
                # to create the STRUCT fields.
                break
            else:
                # Handle unknown types or raise an error
                raise ValueError(f"Unsupported data type {val_type} for column {col_name}")

        if bq_type is None:  # Column contains only NULLs
            bq_type = "STRING"  # Default to STRING for columns with all NULLs.
            mode = "NULLABLE"  # Make sure mode is NULLABLE

        schema.append(bigquery.SchemaField(col_name, bq_type, mode=mode))

    return schema

