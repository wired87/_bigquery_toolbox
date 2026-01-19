
import os
import io
import json
import logging
import asyncio
import hashlib
import uuid
import pandas as pd
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field

# Google Cloud
from google.cloud import bigquery
from google.cloud import documentai
from google.api_core.client_options import ClientOptions
import vertexai
from vertexai.language_models import TextEmbeddingModel

# LangChain
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from bs4 import BeautifulSoup, Tag
from pdfminer.high_level import extract_text_to_fp
from pdfminer.layout import LAParams

from client_package.processor.main import FileProcessorFacade
from gutils import GUtils

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
PROJECT_ID = "aixr-401704" # Replace with your project
LOCATION = "us"
DOCAI_LOCATION = "us"
PROCESSOR_ID = os.getenv("DOCAI_PROCESSOR_ID", "YOUR_PROCESSOR_ID_HERE") 
DATASET_ID = "IDB"
TABLE_ID = "nodes"
MODEL_ID = "embedding_model"

class PipelineConfig(BaseModel):
    chunk_size: int = 200
    chunk_overlap: int = 50
    use_docai: bool = True
    processor_id: Optional[str] = PROCESSOR_ID
    dataset_id: str
    table_id: str = "KB"

class KnowledgeRow(BaseModel):
    """
    Standardized BQ Schema Row
    """
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_id: str
    file_type: str
    content: str
    embedding: Optional[List[float]] = None # Populated by BQML if None
    metadata: str # JSON string for extra fields
    ingested_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    parent_file_id: Optional[str] = None
    row_type: str = "chunk" 
    
    # Specific fields for PDF/HTML chunks
    html_tag: Optional[str] = None
    page_number: Optional[int] = None
    # New Field
    relative_parent_dir: Optional[str] = None
    
    # Table-specific fields
    is_table_row: Optional[bool] = None
    table_id: Optional[str] = None
    row_number: Optional[int] = None
    columns: Optional[Dict[str, str]] = None
    
    def to_bq_dict(self):
         data = self.model_dump()
         if data.get("embedding") is None:
             data["embedding"] = [] # Return empty list for REPEATED field
         return data

class ProductionIngestionPipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        try:
            self.bq_client = bigquery.Client()
            global PROJECT_ID
            PROJECT_ID = self.bq_client.project
        except Exception as e:
            print(f"⚠️  Failed to init BQ Client in Pipeline: {e}")
            self.bq_client = None
            
        self.docai_client = None
        self.file_handler = FileProcessorFacade()

        # Init DocAI (only if needed)
        if self.config.use_docai and self.config.processor_id:
             pass 

        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.config.chunk_size,
            chunk_overlap=self.config.chunk_overlap
        )
        
        # Init Vertex AI for embeddings
        if self.bq_client:
            try:
                vertexai.init(project=PROJECT_ID, location="us-central1")
                self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
                print("✅ Vertex AI Embedding Model (text-embedding-004) initialized.")
            except Exception as e:
                print(f"⚠️  Failed to init Vertex AI: {e}")
                self.embedding_model = None

        self.start_time = None

    async def run_pipeline_for_bytes(
            self,
            filename: str,
            content: bytes,
            status_callback=None,
            metadata: Optional[Dict[str, Any]] = None):
        self.start_time = datetime.now()
        
        async def report(msg, step=None):
             if status_callback: await status_callback(msg, step or "pipeline")

        print(f"🚀 Processing file: {filename}")
        
        if not self.bq_client:
            print("❌ BigQuery client not available. Aborting pipeline.")
            return "Failed: Credentials missing on server."

        try:
            # 1. Extraction (In-Memory)
            await report(f"📑 Extracting content from {filename}...")
            
            docs:list[Document] = self.file_handler.process_bytes(filename, content)
            if not docs:
                print(f"No content extracted from {filename}")
                await report("⚠️ No content extracted.")
                return "No content extracted."

            # 2. Transformation
            await report(f"🧩 Chunking {len(docs)} documents...")
            rows = self.transform_to_rows(filename, docs, metadata)
            
            # 3. Schema Check
            await report("🛠️ Verifying BigQuery resources...")
            try:
                await asyncio.to_thread(self.ensure_resources)
            except Exception as e:
                print(f"⚠️ Resource verification warning: {e}")
                # Continue, as tables might already exist or simple schema update failed
            
            # 4. Generate Embeddings (Vertex AI)
            if self.embedding_model:
                await report(f"🧠 Generating embeddings for {len(rows)} chunks...")
                
                try:
                    # No longer wrapping in to_thread here as the method itself is now async and handles internal blocking calls
                    await self.generate_batch_embeddings(rows, status_callback=report)
                except Exception as e:
                     await report(f"⚠️ Embedding generation failed: {e}")
                     print(f"Embedding error: {e}")
            else:
                await report("⚠️  Embedding model not available. Skipping embedding generation.")
                
            # 5. Upsert (Optimized)
            await report(f"💾 Upserting {len(rows)} rows to BigQuery...")
            upsert_start = datetime.now()
            count = await asyncio.to_thread(self.upsert_rows, rows)
            upsert_time = (datetime.now() - upsert_start).total_seconds()
            
            total_time = (datetime.now() - self.start_time).total_seconds()
            print(f"⏱️ Total processing time: {total_time:.2f}s (Upsert: {upsert_time:.2f}s)")
            
            if total_time > 4: 
                print(f"⚠️ Processing time {total_time:.2f}s exceeded target.")
                await report(f"⚠️ Processing time {total_time:.2f}s exceeded target.")

            return f"Processed {filename}: Ingested {count} rows."
            
        except Exception as e:
            print(f"❌ Pipeline Critical Error: {e}")
            await report(f"❌ Critical Pipeline Failure: {str(e)}")
            raise e



    def _get_mime_type(self, ext):
        mimes = {'pdf': 'application/pdf', 'jpg': 'image/jpeg', 'png': 'image/png', 'csv': 'text/csv'}
        return mimes.get(ext, 'application/octet-stream')

    def _process_with_docai(self, content: bytes, mime_type: str, filename: str) -> List[Document]:
        """
        Calls DocAI API with RawDocument.
        """
        # This method is no longer called from extract_content based on the provided edit.
        # Keeping it for completeness if other parts of the system still call it.
        try:
            if not self.docai_client: # Lazy init if not already done
                opts = ClientOptions(api_endpoint=f"{DOCAI_LOCATION}-documentai.googleapis.com")
                self.docai_client = documentai.DocumentProcessorServiceClient(client_options=opts)
                self.processor_name = self.docai_client.processor_path(PROJECT_ID, DOCAI_LOCATION, self.config.processor_id)
                print(f"Using DocAI Processor: {self.config.processor_id}")

            print(f"Sending {len(content)} bytes to DocAI ({mime_type})...")
            raw_document = documentai.RawDocument(content=content, mime_type=mime_type)
            request = documentai.ProcessRequest(name=self.processor_name, raw_document=raw_document)
            result = self.docai_client.process_document(request=request)
            document = result.document
            
            return [Document(page_content=document.text, metadata={"file_name": filename, "type": "docai_ocr"})]
            
        except Exception as e:
            print(f"DocAI Error: {e}")
            return []

    async def _process_pdf_html(self, content: bytes, filename: str) -> List[Document]:
        """
        Extracts HTML from PDF, cleans tags to keep only content and tag name.
        Enhanced to handle table elements with row/column structure.
        """
        try:
            # 1. Bare HTML Extraction (pdfminer)
            output_string = io.BytesIO()
            with io.BytesIO(content) as input_stream:
                extract_text_to_fp(input_stream, output_string, output_type='html', laparams=LAParams())
            html_content = output_string.getvalue().decode("utf-8")

            # 2. Parse & Clean
            soup = BeautifulSoup(html_content, 'html.parser')

            # Remove scripts and styles
            for script_or_style in soup(["script", "style"]):
                script_or_style.decompose()

            gutils = GUtils(project_id=PROJECT_ID)
            docs = []

            def traverse(tag: Tag, parent_id: Optional[str] = None):
                if not isinstance(tag, Tag): return

                # Special handling for table elements
                if tag.name == 'table':
                    table_docs = self._process_table_element(tag, filename, parent_id)
                    docs.extend(table_docs)
                    return  # Don't traverse children of table, already handled

                # Get clean text content (no HTML/CSS)
                text_content = tag.get_text(strip=True)

                # Only process tags that have actual text content
                if text_content:
                    # Save just the clean content and the tag name
                    # We avoid stringifying the whole tag (str(tag)) which contains attributes/styles
                    node = gutils.create_node(
                        tag_name=tag.name,
                        content=text_content,
                        parent_id=parent_id,
                        metadata={
                            "file_name": filename,
                            "file_type": "pdf",
                            "tag": tag.name,
                            "page_number": 1
                        },
                        defer_embedding=True
                    )

                    # Also create Documents for the pipeline flow
                    # If content is long, we split it here
                    if len(text_content) > 200:
                        splits = self.splitter.split_text(text_content)
                    else:
                        splits = [text_content]

                    for i, split in enumerate(splits):
                        docs.append(Document(
                            page_content=split,
                            metadata={
                                "id": f"{node.id}_{i}",
                                "file_name": filename,
                                "html_tag": tag.name,
                                "parent_ref": parent_id
                            }
                        ))

                    for child in tag.children:
                        if isinstance(child, Tag):
                            traverse(child, node.id)

            root = soup.body if soup.body else soup
            traverse(root)
            print(f"✅ Extracted {len(docs)} clean content blocks from {filename}")
            return docs

        except Exception as e:
            print(f"PDF HTML Extraction Error: {e}")
            return []

    def _process_table_element(self, table_tag: Tag, filename: str, parent_id: Optional[str]) -> List[Document]:
        """
        Processes a single HTML table element, extracting each row with column references.
        Each row becomes a separate Document with column data preserved.
        
        Args:
            table_tag: BeautifulSoup Tag object representing the <table>
            filename: Source PDF filename
            parent_id: Parent node ID from the graph
            
        Returns:
            List of Document objects, one per table row
        """
        docs = []
        table_id = str(uuid.uuid4())  # Unique ID for this table instance
        
        try:
            # Step 1: Extract column headers
            headers = []
            thead = table_tag.find('thead')
            
            if thead:
                # Look for headers in <thead>
                header_row = thead.find('tr')
                if header_row:
                    headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
            
            # If no <thead>, try first <tr> in <tbody> or table
            if not headers:
                first_row = table_tag.find('tr')
                if first_row:
                    # Check if first row looks like headers (contains <th> tags)
                    ths = first_row.find_all('th')
                    if ths:
                        headers = [th.get_text(strip=True) for th in ths]
                    else:
                        # Use generic column names if no headers found
                        first_cells = first_row.find_all(['td', 'th'])
                        headers = [f"col_{i+1}" for i in range(len(first_cells))]
            
            # Step 2: Extract table rows
            tbody = table_tag.find('tbody')
            rows = tbody.find_all('tr') if tbody else table_tag.find_all('tr')
            
            # Skip first row if it was used as headers and contained <th> tags
            skip_first = False
            if rows and not thead:
                first_row_ths = rows[0].find_all('th')
                if first_row_ths:
                    skip_first = True
            
            row_start_idx = 1 if skip_first else 0
            
            # Step 3: Process each data row
            for row_idx, tr in enumerate(rows[row_start_idx:], start=1):
                cells = tr.find_all(['td', 'th'])
                
                # Extract cell contents
                cell_contents = [cell.get_text(strip=True) for cell in cells]
                
                # Skip empty rows
                if not any(cell_contents):
                    continue
                
                # Map columns to content
                columns_dict = {}
                for i, content in enumerate(cell_contents):
                    col_name = headers[i] if i < len(headers) else f"col_{i+1}"
                    columns_dict[col_name] = content
                
                # Create concatenated content for embedding/search
                row_content = " | ".join([f"{k}: {v}" for k, v in columns_dict.items() if v])
                
                # Create Document for this table row
                doc = Document(
                    page_content=row_content,
                    metadata={
                        "id": f"{table_id}_row_{row_idx}",
                        "file_name": filename,
                        "html_tag": "tr",
                        "parent_ref": parent_id,
                        "is_table_row": True,
                        "table_id": table_id,
                        "row_number": row_idx,
                        "columns": columns_dict,
                        "column_headers": headers
                    }
                )
                docs.append(doc)
            
            print(f"📊 Extracted {len(docs)} rows from table in {filename}")
            
        except Exception as e:
            print(f"Error processing table element: {e}")
        
        return docs

    def _process_csv(self, content: bytes, filename: str) -> List[Document]:
        # This method is no longer called from extract_content based on the provided edit.
        # Keeping it for completeness if other parts of the system still call it.
        try:
            df = pd.read_csv(io.BytesIO(content))
            text = df.to_string(index=False)
            return [Document(page_content=text, metadata={"file_name": filename, "type": "csv"})]
        except Exception as e:
             print(f"CSV Error: {e}")
             return []

    def transform_to_rows(self, filename: str, docs: List[Document], metadata: Optional[Dict[str, Any]] = None) -> List[KnowledgeRow]:
        rows = []
        rel_parent = metadata.get("relative_parent_dir") if metadata else None
        
        for d in docs:
            rows.append(KnowledgeRow(
                id=d.metadata.get("id", str(uuid.uuid4())), # Use ID from metadata if available (e.g., GNode ID)
                file_id=filename,
                file_type=filename.split(".")[-1], # Assuming this path is primarily for PDF/HTML or determined by caller
                content=d.page_content,
                embedding=d.metadata.get("embedding"),
                html_tag=d.metadata.get("html_tag"),
                page_number=d.metadata.get("page_number"),
                parent_file_id=d.metadata.get("parent_ref"),
                metadata=json.dumps(d.metadata), 
                row_type="chunk",
                relative_parent_dir=rel_parent, # Pass the value
                # Table-specific fields
                is_table_row=d.metadata.get("is_table_row"),
                table_id=d.metadata.get("table_id"),
                row_number=d.metadata.get("row_number"),
                columns=d.metadata.get("columns")
            ))
        return rows

    def ensure_resources(self):
        # Update schema with new fields
        table_ref = f"{PROJECT_ID}.{self.config.dataset_id}.{self.config.table_id}"
        schema = [
            bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
            bigquery.SchemaField("file_id", "STRING"),
            bigquery.SchemaField("file_type", "STRING"),
            bigquery.SchemaField("content", "STRING"),
            bigquery.SchemaField("embedding", "FLOAT64", mode="REPEATED"),
            bigquery.SchemaField("html_tag", "STRING"),     
            bigquery.SchemaField("page_number", "INT64"),   
            bigquery.SchemaField("parent_file_id", "STRING"),
            bigquery.SchemaField("metadata", "JSON"),
            bigquery.SchemaField("ingested_at", "STRING"),
            bigquery.SchemaField("row_type", "STRING"),
            bigquery.SchemaField("relative_parent_dir", "STRING"),
            # Table-specific fields
            bigquery.SchemaField("is_table_row", "BOOL"),
            bigquery.SchemaField("table_id", "STRING"),
            bigquery.SchemaField("row_number", "INT64"),
            bigquery.SchemaField("columns", "JSON")
        ]
        try:
            table = self.bq_client.get_table(table_ref)
            # Schema Evolution: Add missing columns
            existing_fields = {f.name for f in table.schema}
            new_fields = []
            for f in schema:
                if f.name not in existing_fields:
                    new_fields.append(f)
            
            if new_fields:
                print(f"Adding {len(new_fields)} new columns to {table_ref}...")
                new_schema = table.schema[:] # Copy
                new_schema.extend(new_fields)
                table.schema = new_schema
                self.bq_client.update_table(table, ["schema"])
                
        except Exception: # Simplification as NotFound might not be imported
            print(f"Creating table {table_ref}...")
            t = bigquery.Table(table_ref, schema=schema)
            self.bq_client.create_table(t)
            
        # Ensure META table exists too (omitted for brevity)
        # meta_table_ref = f"{PROJECT_ID}.{self.config.dataset_id}.META"
        # meta_schema = [
        #      bigquery.SchemaField("id", "STRING", mode="REQUIRED"),
        #      bigquery.SchemaField("rule_key", "STRING", mode="REQUIRED"),
        #      bigquery.SchemaField("rule_value", "JSON"),
        #      bigquery.SchemaField("created_at", "STRING")
        # ]
        # try:
        #      self.bq_client.get_table(meta_table_ref)
        # except Exception:
        #      print(f"Creating table {meta_table_ref}...")
        #      t = bigquery.Table(meta_table_ref, schema=meta_schema)
        #      self.bq_client.create_table(t)

        # 3. BQML Model
        self._ensure_bqml_model()
        
        # 4. Vector Index (Fixed for search)
        try:
            # We need a BigQueryRAG instance or similar to call create_vector_index
            # ProductionIngestionPipeline has bq_client and PROJECT_ID
            # Let's use a temporary BigQueryRAG instance for this maintenance task
            from bq_handler import BigQueryRAG
            rag = BigQueryRAG(dataset=self.config.dataset_id)
            rag.create_vector_index(table_id=self.config.table_id, column_name="embedding")
        except Exception as e:
            print(f"⚠️ Failed to ensure vector index: {e}")

    def _ensure_bqml_model(self):
        model_name = f"{PROJECT_ID}.{self.config.dataset_id}.{MODEL_ID}"
        try:
            self.bq_client.get_model(model_name)
        except Exception:
            print(f"Checking for BigQuery Connection for Vertex AI...")
            # We check if vertex_ai_conn exists in US location
            # If not found, BQML fails. 
            # We try to create it BEST EFFORT but query time is restricted
            query = f"""
            CREATE MODEL IF NOT EXISTS `{model_name}`
            REMOTE WITH CONNECTION `{PROJECT_ID}.us.vertex_ai_conn`
            OPTIONS(endpoint = 'text-embedding-004');
            """
            print(f"🚀 Creating BQML Model {MODEL_ID} (Optimized Search)...")
            try:
                # Set a 30s timeout for this setup query
                job_config = bigquery.QueryJobConfig(timeout_ms=30000)
                self.bq_client.query(query, job_config=job_config).result()
            except Exception as e:
                print(f"⚠️ BQML Model optimization skipped: {e}")
                print("ℹ️ Pipeline will continue using standard search.")

    def upsert_rows(self, rows: List[KnowledgeRow]) -> int:
        if not rows: return 0
        
        table_ref = f"{PROJECT_ID}.{self.config.dataset_id}.{self.config.table_id}"
        bq_rows = [r.to_bq_dict() for r in rows]
        
        # Batching for Upsert (Limit 200 per user request)
        BATCH_SIZE = 200
        total_batches = (len(bq_rows) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"📦 Upserting {len(bq_rows)} rows in {total_batches} batches...")
        
        inserted_count = 0
        
        for i in range(0, len(bq_rows), BATCH_SIZE):
            batch = bq_rows[i : i + BATCH_SIZE]
            
            # DEBUG PRINTS visible in CLI
            print(f"   Batch {i//BATCH_SIZE + 1}/{total_batches}: {len(batch)} rows")
            
            try:
                errors = self.bq_client.insert_rows_json(table_ref, batch)
                if errors:
                    print(f"BQ Insert Errors (Batch {i}): {errors}")
                else:
                    inserted_count += len(batch)
            except Exception as e:
                print(f"Insert failed (Batch {i}): {e}")
            
        print(f"✅ Upsert complete. {inserted_count}/{len(bq_rows)} rows inserted.")
        return inserted_count

    async def generate_batch_embeddings(self, rows: List[KnowledgeRow], status_callback=None):
        """
        Generates embeddings for a list of rows using Vertex AI in batches.
        """
        if not self.embedding_model:
            return

        texts = [row.content for row in rows]
        # Vertex AI limit for text-embedding-004 is 250 instances per request
        # HOWEVER, there is also a token limit of 20,000 tokens per request.
        # Reducing batch size to 50 to be safe.
        BATCH_SIZE = 50
        all_embeddings = []
        total_batches = (len(texts) + BATCH_SIZE - 1) // BATCH_SIZE

        print(f"🧠 Generating embeddings for {len(texts)} rows in batches of {BATCH_SIZE}...")
        
        for i in range(0, len(texts), BATCH_SIZE):
            batch_num = i // BATCH_SIZE + 1
            batch_texts = texts[i : i + BATCH_SIZE]
            
            # Report progress
            if status_callback:
                await status_callback(f"🧠 Generating embeddings: Batch {batch_num}/{total_batches}...", "embedding")

            try:
                # Local Embedding Call - needs to be awaited if blocking, but Vertex SDK is sync by default
                embeddings = await self.safe_get_embeddings(batch_texts)
                all_embeddings.extend([e.values for e in embeddings])
                print(f"   Processed batch {batch_num}...")
            except Exception as e:
                print(f"❌ Failed to generate embeddings for batch {i}: {e}")
                if status_callback:
                    await status_callback(f"❌ Embedding Error (Batch {batch_num}): {str(e)[:100]}...", "error")
                # Pad with empty lists if error
                all_embeddings.extend([[] for _ in range(len(batch_texts))])

        # Map back to rows
        for row, emb in zip(rows, all_embeddings):
            row.embedding = emb

    async def safe_get_embeddings(self, texts: List[str]):
        """
        Wrapper to handle token limit errors by splitting batches recursively.
        """
        try:
             return await asyncio.to_thread(self.embedding_model.get_embeddings, texts)
        except Exception as e:
             err_str = str(e).lower()
             if "token count" in err_str and len(texts) > 1:
                 # Recursive split
                 mid = len(texts) // 2
                 print(f"⚠️ Token limit hit. Splitting batch of {len(texts)} into {mid} and {len(texts)-mid}...")
                 left = await self.safe_get_embeddings(texts[:mid])
                 right = await self.safe_get_embeddings(texts[mid:])
                 return left + right
             else:
                 raise e



    def generate_missing_embeddings(self):
         pass # Handled in batch

if __name__ == "__main__":
    # Test Run
    pass
