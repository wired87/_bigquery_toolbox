import json




import asyncio
from typing import List, Dict




class ABQHandler(BQCore):
    """
    Unauthorized issue:
    creds valid,
    path correct,
    iam roles set
    small queries or through api get exec without problem
    """

    def __init__(self, dataset: str or None = None):
        self.dataset = dataset or "brainmaster"
        BQCore.__init__(self, dataset_id=self.dataset)
        self.project = GCP_ID

        self.awclient = BigQueryWriteAsyncClient()
        self.arclient = BigQueryReadAsyncClient()

    async def async_write_rows(self, rows: List[Dict], table: str):
        """Writes rows to BigQuery using the BigQuery Storage Write API."""
        print(f"Writing {len(rows)} rows to BQ table: {table}")
        schema={}
        client = BigQueryWriteAsyncClient()
        stream = await client.create_write_stream(
            request=CreateWriteStreamRequest(
                parent=self.get_parent(table),
                write_stream=WriteStream(type_=WriteStream.Type.COMMITTED),
            )
        )

        serialized_rows = [json.dumps(row).encode("utf-8") for row in rows]

        schema = ProtoSchema(
            proto_descriptor=descriptor_pb2.DescriptorProto(
                name="RowData",
                field=[
                    descriptor_pb2.FieldDescriptorProto(
                        name=k, number=1, type=self.bq_type_to_proto_enum(v)
                    ) for k,v in schema.items()

                    # add more fields matching your table...
                ]
            )
        )
        request = AppendRowsRequest(
            write_stream=stream.name,
            proto_rows=AppendRowsRequest.ProtoData(
                writer_schema=schema,
                rows=ProtoRows(serialized_rows=serialized_rows)
            )
        )

        request_iter = iter([request])
        response_stream = await client.append_rows(requests=request_iter)
        async for response in response_stream:
            print("Response offset:", response.append_result.offset) #updated_schema

        print(f"✅ {len(rows)} rows successfully written to {table}")





    async def async_read_rows(self, table, selected_fields: List[str] = None) -> List[Dict]:
        table_path = f"projects/{self.project}/datasets/{self.dataset}/tables/{table}"
        read_session = ReadSession(
            table=table_path,
            data_format=ReadSession.DataFormat.AVRO,
            read_options={"selected_fields": selected_fields or []},  # empty=all
        )

        session = await self.arclient.create_read_session(
            parent=f"projects/{self.project}",
            read_session=read_session,
            max_stream_count=1,
        )

        stream = session.streams[0].name
        request = ReadRowsRequest(read_stream=stream)

        row_reader = self.arclient.read_rows(request)
        rows = []

        async for response in row_reader:
            # Parse AVRO payload here based on schema (placeholder)
            rows.append(response.avro_rows.serialized_binary)

        print(f"📥 Read {len(rows)} rows from {table}.")
        return rows






    async def aupdate_bq_schema(self, keys, table):
        print("BQ schema porcess")
        schema = await self.bq_get_table_schema(table_name=table)
        #print("Current schema:", schema)
        #print("Collected keys")
        #pprint.pp(keys)

        all_queries = []
        for k, v in keys.items():
            if schema is not None and k not in schema:
                all_queries.append(self.add_col_query(
                    col_name=k,
                    table=table,
                    col_type=v
                ))

        #print("all_queries:", all_queries)
        if len(all_queries):
            print("Update BQ schema")
            await asyncio.gather(*[asyncio.to_thread(self.run_query, query) for query in all_queries])
        print(">>>BQ schema process finished")

    async def bq_get_table_schema(self, table_name):
        print("table_name", table_name)
        if table_name:
            try:
                table = self.bqclient.get_table(self.get_table_name(table_name))
                schema = {field.name: field.field_type for field in table.schema}
                #print(f"table schema {table_name}", schema)
                return schema
            except Exception as e:
                print("table name not exists", e)
                await self.acheck_add_bq_table(
                    table_name=table_name,
                    ttype="edge" if any(c.islower() for c in table_name) else "node",
                    schema_fetch=False
                )

    async def acreate_table_batch_query(self, table_batch: List[str], ttype: str) -> str:
        """
        Creates a single query string containing multiple CREATE TABLE IF NOT EXISTS statements
        for a batch of tables.

        Args:
            table_batch: A list of table IDs (strings).
            ttype: The table type ("node" or "edge") to determine naming conventions.

        Returns:
            A single string containing all CREATE TABLE queries separated by newlines.
        """
        query = ""
        for table in table_batch:
            # Note: self.create_default_table_query is a synchronous method,
            # but it primarily handles string formatting (not I/O), so calling it directly
            # in an async loop is efficient and safe in this context.
            query += f"{self.create_default_table_query(table_id=table, ttype=ttype)}\n"

        # NOTE to avoid SQL syntax error: self.create_default_table_query must
        # remove the trailing comma after the last column 'id STRING'.

        return query

    def aget_create_bq_table(self, table_names, ttype="node"):
        try:
            #if query is None:
            query = self.acreate_table_batch_query(
                table_batch=table_names,
                ttype=ttype
            )
            table:_EmptyRowIterator=self.run_query(query) #_EmptyRowIterator
            print("schema", table.schema)
            print("pages", table.pages)
            print("total_rows", table.total_rows)
            return table
        except Exception as e:
            print("Error create_table", e)


    async def abq_check_table_exists(self, table_name):
        try:
            self.bqclient.get_table(f"{self.pid}.{self.ds_id}.{table_name}")
            print("Table exists")
            return True
        except Exception as e:
            print(f"Table not {table_name} found:", e)
            return False

    async def acheck_add_bq_table(self, table_name, ttype: str, schema_fetch=True):
        print("BQ Table creation process")
        try:
            table_exists = await self.abq_check_table_exists(table_name)
            print(f"{ttype} table {table_name}", table_exists)

            if not table_exists or table_exists is False:
                print(f"🛠 Creating {ttype} Table: {table_name}")
                self.aget_create_bq_table(table_name, ttype=ttype)

            if schema_fetch:
                return await self.bq_get_table_schema(table_name)

        except Exception as e:
            print(f"Error check add BQ table: {e}")
        print(">>>BQ Table creation process finished")





    async def delete_table(self, table_id: str) -> None:
        table_ref = self.bqclient.dataset(self.dataset).table(table_id)
        try:
            await asyncio.to_thread(self.bqclient.delete_table, table_ref)
            print(f"🗑️ Table {table_id} deleted.")
        except exceptions.NotFound:
            print(f"⚠️ Table {table_id} not found.")

    async def get_table_schema(self, table_id: str) -> List[TableFieldSchema]:
        table_ref = self.bqclient.dataset(self.dataset).table(table_id)
        table = await asyncio.to_thread(self.bqclient.get_table, table_ref)
        return table.schema