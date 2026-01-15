import os
import json
from typing import List
import dotenv

from auth.load_sa_creds import load_service_account_credentials

dotenv.load_dotenv()
import networkx as nx
import pandas as pd
import io
import re

from google.api_core.exceptions import NotFound
from google.cloud.bigquery.table import _EmptyRowIterator

from google.cloud import bigquery

# Default Configuration
BQ_DATASET_ID = "IDB"
class BQGroundZero:

    """
    BQ ERLAUBT NUR 5 ROW UPSERTIONS / 10sec / TABLE
    todo: migrate tables  from sp <-> bq
    """

    def __init__(self, dataset_id=None):
        self.bqclient = bigquery.Client(
            credentials=load_service_account_credentials(os.getenv("GOOGLE_APPLICATION_CREDENTIALS"))
        )
        self.pid = self.bqclient.project
        self.ds_id = dataset_id or BQ_DATASET_ID
        self.base_path = f"{self.pid}.{self.ds_id}"
        self.ds_ref = self.base_path
        self.ensure_dataset_exists()

    def ensure_dataset_exists(self, ds_name=None):
        """
        Ensure that the BigQuery dataset exists before creating tables.
        """
        if ds_name is None:
            ds_name = self.ds_id

        ds_name = f"{self.pid}.{ds_name}"
        try:
            self.bqclient.get_dataset(ds_name)
            # print(f"Dataset '{ds_name}' already exists.")
        except NotFound:
             print(f"Dataset '{ds_name}' does not exist. Creating...")
             try:
                 dataset = bigquery.Dataset(ds_name)
                 dataset.location = "US"
                 self.bqclient.create_dataset(dataset)
                 print(f"✅ Dataset '{ds_name}' created successfully.")
             except Exception as create_err:
                 print(f"❌ Failed to create dataset '{ds_name}': {create_err}")
                 # Re-raise or handle as critical failure depending on context
                 # For BQHandler generic init, maybe just print
        except Exception as e:
            print(f"❌ Error checking dataset '{ds_name}': {e}")



    def sql_escape_string(self, s):
        """Escape a string for use in BigQuery SQL."""
        if s is None:
            return "NULL"
        # Replace backslashes first, then single quotes, then newlines
        s = str(s).replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n").replace("\r", "\\r")
        return f"'{s}'"

    def upsert_query(self, table_id):
        return f"""
        MERGE INTO `{self.pid}.{self.ds_id}.{table_id.upper()}` T
        USING `{self.pid}.{self.ds_id}.{table_id.upper()}` S
        ON T.nid = S.nid
        WHEN MATCHED THEN
          UPDATE SET
            T.column1 = S.column1,
            T.column2 = S.column2,
            T.last_updated = CURRENT_TIMESTAMP() 
        WHEN NOT MATCHED THEN
          INSERT (nid, column1, column2)
          VALUES (S.nid, S.column1, S.column2);
        """

    def upsert_row_query(self, table_id: str, rows: list[dict], schema: dict[str]) -> str:
        # 1. Determine column names and types from schema to ensure consistent order
        if isinstance(schema, list):
            col_map = {}
            col_names = []
            for f in schema:
                col_names.append(f.name)
                f_type = f.field_type
                if f.mode == "REPEATED":
                    f_type = f"ARRAY<{f_type}>"
                col_map[f.name] = f_type
        elif isinstance(schema, dict):
            col_map = schema
            col_names = list(schema.keys())
        else:
            raise ValueError("Schema must be a dict or list of SchemaFields")

        # 2. Build STRUCT strings
        struct_rows = []
        for row in rows:
            val_strs = []
            for k in col_names:
                v = row.get(k)
                col_type = col_map.get(k, "STRING")
                
                # Skip columns with backslashes in name or type
                if "\\" in col_type or "\\" in k:
                    continue

                if v is None:
                    val_strs.append(f'CAST(NULL AS {col_type}) AS {k}')
                elif isinstance(v, bool):
                    val_strs.append(f'{str(v).upper()} AS {k}')
                elif isinstance(v, (int, float)):
                    val_strs.append(f'{v} AS {k}')
                elif isinstance(v, str):
                    # Use the new sql_escape_string helper
                    val_strs.append(f'{self.sql_escape_string(v)} AS {k}')
                elif isinstance(v, list):
                    if "ARRAY" in col_type:
                        # Build array literal
                        safe_list = []
                        for item in v:
                            if item is None:
                                safe_list.append("NULL")
                            elif isinstance(item, bool):
                                safe_list.append(str(item).upper())
                            elif isinstance(item, (int, float)):
                                safe_list.append(str(item))
                            else:
                                safe_list.append(self.sql_escape_string(str(item)))
                        array_literal = f"[{', '.join(safe_list)}]"
                        val_strs.append(f'{array_literal} AS {k}')
                    else:
                        # Store list as JSON string
                        val_strs.append(f'{self.sql_escape_string(str(v))} AS {k}')
                elif isinstance(v, dict):
                    # Store dict as JSON string
                    val_strs.append(f'{self.sql_escape_string(str(v))} AS {k}')
                else:
                    # Fallback: convert to string
                    val_strs.append(f'{self.sql_escape_string(str(v))} AS {k}')

            struct_str = ", ".join(val_strs)
            struct_rows.append(f"STRUCT({struct_str})")

        # Construct the USING clause
        unnested_source = f"""
            (SELECT * FROM UNNEST([
                {', '.join(struct_rows)}
            ]))
        """

        # Construct UPDATE SET clause
        update_clause_parts = []
        for k in col_names:
            col_type = col_map.get(k, "STRING")
            if "\\" not in col_type and "\\" not in k:
                if "ARRAY" not in col_type:
                    update_clause_parts.append(f"T.{k} = CAST(S.{k} AS {col_type})")
                else:
                    update_clause_parts.append(f"T.{k} = S.{k}")
        update_clause = ",\n          ".join(update_clause_parts)

        # Construct INSERT clause
        valid_cols = [c for c in col_names if "\\" not in c and "\\" not in col_map.get(c, "STRING")]
        insert_cols = ", ".join(valid_cols)
        insert_vals_list = []
        for col in valid_cols:
            col_type = col_map.get(col, "STRING")
            if "ARRAY" not in col_type:
                insert_vals_list.append(f"CAST(S.{col} AS {col_type})")
            else:
                insert_vals_list.append(f"S.{col}")
        insert_vals = ", ".join(insert_vals_list)

        # Primary Key
        primary_key = "nid"
        if "id" in col_names:
            primary_key = "id"
        
        query = f"""
            MERGE INTO `{self.pid}.{self.ds_id}.{table_id}` T
            USING {unnested_source} AS S
            ON T.{primary_key} = S.{primary_key}
            WHEN MATCHED THEN
              UPDATE SET
                {update_clause}
            WHEN NOT MATCHED THEN
              INSERT ({insert_cols}) VALUES ({insert_vals})
        """
        return query.strip()

    def get_parent(self, table:str):
        return f"projects/{self.pid}/datasets/{self.ds_id}/tables/{table}"


    def get_table_name(self, table):
        return f"{self.pid}.{self.ds_id}.{table}"

    def table_schema_query(self, table):
        return f"""
        
        SELECT
            column_name, data_type
        FROM
          `{self.pid}.{self.ds_id}.INFORMATION_SCHEMA.COLUMNS`
        WHERE
          table_name = '{table}'
        ORDER BY
          ordinal_position
        """
    def create_default_table_query(self, table_id, ttype):
        query= f"""
            CREATE TABLE IF NOT EXISTS `{self.pid}.{self.ds_id}.{table_id.upper() if ttype == "node" else table_id}` (
                id STRING,
            )
            """
        #print("Table query", query)
        return query


    def add_col_query(self, col_name, table, col_value):
        col_type=self.get_bq_type(col_value)
        return f"""
            ALTER TABLE `{self.pid}.{self.ds_id}.{table}`
            ADD COLUMN `{col_name}` {col_type}
        """

    def get_id_from_table_query(self,  table,):
        return f"""
            SELECT id FROM `{self.pid}.{self.ds_id}.{table}`
        """

    def get_entry_from_table_query(self, table, key_of_interest, value_of_interest):
        return f"""
            SELECT * FROM `{self.pid}.{self.ds_id}.{table}`
            WHERE {key_of_interest} = {value_of_interest}
        """


    def entry_from_parent_entry_query(self, table, parent_entry):
        return f"""
        SELECT *
        FROM `{self.pid}.{self.ds_id}.{table}`
        WHERE EXISTS(SELECT 1 FROM UNNEST(parent) AS item 
        WHERE item = {parent_entry})
        """

    def get_bq_type(self, value):
        # Convert Python types to BigQuery types
        if isinstance(value, int):
            return "INT64"
        elif isinstance(value, float):
            return "FLOAT64"
        elif isinstance(value, bool):
            return "BOOL"
        elif isinstance(value, bytes):
            return "BYTES"
        elif isinstance(value, list):
            return "ARRAY<STRING>"  # Adjust as needed
        else:
            return "STRING"


    def schema_from_dict(self, rows:list, embed=None):
        """
        Dynamically infers BigQuery schema from a list of JSON dictionaries.

        Args:
            json_data (list): A list of dictionaries representing JSON rows.

        Returns:
            list: A list of bigquery.SchemaField objects.
        """
        schema_map = {}
        all_keys = set()
        
        for data in rows:
            all_keys.update(data.keys())
            for key, value in data.items():
                if value is None:
                    continue
                    
                if isinstance(value, bool):
                    field_type = "BOOL"
                elif isinstance(value, int):
                    field_type = "INT64"
                elif isinstance(value, float):
                    field_type = "FLOAT64"
                elif isinstance(value, list):
                    if len(value) > 0 and isinstance(value[0], str):
                         field_type = "ARRAY<STRING>"
                    elif len(value) > 0 and isinstance(value[0], (int, float)):
                         field_type = "ARRAY<FLOAT64>"
                    elif embed:
                         field_type = "ARRAY<FLOAT64>" # Legacy support
                    else:
                         field_type = "STRING" # Fallback
                else:
                    field_type = "STRING"
                
                if key not in schema_map:
                    schema_map[key] = field_type
                else:
                    # Conflict resolution
                    prev = schema_map[key]
                    if prev != field_type:
                        if "ARRAY" in prev and "ARRAY" in field_type:
                             pass # Assume compatible
                        elif prev == "INT64" and field_type == "FLOAT64":
                            schema_map[key] = "FLOAT64"
                        elif prev == "FLOAT64" and field_type == "INT64":
                            pass # Keep FLOAT64
                        else:
                            schema_map[key] = "STRING" # Fallback to string for mixed types
                            
        # Handle keys that were always None
        for key in all_keys:
            if key not in schema_map:
                schema_map[key] = "STRING"

        schema = []
        for k, v in schema_map.items():
            mode = "NULLABLE"
            field_type = v
            if v.startswith("ARRAY<"):
                mode = "REPEATED"
                # Extract inner type: ARRAY<STRING> -> STRING
                field_type = v[6:-1]
            
            schema.append(bigquery.SchemaField(k, field_type, mode=mode))
        return schema

    def convert_dict_shema_bq(self, schema):
        s=[]
        for k,v in schema.items():
            s.append(bigquery.SchemaField(k, v, mode="NULLABLE"))
        return s

    def run_query(self, query: str or list, conv_to_dict=False, raise_exception=False):
        try:
            if isinstance(query, list):
                query = ";\n".join(query)

            job = self.bqclient.query(query)

            result = job.result()

            if conv_to_dict is True:
                result = [dict(row) for row in result]

            # print("BQ Query Result finished")
            # print("Return", result)

            return result
        except Exception as e:
            print("Error executing query:", e)
            if raise_exception:
                raise e


