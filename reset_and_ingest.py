from engine import CoreEngine
import logging
from google.cloud import bigquery

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    print("🚀 Starting Clean Ingestion Run...")
    engine = CoreEngine()
    
    # 1. Drop existing 'nodes' table to apply new Schema
    bq_client = bigquery.Client()
    table_id = "nodes"
    table_ref = f"{engine.project_id}.{engine.current_dataset_id}.{table_id}"
    
    try:
        bq_client.delete_table(table_ref)
        print(f"✅ Dropped old table {table_ref}")
    except Exception:
        print(f"ℹ️ Table {table_ref} did not exist or could not be dropped.")

    # 2. Run Ingestion
    try:
        engine.ingest_data(table_id)
        print("✅ Ingestion finished successfully.")
    except Exception as e:
        print(f"❌ Ingestion failed: {e}")

if __name__ == "__main__":
    main()
