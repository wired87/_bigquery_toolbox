import os
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Optional

# Google Cloud
from google.cloud import bigquery
import vertexai
from vertexai.language_models import TextEmbeddingModel
from langchain_core.documents import Document

# KnowledgeRow is defined locally as PipelineRow below.
from pydantic import BaseModel, Field
import uuid

# aDefine a local Schema for Pipeline Row to match BQ Schema
class PipelineRow(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    file_id: str
    file_type: str
    content: str
    embedding: Optional[List[float]] = None
    metadata: str
    ingested_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    parent_file_id: Optional[str] = None
    row_type: str = "chunk" 
    html_tag: Optional[str] = None
    page_number: Optional[int] = None
    relative_parent_dir: Optional[str] = None
    edge_ids: List[str] = Field(default_factory=list)
    is_table_row: Optional[bool] = None
    table_id: Optional[str] = None
    row_number: Optional[int] = None
    columns: Optional[Dict[str, str]] = None
    category: Optional[str] = None
    
    def to_bq_dict(self):
         data = self.model_dump()
         if data.get("embedding") is None:
             data["embedding"] = []
         return data

from .base_pipeline import BasePipeline
from ..processor.pdf_processor import PdfProcessor
from .set_category import CategoryHandler
# We need to access BQ and Vertex services. 
# In a clean architecture, these should be injected.

class ProductionPipeline(BasePipeline):
    def __init__(self, config: Dict[str, Any], bq_client=None, embedding_model=None):
        super().__init__(config)
        self.bq_client = bq_client
        self.embedding_model = embedding_model
        self.category_handler = None
        
        # Self-initialize Vertex AI if client provided but model missing
        if self.bq_client:
            try:
                project_id = self.bq_client.project
                vertexai.init(project=project_id, location="us-central1")
                
                if not self.embedding_model:
                    self.embedding_model = TextEmbeddingModel.from_pretrained("text-embedding-004")
                    print("✅ Vertex AI Embedding Model (text-embedding-004) initialized.")
                
                self.category_handler = CategoryHandler(project_id)
            except Exception as e:
                print(f"⚠️  Failed to init Vertex AI: {e}")
        
        self.processor = PdfProcessor() # Default to PDF for this specific pipeline variant

    async def run_pipeline(self, filename: str, content: bytes, metadata: Optional[Dict[str, Any]] = None, status_callback=None):
        start_time = datetime.now()
        async def report(msg, step=None):
             if status_callback: await status_callback(msg, step)

        if not self.bq_client:
             return "Failed: BigQuery client missing."

        try:
            # 0. Ensure Resources (Schema, Models, Indices)
            await report(f"🛠️ Verifying resources for {filename}...")
            await self.ensure_resources_safe()

            # 1. Extraction (Delegated to Processor)
            await report(f"📑 Extracting content from {filename}...")
            # Detect type and select processor (Logic could be in a Factory, but keeping simple here)
            # The ProductionIngestionPipeline handled multiple types.
            
            # Using the Facade logic locally or delegating? 
            # The Request was to "distribute... to specific processors".
            # So here we use PdfProcessor for PDF, etc.
            
            row_type_map = {} # To map processor output to PipelineRow
            
            raw_docs = []
            if filename.lower().endswith(".pdf"):
                raw_docs = self.processor.process_bytes(filename, content, category="Document")
            elif filename.lower().endswith(".txt"):
                # Handle text files directly
                text_content = content.decode("utf-8", errors="replace")
                # Create a single document chunk (simple ingestion)
                raw_docs = [Document(page_content=text_content, metadata={"file_name": filename, "type": "txt"})]
            
            # Resolve structural edges (Hierarchy, Tables)
            if raw_docs:
                raw_docs = self.processor.resolve_edges(raw_docs)

            # Add other processors here if needed, or inject a "ProcessorFacade"
            
            if not raw_docs:
                return "No content extracted (Unsupported file type)."

            # 1.5 Generate Category
            await report(f"🏷️ Generating category for {filename}...")
            # Use the first chunk's content as a snippet
            snippet = raw_docs[0].page_content if raw_docs else ""
            category = "Uncategorized"
            if self.category_handler:
                category = await self.category_handler.generate_category(filename, snippet)
            await report(f"🏷️ Category assigned: {category}")

            # 2. Transformation to PipelineRow (Standardization)
            rows = []
            rel_parent = metadata.get("relative_parent_dir") if metadata else None
            
            for d in raw_docs:
                rows.append(PipelineRow(
                    id=d.metadata.get("id", str(uuid.uuid4())),
                    file_id=filename,
                    file_type=filename.split(".")[-1],
                    content=d.page_content,
                    embedding=d.metadata.get("embedding"),
                    html_tag=d.metadata.get("html_tag"),
                    page_number=d.metadata.get("page_number"),
                    parent_file_id=d.metadata.get("parent_ref"),
                    metadata=d.metadata.get("metadata_json", "{}"), # Processor might not JSON dump
                    row_type="chunk",
                    relative_parent_dir=rel_parent,
                    is_table_row=d.metadata.get("is_table_row"),
                    table_id=d.metadata.get("table_id"),
                    row_number=d.metadata.get("row_number"),
                    columns=d.metadata.get("columns"),
                    category=category
                ))

            # 3. Embedding Generation
            if self.embedding_model:
                await report(f"🧠 Generating embeddings for {len(rows)} chunks...")
                await self._generate_embeddings(rows, status_callback=report) # Internal optimized method
            
            # 4. Semantic Linking (Delegated to Base)
            await report(f"🕸️ Linking {len(rows)} nodes...")
            self.calculate_semantic_edges(rows)

            # 5. Upsert
            await report(f"💾 Upserting {len(rows)} rows...")
            count = await self._upsert_rows(rows)

            return f"Processed {filename}: Ingested {count} rows. Category: {category}"

        except Exception as e:
            await report(f"❌ Error: {e}")
            raise e

    async def _generate_embeddings(self, rows: List[PipelineRow], status_callback=None):
        if not self.embedding_model: return
        
        texts = [r.content for r in rows]
        # Optimized parallel batching logic (Ported from recent fix)
        BATCH_SIZE = 20
        sem = asyncio.Semaphore(15)
        
        all_embeddings = [None] * len(texts)

        async def process_batch(start_idx, batch_texts):
             async with sem:
                try:
                    embeddings = await asyncio.to_thread(self.embedding_model.get_embeddings, batch_texts)
                    return start_idx, [e.values for e in embeddings]
                except Exception as e:
                    # Recursive retry logic or error handling
                    print(f"Batch failed: {e}")
                    return start_idx, [[] for _ in batch_texts]

        tasks = []
        for i in range(0, len(texts), BATCH_SIZE):
            tasks.append(process_batch(i, texts[i:i+BATCH_SIZE]))
        
        results = await asyncio.gather(*tasks)
        
        for start_idx, embs in results:
            for i, emb in enumerate(embs):
                if start_idx + i < len(all_embeddings):
                    all_embeddings[start_idx + i] = emb

        for row, emb in zip(rows, all_embeddings):
            if emb: row.embedding = emb

    async def _upsert_rows(self, rows: List[PipelineRow]) -> int:
        table_id = self.config.get("table_ref")
        bq_rows = [r.to_bq_dict() for r in rows]
        
        BATCH_SIZE = 500
        total_inserted = 0
        
        async def insert(batch):
            errors = await asyncio.to_thread(self.bq_client.insert_rows_json, table_id, batch)
            return len(batch) if not errors else 0

        tasks = []
        for i in range(0, len(bq_rows), BATCH_SIZE):
            tasks.append(insert(bq_rows[i:i+BATCH_SIZE]))

        results = await asyncio.gather(*tasks)
        return sum(results)

    async def ensure_resources_safe(self):
         try:
             await asyncio.to_thread(self.ensure_resources)
         except Exception as e:
             print(f"Schema check warn: {e}")

    def ensure_resources(self):
        project_id = self.bq_client.project
        dataset_id = self.config.get("dataset_id", "IDB")
        table_id = self.config.get("table_id", "KB")
        
        # 1. Ensure Table Schema
        table_ref = f"{project_id}.{dataset_id}.{table_id}"
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
            bigquery.SchemaField("edge_ids", "STRING", mode="REPEATED"),
            # Table-specific fields
            bigquery.SchemaField("is_table_row", "BOOL"),
            bigquery.SchemaField("table_id", "STRING"),
            bigquery.SchemaField("row_number", "INT64"),
            bigquery.SchemaField("columns", "JSON"),
            bigquery.SchemaField("category", "STRING")
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
                
        except Exception: 
            print(f"Creating table {table_ref}...")
            t = bigquery.Table(table_ref, schema=schema)
            self.bq_client.create_table(t)

        # 2. BQML Model
        self._ensure_bqml_model(project_id, dataset_id)
        
        # 3. Vector Index
        self._ensure_vector_index(dataset_id, table_id)

    def _ensure_bqml_model(self, project_id, dataset_id):
        # Using a fixed ID for the embedding model as per legacy logic
        MODEL_ID = "embedding_model" 
        model_name = f"{project_id}.{dataset_id}.{MODEL_ID}"
        try:
            self.bq_client.get_model(model_name)
        except Exception:
            print(f"Checking for BigQuery Connection for Vertex AI...")
            query = f"""
            CREATE MODEL IF NOT EXISTS `{model_name}`
            REMOTE WITH CONNECTION `{project_id}.us.vertex_ai_conn`
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

    def _ensure_vector_index(self, dataset_id, table_id):
        try:
            # Use local import to avoid circular dependency
            from bq_handler import BigQueryRAG
            rag = BigQueryRAG(dataset=dataset_id)
            rag.create_vector_index(table_id=table_id, column_name="embedding")
        except Exception as e:
            print(f"⚠️ Failed to ensure vector index: {e}")
