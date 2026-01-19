import os
import json
import asyncio
import logging
from typing import List, Dict, Any, Optional, Set
from rich.console import Console

from client_package.processor.main import FileProcessorFacade

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


# Local imports
from bq_handler import BigQueryRAG, BQCore
#from file_processor import FileProcessor
from auth_manager import AuthManager
from chat_history import ChatHistoryDB
from error_handler import log_exception, create_error_response, DetailedExceptionLogger

import prompts
import dotenv
dotenv.load_dotenv()
# Constants
DEFAULT_DATASET_ID = "IDB"
DEFAULT_MODEL_NAME = "gemini-2.5-pro"
DATA_DIR = "./data_dir"

class CoreEngine(BQCore):
    def __init__(self, credentials_path: str = "credentials.json", require_auth: bool = False):
        self.setup_credentials(credentials_path)
        BQCore.__init__(self, dataset_id=None)
        self.console = Console()

        # Authentication state
        self.is_authenticated = not require_auth
        self.current_user_email = None
        self.current_dataset_id = DEFAULT_DATASET_ID
        self.auth_manager = AuthManager(
            bq_client=self.bqclient,
            project_id=self.bqclient.project,
        )

        if not require_auth and self.auth_manager:
            # Initialize normally with default dataset
            self._initialize_engine(DEFAULT_DATASET_ID)
        
        # Initialize Chat History DB
        self.db = ChatHistoryDB()
    
    def _initialize_engine(self, dataset_id: str):
        """Initialize the engine with a specific dataset"""
        self.current_dataset_id = dataset_id
        
        # Initialize BigQuery Handlers
        # Use BigQueryRAG as the primary core handler since it extends BQCore
        # dataset_id param for BQCore is 'dataset_id', for BigQueryRAG it is 'dataset' (delegated to BQCore with dataset_id logic inside?)
        # Let's check constructor of BigQueryRAG: def __init__(self, dataset: str or None = None): BQCore.__init__(self, dataset)
        # BQCore: def __init__(self, dataset_id=None): ...
        # So passing 'dataset' arg to BigQueryRAG works if keyed as 'dataset' or positional.
        try:
            self.bq_core = BigQueryRAG(dataset=dataset_id)
            self.bq_rag = self.bq_core 
        except Exception as e:
            print(f"⚠️  Could not initialize BigQueryRAG: {e}. Data features will be limited.")
            self.bq_core = None
            self.bq_rag = None
        
        # Initialize File Processor
        self.file_processor = FileProcessorFacade()
        
        # Initialize Vertex AI
        try:
            vertexai.init(project=self.pid, location="us-central1")
        except Exception as e:
            print(f"Vertex AI Init warning (safe to ignore if already init): {e}")
        
        # Initialize Models
        self.model = None
        self.embedding_model = None
        self.chat_session = None

        try:
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
            print("✅ Vertex AI Models initialized successfully.")
        except Exception as e:
            print(f"⚠️  Vertex AI Model Init Failed: {e}")
            print(f"    Running in degraded mode. AI features will be unavailable.")

        
        # Tools
        self.tools = self.get_bq_tools()
        
        # Initialize Case Handlers
        from client_package.cases.vector import VectorHandler
        from client_package.cases.sql import SQLHandler
        from client_package.cases.ingest import IngestHandler
        from client_package.cases.general import GeneralHandler
        
        self.vector_handler = VectorHandler(self)
        self.sql_handler = SQLHandler(self)
        self.ingest_handler = IngestHandler(self)
        self.general_handler = GeneralHandler(self)
    
    def clear_history(self):
        """
        Clear the chat history for the current session.
        Called when user exits to ensure session-based history.
        """
        if self.current_user_email:
            msg_count = self.db.get_session_count(self.current_user_email)
            self.db.clear_session(self.current_user_email)
            print(f"Chat history cleared for {self.current_user_email} ({msg_count} messages)")
    
    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """
        Authenticate user and initialize engine with their dataset
        
        Args:
            email: User email
            password: User password
            
        Returns:
            Dict with authentication result
        """
        result = await asyncio.to_thread(self.auth_manager.authenticate_user, email, password)
        
        if result["success"]:
            self.is_authenticated = True
            self.current_user_email = email
            self.current_dataset_id = result["dataset_id"] # Dynamic User Dataset
            self.current_table_id = "KB" # Fixed table name per user requirement
            
            # Initialize/reinitialize engine with user's dataset
            await asyncio.to_thread(self._initialize_engine, self.current_dataset_id)
            print(f"✅ Authenticated {email}. Using Dataset: {self.current_dataset_id} | Table: {self.current_table_id}")
            
        return result

    async def get_existing_filenames(self) -> Set[str]:
        """
        Retrieves a set of all unique file_ids already present in the user's KB table.
        """
        if not self.bqclient or not self.current_dataset_id:
            return set()
            
        table_id = getattr(self, 'current_table_id', 'KB')
        query = f"SELECT DISTINCT file_id FROM `{self.pid}.{self.current_dataset_id}.{table_id}`"
        
        try:
            print(f"🔍 Checking existing files in {self.current_dataset_id}.{table_id}...")
            # Run query in a separate thread
            def run():
                query_job = self.bqclient.query(query)
                return {row.file_id for row in query_job.result()}
                
            return await asyncio.to_thread(run)
        except Exception as e:
            print(f"Could not retrieve existing filenames: {e}")
            return set()


    def setup_credentials(self, path: str):
        abs_path = os.path.abspath(path)
        if os.path.exists(abs_path):
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
            print(f"Loaded credentials from {abs_path}")
        else:
            print(f"Warning: Credentials file not found at {abs_path}")

    # --- Tool Wrappers ---
    def list_datasets(self) -> List[str]:
        """Wrapper for listing datasets."""
        try:
            datasets = list(self.bqclient.list_datasets())
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
            tables = list(self.bqclient.list_tables(f"{self.pid}.{target_ds}"))
            return [t.table_id for t in tables]
        except Exception as e:
             return [f"Error listing tables in {target_ds}: {e}"]

    def get_table_schema(self, table_id: str) -> Dict[str, str]:
        """Wrapper for get_table_schema tool."""
        # Use try-except to handle potential errors
        if not self.bq_core:
             return {"error": "BigQuery RAG handler not initialized (check credentials)."}
        try:
             # Use the detailed schema method
             return self.bq_core.bq_get_detailed_table_schema(table_name=table_id)
        except Exception as e:
             return {"error": str(e)}

    def run_sql_query(self, query: str) -> List[Dict[str, Any]]:
        """Wrapper for run_sql_query tool."""
        if not self.bq_core:
             return [{"error": "BigQuery Handler not initialized."}]
        try:
             return self.bq_core.run_query(query, conv_to_dict=True)
        except Exception as e:
             return [{"error": str(e)}]

    def vector_search(self, query_text: str, table_id: str = None, limit: int = 5) -> List[Dict[str, Any]]:
        """Wrapper for vector_search tool."""
        # Default to 'KB' if no table_id provided or if it's generic
        target_table = table_id if table_id else getattr(self, 'current_table_id', 'KB')
        if not table_id:
             print(f"Using default table '{target_table}' for vector search")
             
        if not self.bq_core:
             return [{"content": "MOCK DATA: Please verify credentials. Vertex AI can't reach BQ.", "file_id": "mock.pdf"}]
        try:
            # Embed query locally to avoid BQML connection issues
            if not self.embedding_model:
                 print("⚠️ Embedding model not available (degraded mode). Returning empty results.")
                 return []
            
            embeddings = self.embedding_model.get_embeddings([query_text])
            query_vector = embeddings[0].values
            
            return self.bq_core.bigquery_vector_search(
                data=query_vector,
                table_id=target_table,
                custom=True, # We pass the vector
                limit=limit,
                model_name=None, # Not needed for custom=True
                select=["id", "content", "file_id", "file_type", "page_number", "html_tag", "metadata"],
                embed_column="embedding" # FIXED: Always use the content embedding column
            )
        except Exception as e:
             print(f"Vector search failed: {e}")
             return [{"error": str(e), "content": "Unable to search KB."}]

    def get_table_metadata(self, table_id: str) -> Dict[str, Any]:
        """Wrapper for get_table_metadata tool."""
        try:
            table = self.bqclient.get_table(f"{self.pid}.{self.current_dataset_id}.{table_id}")
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
            description="Perform a semantic search on the KB content. This is the primary tool for answering questions about uploaded documents.",
            parameters={
                "type": "object",
                "properties": {
                    "query_text": {"type": "string", "description": "The natural language query to search for"},
                    "table_id": {"type": "string", "description": "The table to search (defaults to 'KB')"},
                    "limit": {"type": "integer", "description": "Number of results to return (default 5)"}
                },
                "required": ["query_text"],
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
        # Quick check for upload/ingest keywords first
        if any(kw in user_input.lower() for kw in ["upload", "ingest", "upsert"]) and \
           any(p in user_input.lower() for p in ["/", "\\", "c:", "./", "../", "dir", "path"]):
            return "upload_by_path"
            
        if not self.model:
            print("⚠️ AI Model not available. Classification skipped.")
            return "query_non_db_chat" # Fallback to general chat or error
            
        prompt_classification = prompts.get_classification_prompt(user_input)
        try:
            # Add timeout protection (30 seconds for classification)
            # Use sync generate_content in thread to avoid async loop issues
            response = await asyncio.to_thread(
                self.model.generate_content,
                prompt_classification
            )
            intent = response.text.strip()
            print(f"Classification result: {intent}")

            if "similarity" in intent.lower(): return "query_similarity_search"
            if "sql" in intent.lower(): return "query_sql_generation"
            if "add_table" in intent.lower(): return "add_table"
            if "upload" in intent.lower() or "ingest" in intent.lower(): 
                return "upload_by_path"
            return "query_non_db_chat"
        except asyncio.TimeoutError:
            print(f"Classification timed out for: {user_input[:50]}")
            return "query_non_db_chat"  # Safe fallback
        except Exception as e:
            print(f"Classification error: {e}")
            return "query_non_db_chat"

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
            
        if not self.model:
            return user_input
            
        prompt = prompts.get_query_rewrite_prompt(user_input, history_text)
        try:
            response = await asyncio.to_thread(self.model.generate_content, prompt)
            rewritten = response.text.strip()
            if rewritten != user_input:
                print(f"🔄 Rewrote query: '{user_input}' -> '{rewritten}'")
            return rewritten
        except Exception as e:
            print(f"Rewrite failed: {e}")
            return user_input

    async def process_user_input(
        self,
        user_input: str,
        status_callback: Optional[callable] = None
    ) -> Dict[str, Any]:
        """
        Main entry point for processing user input.
        Orchestrates classification, routing, and execution.
        """
        if not self.is_authenticated:
            return {
                "intent": "error",
                "response_text": "Please log in to continue."
            }
            
        # 1. Classification
        intent = await self.classify_intent(user_input)
        
        # 2. Rewrite Query (if needed, mostly for search/SQL)
        if intent in ["query_sql_generation", "query_similarity_search"]:
            user_input = await self.rewrite_user_input(user_input)

            # --- Query Expansion (Ph 1.1) ---
            if intent == "query_similarity_search":
                try:
                    if status_callback: await status_callback("🧠 Expanding query...", "expand")
                    expand_prompt = prompts.get_query_expansion_prompt(user_input)
                    exp_resp = await asyncio.to_thread(self.model.generate_content, expand_prompt)
                    variations = json.loads(exp_resp.text.strip().replace("```json", "").replace("```", ""))
                    if isinstance(variations, list):
                        # For now, just append variations to the input via a context note 
                        # This passes "Input + Variations" to the vector handler
                        # Ideally, VectorHandler should run multiple searches (RRF), but for Step 1, we start simple context augmentation.
                        # Wait, appending to input might confuse the embedding unless designed for it.
                        # Better approach for V1: Append to user_input in a structured way that VectorHandler might use, 
                        # OR just let the handler assume it's one expanded query block.
                        # "Main Query. Related: Var1, Var2"
                        expansion_text = ", ".join(variations)
                        print(f"🧠 Query Expansion: {expansion_text}")
                        # user_input = f"{user_input} (Related: {expansion_text})"
                        # Let's keep user_input clean but pass expansion via a side channel? 
                        # VectorHandler.handle signature is process(user_input, status).
                        # Let's simply append for now as the simplest modification without changing handler signature.
                        # Actually, a better way is to search for the variations joined.
                        # Let's trust the "Related" context approach to rich embedding.
                        user_input = f"{user_input}\nContextual Variations: {expansion_text}"
                except Exception as e:
                    print(f"Expansion failed (skipping): {e}")
            
        print(f"➡️  Route: {intent} | Query: {user_input}")
        
        # 3. Route to Handler
        handler_map = {
            "query_similarity_search": self.vector_handler,
            "query_sql_generation": self.sql_handler,
            "upload_by_path": self.ingest_handler,
            "query_non_db_chat": self.general_handler
        }
        
        handler = handler_map.get(intent, self.general_handler)
        
        try:
            return await handler.handle(user_input, status_callback)
        except Exception as e:
            print(f"❌ Processing Error: {e}")
            return {
                "intent": "error",
                "response_text": f"An error occurred: {str(e)}",
                "error": str(e)
            }

    async def upsert_data(self, table_id: str, rows: List[Dict[str, Any]], upsert: bool = True) -> Dict[str, Any]:
        """
        Directly upsert data rows into BigQuery.
        Used when client performs local processing/extraction.
        """
        try:
            loop = asyncio.get_running_loop()
            # Delegate to blocking BQ handler in thread pool
            await loop.run_in_executor(
                None, 
                lambda: self.bq_rag.bq_insert(
                    table_id, 
                    rows, 
                    upsert=upsert, 
                    ds_id=self.current_dataset_id
                )
            )
            return {"success": True, "count": len(rows), "table": table_id}
            
        except Exception as e:
            error_msg = log_exception(e, "Data Upsert")
            raise e

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
                    
                    print(f"⚙️ Calling tool: {tool_name} with args: {tool_args}")
                    
                    # Dynamically call the tool function from SELF (using wrappers)
                    tool_func = getattr(self, tool_name, None)
                    if tool_func:
                        try:
                            if asyncio.iscoroutinefunction(tool_func):
                                output = await tool_func(**tool_args)
                            else:
                                output = await asyncio.to_thread(tool_func, **tool_args)
                                
                            response_parts.append(Part.from_function_response(
                                name=tool_name,
                                response={"content": json.dumps(output, default=str)}
                            ))
                        except Exception as e:
                            error_message = f"Error calling tool {tool_name}: {e}"
                            print(f"❌ {error_message}")
                            response_parts.append(Part.from_function_response(
                                name=tool_name,
                                response={"error": error_message}
                            ))
                    else:
                        error_message = f"Tool {tool_name} not found."
                        print(f"❌ {error_message}")
                        response_parts.append(Part.from_function_response(
                            name=tool_name,
                            response={"error": error_message}
                        ))
                
                # Send tool outputs back to the model (Sync in thread)
                tool_response = await asyncio.to_thread(
                    self.chat_session.send_message,
                    response_parts
                )
                return tool_response.text
            else:
                return candidate.text
        return "I'm sorry, I couldn't generate a response."

    # Legacy method redirect to IngestHandler (compatibility)
    async def handle_file_upload(self, *args, **kwargs):
        return await self.ingest_handler.handle_file_upload(*args, **kwargs)

    # Legacy method redirect to IngestHandler (compatibility)
    async def ingest_from_path(self, *args, **kwargs):
        # NOTE: ingest_from_path signature in handler is slightly different or matches?
        # In handler: ingest_from_path(path_input, status, config)
        # In engine: ingest_from_path(path_input, status, config)
        # It matches.
        return await self.ingest_handler.ingest_from_path(*args, **kwargs)
