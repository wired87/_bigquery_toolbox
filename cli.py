import typer
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.markdown import Markdown
from rich.prompt import Prompt
import pandas as pd
import os
import json
import asyncio
from typing import Optional, List, Dict, Any
import glob
import openpyxl
import time

# Local imports
from bq_handler import BQCore, BigQueryRAG, BQ_DATASET_ID
import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part, Content, ChatSession
from vertexai.language_models import TextEmbeddingModel
from google.cloud import bigquery

app = typer.Typer()
console = Console()

# Constants
DEFAULT_DATASET_ID = "IDB"
DEFAULT_MODEL_NAME = "gemini-2.5-pro"
DATA_DIR = "./data_dir"

def ensure_data_dir():
    if not os.path.exists(DATA_DIR):
        os.makedirs(DATA_DIR)
        console.print(f"[green]Created data directory at {DATA_DIR}[/green]")

def infer_bq_type(value) -> str:
    """
    Infer BigQuery type from a Python value.
    """
    if pd.isna(value) or value is None:
        return "STRING"  # Default for NULL
    
    if isinstance(value, bool):
        return "BOOL"
    elif isinstance(value, int):
        return "INT64"
    elif isinstance(value, float):
        return "FLOAT64"
    elif isinstance(value, (pd.Timestamp, pd.DatetimeTZDtype)):
        return "TIMESTAMP"
    elif isinstance(value, list):
        if len(value) > 0:
            inner_type = infer_bq_type(value[0])
            return f"ARRAY<{inner_type}>"
        return "ARRAY<STRING>"
    else:
        return "STRING"

