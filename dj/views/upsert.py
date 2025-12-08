from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers

from _bq_core.bq_handler import BQCore


class BQBatchUpsertSerializer(serializers.Serializer):
    """
    Validiert den gesamten Payload für den BigQuery Batch-Upsert.
    """
    dataset_id = serializers.CharField(max_length=255, required=True)
    table = serializers.CharField(max_length=255, required=True)

    schema = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        required=True
    )

    # Die Daten selbst. Wir validieren hier nur, dass es eine Liste von Dictionaries ist.
    # Die Validierung der Zeilen gegen das Schema erfolgt sinnvollerweise in der View-Logik.
    data = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
        required=True
    )


class BQBatchUpsertView(APIView):
    serializer_classes = BQBatchUpsertSerializer
    def post(self, request):
        try:
            payload = request.data
            data = payload.get("data")
            schema = payload.get("schema")
            dataset_id = payload.get("dataset_id")
            table = payload.get("table")
            print("Received data")
            if not data or not schema or not dataset_id or not table:
                return Response({"error": "Missing data"}, status=status.HTTP_400_BAD_REQUEST)
            print("validated data")
            bqc = BQCore(
                dataset_id=dataset_id
            )
            if isinstance(data, list) and isinstance(table, str):
                # Access db_manager however it's available, e.g. via self.db_manager
                bqc.bq_insert(
                    table_id=table.upper(),
                    rows=data,
                )
            print(f"Upserted {len(data)} to {table}")
            return Response({"message": f"Upserted {len(data)} to {table}"}, status=status.HTTP_200_OK)
        except Exception as e:
            print(f"Error upserting: {e}")

