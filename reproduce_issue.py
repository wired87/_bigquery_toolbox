import json
from unittest.mock import MagicMock
from bq_handler import BQCore

# Mock BQCore to avoid API calls
class MockBQCore(BQCore):
    def __init__(self):
        self.pid = "test-project"
        self.ds_id = "test_dataset"
        self.bqclient = MagicMock()

def test_query_generation():
    bq = MockBQCore()
    
    # Schema mimicking the user's data
    schema = {
        "id": "STRING",
        "slug": "STRING",
        "title": "STRING",
        "imgs": "STRING", # Note: Schema says STRING, but data might be list-like string
        "brand": "STRING",
        "category": "STRING",
        "vendor": "STRING",
        "used": "STRING",
        "address": "STRING",
        "availability": "STRING",
        "currency": "STRING",
        "original_price": "FLOAT64",
        "discounted_price": "FLOAT64",
        "specifications": "STRING",
        "description": "STRING",
        "delivery_fee": "FLOAT64",
        "delivery_details": "STRING",
        "warranty": "STRING",
        "warranty_type": "STRING",
        "average_rating": "FLOAT64",
        "num_ratings": "FLOAT64",
        "reviews": "STRING",
        "content": "STRING",
        "embed": "FLOAT64" # Wait, embed should be ARRAY<FLOAT64> usually?
    }
    
    # Sample row mimicking the user's data
    row = {
        "id": "800",
        "slug": "https://priceoye.pk/wireless-earbuds/realme/realme-buds-wireless",
        "title": "Realme Buds Wireless",
        "imgs": "['https://images.priceoye.pk/realme-buds-wireless-pakistan-priceoye-0bavl-270x270.webp']",
        "brand": "Realme",
        "category": "Earbuds",
        "vendor": "PriceOye",
        "used": "0",
        "address": None,
        "currency": "PKR",
        "original_price": 6999.0,
        "discounted_price": 4999.0,
        "specifications": "{'Model': 'Wireless'}",
        "description": "Some description with \"quotes\" and \n newlines and \\ backslashes",
        "delivery_fee": 0.0,
        "delivery_details": None,
        "warranty": "1 year",
        "warranty_type": "Brand Warranty",
        "average_rating": 4.5,
        "num_ratings": 10.0,
        "reviews": "[]",
        "content": "Search content",
        "embed": None
    }
    
    print("Generating query...")
    query = bq.upsert_row_query("hi", [row], schema)
    
    print("\n--- Generated Query (Split) ---")
    lines = query.split('\n')
    for i, line in enumerate(lines):
        print(f"{i+1}: {line}")
    
    print("\n-----------------------")

if __name__ == "__main__":
    test_query_generation()