def read_file_with_schema(file_path: str) -> tuple[List[Dict[str, Any]], Dict[str, str]]:
    """
    Read file and return both data and inferred schema.
    Returns: (rows, schema_dict) where schema_dict maps column_name -> bq_type
    """
    console.print(f"[dim]  🔍 DEBUG: Reading file with schema inference...[/dim]")
    
    try:
        # Read file into DataFrame
        if file_path.endswith('.csv'):
            df = pd.read_csv(file_path)
        elif file_path.endswith('.xlsx') or file_path.endswith('.xls'):
            df = pd.read_excel(file_path)
        elif file_path.endswith('.jsonl') or file_path.endswith('.json'):
            df = pd.read_json(file_path, lines=True if file_path.endswith('.jsonl') else False)
        else:
            return [], {}
        
        if df.empty:
            return [], {}
        
        # Ensure 'id' column exists
        if 'id' not in df.columns:
            df.insert(0, 'id', df.index.astype(str))
        else:
            df['id'] = df['id'].astype(str)
        
        # Infer schema from actual data
        schema = {}
        console.print(f"[dim]  📋 DEBUG: Inferring schema from {len(df)} rows...[/dim]")
        
        for col in df.columns:
            # Get first non-null value to infer type
            non_null_values = df[col].dropna()
            if len(non_null_values) > 0:
                sample_value = non_null_values.iloc[0]
                inferred_type = infer_bq_type(sample_value)
                schema[col] = inferred_type
                console.print(f"[dim]    • {col}: {inferred_type} (sample: {str(sample_value)[:50]})[/dim]")
            else:
                schema[col] = "STRING"
                console.print(f"[dim]    • {col}: STRING (all NULL)[/dim]")
        
        # Convert DataFrame to list of dicts
        rows = df.to_dict(orient='records')
        
        # Convert NaN to None for JSON compatibility
        for row in rows:
            for key, value in row.items():
                if pd.isna(value):
                    row[key] = None
        
        console.print(f"[dim]  ✓ DEBUG: Extracted {len(rows)} rows with {len(schema)} columns[/dim]")
        return rows, schema
        
    except Exception as e:
        console.print(f"[red]  ❌ Error reading {file_path}: {e}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return [], {}

def merge_schemas(schemas: List[Dict[str, str]]) -> Dict[str, str]:
    """
    Merge multiple schemas into a unified schema.
    Resolves type conflicts by choosing the most general type.
    """
    console.print(f"[dim]🔧 DEBUG: Merging {len(schemas)} schemas...[/dim]")
    
    merged = {}
    type_priority = {
        "STRING": 5,
        "FLOAT64": 4,
        "INT64": 3,
        "BOOL": 2,
        "TIMESTAMP": 1,
    }
    
    for schema in schemas:
        for col, col_type in schema.items():
            if col not in merged:
                merged[col] = col_type
                console.print(f"[dim]  + Added column '{col}' as {col_type}[/dim]")
            elif merged[col] != col_type:
                # Type conflict - choose more general type
                current_priority = type_priority.get(merged[col], 0)
                new_priority = type_priority.get(col_type, 0)
                
                if new_priority > current_priority:
                    console.print(f"[dim]  ⚠️  Type conflict for '{col}': {merged[col]} vs {col_type} → using {col_type}[/dim]")
                    merged[col] = col_type
                else:
                    console.print(f"[dim]  ⚠️  Type conflict for '{col}': {merged[col]} vs {col_type} → keeping {merged[col]}[/dim]")
    
    console.print(f"[dim]✓ DEBUG: Merged schema has {len(merged)} columns[/dim]")
    return merged

def normalize_row_to_schema(row: Dict[str, Any], schema: Dict[str, str]) -> Dict[str, Any]:
    """
    Normalize a row to match the merged schema.
    Adds missing columns with None values.
    """
    normalized = {}
    for col, col_type in schema.items():
        if col in row:
            normalized[col] = row[col]
        else:
            normalized[col] = None
    return normalized

def ingest_data(table_name: str, bq_core: BQCore):
    """
    Improved data ingestion with intelligent schema merging and single batch upsert.
    """
    ensure_data_dir()
    files = glob.glob(os.path.join(DATA_DIR, "*"))
    
    console.print(f"\n[bold cyan]📂 Starting Intelligent Data Ingestion[/bold cyan]")
    console.print(f"[cyan]📂 Scanning data directory: {DATA_DIR}[/cyan]")
    console.print(f"[cyan]📊 Target table: {table_name}[/cyan]")
    
    if not files:
        console.print("[yellow]⚠️  No files found in data_dir.[/yellow]")
        return
    
    # Phase 1: Read all files and extract schemas
    console.print(f"\n[bold blue]Phase 1: Schema Extraction[/bold blue]")
    
    file_data = []  # List of (filename, rows, schema)
    all_schemas = []
    total_rows = 0
    
    for f in files:
        if f.endswith(('.csv', '.xlsx', '.xls', '.json', '.jsonl')):
            console.print(f"\n[blue]📄 Processing file: {os.path.basename(f)}[/blue]")
            
            rows, schema = read_file_with_schema(f)
            
            if rows and schema:
                console.print(f"[green]  ✓ Loaded {len(rows)} rows with {len(schema)} columns[/green]")
                file_data.append((os.path.basename(f), rows, schema))
                all_schemas.append(schema)
                total_rows += len(rows)
            else:
                console.print(f"[yellow]  ⚠️  No data extracted from {os.path.basename(f)}[/yellow]")
    
    if not file_data:
        console.print("[yellow]⚠️  No valid data found to ingest.[/yellow]")
        return
    
    console.print(f"\n[green]✓ Phase 1 Complete: {len(file_data)} files, {total_rows} total rows[/green]")
    
    # Phase 2: Merge schemas
    console.print(f"\n[bold blue]Phase 2: Schema Merging[/bold blue]")
    
    merged_schema = merge_schemas(all_schemas)
    
    console.print(f"\n[bold green]✓ Merged Schema ({len(merged_schema)} columns):[/bold green]")
    for col, col_type in list(merged_schema.items())[:10]:
        console.print(f"[green]  • {col}: {col_type}[/green]")
    if len(merged_schema) > 10:
        console.print(f"[dim]  ... and {len(merged_schema) - 10} more columns[/dim]")
    
    # Phase 3: Normalize and merge all data
    console.print(f"\n[bold blue]Phase 3: Data Normalization & Merging[/bold blue]")
    
    all_rows = []
    for filename, rows, schema in file_data:
        console.print(f"[blue]  📦 Normalizing {len(rows)} rows from {filename}...[/blue]")
        
        for row in rows:
            # Normalize to merged schema
            normalized_row = normalize_row_to_schema(row, merged_schema)
            # Add source file metadata
            normalized_row['_source_file'] = filename
            all_rows.append(normalized_row)
        
        console.print(f"[green]    ✓ Normalized {len(rows)} rows[/green]")
    
    # Update merged schema to include _source_file
    merged_schema['_source_file'] = 'STRING'
    
    console.print(f"\n[bold green]✓ Phase 3 Complete: {len(all_rows)} normalized rows ready[/bold green]")
    
    # Phase 4: Single Batch Upsert
    console.print(f"\n[bold blue]Phase 4: BigQuery Upsert[/bold blue]")
    console.print(f"[cyan]💾 Upserting {len(all_rows)} rows to table '{table_name}'...[/cyan]")
    
    # Check if table exists
    table_exists = bq_core.bq_check_table_exists(table_name)
    if not table_exists:
        console.print(f"[yellow]🔨 Table '{table_name}' does not exist, will be created automatically[/yellow]")
    else:
        console.print(f"[green]✓ Table '{table_name}' already exists[/green]")
    
    try:
        # Single batch upsert
        console.print(f"[dim]  🔧 DEBUG: Executing single batch upsert...[/dim]")
        bq_core.bq_insert(table_id=table_name, rows=all_rows, upsert=True)
        console.print(f"[bold green]✅ Data ingestion complete! {len(all_rows)} rows upserted to '{table_name}'[/bold green]")
        
        # Verify the upsert
        console.print(f"[dim]  🔍 DEBUG: Verifying upsert...[/dim]")
        verify_query = f"SELECT COUNT(*) as row_count FROM `{bq_core.pid}.{bq_core.ds_id}.{table_name}`"
        result = bq_core.run_query(verify_query, conv_to_dict=True)
        if result:
            console.print(f"[green]✓ Verification: Table '{table_name}' now contains {result[0]['row_count']} rows[/green]")
        
        # Display schema summary
        console.print(f"\n[bold cyan]📋 Final Table Schema:[/bold cyan]")
        actual_schema = bq_core.bq_get_table_schema(table_name)
        if actual_schema:
            for col, col_type in list(actual_schema.items())[:15]:
                console.print(f"[cyan]  • {col}: {col_type}[/cyan]")
            if len(actual_schema) > 15:
                console.print(f"[dim]  ... and {len(actual_schema) - 15} more columns[/dim]")
        
    except Exception as e:
        console.print(f"[bold red]❌ Ingestion failed: {e}[/bold red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return
    
    # Update metadata after successful ingestion
    update_table_metadata(table_name, bq_core)


def update_table_metadata(table_name: str, bq_core: BQCore):
    """
    Updates metadata table with comprehensive information about the data table.
    This enables answering general questions about table content.
    """
    console.print(f"\n[bold cyan]📊 Updating metadata for table '{table_name}'...[/bold cyan]")
    
    metadata_table = "_table_metadata"
    
    try:
        # 1. Gather table statistics
        console.print(f"[dim]📊 DEBUG: Gathering statistics for '{table_name}'...[/dim]")
        
        # Get row count
        count_query = f"SELECT COUNT(*) as row_count FROM `{bq_core.pid}.{bq_core.ds_id}.{table_name}`"
        count_result = bq_core.run_query(count_query, conv_to_dict=True)
        row_count = count_result[0]['row_count'] if count_result else 0
        console.print(f"[dim]  ✓ Row count: {row_count}[/dim]")
        
        # Get schema
        schema = bq_core.bq_get_table_schema(table_name)
        columns = list(schema.keys()) if schema else []
        column_count = len(columns)
        console.print(f"[dim]  ✓ Column count: {column_count}[/dim]")
        console.print(f"[dim]  ✓ Columns: {', '.join(columns[:5])}{'...' if len(columns) > 5 else ''}[/dim]")
        
        # Format column types
        column_types = json.dumps(schema) if schema else "{}"
        
        # 2. Get sample data (first 3 rows)
        console.print(f"[dim]📋 DEBUG: Collecting sample data...[/dim]")
        sample_query = f"SELECT * FROM `{bq_core.pid}.{bq_core.ds_id}.{table_name}` LIMIT 3"
        sample_result = bq_core.run_query(sample_query, conv_to_dict=True)
        
        # Format sample data as readable text
        sample_data_text = ""
        if sample_result:
            for i, row in enumerate(sample_result, 1):
                sample_data_text += f"Row {i}: "
                row_items = []
                for k, v in row.items():
                    if k != 'embed' and k != '_source_file':
                        str_val = str(v)
                        if len(str_val) > 100:
                            str_val = str_val[:100] + "..."
                        row_items.append(f"{k}={str_val}")
                sample_data_text += "; ".join(row_items) + "\n"
        console.print(f"[dim]  ✓ Collected {len(sample_result) if sample_result else 0} sample rows[/dim]")
        
        # 3. Generate data summary
        console.print(f"[dim]🧠 DEBUG: Generating data summary...[/dim]")
        
        # Get unique value counts for key columns
        unique_values_info = {}
        for col in columns[:5]:
            if col not in ['embed', 'id', '_source_file']:
                try:
                    unique_query = f"""
                    SELECT COUNT(DISTINCT {col}) as unique_count 
                    FROM `{bq_core.pid}.{bq_core.ds_id}.{table_name}` 
                    WHERE {col} IS NOT NULL
                    """
                    unique_result = bq_core.run_query(unique_query, conv_to_dict=True)
                    if unique_result:
                        unique_values_info[col] = unique_result[0]['unique_count']
                except Exception:
                    pass
        
        unique_values_sample = json.dumps(unique_values_info)
        console.print(f"[dim]  ✓ Unique value counts: {unique_values_info}[/dim]")
        
        # Create comprehensive summary
        data_summary = f"""Table: {table_name}
Total Rows: {row_count}
Total Columns: {column_count}
Column Names: {', '.join(columns)}
Unique Value Counts: {unique_values_sample}
Sample Data Preview:
{sample_data_text}""".strip()
        
        # 4. Upsert metadata
        console.print(f"[dim]💾 DEBUG: Upserting metadata to '{metadata_table}'...[/dim]")
        metadata_row = {
            "table_name": table_name,
            "row_count": row_count,
            "column_count": column_count,
            "columns": json.dumps(columns),
            "column_types": column_types,
            "sample_data": sample_data_text[:1000],
            "last_updated": pd.Timestamp.now().isoformat(),
            "data_summary": data_summary[:2000],
            "unique_values_sample": unique_values_sample
        }
        
        # Ensure metadata table exists and has proper schema
        if not bq_core.bq_check_table_exists(metadata_table):
            console.print(f"[yellow]🔨 Creating metadata table '{metadata_table}'...[/yellow]")
            bq_core.get_create_bq_table(metadata_table, ttype="metadata")
        
        bq_core.update_bq_schema(metadata_table, [metadata_row])
        
        # Delete existing metadata for this table and insert new
        try:
            delete_query = f"DELETE FROM `{bq_core.pid}.{bq_core.ds_id}.{metadata_table}` WHERE table_name = '{table_name}'"
            bq_core.run_query(delete_query)
        except Exception:
            pass
        
        bq_core.bq_insert(table_id=metadata_table, rows=[metadata_row], upsert=False)
        
        console.print(f"[bold green]✅ Metadata updated successfully![/bold green]")
        console.print(f"[green]  ✓ Table: {table_name}, Rows: {row_count}, Columns: {column_count}[/green]")
        
    except Exception as e:
        console.print(f"[red]❌ Failed to update metadata: {e}[/red]")

def generate_embeddings_client(table_name: str, bq_core: BQCore):
    """
    Generates embeddings using Vertex AI SDK (client-side) and updates BigQuery.
    This avoids the need for BigQuery Remote Models and Connections.
    """
    console.print(f"\n[bold cyan]🧠 Starting embedding generation for table '{table_name}'...[/bold cyan]")
    
    # 1. Fetch rows without embeddings
    # We assume 'embed' column might not exist or is null
    # First, ensure 'embed' column exists
    console.print(f"[blue]🔧 DEBUG: Ensuring 'embed' column exists in '{table_name}'...[/blue]")
    bq_core.insert_col(table_name, "embed", "ARRAY<FLOAT64>")
    console.print(f"[dim]✓ DEBUG: 'embed' column check complete[/dim]")
    
    # Get rows where embed is NULL
    console.print(f"[blue]🔍 DEBUG: Querying rows without embeddings...[/blue]")
    query = f"SELECT id, content FROM `{bq_core.pid}.{bq_core.ds_id}.{table_name}` WHERE embed IS NULL AND content IS NOT NULL"
    console.print(f"[dim]  Query: {query}[/dim]")
    rows = bq_core.run_query(query, conv_to_dict=True)
    
    if not rows:
        console.print("[green]✅ All rows already have embeddings. No work needed.[/green]")
        return

    console.print(f"[yellow]📊 Found {len(rows)} rows needing embeddings[/yellow]")
    console.print(f"[blue]🤖 DEBUG: Loading text-embedding-004 model from Vertex AI...[/blue]")
    
    model = TextEmbeddingModel.from_pretrained("text-embedding-004")
    console.print(f"[green]✓ DEBUG: Model loaded successfully[/green]")
    
    # Batch process
    batch_size = 5 # Rate limits apply
    updated_rows = []
    total_batches = (len(rows) + batch_size - 1) // batch_size
    
    console.print(f"[cyan]⚙️  Processing {len(rows)} rows in {total_batches} batches (batch size: {batch_size})...[/cyan]")
    
    for i in range(0, len(rows), batch_size):
        batch = rows[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        texts = [r['content'] for r in batch]
        
        console.print(f"[blue]  📦 Batch {batch_num}/{total_batches}: Generating embeddings for {len(batch)} rows...[/blue]")
        console.print(f"[dim]    DEBUG: Sample text (first 100 chars): {texts[0][:100] if texts else 'N/A'}...[/dim]")
        
        try:
            embeddings = model.get_embeddings(texts)
            console.print(f"[dim]    DEBUG: Received {len(embeddings)} embeddings[/dim]")
            
            for j, emb in enumerate(embeddings):
                row_id = batch[j]['id']
                vector = emb.values
                updated_rows.append({"id": row_id, "embed": vector})
                console.print(f"[dim]    DEBUG: Row {j+1}/{len(batch)} - ID: {row_id}, Vector dim: {len(vector)}[/dim]")
            
            console.print(f"[green]    ✓ Batch {batch_num}/{total_batches} completed ({len(embeddings)} embeddings generated)[/green]")
                
        except Exception as e:
            console.print(f"[red]    ❌ Error in batch {batch_num}: {e}[/red]")
            time.sleep(1) # Backoff
            
    if updated_rows:
        console.print(f"\n[bold cyan]💾 DEBUG: Updating {len(updated_rows)} embeddings in BigQuery table '{table_name}'...[/bold cyan]")
        bq_core.bq_insert(table_id=table_name, rows=updated_rows, upsert=True)
        console.print(f"[bold green]✅ Embeddings updated successfully![/bold green]")
        
        # Verify embeddings were created
        console.print(f"[dim]🔍 DEBUG: Verifying embeddings were created...[/dim]")
        verify_query = f"SELECT COUNT(*) as embedded_count FROM `{bq_core.pid}.{bq_core.ds_id}.{table_name}` WHERE embed IS NOT NULL"
        result = bq_core.run_query(verify_query, conv_to_dict=True)
        if result:
            console.print(f"[green]✓ Verification: {result[0]['embedded_count']} rows now have embeddings[/green]")
            console.print(f"[bold green]🎯 Table '{table_name}' is ready for vector search![/bold green]")
    else:
        console.print("[yellow]⚠️  No embeddings were generated[/yellow]")

# --- AI Chat Tools ---

def get_bq_tools():
    list_datasets_func = FunctionDeclaration(
        name="list_datasets",
        description="Get a list of datasets that will help answer the user's question",
        parameters={"type": "object", "properties": {}},
    )

    list_tables_func = FunctionDeclaration(
        name="list_tables",
        description="List tables in a dataset that will help answer the user's question",
        parameters={
            "type": "object",
            "properties": {
                "dataset_id": {"type": "string", "description": "Dataset ID to fetch tables from."}
            },
            "required": ["dataset_id"],
        },
    )

    get_table_func = FunctionDeclaration(
        name="get_table_schema",
        description="Get the schema of a table. Always use fully qualified dataset and table names.",
        parameters={
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "Table ID to get schema for"}
            },
            "required": ["table_id"],
        },
    )

    sql_query_func = FunctionDeclaration(
        name="run_sql_query",
        description="Run a SQL query on BigQuery. Use fully qualified names.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "SQL query to execute"}
            },
            "required": ["query"],
        },
    )
    
    vector_search_func = FunctionDeclaration(
        name="vector_search",
        description="Perform a semantic/ML search on a table using vector embeddings.",
        parameters={
            "type": "object",
            "properties": {
                "query_text": {"type": "string", "description": "The natural language query to search for"},
                "table_id": {"type": "string", "description": "The table to search in"},
                "limit": {"type": "integer", "description": "Number of results to return (default 5)"}
            },
            "required": ["query_text", "table_id"],
        },
    )
    
    get_metadata_func = FunctionDeclaration(
        name="get_table_metadata",
        description="Get comprehensive metadata about a table including row count, columns, sample data, and statistics. Use this for general questions like 'what's in the table' or 'how many rows'.",
        parameters={
            "type": "object",
            "properties": {
                "table_id": {"type": "string", "description": "The table to get metadata for"}
            },
            "required": ["table_id"],
        },
    )

    return Tool(
        function_declarations=[
            list_datasets_func,
            list_tables_func,
            get_table_func,
            sql_query_func,
            vector_search_func,
            get_metadata_func
        ]
    )

