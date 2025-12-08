import os
import json
from bq_handler import BQCore

# Set credentials if needed (assuming they are in current dir)
if os.path.exists("credentials.json"):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = os.path.abspath("credentials.json")

def test_upsert():
    print("--- Starting Debug Script ---")
    try:
        bq = BQCore(dataset_id="IDB")
        print("BQCore initialized")
        
        table_name = "debug_test_table"
        
        # Test data with various types to exercise the fix
        rows = [
            {"id": "1", "name": "Test 1", "active": True, "score": 10.5, "tags": ["a", "b"], "meta": {"key": "value"}},
            {"id": "2", "name": "Test 2", "active": False, "score": 20.0, "tags": [], "meta": None},
            {"id": "3", "name": "Test 3", "active": None, "score": None, "tags": ["c"], "meta": {"nested": [1, 2]}}
        ]
        
        print(f"Upserting {len(rows)} rows to {table_name}...")
        bq.bq_insert(table_id=table_name, rows=rows, upsert=True)
        print("Upsert call finished")
        
    except Exception as e:
        print(f"Caught exception: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_upsert()
