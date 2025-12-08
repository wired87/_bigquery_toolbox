
"""
1.delimit json
2. create & save schema
3. upload



"""
from google.cloud import bigquery

TABLE_ID =f"aixr-401704.brainmaster.01"
JSON_DIR = r"C:\Users\wired\OneDrive\Desktop\Projects\aws_to_bucket\extract_data\data\filtered_data\checkpoints"
OUTPUT_DIR = r"C:\Users\wired\OneDrive\Desktop\Projects\aws_to_bucket\extract_data\data\filtered_data\delimited"
SCHEMA_DIR = r"C:\Users\wired\OneDrive\Desktop\Projects\aws_to_bucket\extract_data\data\filtered_data\bq_schemes"

"""if __name__ == "__main__":
    table = bq_client.get_table(TABLE_ID)

https://console.cloud.google.com/apis/api/cloudaicompanion.googleapis.com/cost?inv=1&invt=Abmuow&project=aixr-401704




    all_fields = [field.name for field in table.schema]
    print("ALL FIELDS:", all_fields)

    job_config = bigquery.LoadJobConfig(
        autodetect=True, source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        scheme=
    )
    print("jcc")
    uri = "gs://bestbrain/gocam.json"

    load_job = bq_client.load_table_from_uri(
        uri, TABLE_ID, job_config=job_config
    )

    load_job.result()  # Waits for the job to complete.
    destination_table = bq_client.get_table(TABLE_ID)
    print("Loaded {} rows.".format(destination_table.num_rows))"""


import os
import json


def normalize_json(json_file, output_file):
    """
    Delimits JSON for BigQuery compatibility (NDJSON format).
    Each JSON object is written on a new line.
    """
    def normalize_record(record, parent_key='', sep='__'):
        """
        Flattens nested JSON keys with delimiters for BigQuery compatibility.
        """
        items = {}
        for k, v in record.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.update(normalize_record(v, new_key, sep=sep))
            elif isinstance(v, list):
                items[new_key] = json.dumps(v)  # Store arrays as JSON strings
            else:
                items[new_key] = v
        return items

    with open(json_file, "r") as infile:
        data = json.load(infile)

    delimited_data = []

    # Check if the JSON is a list (array of objects) or a single object
    if isinstance(data, list):
        for record in data:
            delimited_data.append(normalize_record(record))
    elif isinstance(data, dict):
        delimited_data.append(normalize_record(data))
    else:
        raise ValueError("Input JSON must be an object or an array of objects.")

    with open(output_file, "w") as outfile:
        outfile.write(json.dumps([record + "\n" for record in delimited_data]))



def normalize_record(record, parent_key='', sep='__'):
    """
    Flattens nested JSON keys with delimiters for BigQuery.
    """
    items = {}
    for k, v in record.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(normalize_record(v, new_key, sep=sep))
        elif isinstance(v, list):
            items[new_key] = json.dumps(v)  # Store arrays as JSON strings
        else:
            items[new_key] = v
    return items




def upload_to_bigquery(table_id, json_file, schema_file):
    """
    Uploads JSON to BigQuery using a specified schema.
    """
    client = bigquery.Client()

    # Load the schema
    with open(schema_file, "r") as schema_infile:
        schema = [
            bigquery.SchemaField(
                name=field["name"],
                field_type=field["type"],
                mode=field.get("mode", "NULLABLE")
            )
            for field in json.load(schema_infile)
        ]

    # Configure load job
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        schema=schema
    )

    with open(json_file, "rb") as source_file:
        job = client.load_table_from_file(source_file, table_id, job_config=job_config)

    job.result()  # Wait for the job to complete
    print(f"Uploaded {json_file} to {table_id}")


def main(json_dir, output_dir, schema_dir, table_id):
    """
    Main workflow: Normalize JSON, generate schema, and upload to BigQuery.
    """
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(schema_dir, exist_ok=True)

    for file_name in os.listdir(json_dir):
        if file_name.endswith(".json"):
            input_path = os.path.join(json_dir, file_name)
            output_path = os.path.join(output_dir, file_name)
            schema_path = os.path.join(schema_dir, f"{os.path.splitext(file_name)[0]}_schema.json")

            # Step 1: Normalize JSON
            normalize_json(input_path, output_path)
            print(f"Normalized JSON saved to {output_path}")

            # Step 3: Upload to BigQuery
            upload_to_bigquery(table_id, output_path, schema_path)

if __name__ == "__main__":
    # Directories and BigQuery table configuration


    main(JSON_DIR, OUTPUT_DIR, SCHEMA_DIR, TABLE_ID)
