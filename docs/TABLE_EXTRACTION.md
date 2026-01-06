# PDF Table Extraction Enhancement

## Overview

The PDF extraction pipeline has been enhanced to properly handle HTML `<table>` elements extracted from PDFs. Each table row is now stored as a separate BigQuery row with its column structure preserved, enabling structured queries on tabular data.

## What's New

### 1. Enhanced Schema

Four new fields have been added to the `KB` table schema:

| Field | Type | Description |
|-------|------|-------------|
| `is_table_row` | BOOL | Flag indicating if this row represents a table row (vs regular content) |
| `table_id` | STRING | Unique identifier linking all rows from the same table |
| `row_number` | INT64 | Sequential position of the row within its table |
| `columns` | JSON | Dictionary mapping column names to cell content |

### 2. Table Processing Logic

When a PDF is processed:

1. **Detection**: The system detects `<table>` HTML elements in the PDF
2. **Header Extraction**: Extracts column headers from `<thead>` or the first `<tr>`
3. **Row Processing**: Each table row (`<tr>`) becomes a separate BigQuery row
4. **Column Mapping**: Cell content is mapped to column names and stored in the `columns` JSON field
5. **Full-Text Content**: Row content is concatenated for embedding and search

### 3. Data Structure Example

For a table like this in a PDF:

```
Name     | Age | Department
---------|-----|------------
John Doe | 30  | Engineering
Jane Smith | 28 | Marketing
```

The system creates 2 BigQuery rows (one per data row):

**Row 1:**
```json
{
  "id": "uuid_row_1",
  "file_id": "report.pdf",
  "content": "Name: John Doe | Age: 30 | Department: Engineering",
  "html_tag": "tr",
  "is_table_row": true,
  "table_id": "abc-123-def",
  "row_number": 1,
  "columns": {
    "Name": "John Doe",
    "Age": "30",
    "Department": "Engineering"
  }
}
```

**Row 2:**
```json
{
  "id": "uuid_row_2",
  "file_id": "report.pdf",
  "content": "Name: Jane Smith | Age: 28 | Department: Marketing",
  "html_tag": "tr",
  "is_table_row": true,
  "table_id": "abc-123-def",
  "row_number": 2,
  "columns": {
    "Name": "Jane Smith",
    "Age": "28",
    "Department": "Marketing"
  }
}
```

## Usage

### Processing PDFs with Tables

No changes needed! Just use the existing ingestion pipeline:

```python
from ingestion_pipeline import ProductionIngestionPipeline, PipelineConfig

# Configure pipeline
config = PipelineConfig(
    dataset_id="IDB",
    table_id="KB",
    chunk_size=200,
    chunk_overlap=50
)

# Initialize
pipeline = ProductionIngestionPipeline(config)

# Process PDF (automatically handles tables)
with open("document.pdf", "rb") as f:
    content = f.read()
    
result = await pipeline.run_pipeline_for_bytes(
    filename="document.pdf",
    content=content
)
```

### Querying Table Data

#### Get All Tables

```sql
SELECT 
  file_id,
  table_id,
  row_number,
  columns,
  content
FROM `PROJECT.DATASET.KB`
WHERE is_table_row = true
ORDER BY table_id, row_number
```

#### Query Specific Table

```sql
SELECT 
  row_number,
  columns,
  content
FROM `PROJECT.DATASET.KB`
WHERE is_table_row = true
  AND table_id = 'your-table-id'
ORDER BY row_number
```

#### Extract Specific Column

```sql
SELECT 
  row_number,
  JSON_VALUE(columns, '$.Name') as name,
  JSON_VALUE(columns, '$.Age') as age,
  JSON_VALUE(columns, '$.Department') as department
FROM `PROJECT.DATASET.KB`
WHERE is_table_row = true
  AND table_id = 'your-table-id'
ORDER BY row_number
```

#### Search Within Tables

```sql
SELECT 
  file_id,
  table_id,
  row_number,
  columns
FROM `PROJECT.DATASET.KB`
WHERE is_table_row = true
  AND content LIKE '%Engineering%'
ORDER BY table_id, row_number
```

#### Aggregate Table Data

```sql
SELECT 
  table_id,
  COUNT(*) as row_count,
  ARRAY_AGG(DISTINCT JSON_VALUE(columns, '$.Department')) as departments
FROM `PROJECT.DATASET.KB`
WHERE is_table_row = true
GROUP BY table_id
```

### Python API

```python
from bq_handler import BigQueryRAG

rag = BigQueryRAG(dataset="IDB")

# Get all table rows from a specific file
query = """
SELECT * FROM `IDB.KB`
WHERE is_table_row = true 
  AND file_id = 'document.pdf'
ORDER BY table_id, row_number
"""

results = rag.run_query(query)

for row in results:
    print(f"Row {row['row_number']}: {row['columns']}")
```

## Technical Details

### Files Modified

1. **`ingestion_pipeline.py`**
   - Updated `KnowledgeRow` schema with table fields
   - Modified `_process_pdf_html()` to detect and route table elements
   - Added `_process_table_element()` method for table processing
   - Updated `transform_to_rows()` to preserve table metadata
   - Updated `ensure_resources()` to include new schema fields

### Key Methods

#### `_process_table_element(table_tag, filename, parent_id)`

Processes a single HTML table element:
- Extracts column headers from `<thead>` or first row
- Iterates through table rows (`<tr>`)
- Maps cell content to column names
- Creates Document objects with table metadata

**Parameters:**
- `table_tag`: BeautifulSoup Tag object for the `<table>`
- `filename`: Source PDF filename
- `parent_id`: Parent node ID from the graph structure

**Returns:**
- List of Document objects, one per table row

### Edge Cases Handled

1. **No Headers**: Uses generic names `col_1`, `col_2`, etc.
2. **Irregular Tables**: Handles varying column counts per row
3. **Empty Rows**: Skips rows with no content
4. **Nested Tables**: Processes top-level table only (prevents duplication)
5. **Mixed Content**: Tables and regular content coexist properly

## Testing

Use the provided test script:

```bash
python test_table_extraction.py
```

This will:
- Show table statistics (total tables, rows, files)
- Display table content with proper formatting
- Demonstrate search capabilities

## Migration

Existing data is **not affected**. The new fields are optional and will be:
- `NULL` for non-table rows
- Populated automatically for new PDFs with tables

To reprocess existing PDFs with tables:
1. Re-upload the PDF files through the ingestion pipeline
2. Use `mode="o"` (overwrite) or delete old entries first

## Performance Notes

- **Table Detection**: Minimal overhead (~5ms per document)
- **Storage**: JSON column adds ~100-500 bytes per table row
- **Indexing**: The `columns` JSON field is queryable but not indexed by default
- **Search**: Both `content` (full-text) and `columns` (structured) are available

## Future Enhancements

Potential improvements:
1. **Column Type Detection**: Infer numeric/date types from cell content
2. **Table Captions**: Extract and store table titles/captions
3. **Multi-page Tables**: Link table rows spanning multiple PDF pages
4. **Cell Formatting**: Preserve bold/italic/color from original table
5. **Merged Cells**: Handle colspan/rowspan attributes

## Example Queries

See `test_table_extraction.py` for more examples.