class BQCore(BQGroundZero):

    def __init__(self, dataset_id=None):
        BQGroundZero.__init__(self, dataset_id)
        self.dataset_id=dataset_id
        self.batch_upload_size = 200

    def get_tables(self) -> List[str]:
        tables = []
        for table in self.bqclient.list_tables(self.ds_id):
            tables.append(table.table_id)

        return tables



    def bq_check_table_exists(self, table_name):
        try:
            self.bqclient.get_table(f"{self.pid}.{self.ds_id}.{table_name}")
            print("Table exists")
            return True
        except Exception as e:
            print(f"Table not {table_name} found:", e)
            return False



    def get_create_bq_table(self, table_name, query=None, ttype="node"):
        table_exists = self.bq_check_table_exists(table_name)
        print(f"{ttype} table {table_name}", table_exists)

        try:
            if not table_exists or table_exists is False or table_exists is None:
                print(f"🛠 Creating {ttype} Table: {table_name}")
                if query is None:
                    query = self.create_default_table_query(table_id=table_name, ttype=ttype)
                table:_EmptyRowIterator=self.run_query(query)
                print("schema", table.schema)
                print("pages", table.pages)
                print("total_rows", table.total_rows)
                return table
            else:
                print("Table already exists")
        except Exception as e:
            print("Error create_table", e)

    def bq_get_table_schema(self, table_name):
        if table_name:
            try:
                table = self.bqclient.get_table(self.get_table_name(table_name))
                schema = {field.name: field.field_type for field in table.schema}
                # print(f"table schema {table_name}", schema)
                print(f"schema received: {schema}")
                return schema
            except Exception as e:
                print(f"table {table_name} not found or error: {e}. Attempting creation...")
                # Ensure the table is created with default schema if missing
                self.get_create_bq_table(
                    table_name=table_name,
                    ttype="edge" if any(c.islower() for c in table_name) else "node"
                )
                # Re-try getting schema after creation
                return self.bq_get_table_schema(table_name)


    def update_bq_schema(self, table, rows):
        schema = self.bq_get_table_schema(table_name=table)

        all_queries = []
        for r in rows:
            for k, v in r.items():
                if schema is not None and k not in schema:
                    all_queries.append(self.add_col_query(
                        col_name=k,
                        table=table,
                        col_value=v
                    ))

        # print("all_queries:", all_queries)
        if len(all_queries):
            print("Update BQ schema")
            for query in all_queries:
                self.run_query(query)







    def up2bq(self, table_id, csv_data, mode="o"):
        """
        Uploads CSV data from a string variable to BigQuery, auto-detecting the schema.

        Args:
            table_id: The ID of the BigQuery table.
            csv_data: The CSV data as a string.

        Returns:
            None. Raises an exception if an error occurs.
        """
        print("Update BQ ROWS")
        try:
            if mode == "a": # append
                write_disposition = bigquery.WriteDisposition.WRITE_APPEND
            elif mode == "o": # overwrite
                write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE
            elif mode == "u": #unique
                write_disposition = bigquery.WriteDisposition.WRITE_EMPTY
            else:
                write_disposition = bigquery.WriteDisposition.WRITE_TRUNCATE

            # 2. Construct the table reference
            table_ref = f"{GCP_ID}.{self.ds_id}.{table_id}"

            # 3. Create a Pandas DataFrame from the CSV data
            df = pd.read_csv(io.StringIO(csv_data))  # Read csv from string

            # 4. Infer the schema from the DataFrame
            job_config = bigquery.LoadJobConfig(
                # Schema is auto-detected from Pandas DataFrame
                source_format=bigquery.SourceFormat.CSV,
                autodetect=True,  # Important for auto-schema detection
                write_disposition=write_disposition,  # Overwrite table if exists
                max_bad_records=50,  # Allow up to 50 bad rows before failing

                # Optionally set other load job config options
                # like field delimiters, skip_leading_rows, etc.
            )

            # 5. Load the DataFrame to BigQuery
            job = self.bqclient.load_table_from_dataframe(df, table_ref, job_config=job_config)  # Make an API request.
            job.result()  # Wait for the job to complete.

            print(f"Successfully loaded CSV data to {table_ref}")

        except Exception as e:
            print(f"An error occurred: {e}")
            raise  # Re-raise the exception for proper error handling

    def get_layer_from_table_name(self, input_string):
        parts = input_string.split("-")
        return parts[1] if len(parts) > 1 else None

    def get_column_values(self, table: str, column: str) -> List[str]:
        query = f"SELECT DISTINCT {column} FROM `{self.pid}.{self.ds_id}.{table}`"
        results = self.run_query(query)
        return [row[column] for row in results]

    def id_mapping(self, rows, all_ids):
        print("")
        existing_rows=[]
        new_rows=[]
        for row in rows:
            if row["nid"] in all_ids:
                existing_rows.append(row)
            else:
                new_rows.append(row)
        return existing_rows, new_rows


    def ensure_table_exists(self, table_name: str,rows:list, ds_id=None):
        """
        Ensures a BigQuery table exists, creating it if necessary.
        :param table_name: The BigQuery table name.
        """
        if ds_id is None:
            ds_id = self.ds_id
        table_ref = f"{self.bqclient.project}.{ds_id}.{table_name}"
        schema = self.schema_from_dict(rows)
        try:
            self.bqclient.get_table(table_ref)
        except NotFound:
            print(f"Table {table_name} not found, creating...")
            table = bigquery.Table(table_ref, schema=schema)

            self.bqclient.create_table(table)

        except Exception as e:
            print(f"Erro happened:{e}")

        return table_ref, schema


    def get_ds_ref(self, ds_id=None):
        ds_id = ds_id or self.ds_id
        return f"{self.pid}.{ds_id}"

    def bq_insert(self, table_id: str, rows: List[dict], upsert=False, ds_id=None):
        print(f"Preparing to insert/upsert {len(rows) if isinstance(rows, list) else 1} rows into {table_id}...")
        table_ref, schema=self.ensure_table_exists(table_id, rows, ds_id)
        self.update_bq_schema(table_id, rows)

        if not isinstance(rows, list):
            rows = [rows]  # if just Single dict
        
        total_rows = len(rows)
        if total_rows > 0:
            print(f"🚀 Starting upsert for {total_rows} rows to '{table_id}'...")
            
            # Use a smaller default batch size for safety, but respect the user's wish if possible
            # We will use the recursive strategy to handle large batches
            
            # Initial batch processing
            total_batches = (total_rows + self.batch_upload_size - 1) // self.batch_upload_size
            
            for i in range(0, total_rows, self.batch_upload_size):
                batch_num = (i // self.batch_upload_size) + 1
                batch_chunk = rows[i:i + self.batch_upload_size]
                if not batch_chunk:
                    continue
                
                print(f"  📦 Processing batch {batch_num}/{total_batches} ({len(batch_chunk)} rows)...")
                self._upsert_batch_recursive(table_id, batch_chunk, schema, upsert, table_ref)
            
            print(f"✅ Completed upsert for {total_rows} rows.")
        else:
            print("⚠️ No new rows to upsert")

    def _upsert_batch_recursive(self, table_id, rows, schema, upsert, table_ref):
        """
        Recursively tries to upsert a batch. If it fails, splits the batch in half and retries.
        """
        if not rows:
            return

        try:
            if upsert is True:
                query = self.upsert_row_query(
                    table_id, rows=rows, schema=schema
                )
                # We must raise exception here to trigger the retry logic
                self.run_query(query, raise_exception=True)
            else:
                result = self.bqclient.insert_rows_json(table=table_ref, json_rows=rows)
                if result:
                    raise Exception(f"Insert errors: {result}")
                    
        except Exception as e:
            error_msg = str(e)
            
            # Log query to file for debugging
            if True:
                try:
                    import os
                    debug_file = os.path.join(os.path.dirname(__file__), "failed_query_debug.sql")
                    with open(debug_file, "w", encoding="utf-8") as f:
                        f.write(f"-- Error: {error_msg}\n")
                        f.write(f"-- Table: {table_id}\n")
                        f.write(f"-- Rows: {len(rows)}\n")
                        f.write(f"-- First row: {json.dumps(rows[0], default=str)[:200]}\n\n")
                        if upsert:
                            query = self.upsert_row_query(table_id, rows=rows, schema=schema)
                            f.write(query)
                    print(f"🐛 DEBUG: Failed query saved to {debug_file}")
                except Exception as log_err:
                    print(f"⚠️  Could not save debug query: {log_err}")
            
            # If we have more than 1 row, we can split and retry
            if len(rows) > 1:
                print(f"⚠️ Batch of {len(rows)} failed. Splitting and retrying... Error: {error_msg[:100]}...")
                mid = len(rows) // 2
                left_half = rows[:mid]
                right_half = rows[mid:]
                
                self._upsert_batch_recursive(table_id, left_half, schema, upsert, table_ref)
                self._upsert_batch_recursive(table_id, right_half, schema, upsert, table_ref)
            else:
                # If we are down to 1 row and it still fails, we log it and move on (or raise)
                print(f"❌ Failed to upsert single row. Error: {error_msg}")
                print(f"   Row content: {json.dumps(rows[0], default=str)[:200]}...")
                # Optionally dump the failing row to a file for inspection
                # print(f"Failing row: {rows[0]}")




    def insert_col(self, table_id: str, column_name: str, column_type: str):
        """
        Checks if a column exists in the BigQuery table. If not, it creates it.

        Args:
            project_id (str): Google Cloud Project ID.
            dataset_id (str): BigQuery Dataset ID.
            table_id (str): BigQuery Table ID.
            column_name (str): Name of the column to check/create.
            column_type (str): BigQuery data type (e.g., STRING, INT64, FLOAT64).
        """
        print("insert col")
        table_ref = f"{self.pid}.{self.ds_id}.{table_id}"

        # Get table schema
        table = self.bqclient.get_table(table_ref)
        existing_columns = [field.name for field in table.schema]

        if column_name not in existing_columns:
            print(f"⚠️ Column '{column_name}' does not exist. Adding it...")
            alter_query = f"ALTER TABLE `{table_ref}` ADD COLUMN {column_name} {column_type}"
            self.bqclient.query(alter_query).result()
            print(f"✅ Column '{column_name}' added successfully.")
        else:
            print(f"✅ Column '{column_name}' already exists.")


    def list_tables(self) -> list:
        """Lists all tables in a BigQuery dataset.

        Args:
            client: A BigQuery client instance.
            dataset_id: The ID of the dataset.

        Returns:
            A list of bigquery.Table objects, or an empty list if no tables are found
            or if an error occurs.  Returns None if an error occurs.
        """
        try:
            dataset_ref = self.bqclient.dataset(self.ds_id)  # API request
            tables = list(self.bqclient.list_tables(dataset_ref))  # API request
            table_names = [table.table_id for table in tables]
            return table_names
        except Exception as e:
            print(f"An error occurred: {e}")
            return None


    def get_bq_type(self, value):
        """
        Determines the BigQuery type for a given Python value.
        :param value: The value to determine the type for.
        :return: A BigQuery-compatible data type.
        """
        if value is None:
            return "STRING"
        if isinstance(value, bool):
            return "BOOL"
        if isinstance(value, int):
            return "INT64"
        if isinstance(value, float):
            return "FLOAT64"
        if isinstance(value, list):

            return f"ARRAY<{self.get_bq_type(value[0]) if len(value) else 'STRING'}>"

        return "STRING"



class BigQueryGraphHandler(BQCore):
    def __init__(self):
        """Initializes the BigQuery handler."""
        super().__init__()

    def upload_graph(self, graph: nx.Graph):
        """
        Converts a NetworkX graph into CSV format (nodes & edges) and uploads it to BigQuery.

        :param graph: A NetworkX graph object.
        """

        # Ensure tables exist
        self.ensure_table_exists("nodes")
        self.ensure_table_exists("EDGES")

        # Convert to DataFrames
        nodes_df = self.graph_to_nodes_df(graph)
        edges_df = self.graph_to_edges_df(graph)

        # Ensure schema consistency
        self.check_add_fields(self.extract_schema(nodes_df), "nodes")
        self.check_add_fields(self.extract_schema(edges_df), "EDGES")

        # Upload to BigQuery
        self.upload_dataframe_to_bq(nodes_df, "nodes")
        self.upload_dataframe_to_bq(edges_df, "EDGES")

    def graph_to_nodes_df(self, graph: nx.Graph) -> pd.DataFrame:
        """
        Converts NetworkX nodes to a Pandas DataFrame.

        :param graph: A NetworkX graph object.
        :return: Pandas DataFrame containing nodes.
        """
        node_data = []
        for node, attrs in graph.nodes(data=True):
            row = dict(nid=node, **attrs)
            new_row = {}
            for k, v in row.items():
                new_row[re.sub(r"\.", "_", k)] = v  # Normalize column names
            node_data.append(new_row)
        return pd.DataFrame(node_data)

    def graph_to_edges_df(self, graph: nx.Graph) -> pd.DataFrame:
        """
        Converts NetworkX edges to a Pandas DataFrame.

        :param graph: A NetworkX graph object.
        :return: Pandas DataFrame containing edges.
        """
        edge_data = []
        for src, tgt, attrs in graph.edges(data=True):
            row = dict(src=src, tgt=tgt, **attrs)
            new_row = {}
            for k, v in row.items():
                new_row[re.sub(r"\.", "_", k)] = v
            edge_data.append(new_row)
        return pd.DataFrame(edge_data)

    def extract_schema(self, df: pd.DataFrame) -> dict:
        """
        Extracts a schema from a Pandas DataFrame for BigQuery.
        :param df: The Pandas DataFrame.
        :return: Dictionary mapping column names to BigQuery types.
        """
        schema = {}
        for col in df.columns:
            sample_value = df[col].dropna().iloc[0] if not df[col].dropna().empty else None
            schema[col] = self.get_bq_type(sample_value)
        print("schema", schema)
        return schema

    def upload_dataframe_to_bq(self, df: pd.DataFrame, table_name: str):
        """
        Uploads a Pandas DataFrame to BigQuery.

        :param df: The DataFrame to upload.
        :param table_name: The BigQuery table name.
        """
        table_ref = f"{self.bqclient.project}.{self.ds_id}.{table_name}"
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.CSV,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_APPEND,
            max_bad_records=50,
        )
        csv_buffer = io.StringIO()
        df.to_csv(csv_buffer, index=False)
        csv_buffer.seek(0)  # Reset buffer position

        job = self.bqclient.load_table_from_file(csv_buffer, table_ref, job_config=job_config)
        job.result()  # Wait for completion
        print(f"✅ Uploaded {len(df)} rows to {table_name}.")

    def check_add_fields(self, schema: dict, table_name: str):
        """
        Ensures all required columns exist in BigQuery before uploading.

        :param schema: Expected schema dictionary {column_name: column_type}.
        :param table_name: The BigQuery table name.
        """
        existing_columns = self.get_column_names(table_name)
        new_columns = {col: col_type for col, col_type in schema.items() if col not in existing_columns}
        if new_columns:
            self.add_columns_bulk(table_name, new_columns)

    def get_column_names(self, table_name: str):
        """
        Retrieves column names from a BigQuery table.
        :param table_name: The BigQuery table name.
        :return: A set of column names.
        """
        table_ref = f"{self.bqclient.project}.{self.ds_id}.{table_name}"
        try:
            table = self.bqclient.get_table(table_ref)
            return {field.name for field in table.schema}
        except Exception as e:
            print(f"⚠️ Error retrieving columns for {table_name}: {e}")
            return set()

    def add_columns_bulk(self, table_name: str, new_columns: dict):
        """
        Adds multiple missing columns in one operation.

        :param table_name: The BigQuery table name.
        :param new_columns: Dictionary {column_name: column_type}.
        """
        table_ref = f"{self.bqclient.project}.{self.ds_id}.{table_name}"
        table = self.bqclient.get_table(table_ref)
        updated_schema = table.schema + [bigquery.SchemaField(col, col_type) for col, col_type in new_columns.items()]
        table.schema = updated_schema
        self.bqclient.update_table(table, ["schema"])
        print(f"✅ Added missing columns: {', '.join(new_columns.keys())}")





