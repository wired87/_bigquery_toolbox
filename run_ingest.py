from engine import CoreEngine
import logging

# Setup logging to console for demonstration
logging.basicConfig(level=logging.INFO)

def main():
    print("🚀 Starting Ingestion Run...")
    try:
        engine = CoreEngine()
        engine.ingest_data("nodes")
        print("✅ Run finished successfully.")
    except Exception as e:
        print(f"❌ Run failed: {e}")

if __name__ == "__main__":
    main()
