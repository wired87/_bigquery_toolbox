import re

import pandas as pd
import requests
from django.http import JsonResponse
from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from google.cloud import bigquery
from rest_framework.views import APIView



@method_decorator(ratelimit(key='ip', rate='5/m', block=True), name='dispatch')
class ProcessDSView(APIView):
    """
    Django class-based view that extracts URLs from a string,
    verifies if they are CSVs, and stores valid CSV content in BigQuery.
    """

    PROJECT_ID = "your-gcp-project-id"
    DATASET_ID = "your_dataset"
    TABLE_ID = "your_table"

    def post(self, request, *args, **kwargs):
        """
        Extract URLs, filter CSV files, and insert valid data into BigQuery.
        """
        data = request.POST.get("urls", "")  # Receive the string of URLs
        urls = self.extract_urls(data)

        if not urls:
            return JsonResponse({"message": "No valid URLs found."}, status=400)

        csv_urls = [url for url in urls if url.lower().endswith(".csv")]

        if not csv_urls:
            return JsonResponse({"message": "No CSV URLs found."}, status=400)

        # Process each CSV URL and insert into BigQuery
        for url in csv_urls:
            self.process_csv_to_bigquery(url)

        return JsonResponse({"message": "Processing completed."}, status=200)

    def extract_urls(self, text):
        """
        Extract all URLs from a given text string using regex.
        """
        url_pattern = r"https?://[^\s]+"
        return re.findall(url_pattern, text)

    def process_csv_to_bigquery(self, url):
        """
        Fetch CSV from the URL, process it, and insert data into BigQuery.
        """
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raise error if request fails

            # Read CSV content into a Pandas DataFrame
            df = pd.read_csv(pd.compat.StringIO(response.text))

            # Check if the table exists, create if not
            self.ensure_table_exists(df)

            # Insert data into BigQuery
            client = BQ
            table_ref = f"{self.PROJECT_ID}.{self.DATASET_ID}.{self.TABLE_ID}"
            job = client.load_table_from_dataframe(df, table_ref)
            job.result()  # Wait for the job to complete

            print(f"Inserted {len(df)} rows from {url} into {table_ref}")

        except requests.exceptions.RequestException as e:
            print(f"Error fetching CSV: {e}")
        except pd.errors.ParserError:
            print(f"Invalid CSV format: {url}")
        except Exception as e:
            print(f"Unexpected error: {e}")

    def ensure_table_exists(self, df):
        """
        Checks if the BigQuery table exists. If not, creates it dynamically.
        """
        client = bigquery.Client()
        table_ref = f"{self.PROJECT_ID}.{self.DATASET_ID}.{self.TABLE_ID}"

        try:
            client.get_table(table_ref)  # Check if table exists
            print(f"Table {table_ref} exists.")
        except Exception:
            print(f"Table {table_ref} does not exist. Creating...")

            schema = [
                bigquery.SchemaField(col, "STRING") for col in df.columns
            ]  # Assume all columns as STRING

            table = bigquery.Table(table_ref, schema=schema)
            client.create_table(table)
            print(f"Created table {table_ref}.")