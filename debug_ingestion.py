
import asyncio
import os
from ingestion_pipeline import ProductionIngestionPipeline, PipelineConfig
import logging

# Configure Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')
logger = logging.getLogger("DeepDebug")

async def run_pipeline_debug(dataset_id: str, file_path: str):
    print("="*60)
    print(f"🔧 Starting In-Depth Debug of Ingestion Pipeline for: {file_path}")
    print("="*60)
    
    # Check File
    if not os.path.exists(file_path):
        logger.error(f"File not found: {file_path}")
        return

    with open(file_path, "rb") as f:
        content = f.read()

    # 1. Config Init
    logger.info("Step 1: Initializing Pipeline & Config")
    config = PipelineConfig(
        dataset_id=dataset_id,
        table_id="KB",
        use_docai=True,
        chunk_size=1000,
        chunk_overlap=200
    )
    pipeline = ProductionIngestionPipeline(config)
    print(f"   Configs: {config.model_dump()}")

    # 2. Resource Verification
    logger.info("Step 2: Resource Verification (Dataset, KB Table, META Table, BQML)")
    try:
        pipeline.ensure_resources()
        print("   ✅ Resources verified/created successfully.")
    except Exception as e:
        logger.error(f"   ❌ Resource verification failed: {e}")
        return

    # 3. Extraction
    logger.info("Step 3: Content Extraction (In-Memory)")
    try:
        docs = await pipeline.extract_content(os.path.basename(file_path), content)
        print(f"   ✅ Extracted {len(docs)} document elements.")
        if docs:
            print(f"   📄 Sample content (first 200 chars): {docs[0].page_content[:200]}...")
    except Exception as e:
        logger.error(f"   ❌ Extraction failed: {e}")
        return

    # 4. Transformation
    logger.info("Step 4: Transformation & Chunking")
    try:
        rows = pipeline.transform_to_rows(os.path.basename(file_path), docs)
        print(f"   ✅ Generated {len(rows)} KnowledgeRows.")
        
        full_doc_rows = [r for r in rows if r.row_type == 'full_doc']
        chunk_rows = [r for r in rows if r.row_type == 'chunk']
        
        print(f"   📄 Full Doc Rows: {len(full_doc_rows)}")
        print(f"   🧩 Chunk Rows: {len(chunk_rows)}")
        
        if chunk_rows:
            print(f"   🔗 Sample Chunk Parent Ref: {chunk_rows[0].parent_file_id}")
            
    except Exception as e:
        logger.error(f"   ❌ Transformation failed: {e}")
        return

    # 5. Upsert
    logger.info("Step 5: BigQuery Upsert (Idempotent MERGE)")
    try:
        count = pipeline.upsert_rows(rows)
        print(f"   ✅ Upserted {count} rows to {pipeline.config.dataset_id}.KB")
    except Exception as e:
        logger.error(f"   ❌ Upsert failed: {e}")
        return

    # 6. Embedding
    logger.info("Step 6: Automated Embedding Generation (BQML)")
    try:
        pipeline.generate_missing_embeddings()
        print("   ✅ Embedding generation query trigger successfully.")
    except Exception as e:
        logger.error(f"   ❌ Embedding generation failed: {e}")
        return
        
    print("="*60)
    print("✅✅ Deep Debug Complete: All Core Functionalities Validated.")
    print("="*60)

if __name__ == "__main__":
    # USER CONFIG
    TEST_DATASET_ID = "test_debug"
    # Create a dummy PDF if possible, or use one if exists. 
    # Since we can't easily creating a valid PDF binary with echo, let's assume one exists or fail gracefully.
    # Actually, we can try to use a real PDF if the user has one, or just skip if not.
    # But wait, we need to verify the *HTML* extraction. 
    # Let's try to locate ANY pdf in the directory.
    
    preferred_test = "test_graph_pdf.pdf"
    if os.path.exists(preferred_test):
         TEST_FILE = preferred_test
    else:
        pdf_files = [f for f in os.listdir(".") if f.lower().endswith(".pdf")]
        if pdf_files:
            TEST_FILE = pdf_files[0]
        else:
            print("No PDF found for testing graph extraction. Please provide a PDF.")
            # Fallback to requirements.txt for non-graph test? No, user wants to verify graph.
            # We will try to create a dummy PDF using reportlab if available, or just warn.
            TEST_FILE = "dummy_test.pdf"
            try:
                from reportlab.pdfgen import canvas
                c = canvas.Canvas(TEST_FILE)
                for i in range(5):
                    c.drawString(100, 750, f"Hello World {i}")
                    c.drawString(100, 700, "<p>This is a paragraph</p>")
                c.save()
            except ImportError:
                print("Reportlab not installed, cannot create dummy PDF. Please provide a PDF.")

    if os.path.exists(TEST_FILE):
        asyncio.run(run_pipeline_debug(TEST_DATASET_ID, TEST_FILE))
    else:
        print("Skipping debug run as no PDF file found.")