import typing
from typing import List, Optional
from google.cloud.bigquery import ScalarQueryParameter, ArrayQueryParameter # Import for explicit parameter typing


class BigQueryRAG(BQCore):  # Inherit from BigQueryLoader if you have one
    """
    A class to perform RAG-like vector search using Google Cloud BigQuery.
    Mirrors the functionality of SpannerRAG for vector search.
    """

    def __init__(self, dataset: str or None = None):
        BQCore.__init__(self, dataset)
        self.project = self.pid
        self.base_path=f"{self.pid}.{self.ds_id}"

    # inlude ping 
    def bigquery_vector_search(
        self,
        data: typing.Any, # Can be text for custom=False, or already embedded data if custom=True
        table_id: str,
        custom: bool = True,
        limit: int = 10,
        select: List[str] = ["id", "content", "file_id"],
        embed_column: str = "embedding", # Standardized column name
        model_name: Optional[str] = None # Required if custom=False
    ) -> List[typing.Dict]:
        """
        Performs a vector similarity search in a BigQuery table.

        Args:
            data: The query data. If custom=True, this should be the pre-calculated
                  embedding vector (List[float]). If custom=False, this should
                  be the text data (str) to be embedded by BQML.
            table_id: The ID of the BigQuery table containing the embeddings.
            custom: If True, uses a pre-calculated embedding from 'data'.
                    If False, uses BQML's GENERATE_EMBEDDING to embed 'data'.
            limit: The maximum number of results to return.
            select: A list of column names to select from the table,
                    in addition to the calculated distance.
            embed_column: The name of the column in the table that stores the embeddings.
            model_name: Required if custom=False. The name of the BQML model
                        or the model identifier string (e.g., 'text-embedding-004')
                        used for embedding the query text. This can be a full
                        `project.dataset.model` path or just the model ID if in
                        the same dataset.

        Returns:
            A list of dictionaries, where each dictionary represents a row
            with the selected columns and the cosine distance.
        """
        full_table_path = f"`{self.base_path}.{table_id}`" # Use backticks for table names

        query_parameters = []
        selected_columns_sql = ', '.join([f't.{col}' for col in select]) # Select columns from the table alias

        if custom:
            # Assume 'data' is already the embedding vector (List[float])
            if not isinstance(data, list) or not all(isinstance(i, (int, float)) for i in data):
                 raise ValueError("When custom=True, 'data' must be a list of numbers (embedding vector).")

            query = f"""
            SELECT
                {selected_columns_sql},
                COSINE_DISTANCE(
                    t.{embed_column},
                    @query_embedding
                ) AS distance
            FROM {full_table_path} AS t
            WHERE t.{embed_column} IS NOT NULL
            ORDER BY distance
            LIMIT @limit;
            """
            # BigQuery uses ARRAY<FLOAT64> for vector embeddings
            # Use ArrayQueryParameter for array types, not ScalarQueryParameter
            query_parameters.append(ArrayQueryParameter("query_embedding", "FLOAT64", data))
            query_parameters.append(ScalarQueryParameter("limit", "INT64", limit))

        else:
            # Use BQML to generate the embedding for the query text 'data'
            if not isinstance(data, str):
                 raise ValueError("When custom=False, 'data' must be a string (query text).")
            if not model_name:
                 raise ValueError("When custom=False, 'model_name' must be provided.")

            # Use GENERATE_EMBEDDING function with the specified model
            # Join the main table with the result of the embedding function
            query = f"""
            SELECT
                {selected_columns_sql},
                COSINE_DISTANCE(
                    t.{embed_column},
                    embeddings.vector # The column name for the embedding vector output from GENERATE_EMBEDDING is 'vector'
                ) AS distance
            FROM {full_table_path} AS t,
            ML.GENERATE_EMBEDDING(MODEL `{self.pid}.{self.ds_id}.{model_name}`, # Reference the model
                (SELECT @query_text AS content) # Input data as a STRUCT with 'content' field
            ) AS embeddings
            WHERE t.{embed_column} IS NOT NULL
            ORDER BY distance
            LIMIT @limit;
            """
            query_parameters.append(ScalarQueryParameter("query_text", "STRING", data))
            query_parameters.append(ScalarQueryParameter("limit", "INT64", limit))
            # Note: Depending on the model type (e.g., a remote model like text-embedding-004
            # versus a BQML trained model), the MODEL reference might just be
            # `model_name` if it's a public endpoint string or a model alias.
            # Using the full path `project.dataset.model_name` is safest for
            # models created within your BQML environment.

        print("Executing BigQuery SQL:")
        print(query)

        # Configure the query job with parameters
        job_config = bigquery.QueryJobConfig(query_parameters=query_parameters)
        query_job = self.bqclient.query(query, job_config=job_config)
        return [dict(row) for row in query_job.result()]

    def generate_embeddings(self, table_id: str, content_column: str = "content", embed_column: str = "embed", model_name: str = "text-embedding-004"):
        """
        Generates embeddings for rows where the embedding column is NULL.
        Assumes the table exists and has the content column.
        Creates the embedding column if it doesn't exist.
        """
        full_table_path = f"`{self.pid}.{self.ds_id}.{table_id}`"
        
        # 1. Ensure embedding column exists
        self.insert_col(table_id, embed_column, "ARRAY<FLOAT64>")
        
        # 2. Create Remote Model if not exists (This requires connection setup, assuming it exists or using a public one if possible, 
        # but usually we need a connection. For simplicity, we assume a model 'embedding_model' exists or we use a public one via a connection)
        # We will try to use a model named 'embedding_model' in the dataset.
        # If the user hasn't set up a remote model, this might fail. 
        # We'll assume the user has a model or we create a placeholder one.
        # Actually, let's try to create it if we can, but we need a connection ID.
        # For now, we will assume the model `embedding_model` is properly configured in the dataset.
        
        model_path = f"`{self.pid}.{self.ds_id}.embedding_model`"
        
        # 3. Update embeddings
        query = f"""
        UPDATE {full_table_path} t
        SET t.{embed_column} = ml_generate_embedding_result.vector
        FROM ML.GENERATE_EMBEDDING(
            MODEL {model_path},
            (
                SELECT {content_column} AS content, id
                FROM {full_table_path}
                WHERE {embed_column} IS NULL AND {content_column} IS NOT NULL
            )
        ) AS ml_generate_embedding_result
        WHERE t.id = ml_generate_embedding_result.id
        """
        
        print(f"Generating embeddings for {table_id}...")
        try:
            job = self.bqclient.query(query)
            job.result()
            print(f"Embeddings updated for {table_id}")
        except Exception as e:
            print(f"Failed to generate embeddings: {e}")
            print("Ensure you have a remote model named 'embedding_model' in your dataset.")




    def ensure_embedding_model(self, model_name: str = "embedding_model", connection_id: str = "vertex_ai_conn"):
        """
        Ensures the BigQuery ML remote model exists.
        Creates a connection and the model if missing.
        """
        model_ref = f"{self.pid}.{self.ds_id}.{model_name}"
        try:
            self.bqclient.get_model(model_ref)
            # print(f"Model {model_name} already exists.")
            return
        except NotFound:
            print(f"Model {model_name} not found. Initiating setup...")

        # 1. Create Connection (if not exists)
        location = "us" # Assuming US multi-region for dataset
        full_connection_id = f"{location}.{connection_id}"
        
        print(f"Ensuring connection `{self.pid}.{full_connection_id}` exists...")
        create_conn_query = f"""
        CREATE CONNECTION IF NOT EXISTS `{self.pid}.{full_connection_id}`
        OPTIONS(cloud_resource=STRUCT());
        """
        try:
            self.run_query(create_conn_query)
        except Exception as e:
            print(f"Warning: Could not create connection: {e}")
            # Proceeding, maybe it exists or user has no permission

        # 2. Create Model
        print(f"Creating remote model `{model_ref}`...")
        create_model_query = f"""
        CREATE OR REPLACE MODEL `{model_ref}`
        REMOTE WITH CONNECTION `{self.pid}.{full_connection_id}`
        OPTIONS(
            ENDPOINT = 'textembedding-gecko@003'
        );
        """
        
        try:
            self.run_query(create_model_query)
            print(f"✅ Model {model_name} created successfully.")
        except Exception as e:
            print(f"❌ Failed to create model. This is likely a permission issue.")
            print(f"ACTION REQUIRED: Go to BigQuery Console -> Explorer -> External Connections.")
            print(f"Find '{full_connection_id}', copy the 'Service Account ID'.")
            print(f"Grant that Service Account the 'Vertex AI User' role in IAM.")
            print(f"Then run this tool again.")
            # We don't raise here, we let the embedding generation fail later with a clearer message if needed.

    def create_embedding_model(
            self,
            model_id: str,
            connection_id: str,
            connection_location: str,
            replace: bool = True
    ):
        """
        Creates a BigQuery ML remote model that points to a Vertex AI
        embedding service endpoint.

        This allows you to use the model name (e.g., `project.dataset.model_id`)
        with BQML functions like `ML.GENERATE_EMBEDDING`.

        Args:
            model_id: The name to give the BQML model (e.g., 'text_embedding_model').
            connection_id: The ID of the Google Cloud connection resource. This
                           connection must be configured to connect to Vertex AI
                           and have necessary permissions.
            connection_location: The location of the connection resource (e.g., 'us-central1').
            replace: If True, uses CREATE OR REPLACE MODEL. If False, uses CREATE MODEL.
                     Defaults to True.

        Requires:
            - A Google Cloud Connection resource already created in the specified location.
            - The Connection must be linked to Vertex AI.
            - The BigQuery service account needs Vertex AI permissions
              (e.g., `Vertex AI User` role).
        """
        full_model_path = f"`{self.base_path}.{model_id}`"
        full_connection_path = f"`{self.pid}.{connection_location}.{connection_id}`"

        create_statement = "CREATE OR REPLACE MODEL" if replace else "CREATE MODEL"

        query = f"""
        {create_statement} {full_model_path}
        REMOTE WITH CONNECTION {full_connection_path}
        OPTIONS (remote_service_type = 'CLOUD_AI_EMBEDDING');
        """
        print(f"Executing BigQuery SQL to create model {full_model_path}:")
        print(query)

        query_job = self.bqclient.query(query)

        # Wait for the job to complete
        query_job.result()

        print(f"BigQuery ML model {full_model_path} created successfully.")
        return f"BigQuery ML model {full_model_path} created successfully."

    def create_vector_index(self, table_id: str, column_name: str = "embedding"):
        """
        Creates a vector index (IVF) on the specified column to accelerate vector search.
        Required for large datasets to perform efficient similarity search.
        """
        full_table_path = f"`{self.base_path}.{table_id}`"
        index_name = f"{table_id}_{column_name}_idx"
        
        query = f"""
        CREATE OR REPLACE VECTOR INDEX `{index_name}`
        ON {full_table_path}({column_name})
        OPTIONS(distance_type='COSINE', index_type='IVF');
        """
        print(f"🚀 Creating Vector Index on {full_table_path}...")
        try:
            self.run_query(query)
            print(f"✅ Vector index {index_name} created.")
        except Exception as e:
            print(f"⚠️ Vector index creation warning (safe to ignore if already exists or table small): {e}")




















