# Enhanced BigQuery Vector Search Implementation

## Overview
This document describes the enhanced question-answer process implemented in the BigQuery Toolbox CLI that leverages embeddings and similarity search with comprehensive debug logging.

## Key Features Implemented

### 1. **Automatic Embedding Generation**
- **Location**: `generate_embeddings_client()` function in `cli.py`
- **Functionality**:
  - Automatically checks and creates an `embed` column (ARRAY<FLOAT64>) in the target table
  - Queries for rows without embeddings (WHERE embed IS NULL)
  - Uses Vertex AI's `text-embedding-004` model for client-side embedding generation
  - Processes rows in batches of 5 to respect rate limits
  - Updates BigQuery table with generated embeddings via upsert
  - Verifies successful embedding creation

- **Debug Messages**:
  - Column existence check
  - Query execution details
  - Model loading status
  - Batch processing progress (X/Y batches)
  - Sample text preview
  - Individual row processing (ID, vector dimension)
  - Verification count

### 2. **LLM-Powered Query Generation**
- **Location**: `generate_search_queries()` function in `cli.py`
- **Functionality**:
  - Takes user input and generates 3 diverse search queries
  - Uses Gemini model to create queries from different angles
  - Maximizes coverage for similarity search
  - Falls back to original query if generation fails

- **Debug Messages**:
  - Number of queries being generated
  - Original user input
  - Generated queries list
  - Fallback notification if generation fails

### 3. **Multi-Query Vector Search**
- **Location**: Enhanced `vector_search` tool in `handle_tool_call()` function
- **Workflow**:
  1. **Query Generation**: Generate 3 search queries using LLM
  2. **Embedding Creation**: Create embeddings for each query using text-embedding-004
  3. **Similarity Search**: Execute BigQuery vector search for each query
  4. **Result Aggregation**: Collect unique results across all queries
  5. **Ranking**: Sort by cosine distance and select top 5 results
  6. **Rendering**: Display results in a formatted Rich table

- **Debug Messages**:
  - Search initialization (table name, limit)
  - Query generation progress
  - List of generated queries
  - Model loading status
  - Per-query execution:
    - Query text
    - Embedding generation (dimension)
    - BigQuery search execution
    - Number of results retrieved
    - New unique results added
  - Final sorting and filtering
  - Total results selected

### 4. **Rich Console Table Rendering**
- **Location**: `vector_search` tool result rendering
- **Features**:
  - Displays top N results in a formatted table
  - Color-coded columns (cyan for data, yellow for distance)
  - Automatic truncation of long text (100 chars + "...")
  - Distance values formatted to 4 decimal places
  - Clear visual separation with headers

### 5. **Comprehensive Debug Logging**
All major operations include debug messages:
- 🔧 Configuration/setup operations
- 🔍 Query/search operations
- 🤖 Model loading
- 📦 Batch processing
- 💾 Database operations
- ✓ Success confirmations
- ❌ Error notifications
- 📊 Statistics and counts

## Usage Flow

### Initial Setup (Automatic)
```
1. User starts CLI: python cli.py
2. System prompts for table name (default: "knowledge_base")
3. System scans data_dir/ for files (.csv, .xlsx, .json, .jsonl)
4. System ingests data into BigQuery table
5. System generates embeddings for all rows without them
```

### Question-Answer Process
```
User Input: "What is machine learning?"
    ↓
1. Intent Classification
   - Classifies as VECTOR_SEARCH, SQL_QUERY, or GENERAL_CHAT
    ↓
2. LLM Query Generation (if vector search)
   - Generates 3 diverse queries:
     * "What is machine learning?"
     * "Define machine learning concepts"
     * "Explain ML fundamentals"
    ↓
3. Embedding Generation (for each query)
   - Uses text-embedding-004
   - Creates 768-dimensional vectors
    ↓
4. BigQuery Vector Search (for each query)
   - Executes COSINE_DISTANCE search
   - Retrieves top 5 results per query
    ↓
5. Result Aggregation
   - Deduplicates results across queries
   - Sorts by distance (lowest = most similar)
   - Selects top 5 overall
    ↓
6. Console Rendering
   - Displays results in Rich table format
   - Shows all columns + distance scores
    ↓
7. AI Synthesis
   - LLM formulates answer based on results
   - Streams response to terminal
```

