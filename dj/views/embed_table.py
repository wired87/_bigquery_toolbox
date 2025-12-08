from rest_framework import serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from google.cloud import bigquery

from _google import GCP_ID
from _google.gdb_manager.bq.auth_handler import BQAuthHandler

bq_auth_handler = BQAuthHandler()

class S(serializers.Serializer):
    table_id = serializers.CharField(
        default="table_id",
        label="table_id",
        help_text="Table ID"
    )

class GenerateEmbeddingsView(APIView):
    serializer_class = S

    def post(self, request):
        """Generates embeddings for the 'text' field in a BigQuery table."""
        serializer = self.serializer_class(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=400)

        table_id = serializer.validated_data["table_id"]
        client = bigquery.Client(project=GCP_ID)
        table_ref = f"{GCP_ID}.brainmaster.{table_id}"
        temp_table_ref = f"{GCP_ID}.brainmaster.temp_{table_id}"

        try:
            query_job = client.query("query")
            query_job.result()  # Wait for query completion

            return Response({"message": "Embeddings generated successfully."}, status=200)

        except Exception as e:
            return Response({"error": str(e)}, status=500)