# Example Usage (requires Google Cloud authentication and a BigQuery table with embeddings)
if __name__ == '__main__':
    # !!! IMPORTANT !!!
    # Replace 'your-gcp-project-id' and 'your_dataset_id' with your actual IDs
    # Also, make sure you have a table named 'your_embeddings_table'
    # with a column named 'embed' (ARRAY<FLOAT64>) and an 'id' column.
    # If using custom=False, make sure you have a BQML model named 'your_embedding_model'
    # or provide the appropriate model_name/path.
    try:
        bq_rag = BigQueryRAG(project_id='your-gcp-project-id', dataset_id='your_dataset_id')

        # --- Example with custom embedding (embedding done outside BQ) ---
        # You would replace this placeholder vector with the actual embedding
        # generated from your query text using your embedding model.
        # dummy_query_embedding = embed("This is a test query") # Call your actual embed function
        # print("Running custom embedding search...")
        # results_custom = bq_rag.bigquery_vector_search(
        #     data=[0.01] * 768, # Replace with actual vector from embed("Your query text")
        #     table_id='your_embeddings_table',
        #     custom=True,
        #     limit=5,
        #     select=["id", "another_column"] # Example of selecting multiple columns
        # )
        # print("Custom Search Results:", results_custom)

        # --- Example with BQML embedding (embedding done inside BQ) ---
        print("\nRunning BQML embedding search...")
        results_bqml = bq_rag.bigquery_vector_search(
            data="This is another test query for BQML.",
            table_id='your_embeddings_table',
            custom=False,
            limit=5,
            select=["nid"],
            model_name='your_embedding_model' # Replace with your BQML model name/path
        )
        print("BQML Search Results:", results_bqml)

    except NotImplementedError as e:
         print(f"Error: {e}. Please implement the 'embed' function or provide a valid BQML model.")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Please ensure your GCP project, dataset, table, and potentially BQML model are correctly configured and accessible.")



if __name__ == "__main__":
    v=BQGroundZero()
    print(v.run_query(query="SELECT 1"))