## Technical Details

### BigQuery Integration
- **Vector Search**: Uses `COSINE_DISTANCE()` function
- **Embedding Storage**: ARRAY<FLOAT64> column type
- **Client-Side Embeddings**: Vertex AI SDK (no remote model needed)
- **Upsert Support**: MERGE queries for efficient updates

### Models Used
- **Embedding Model**: `text-embedding-004` (768 dimensions)
- **Chat Model**: `gemini-2.5-pro` (configurable)
- **Query Generator**: Same as chat model (reused)

### Performance Optimizations
- Batch processing (5 rows per batch for embeddings)
- Deduplication of search results
- Efficient MERGE queries for upserts
- Async operations for LLM calls

## Example Debug Output

```
🧠 Starting embedding generation for table 'knowledge_base'...
🔧 DEBUG: Ensuring 'embed' column exists in 'knowledge_base'...
✓ DEBUG: 'embed' column check complete
🔍 DEBUG: Querying rows without embeddings...
  Query: SELECT id, content FROM `project.IDB.knowledge_base` WHERE embed IS NULL AND content IS NOT NULL
📊 Found 10 rows needing embeddings
🤖 DEBUG: Loading text-embedding-004 model from Vertex AI...
✓ DEBUG: Model loaded successfully
⚙️  Processing 10 rows in 2 batches (batch size: 5)...
  📦 Batch 1/2: Generating embeddings for 5 rows...
    DEBUG: Sample text (first 100 chars): Machine learning is a subset of artificial intelligence...
    DEBUG: Received 5 embeddings
    DEBUG: Row 1/5 - ID: 001, Vector dim: 768
    ✓ Batch 1/2 completed (5 embeddings generated)

🔍 Starting Enhanced Vector Search
📊 DEBUG: Table: 'knowledge_base', Limit: 5
🔍 DEBUG: Generating 3 search queries for: 'What is machine learning?'
✓ DEBUG: Generated 3 queries: ['What is machine learning?', 'Define machine learning', 'Explain ML']
📝 Generated 3 search queries:
  1. What is machine learning?
  2. Define machine learning
  3. Explain ML
🤖 DEBUG: Loading text-embedding-004 model...
✓ DEBUG: Model loaded successfully
🔎 Query 1/3: Performing similarity search...
  Query text: 'What is machine learning?'
  🧠 DEBUG: Generating embedding...
  ✓ DEBUG: Embedding generated (dimension: 768)
  💾 DEBUG: Executing BigQuery vector search...
  ✓ DEBUG: Retrieved 5 results
  ✓ Query 1 complete: 5 new unique results added
...
✅ Vector search complete: 5 top results selected

📋 Top 5 Results:
┏━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━┓
┃ id  ┃ content                                                                                      ┃ distance ┃
┡━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━┩
│ 001 │ Machine learning is a subset of artificial intelligence that enables systems to learn...   │ 0.0234   │
│ 002 │ ML algorithms can be supervised, unsupervised, or reinforcement learning...                │ 0.0456   │
└─────┴──────────────────────────────────────────────────────────────────────────────────────────────┴──────────┘
```

## Configuration

### Constants (in cli.py)
- `DEFAULT_DATASET_ID = "IDB"` - BigQuery dataset
- `DEFAULT_MODEL_NAME = "gemini-2.5-pro"` - LLM model
- `DATA_DIR = "./data_dir"` - Data ingestion directory

### Adjustable Parameters
- Number of search queries: `num_queries=3` in `generate_search_queries()`
- Embedding batch size: `batch_size=5` in `generate_embeddings_client()`
- Search result limit: `limit=5` (default) in vector_search tool
- Text truncation: `100` characters in table rendering

## Error Handling
- Graceful fallback if query generation fails
- Retry logic for embedding batch failures (1s backoff)
- Comprehensive error messages with DEBUG prefix
- Exception catching at all tool levels

## Future Enhancements
- Configurable number of search queries
- Parallel embedding generation
- Caching of embeddings
- Support for multiple embedding models
- Advanced result ranking (beyond distance)
- Result filtering by metadata
