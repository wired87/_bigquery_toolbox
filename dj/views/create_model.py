
from django_ratelimit.decorators import ratelimit
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


@ratelimit(key='ip', rate='10/m', block=True)
class CreateModelView(APIView):
    serializer_class = S

    def post(self, request):
        print("=======================")
        print("CREATE BQ EMBEDDER ")
        print("=======================")

        user_id = TEST_USER_ID  # todo
        print("TEST_USER_ID", user_id)

        bq_rag = BigQueryRAG(
            dataset=DS_ID
        )
        resp = bq_rag.create_embedding_model(
            model_id=TEST_USER_ID,
            connection_id=TEST_USER_ID,
            connection_location="eu-west3",
            replace=True
        )
        return Response(data=dict(response=resp))