async def generate_search_queries(user_input: str, model: GenerativeModel, num_queries: int = 3) -> List[str]:
    """
    Generate multiple search queries optimized for similarity search using LLM.
    """
    console.print(f"[dim]🔍 DEBUG: Generating {num_queries} search queries for: '{user_input}'[/dim]")
    
    prompt = f"""
    Given the user's question, generate {num_queries} different search queries that would help find relevant information in a knowledge base.
    Each query should approach the question from a different angle to maximize coverage.
    
    User Question: {user_input}
    
    Return ONLY the queries, one per line, without numbering or additional text.
    """
    
    try:
        response = await model.generate_content_async(prompt)
        queries = [q.strip() for q in response.text.strip().split('\n') if q.strip()]
        console.print(f"[dim]✓ DEBUG: Generated {len(queries)} queries: {queries}[/dim]")
        return queries[:num_queries]
    except Exception as e:
        console.print(f"[yellow]⚠️  DEBUG: Query generation failed: {e}. Using original input.[/yellow]")
        return [user_input]

async def handle_tool_call(function_call, bq_core: BQCore, bq_rag: BigQueryRAG, default_table_name: str = None, query_generator_model: GenerativeModel = None):
    name = function_call.name
    args = function_call.args
    
    console.print(f"[dim]🔧 DEBUG: Tool Call: {name}({args})[/dim]")

    try:
        if name == "list_datasets":
            console.print(f"[dim]📊 DEBUG: Listing datasets...[/dim]")
            datasets = list(bq_core.bqclient.list_datasets())
            result = [d.dataset_id for d in datasets]
            console.print(f"[dim]✓ DEBUG: Found {len(result)} datasets[/dim]")
            return result
            
        elif name == "list_tables":
            ds_id = args.get("dataset_id", BQ_DATASET_ID)
            console.print(f"[dim]📊 DEBUG: Listing tables in dataset '{ds_id}'...[/dim]")
            temp_core = BQCore(dataset_id=ds_id)
            result = temp_core.list_tables()
            console.print(f"[dim]✓ DEBUG: Found {len(result) if result else 0} tables[/dim]")
            return result

        elif name == "get_table_schema":
            table_id = args.get("table_id", default_table_name)
            if not table_id:
                return "Error: table_id is required."
            if "." in table_id:
                parts = table_id.split(".")
                table_id = parts[-1]
            console.print(f"[dim]📋 DEBUG: Fetching schema for table '{table_id}'...[/dim]")
            result = bq_core.bq_get_table_schema(table_id)
            console.print(f"[dim]✓ DEBUG: Schema retrieved with {len(result) if result else 0} columns[/dim]")
            return result

        elif name == "run_sql_query":
            query = args["query"]
            console.print(f"[dim]💾 DEBUG: Executing SQL query...[/dim]")
            result = bq_core.run_query(query, conv_to_dict=True)
            console.print(f"[dim]✓ DEBUG: Query returned {len(result) if result else 0} rows[/dim]")
            return result
        
        elif name == "get_table_metadata":
            table_id = args.get("table_id", default_table_name)
            if not table_id:
                return "Error: table_id is required."
            
            console.print(f"[dim]📊 DEBUG: Fetching metadata for table '{table_id}'...[/dim]")
            
            # Query the metadata table
            metadata_table = "_table_metadata"
            metadata_query = f"""
            SELECT * FROM `{bq_core.pid}.{bq_core.ds_id}.{metadata_table}` 
            WHERE table_name = '{table_id}'
            """
            
            try:
                metadata_result = bq_core.run_query(metadata_query, conv_to_dict=True)
                if metadata_result:
                    metadata = metadata_result[0]
                    console.print(f"[dim]✓ DEBUG: Metadata retrieved for '{table_id}'[/dim]")
                    console.print(f"[dim]  Rows: {metadata.get('row_count', 'N/A')}, Columns: {metadata.get('column_count', 'N/A')}[/dim]")
                    return metadata.get('data_summary', 'No summary available')
                else:
                    console.print(f"[yellow]⚠️  No metadata found for table '{table_id}'. Generating fresh metadata...[/yellow]")
                    # Generate metadata if not found
                    update_table_metadata(table_id, bq_core)
                    # Try again
                    metadata_result = bq_core.run_query(metadata_query, conv_to_dict=True)
                    if metadata_result:
                        return metadata_result[0].get('data_summary', 'No summary available')
                    return f"Could not retrieve metadata for table '{table_id}'"
            except Exception as e:
                console.print(f"[red]❌ Error fetching metadata: {e}[/red]")
                return f"Error fetching metadata: {str(e)}"

        elif name == "vector_search":
            query_text = args["query_text"]
            table_id = args.get("table_id", default_table_name)
            
            if not table_id:
                return "Error: table_id is required for vector search."
                
            limit = int(args.get("limit", 5))
            
            console.print(f"[bold cyan]🔍 Starting Enhanced Vector Search[/bold cyan]")
            console.print(f"[dim]📊 DEBUG: Table: '{table_id}', Limit: {limit}[/dim]")
            
            # Step 1: Generate multiple search queries using LLM
            if query_generator_model:
                search_queries = await generate_search_queries(query_text, query_generator_model, num_queries=3)
            else:
                console.print(f"[yellow]⚠️  DEBUG: No query generator model provided, using original query only[/yellow]")
                search_queries = [query_text]
            
            console.print(f"[cyan]📝 Generated {len(search_queries)} search queries:[/cyan]")
            for i, q in enumerate(search_queries, 1):
                console.print(f"[dim]  {i}. {q}[/dim]")
            
            # Step 2: Load embedding model
            console.print(f"[dim]🤖 DEBUG: Loading text-embedding-004 model...[/dim]")
            model = TextEmbeddingModel.from_pretrained("text-embedding-004")
            console.print(f"[dim]✓ DEBUG: Model loaded successfully[/dim]")
            
            # Step 3: Perform similarity search for each query
            all_results = []
            seen_ids = set()
            
            for i, search_query in enumerate(search_queries, 1):
                console.print(f"[cyan]🔎 Query {i}/{len(search_queries)}: Performing similarity search...[/cyan]")
                console.print(f"[dim]  Query text: '{search_query}'[/dim]")
                
                # Generate embedding for this query
                console.print(f"[dim]  🧠 DEBUG: Generating embedding...[/dim]")
                embeddings = model.get_embeddings([search_query])
                vector = embeddings[0].values
                console.print(f"[dim]  ✓ DEBUG: Embedding generated (dimension: {len(vector)})[/dim]")
                
                # Execute BigQuery vector search
                console.print(f"[dim]  💾 DEBUG: Executing BigQuery vector search...[/dim]")
                results = bq_rag.bigquery_vector_search(
                    data=vector,
                    table_id=table_id,
                    custom=True,
                    limit=limit,
                    select=["*"]
                )
                console.print(f"[dim]  ✓ DEBUG: Retrieved {len(results)} results[/dim]")
                
                # Add unique results to aggregated list
                new_results = 0
                for result in results:
                    result_id = result.get('id', str(result))
                    if result_id not in seen_ids:
                        seen_ids.add(result_id)
                        all_results.append(result)
                        new_results += 1
                
                console.print(f"[green]  ✓ Query {i} complete: {new_results} new unique results added[/green]")
            
            # Step 4: Sort by distance and take top results
            console.print(f"[dim]📊 DEBUG: Sorting and filtering top {limit} results...[/dim]")
            all_results.sort(key=lambda x: x.get('distance', float('inf')))
            top_results = all_results[:limit]
            
            console.print(f"[bold green]✅ Vector search complete: {len(top_results)} top results selected[/bold green]")
            
            # Step 5: Render results in table format
            if top_results:
                console.print(f"\n[bold cyan]📋 Top {len(top_results)} Results:[/bold cyan]")
                
                # Create Rich table
                table = Table(show_header=True, header_style="bold magenta")
                
                # Add columns based on first result
                columns = list(top_results[0].keys())
                for col in columns:
                    table.add_column(col, style="cyan" if col != "distance" else "yellow")
                
                # Add rows
                for result in top_results:
                    row_values = []
                    for col in columns:
                        value = result.get(col, "")
                        # Format distance values
                        if col == "distance" and isinstance(value, (int, float)):
                            row_values.append(f"{value:.4f}")
                        else:
                            # Truncate long strings
                            str_value = str(value)
                            row_values.append(str_value[:100] + "..." if len(str_value) > 100 else str_value)
                    table.add_row(*row_values)
                
                console.print(table)
            else:
                console.print(f"[yellow]⚠️  No results found[/yellow]")
            
            return top_results
            
    except Exception as e:
        console.print(f"[bold red]❌ DEBUG: Error executing {name}: {str(e)}[/bold red]")
        return f"Error executing {name}: {str(e)}"

