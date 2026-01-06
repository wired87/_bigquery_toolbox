"""
Test script for table extraction from PDF files.

This script demonstrates how to query the BigQuery KB table
to retrieve table rows with their column structure.
"""

from bq_handler import BigQueryRAG

def test_table_extraction():
    """
    Query the KB table to retrieve and display table rows.
    """
    rag = BigQueryRAG(dataset="IDB")
    
    # Query 1: Get all table rows
    query = """
    SELECT 
        file_id,
        table_id,
        row_number,
        html_tag,
        columns,
        content,
        parent_file_id,
        ingested_at
    FROM `aixr-401704.IDB.KB`
    WHERE is_table_row = true
    ORDER BY table_id, row_number
    LIMIT 100
    """
    
    print("🔍 Querying table rows from BigQuery...\n")
    results = rag.run_query(query)
    
    if not results:
        print("⚠️ No table rows found yet. Process a PDF with tables first.")
        return
    
    # Display results
    current_table = None
    for row in results:
        # Print table header when we encounter a new table
        if row['table_id'] != current_table:
            current_table = row['table_id']
            print(f"\n{'='*80}")
            print(f"📊 TABLE: {row['file_id']}")
            print(f"   Table ID: {row['table_id']}")
            print(f"{'='*80}\n")
            
            # Print column headers if available
            if row.get('columns'):
                headers = list(row['columns'].keys())
                print(f"Columns: {' | '.join(headers)}\n")
        
        # Print row data
        print(f"Row {row['row_number']}:")
        if row.get('columns'):
            for col_name, col_value in row['columns'].items():
                print(f"  - {col_name}: {col_value}")
        else:
            print(f"  Content: {row['content']}")
        print()

def test_table_search():
    """
    Test vector search on table content.
    """
    rag = BigQueryRAG(dataset="IDB")
    
    # Example: Search for specific content in tables
    search_query = "revenue"  # Modify this based on your data
    
    print(f"\n🔎 Searching for '{search_query}' in table rows...\n")
    
    query = f"""
    SELECT 
        file_id,
        table_id,
        row_number,
        columns,
        content
    FROM `aixr-401704.IDB.KB`
    WHERE is_table_row = true
      AND LOWER(content) LIKE '%{search_query.lower()}%'
    ORDER BY table_id, row_number
    LIMIT 20
    """
    
    results = rag.run_query(query)
    
    if not results:
        print(f"⚠️ No results found for '{search_query}'")
        return
    
    for row in results:
        print(f"📄 File: {row['file_id']}")
        print(f"   Row {row['row_number']}: {row['content']}")
        if row.get('columns'):
            print(f"   Columns: {row['columns']}")
        print()

def get_table_stats():
    """
    Get statistics about tables in the knowledge base.
    """
    rag = BigQueryRAG(dataset="IDB")
    
    query = """
    SELECT 
        COUNT(*) as total_table_rows,
        COUNT(DISTINCT table_id) as total_tables,
        COUNT(DISTINCT file_id) as total_files_with_tables
    FROM `aixr-401704.IDB.KB`
    WHERE is_table_row = true
    """
    
    print("\n📊 Table Statistics:\n")
    results = rag.run_query(query)
    
    if results:
        stats = results[0]
        print(f"Total Table Rows: {stats['total_table_rows']}")
        print(f"Total Tables: {stats['total_tables']}")
        print(f"Files with Tables: {stats['total_files_with_tables']}")

if __name__ == "__main__":
    print("🚀 PDF Table Extraction Test Suite\n")
    print("="*80)
    
    # Run tests
    get_table_stats()
    test_table_extraction()
    # test_table_search()  # Uncomment to test search
    
    print("\n✅ Test complete!")
