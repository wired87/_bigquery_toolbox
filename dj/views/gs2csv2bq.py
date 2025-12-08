import asyncio
import os
import re

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from rest_framework import serializers

from utils.file.file_checker import dynamic_file_to_csv
from _google.gdb_manager.bq import BQ_INFO_TABLE_ID
from _google.gdb_manager.bq.bq_handler import BQCore
from _google.gdb_manager.bq.schemas.info_table import INFO_TABLE_SCHEMA
from _google.gdb_manager.storage import MOUNT_PATH
from _google.gdb_manager.storage import GBucket



from google.cloud import bigquery

BQ=bigquery.Client()
def extract_urls(text):
    print("Extract urls ")
    if not isinstance(text, str):
        return []
    url_pattern = r"https?://\S+"  # Matches http:// or https:// followed by any non-whitespace character
    return re.findall(url_pattern, text)




class S(serializers.Serializer):
    bucket_path = serializers.CharField(
        default="bucket_path",
        label="bucket_path",
    )





class Gcs2Csv2Bq(APIView):
    def upload_bq_process(self, csv_data, table_name, bq_handler):
        print("Start uploading process")
        bq_handler.up2bq(
            table_id=table_name,
            csv_data=csv_data
        )

    def handle_info(self, bq_handler, ds_table_id, info=None):
        try:
            bq_handler.get_create_table(
                table_name=BQ_INFO_TABLE_ID,
                schema=INFO_TABLE_SCHEMA
            )
            BQ.insert_rows_json(
                BQ_INFO_TABLE_ID,
                [{"dataset": ds_table_id, "info": info}]
            )
        except Exception as e:
            print("Error", e)

    def handle_ds_to_csv(self, blob_content, prefix):
        try:
            iterator = iter(blob_content)  # Ensure we create a new iterator
            for data_blob in iterator:
                if data_blob.name != "info.json":
                    print("Start creating new table")
                    file_path = os.path.join(prefix, data_blob.name)
                    file_type = file_path.split(".")[-1]
                    with data_blob.open("r") as f:  # Corrected mode to read mode
                        csv_data = dynamic_file_to_csv(file_type, f)
                    return csv_data, data_blob.name.split(".")[0]
        except ValueError as ve:
            print("Error: Iterator has already started or consumed.", ve)
            return None, None
        except Exception as e:
            print("Unexpected error in handle_ds_to_csv:", e)
            return None, None

    def post(self, request, *args, **kwargs):
        bq_handler = BQCore()
        bucket = GBucket()

        bucket_path = request.data.get('bucket_path')

        all_bq_tables = bq_handler.list_tables()
        all_bucket_data_blobs = bucket.get_folders_with_files(prefix=bucket_path)

        for blob in all_bucket_data_blobs:
            print("Working blob_name")
            if blob.split("/")[-1] in all_bq_tables:
                print("Datatable already exists in BQ.")
                continue

            blob_name = blob if blob.endswith("/") else blob + "/"
            prefix = bucket_path + blob_name
            local_blob_mount_prefix = os.path.join(MOUNT_PATH, prefix)

            print("Receive Dataset content includes: DS, info.json")
            blob_content = asyncio.run(bucket.gather_folder_blobs(prefix=prefix))

            csv_file = next((file.name for file in blob_content if file.name.endswith(".csv")), None)
            if csv_file:
                with open(os.path.join(local_blob_mount_prefix, csv_file), "r") as f:
                    csv_data = f.read()
                    file_name = csv_file.split(".")[0]
                print("Conv. csv file already in bucket")
            else:
                csv_data, file_name = self.handle_ds_to_csv(blob_content, local_blob_mount_prefix)
                if csv_data is None:
                    continue  # Skip if conversion failed

            print("Start graph conv. -> BQ")
            self.upload_bq_process(
                csv_data,
                file_name,
                bq_handler
            )

        return Response(status=status.HTTP_200_OK)



