from google.cloud import bigquery
from rest_framework.response import Response
from rest_framework.views import APIView
from vertexai.language_models import TextEmbeddingModel

from ggoogle import GCP_ID
from ggoogle.bq import BQ
from ggoogle.bq.auth_handler import BQAuthHandler

bq_auth_handler = BQAuthHandler()

class DocumentQueryView(APIView):
    def post(self, request, *args, **kwargs):
        user_id = request.data.get("user_id")
        query = request.data.get("query")

        if not user_id or not query:
            return Response({"error": "Missing user_id or query"}, status=400)

        # Embed the query

        # Perform vector search in BigQuery
        table_id = user_id + "_files"

        # Construct the SQL query for vector search
        sql_query = f"""
        SELECT
            file,
            url,
            text,
            ML.DISTANCE(embedding, ARRAY{query_embedding}) AS distance
        FROM
            `{GCP_ID}.{bq_auth_handler.ds_id}.{table_id}`
        ORDER BY
            distance
        LIMIT 5;
        """

        query_job = BQ.query(sql_query)
        results = query_job.result()

        # Format the results
        results_list = [{"file": row.file, "url": row.url, "text": row.text, "distance": row.distance} for row in results]

        return Response({"results": results_list}, status=200)