import os
import json
import asyncio
import logging
import pandas as pd
from typing import List, Dict, Any, Optional
from rich.console import Console

# Configure Structured Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Google Cloud & Vertex AI
import vertexai
from vertexai.generative_models import GenerativeModel, Tool, FunctionDeclaration, Part, Content, ChatSession
from vertexai.language_models import TextEmbeddingModel
from google.cloud import bigquery


# Local imports
from bq_handler import BQCore, BigQueryRAG, BQ_DATASET_ID
from file_processor import FileProcessor
from auth_manager import AuthManager
import glob
import prompts

# Constants
DEFAULT_DATASET_ID = "IDB"
DEFAULT_MODEL_NAME = "gemini-2.5-pro"
DATA_DIR = "./data_dir"

class CoreEngine:
    def __init__(self, credentials_path: str = "credentials.json", require_auth: bool = False):
        self.console = Console()
        self.setup_credentials(credentials_path)
        
        # Authentication state
        self.is_authenticated = not require_auth
        self.current_user_email = None
        self.current_dataset_id = DEFAULT_DATASET_ID
        self.auth_manager = None
        
        # Initialize BigQuery client for auth
        self.bq_client = bigquery.Client()
        self.project_id = self.bq_client.project
        
        # Initialize AuthManager
        self.auth_manager = AuthManager(self.bq_client, self.project_id)
        
        if not require_auth:
            # Initialize normally with default dataset
            self._initialize_engine(DEFAULT_DATASET_ID)
        # else: wait for authenticate() to be called
    
    def _initialize_engine(self, dataset_id: str):
        """Initialize the engine with a specific dataset"""
        self.current_dataset_id = dataset_id
        
        # Initialize BigQuery Handlers
        # Use BigQueryRAG as the primary core handler since it extends BQCore
        # dataset_id param for BQCore is 'dataset_id', for BigQueryRAG it is 'dataset' (delegated to BQCore with dataset_id logic inside?)
        # Let's check constructor of BigQueryRAG: def __init__(self, dataset: str or None = None): BQCore.__init__(self, dataset)
        # BQCore: def __init__(self, dataset_id=None): ...
        # So passing 'dataset' arg to BigQueryRAG works if keyed as 'dataset' or positional.
        self.bq_core = BigQueryRAG(dataset=dataset_id)
        self.bq_rag = self.bq_core 
        
        # Initialize File Processor
        self.file_processor = FileProcessor()
        
        # Initialize Vertex AI
        try:
            vertexai.init(project=self.project_id, location="us-central1")
        except Exception as e:
            logger.warning(f"Vertex AI Init warning (safe to ignore if already init): {e}")
        
        # Initialize Models
        system_instruction = [
            "You are a helpful AI assistant with access to a BigQuery Knowledge Base.",
            "When answering questions based on tool outputs (especially vector search), you MUST cite the source file and, if available, the specific section or HTML tag where the information was found.",
            "Use the 'content' field from search results to answer.",
            "If the search result includes 'html_tag', mention it to provide context (e.g. 'Found in a <div> tag' or 'Section <H1>')."
        ]
        self.model = GenerativeModel(DEFAULT_MODEL_NAME, system_instruction=system_instruction)
        self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
        
        # Chat Session
        self.chat_session = self.model.start_chat()
        
        # Tools
        self.tools = self.get_bq_tools()
    
    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and initialize engine with their dataset
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dict with authentication result
        """
        result = self.auth_manager.authenticate_user(email, password)
        
        if result["success"]:
            self.is_authenticated = True
            self.current_user_email = email
            self.current_dataset_id = result["dataset_id"] # Dynamic User Dataset
            self.current_table_id = "kb" # Fixed table name per user requirement
            
            # Initialize/reinitialize engine with user's dataset
            self._initialize_engine(self.current_dataset_id)
            logger.info(f"✅ Authenticated {email}. Using Dataset: {self.current_dataset_id} | Table: {self.current_table_id}")
            
        return result

    async def handle_file_upload(self, filename: str, content: bytes, status_callback=None, metadata: Optional[Dict[str, Any]] = None, ingestion_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Processes an uploaded file, stores it temporarily, and ingests it into BigQuery via Production Pipeline.
        Args:
            metadata: Optional dictionary of metadata (e.g., parent_directory) to attach to the ingested rows.
            ingestion_config: Optional dictionary for pipeline settings (chunk_size, overlap, use_docai).
        """
        async def update_status(message: str, step: str = ""):
            if status_callback:
                await status_callback(message, step)

        # Temp Store Logic
        TEMP_STORE = "temp_store"
        if not os.path.exists(TEMP_STORE):
            os.makedirs(TEMP_STORE)
            
        temp_file_path = os.path.join(TEMP_STORE, filename)

        logger.info(f"📂 Handling file upload via Production Pipeline: {filename} ({len(content)} bytes)")
        if metadata: logger.info(f"   MetaData: {metadata}")
        
        await update_status(f"📂 Preparing to ingest {filename}...", "prep_ingest")
        
        try:
            # 1. Store in Temp Store
            with open(temp_file_path, "wb") as f:
                f.write(content)
            logger.info(f"💾 Stored file in temp store: {temp_file_path}")
            
            # Initialize Pipeline on demand (or can be cached)
            # using default config or env vars
            from ingestion_pipeline import ProductionIngestionPipeline, PipelineConfig
            
            # Default Settings
            defaults = {"chunk_size": 200, "chunk_overlap": 50, "use_docai": True}
            if ingestion_config:
                defaults.update(ingestion_config)
            
            config = PipelineConfig(
                chunk_size=defaults["chunk_size"],
                chunk_overlap=defaults["chunk_overlap"],
                use_docai=defaults["use_docai"],
                dataset_id=self.current_dataset_id,
                table_id=getattr(self, 'current_table_id', 'KB') # Use user table or fallback
            )
            pipeline = ProductionIngestionPipeline(config)
            
            # Run Pipeline
            logger.info("⏳ Starting ingestion pipeline...")
            await update_status(f"🚀 Initializing extraction for {filename}...", "extract")
            
            # We can't easily hook into the pipeline's internal steps without refactoring pipeline,
            # but we can wrap the main call.
            result_message = await pipeline.run_pipeline_for_bytes(filename, content, status_callback=update_status, metadata=metadata)
            
            logger.info("✅ Ingestion pipeline finished.")
            await update_status("✅ Ingestion & Embedding complete!", "done")
            
            # Post-ingestion: Verify and get details
            query = f"""
                SELECT COUNT(*) as count, file_id 
                FROM `{self.project_id}.{self.current_dataset_id}.{getattr(self, 'current_table_id', 'kb')}`
                WHERE file_id = '{filename}'
                GROUP BY file_id
            """
            try:
                results = self.bq_client.query(query).result()
                for row in results:
                    return f"✅ {result_message} (Verified: {row.count} rows in KB)"
            except Exception as e:
                logger.warning(f"Verification query failed: {e}")
                pass # Return original message if check fails
            
            msg = f"✅ {result_message}"
            if filename.lower().endswith(".pdf"):
                graph_link = f"/graphs/{filename}_graph.html"
                 # Markdown link for frontend rendering if possible, or just URL
                msg += f"\n\n🔗 **[View Knowledge Graph]({graph_link})**"
            
            return msg
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            return f"❌ Upload failed: {str(e)}"
        
        finally:
            # Cleanup Temp Store
            if os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                    logger.info(f"🗑️ Deleted temp file: {temp_file_path}")
                except Exception as cleanup_error:
                    logger.error(f"⚠️ Failed to delete temp file {temp_file_path}: {cleanup_error}")

    def ingest_data(self, table_name: str = "nodes"):
        """
        Ingests data from data_dir using the Production Ingestion Pipeline.
        """
        if not os.path.exists(DATA_DIR):
            os.makedirs(DATA_DIR)
            return

        files = glob.glob(os.path.join(DATA_DIR, "*"))
        if not files:
            logger.warning("⚠️  No files found in data_dir.")
            return

        logger.info(f"📂 Found {len(files)} files to ingest via Production Pipeline...")
        
        # We need async here to call the pipeline
        # But ingest_data is currently synchronous and called from CLI sync context
        # We will wrap it in asyncio.run if there is no running loop, or create a task
        
        async def run_pipeline_batch():
            from ingestion_pipeline import ProductionIngestionPipeline, PipelineConfig
            config = PipelineConfig(
                chunk_size=1000,
                chunk_overlap=200,
                use_docai=True
            )
            pipeline = ProductionIngestionPipeline(config)
            
            for f in files:
                logger.info(f"  👉 Processing {os.path.basename(f)}...")
                try:
                    with open(f, "rb") as file_obj:
                         content = file_obj.read()
                    
                    msg = await pipeline.run_pipeline_for_bytes(os.path.basename(f), content)
                    logger.info(f"     ✅ {msg}")
                except Exception as e:
                    logger.error(f"     ❌ Failed: {e}")

        try:
             loop = asyncio.get_event_loop()
             if loop.is_running():
                 # We are likely in a server context, but ingest_data is typically a CLI/Startup command.
                 # If called from CLI (sync), this branch won't hit.
                 # If called from async server, we should await it, but specific method signature is sync.
                 # Let's create a task
                 asyncio.create_task(run_pipeline_batch())
             else:
                 loop.run_until_complete(run_pipeline_batch())
        except RuntimeError:
             # No loop running
             asyncio.run(run_pipeline_batch())


    def setup_credentials(self, path: str):
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
            logger.info(f"Loaded credentials from {abs_path}")
        else:
            logger.error(f"Warning: Credentials file not found at {abs_path}")

    # --- Tool Wrappers ---
    def list_datasets(self) -> List[str]:
        """Wrapper for listing datasets."""
        try:
            datasets = list(self.bq_client.list_datasets())
            return [d.dataset_id for d in datasets]
        except Exception as e:
            return [f"Error listing datasets: {e}"]

    def list_tables(self, dataset_id: str = None) -> List[str]:
        """Wrapper for listing tables. Ignores dataset_id argument to match BQCore signature or adapts."""
        # Note: BQCore.list_tables() lists from self.ds_id. 
        # If dataset_id is different, we might want to respect it, but BQCore is bound to one dataset.
        # For safety, we use the internal client if dataset_id matches current, or try to list from the specific dataset.
        target_ds = dataset_id if dataset_id else self.current_dataset_id
        try:
            tables = list(self.bq_client.list_tables(f"{self.project_id}.{target_ds}"))
            return [t.table_id for t in tables]
        except Exception as e:
             return [f"Error listing tables in {target_ds}: {e}"]

    def get_table_schema(self, table_id: str) -> Dict[str, str]:
        """Wrapper for get_table_schema tool."""
        # Use try-except to handle potential errors
        try:
             return self.bq_core.bq_get_table_schema(table_name=table_id)
        except Exception as e:
             return {"error": str(e)}

    def run_sql_query(self, query: str) -> List[Dict[str, Any]]:
        """Wrapper for run_sql_query tool."""
        try:
             return self.bq_core.run_query(query, conv_to_dict=True)
        except Exception as e:
             return [{"error": str(e)}]

    def vector_search(self, query_text: str, table_id: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Wrapper for vector_search tool."""
        # Default to 'kb' if no table_id provided or if it's generic
        target_table = table_id if table_id else getattr(self, 'current_table_id', 'kb')
        if not table_id:
             logger.info(f"Using default table '{target_table}' for vector search")
             
        try:
            # Embed query locally to avoid BQML connection issues
            embeddings = self.embedding_model.get_embeddings([query_text])
            query_vector = embeddings[0].values
            
            return self.bq_core.bigquery_vector_search(
                data=query_vector,
                table_id=target_table,
                custom=True, # We pass the vector
                limit=limit,
                model_name=None, # Not needed for custom=True
                select=["id", "content", "file_id", "file_type", "page_number", "html_tag", "metadata"],
                embed_column="embedding"
            )
        except Exception as e:
             logger.error(f"Vector search failed: {e}")
             return [{"error": str(e)}]

    def get_table_metadata(self, table_id: str) -> Dict[str, Any]:
        """Wrapper for get_table_metadata tool."""
        try:
            table = self.bq_client.get_table(f"{self.project_id}.{self.current_dataset_id}.{table_id}")
            return {
                "num_rows": table.num_rows,
                "created": str(table.created),
                "modified": str(table.modified),
                "schema_fields": [f.name for f in table.schema],
                "size_bytes": table.num_bytes
            }
        except Exception as e:
             return {"error": str(e)}

    def get_bq_tools(self):
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
            description="Get comprehensive metadata about a table including row count, columns, sample data, and statistics.",
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

    async def classify_intent(self, user_input: str) -> str:
        """
        Classifies the user's intent into one of the defined categories.
        """
        # Quick check for upload keyword first
        if "upload" in user_input.lower() and ("/" in user_input or "\\" in user_input or "C:" in user_input):
            return "command_upload_by_path"
            
        prompt = prompts.get_classification_prompt(user_input)
        try:
            response = await self.model.generate_content_async(prompt)
            intent = response.text.strip()
            if "similarity" in intent.lower(): return "query_similarity_search"
            if "sql" in intent.lower(): return "query_sql_generation"
            if "add_table" in intent.lower(): return "add_table"
            if "upload" in intent.lower(): return "upload_by_path"
            return "query_non_db_chat"
        except Exception as e:
            self.console.print(f"[dim]Classification error: {e}[/dim]")
            return "query_non_db_chat"

    async def ingest_from_path(
            self,
            path_input: str,
            status_callback=None, ingestion_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ingests files from a given path (file or directory).
        Auto-detects recursive directories and extracts 'relative parent directory' metadata.
        """
        import re
        
        # 1. Path Extraction Logic (Robust)
        # Matches: "upload C:\path", "C:\path", "/path/to/file", etc.
        # We strip "upload" keyword if present, then look for the path string.
        clean_input = path_input.replace("upload", "", 1).strip().strip('"\'')
        
        target_path = clean_input
        
        # Check direct existence
        if not os.path.exists(target_path):
             # Try regex match
             path_match = re.search(r'(?:["\'])(.*?)(?:["\'])|(?:\s)((?:[a-zA-Z]:[\\/]|[.\\/])[^\s]+)', path_input)
             if path_match:
                 match = path_match.group(1) if path_match.group(1) else path_match.group(2)
                 if os.path.exists(match):
                    target_path = match
        
        # Fallback: Check if the end of the string is a path (e.g. "please upload C:\data")
        if not target_path or not os.path.exists(target_path):
            potential_path = path_input.split()[-1].strip('"\'')
            if os.path.exists(potential_path):
                target_path = potential_path
        
        if not target_path or not os.path.exists(target_path):
             return {
                "intent": "command_upload_by_path",
                "response_text": f"❌ Path not found: `{target_path or path_input}`. Please check the path and try again."
             }

        abs_path = os.path.abspath(target_path)
        items_to_process = [] # List of (full_path, relative_parent_dir)

        # 2. Traversal & Parent Extraction
        if status_callback: await status_callback(f"📂 Scanning `{abs_path}`...", "scan")
        
        if os.path.isfile(abs_path):
            # Single file. Relative parent is root/none relative to itself.
            items_to_process.append((abs_path, "root"))
        else:
            # Directory
            # requirement: "name of that immediate parent directory (relative to the initial input directory)"
            # Input: /data
            # File: /data/foo/bar.txt -> rel: foo/bar.txt -> parent: foo
            # File: /data/baz.txt -> rel: baz.txt -> parent: root (top level of input)
            
            for root, dirs, files in os.walk(abs_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    
                    # Calculate relative path from the INPUT directory (abs_path)
                    try:
                        rel_path = os.path.relpath(full_path, abs_path)
                        parts = rel_path.split(os.sep)
                        
                        if len(parts) > 1:
                            # It is in a subdirectory relative to input
                            # The "immediate parent" relative to input is the first directory component
                            relative_parent_dir = parts[0]
                        else:
                            # It is directly inside the input directory
                            relative_parent_dir = "root" # or ""
                            
                        items_to_process.append((full_path, relative_parent_dir))
                    except ValueError:
                        # Path issue
                        items_to_process.append((full_path, "unknown"))

        if not items_to_process:
             return {
                "intent": "command_upload_by_path",
                "response_text": f"⚠️ No files found in `{abs_path}`."
             }

        # 3. Processing
        processed_count = 0
        errors = []
        
        if status_callback: await status_callback(f"🚀 Found {len(items_to_process)} files. Starting ingestion...", "start_ingest")
        
        for i, (fpath, parent_dir) in enumerate(items_to_process):
             fname = os.path.basename(fpath)
             if status_callback: await status_callback(f"[{i+1}/{len(items_to_process)}] Processing {fname} (Parent: {parent_dir})...", "process")
             
             try:
                 with open(fpath, "rb") as f:
                     content = f.read()
                 
                 # Pass extra metadata to handle_file_upload
                 # We need to update handle_file_upload to accept metadata dict
                 metadata = {"relative_parent_dir": parent_dir}
                 
                 # Call existing handler (will require update for metadata arg)
                 msg = await self.handle_file_upload(fname, content, status_callback=None, metadata=metadata, ingestion_config=ingestion_config)
                 
                 if "❌" in msg:
                     errors.append(f"{fname}: {msg}")
                 else:
                     processed_count += 1
                     
             except Exception as e:
                 errors.append(f"{fname}: {str(e)}")
        
        report = f"✅ Successfully processed {processed_count}/{len(items_to_process)} files from `{abs_path}`."
        if errors:
            report += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
            if len(errors) > 5: report += f"\n...and {len(errors)-5} more."
            
        return {
             "intent": "command_upload_by_path",
             "response_text": report
        }





    async def rewrite_user_input(self, user_input: str) -> str:
        """
        Rewrites user input using chat history for context.
        """
        if not self.current_user_email: return user_input
        
        # Get history
        session_id = self.current_user_email
        history_text = self.db.get_formatted_history(session_id, limit=6) # Last 3 QA pairs
        
        if not history_text:
            return user_input
            
        prompt = prompts.get_query_rewrite_prompt(user_input, history_text)
        try:
            response = await self.model.generate_content_async(prompt)
            rewritten = response.text.strip()
            if rewritten != user_input:
                logger.info(f"🔄 Rewrote query: '{user_input}' -> '{rewritten}'")
            return rewritten
        except Exception as e:
            logger.warning(f"Rewrite failed: {e}")
            return user_input

    async def process_user_input(
            self,
            user_input: str,
            status_callback=None
    ) -> Dict[str, Any]:
        """
        Main entry point for processing user input.
        Returns a dictionary with response components.
        """
        async def update_status(message: str, step: str = ""):
            """Helper to send status updates if callback provided"""
            if status_callback:
                await status_callback(message, step)
        
        # 0. Contextual Rewrite
        original_input = user_input
        await update_status("🔄 Checking context...", "rewrite")
        user_input = await self.rewrite_user_input(user_input)

        await update_status("🧠 Analyzing your request...", "classify")
        intent = await self.classify_intent(user_input)
        logger.info(f"Intent detected: {intent}")
        
        if intent == "command_upload_by_path":
             return await self.ingest_from_path(user_input, update_status)
        
        result = {
            "intent": intent,
            "response_text": "",
            "source_citation": None,
            "traceability": None
        }

        if intent == "query_similarity_search":
            await update_status("🔍 Performing vector search...", "search")
            # We use the REWRITTEN query for the tool call
            response = await self.chat_session.send_message_async(
                f"User wants to find items: {user_input}. Use vector_search tool if appropriate. Default table is 'kb'.",
                tools=[self.tools]
            )
            await update_status("✨ Generating response...", "generate")
            result["response_text"] = await self.handle_model_response(response)
            
        elif intent == "query_sql_generation":
            await update_status("📊 Analyzing database schema...", "schema")
            # We use the REWRITTEN query for SQL generation
            sql_result = await self.handle_sql_generation(user_input, status_callback)
            result.update(sql_result)
            
        elif intent == "upload_by_path":

        elif intent == "add_table":
            # For now, guide the user to the CLI ingest command or explain
            # For now, guide the user to the CLI ingest command or explain
            result["response_text"] = prompts.get_upload_instructions_text()

        else: # query_non_db_chat
            await update_status("💬 Assisting with platform help...", "chat")
            help_prompt = prompts.get_platform_help_prompt(user_input)
            response = await self.chat_session.send_message_async(help_prompt)
            result["response_text"] = response.text

        await update_status("✅ Complete!", "done")
        return result
        
    async def handle_model_response(self, response) -> str:
        """
        Processes the model's response, including tool calls.
        """
        if response.candidates:
            candidate = response.candidates[0]
            if candidate.function_calls:
                # Handle tool calls
                # Send tool outputs back to the model
                response_parts = []
                for call in candidate.function_calls:
                    tool_name = call.name
                    tool_args = {k: v for k, v in call.args.items()}
                    
                    self.console.print(f"[dim]⚙️ Calling tool: {tool_name} with args: {tool_args}[/dim]")
                    
                    # Dynamically call the tool function from SELF (using wrappers)
                    tool_func = getattr(self, tool_name, None)
                    if tool_func:
                        try:
                            output = tool_func(**tool_args)
                            response_parts.append(Part.from_function_response(
                                name=tool_name,
                                response={"content": json.dumps(output, default=str)}
                            ))
                        except Exception as e:
                            error_message = f"Error calling tool {tool_name}: {e}"
                            self.console.print(f"[red]❌ {error_message}[/red]")
                            response_parts.append(Part.from_function_response(
                                name=tool_name,
                                response={"error": error_message}
                            ))
                    else:
                        error_message = f"Tool {tool_name} not found."
                        self.console.print(f"[red]❌ {error_message}[/red]")
                        response_parts.append(Part.from_function_response(
                            name=tool_name,
                            response={"error": error_message}
                        ))
                
                # Send tool outputs back to the model
                tool_response = await self.chat_session.send_message_async(
                    response_parts
                )
                return tool_response.text
            else:
                return candidate.text
        return "I'm sorry, I couldn't generate a response."

    async def handle_sql_generation(self, user_input: str, status_callback=None) -> Dict[str, Any]:
        """
        Handles the SQL generation workflow.
        """
        async def update_status(message: str, step: str = ""):
            if status_callback:
                await status_callback(message, step)
        
        # 1. Select Tables (Forced to KB)
        relevant_tables = ["KB"]
        
        # Append dataset ID to make them queryable names for context
        formatted_table_names = [f"{self.project_id}.{self.current_dataset_id}.KB"]
        await update_status(f"✅ Selected knowledge base: {formatted_table_names[0]}", "tables_selected")
        
        # 3. Get Schemas for Relevant Tables
        await update_status("📖 Loading schemas...", "load_schema")
        schemas = {}
        for t in relevant_tables:
            # Safely get schema
            try:
                schemas[t] = self.bq_core.bq_get_table_schema(t)
            except Exception:
                schemas[t] = "Schema unavailable"
            
        # 4. Generate SQL
        await update_status("🤖 Generating SQL query...", "generate_sql")
        prompt = prompts.get_sql_generation_prompt(
            user_input, 
            json.dumps(formatted_table_names, indent=2),
            json.dumps(schemas, indent=2)
        )
        
        response = await self.model.generate_content_async(prompt)
        sql_query = response.text.replace("```sql", "").replace("```", "").strip()
        
        self.console.print(f"[dim]📝 Generated SQL: {sql_query}[/dim]")
        
        # 5. Execute SQL
        await update_status("⚡ Executing query on BigQuery...", "execute_query")
        try:
            query_result = self.bq_core.run_query(sql_query, conv_to_dict=True)
            
            # 6. Generate Final Answer
            await update_status("💭 Formulating answer...", "formulate_answer")
            answer_prompt = prompts.get_natural_answer_prompt(
                user_input,
                sql_query,
                json.dumps(query_result, default=str)
            )
            answer_response = await self.model.generate_content_async(answer_prompt)
            
            return {
                "intent": "query_sql_generation",
                "response_text": answer_response.text,
                "source_citation": f"BigQuery SQL on {', '.join(relevant_tables)}",
                "traceability": {
                    "original_question": user_input,
                    "sql_query": sql_query,
                    "tables_used": relevant_tables,
                    "result_preview": str(query_result)[:500]
                }
            }
            
        except Exception as e:
            return {
                "intent": "query_sql_generation",
                "response_text": f"Failed to execute SQL: {e}",
                "traceability": {
                    "original_question": user_input,
                    "sql_query": sql_query,
                    "error": str(e)
                }
            }
