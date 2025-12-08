from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from _google.gdb_manager.bq.bq_handler import BigQueryRAG
from bm.settings import TEST_USER_ID
from builder import DS_ID


class S(serializers.Serializer):
    table_name = serializers.CharField(
        help_text="Name od the Repo you want to query"
    )
    query = serializers.CharField(
        help_text="Rebuild the GCP infrastructure.."
    )


class BigQRag(APIView):
    serializer_class = S

    def post(self, request):
        print("=======================")
        print("Query Request ")
        print("=======================")

        query = request.data.get("query")
        table_name = request.data.get("table_name").upper()
        user_id = TEST_USER_ID  # todo
        print("TEST_USER_ID", user_id)

        bq_rag = BigQueryRAG(
            dataset=DS_ID
        )

        resp = bq_rag.bigquery_vector_search(
            data=query,
            table_id=table_name,
            custom=False,
            limit=2,
            select=["id"],
            model_name=TEST_USER_ID
        )
        return Response(data=dict(response=resp))
