import os
import json
import pandas as pd
from ggoogle.cloud import bigquery

def flatten_json(nested_json, parent_key="", separator="."):
    """
    Recursively flattens a nested JSON object.

    Args:
        nested_json (dict): The JSON object to flatten.
        parent_key (str): The qf_core_base key string for recursion (default is "").
        separator (str): Separator used between keys in flattened format (default is ".").

    Returns:
        dict: A flattened dictionary.
    """
    flattened = {}
    for key, value in nested_json.items():
        new_key = f"{parent_key}{separator}{key}" if parent_key else key
        if isinstance(value, dict):  # If value is a nested dictionary, recurse
            flattened.update(flatten_json(value, new_key, separator))
        elif isinstance(value, list):  # If value is a list, handle it appropriately
            for i, item in enumerate(value):
                if isinstance(item, dict):  # Flatten dictionary items in list
                    flattened.update(flatten_json(item, f"{new_key}[{i}]", separator))
                else:
                    flattened[f"{new_key}[{i}]"] = item
        else:
            flattened[new_key] = value
    return flattened

def process_dynamic_json_to_bigquery(json_dir, project_id, dataset_id, table_id):
    """
    Processes dynamic nested JSON files from a directory and uploads them to BigQuery.

    Args:
        json_dir (str): Path to the directory containing JSON files.
        project_id (str): Google Cloud project ID.
        dataset_id (str): BigQuery dataset ID.
        table_id (str): BigQuery table ID.

    Returns:
        None
    """
    # Initialize BigQuery client
    client = bigquery.Client()

    # Collect and flatten data from all JSON files
    data = []
    for filename in os.listdir(json_dir):
        if filename.endswith(".json"):
            file_path = os.path.join(json_dir, filename)
            with open(file_path, "r") as file:
                json_data = json.load(file)
                flattened_data = flatten_json(json_data)
                data.append(flattened_data)

    # Convert data to a Pandas DataFrame
    df = pd.DataFrame(data)

    # Handle missing values (optional)
    df.fillna("", inplace=True)

    # Create the BigQuery table schema
    job_config = bigquery.LoadJobConfig(
        autodetect=True,  # Automatically infer schema
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE  # Overwrite table if it exists
    )

    # Define BigQuery table reference
    table_ref = f"{project_id}.{dataset_id}.{table_id}"

    # Upload the DataFrame to BigQuery
    job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
    job.result()  # Wait for the job to complete

    print(f"Data uploaded to BigQuery table: {table_ref}")

# Example usage
if __name__ == "__main__":
    json_dir = "path/to/json/files"
    project_id = "your_project_id"
    dataset_id = "your_dataset_id"
    table_id = "your_table_id"



# Example usage
if __name__ == "__main__":
    json_dir = r"C:\Users\wired\OneDrive\Desktop\Projects\aws_to_bucket\extract_data\data\filtered_data\cells_test_hcs"
    project_id = "aixr-401704"
    dataset_id = "brainmaster"
    table_id = "brainmaster01"
    process_dynamic_json_to_bigquery(json_dir, project_id, dataset_id, table_id)
