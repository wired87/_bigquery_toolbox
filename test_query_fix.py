import sys
sys.path.insert(0, r"c:\Users\bestb\Desktop\_bigquery_toolbox")

from bq_handler import BQGroundZero

# Create minimal instance
class TestBQ(BQGroundZero):
    def __init__(self):
        self.pid = "test-project"
        self.ds_id = "test_dataset"

bq = TestBQ()

schema = {"id": "STRING", "name": "STRING", "value": "FLOAT64"}
rows = [
    {"id": "1", "name": "test", "value": 10.5},
    {"id": "2", "name": "test2", "value": 20.0}
]

query = bq.upsert_row_query("test_table", rows, schema)

print("Generated Query:")
print("=" * 80)
print(query)
print("=" * 80)

# Check for backslashes
if "\\" in query:
    print("\n❌ ERROR: Backslash found in query!")
    idx = query.find("\\")
    print(f"Context: ...{query[max(0, idx-30):idx+30]}...")
else:
    print("\n✅ SUCCESS: No backslashes in query!")