async def classify_intent(user_input: str, model: GenerativeModel) -> str:
    """
    Classifies the user's intent to provide visual feedback.
    """
    prompt = f"""
    Classify the following user input into one of these categories:
    - METADATA_QUERY: The user is asking general questions about the table itself (e.g., "what's in the table?", "how many rows?", "what columns exist?", "show me the content").
    - VECTOR_SEARCH: The user is asking for specific information that requires searching the knowledge base content.
    - SQL_QUERY: The user is asking for aggregations, statistics, or specific data points that require SQL.
    - GENERAL_CHAT: The user is engaging in general conversation, greeting, or asking for clarification.
    
    User Input: {user_input}
    
    Return ONLY the category name.
    """
    try:
        response = await model.generate_content_async(prompt)
        return response.text.strip()
    except Exception as e:
        console.print(f"[dim]Classification error: {e}[/dim]")
        return "GENERAL_CHAT"

@app.command()
def main():
    """
    Start the AI Chat CLI (Default).
    """
    console.print("[bold blue]Starting AI Chat...[/bold blue]")
    
    # 0. Load Credentials (Default: credentials.json in project root)
    creds_path = os.path.abspath("credentials.json")
    if os.path.exists(creds_path):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = creds_path
        console.print(f"[green]Loaded credentials from {creds_path}[/green]")
    else:
        console.print(f"[yellow]Warning: Credentials file not found at {creds_path}. Assuming default credentials are set.[/yellow]")

    # Initialize Vertex AI (Late Init)
    try:
        project_id = bigquery.Client().project
        vertexai.init(project=project_id, location="us-central1")
    except Exception as e:
        console.print(f"[bold red]Failed to initialize Google Cloud/Vertex AI:[/bold red] {e}")
        raise typer.Exit(code=1)
    
    # 1. Ask for Knowledge Base Name (Table Name)
    table_name = Prompt.ask("[bold cyan]Enter Knowledge Base Name (Table Name)[/bold cyan]", default="knowledge_base")
    
    bq_core = BQCore(dataset_id=DEFAULT_DATASET_ID)
    bq_rag = BigQueryRAG(dataset=DEFAULT_DATASET_ID)
    
    # 2. Ingest Data
    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task(description="Checking for new data...", total=None)
        ingest_data(table_name, bq_core)
        
        # 3. Generate Embeddings
        progress.add_task(description="Updating embeddings...", total=None)
        generate_embeddings_client(table_name, bq_core)

    tools = get_bq_tools()
    
    # Main Chat Model
    system_instruction = f"""You are a helpful assistant with access to a knowledge base in BigQuery table '{table_name}'.

TOOL USAGE GUIDELINES:
1. For GENERAL questions about the table (e.g., "what's in the table?", "how many rows?", "what columns exist?"):
   - Use 'get_table_metadata' tool first to get comprehensive table information
   
2. For SPECIFIC content questions (e.g., "what is machine learning?", "find information about X"):
   - Use 'vector_search' tool to find relevant content
   - The system will automatically generate multiple search queries for better coverage
   
3. For STATISTICAL queries (e.g., "count of X", "average of Y"):
   - Use 'run_sql_query' tool with appropriate SQL

Always use the table name '{table_name}' when calling tools.
Provide clear, comprehensive answers based on the tool results."""
    
    chat_model = GenerativeModel(DEFAULT_MODEL_NAME, tools=[tools], system_instruction=system_instruction)
    chat_session = chat_model.start_chat()
    
    # Classification Model (Lightweight)
    classifier_model = GenerativeModel(DEFAULT_MODEL_NAME)

    console.print(f"Chatting with context from table: [bold]{table_name}[/bold]")
    console.print("Type 'exit' or 'quit' to stop.")

    # Create a persistent event loop for async operations
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        while True:
            user_input = Prompt.ask("[bold green]User[/bold green]")
            if user_input.lower() in ["exit", "quit"]:
                break
                
            # Status Bar for Classification and Processing
            with Console().status("[bold yellow]Processing...[/bold yellow]") as status:
                
                # 1. Classify Intent
                status.update("[bold yellow]Classifying intent...[/bold yellow]")
                try:
                    intent = loop.run_until_complete(classify_intent(user_input, classifier_model))
                    console.print(f"[dim]Intent detected: {intent}[/dim]")
                except Exception as e:
                    console.print(f"[dim]Classification failed: {e}[/dim]")
                    intent = "GENERAL_CHAT"
                
                # 2. Generate Response
                status.update(f"[bold yellow]Thinking ({intent})...[/bold yellow]")
                
                try:
                    responses = chat_session.send_message(user_input, stream=True)
                    
                    # Consume the stream and print text (if any)
                    has_text = False
                    for chunk in responses:
                        try:
                            if hasattr(chunk, 'text') and chunk.text:
                                if not has_text:
                                    console.print("[bold purple]AI[/bold purple]: ", end="")
                                    has_text = True
                                console.print(chunk.text, end="")
                        except (ValueError, AttributeError):
                            # No text in this chunk, might be a function call
                            pass
                    
                    # Check for function calls
                    last_msg = chat_session.history[-1]
                    
                    # Handle multiple parts if present
                    function_call = None
                    for part in last_msg.parts:
                        if hasattr(part, 'function_call') and part.function_call:
                            function_call = part.function_call
                            break
                    
                    if function_call:
                        if not has_text:
                            console.print("[bold purple]AI[/bold purple]: ", end="")
                        
                        status.update(f"[bold cyan]Executing tool: {function_call.name}...[/bold cyan]")
                        
                        # Execute tool using the persistent event loop
                        result = loop.run_until_complete(handle_tool_call(
                            function_call, 
                            bq_core, 
                            bq_rag, 
                            default_table_name=table_name,
                            query_generator_model=classifier_model
                        ))
                        
                        # Send result back to model (streamed)
                        status.update("[bold yellow]Synthesizing answer...[/bold yellow]")
                        responses = chat_session.send_message(
                            Part.from_function_response(
                                name=function_call.name,
                                response={"content": result}
                            ),
                            stream=True
                        )
                        
                        for chunk in responses:
                            try:
                                if hasattr(chunk, 'text') and chunk.text:
                                    console.print(chunk.text, end="")
                            except (ValueError, AttributeError):
                                pass
                    
                    console.print() # Newline at end of turn
                    
                except Exception as e:
                    console.print(f"\n[bold red]Error:[/bold red] {e}")
    finally:
        # Clean up the event loop
        loop.close()

if __name__ == "__main__":
    app()
