from typing import List
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from _bq_core.bq_handler import BQCore


class BQGetTableDataSerializer(serializers.Serializer):
    """
    Validiert den Payload für die Abfrage von Daten aus BigQuery-Tabellen.
    """
    dataset_id = serializers.CharField(max_length=1024, required=True)
    table_ids = serializers.ListField(
        child=serializers.CharField(),
        allow_empty=False,
        required=True
    )
    target_id = serializers.CharField(max_length=1024, required=True)


class BQGetTableDataView(APIView):
    def post(self, request):
        serializer = BQGetTableDataSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # Die validierten Daten aus dem Serializer holen
        validated_data = serializer.validated_data
        dataset_id = validated_data["dataset_id"]
        table_ids = validated_data["table_ids"]
        target_id = validated_data["target_id"]

        # BigQuery-Client-Instanz erstellen
        bq_handler = BQCore(dataset_id=dataset_id)

        # Die Methode zum Abrufen der Daten aufrufen
        result = self.get_data_from_tables_by_id(
            bq_handler=bq_handler,
            table_ids=table_ids,
            target_id=target_id
        )

        # Das Ergebnis zurückgeben
        return Response(result, status=status.HTTP_200_OK)

    def get_data_from_tables_by_id(
            self,
            bq_handler: BQCore,
            table_ids: List[str],
            target_id: str
    ) -> dict:
        """
        Fragt Daten aus einer Liste von BigQuery-Tabellen ab, gefiltert nach einer spezifischen ID.

        Args:
            bq_handler: Eine Instanz der BQCore-Klasse, die die Verbindung zu BigQuery herstellt.
            table_ids: Eine Liste von BigQuery-Tabellennamen (Strings).
            target_id: Die ID, nach der die Daten gefiltert werden sollen.

        Returns:
            Ein Dictionary, das die Tabellennamen als Schlüssel und die gefilterten
            Ergebnisse als Werte enthält.
        """
        results = {}
        for table_id in table_ids:
            query = f"SELECT * FROM `{bq_handler.pid}.{bq_handler.ds_id}.{table_id}` WHERE id = '{target_id}'"
            print(f"Abfrage für Tabelle {table_id}: {query}")

            query_result = bq_handler.run_query(query, conv_to_dict=True)
            results[table_id] = query_result
        return results