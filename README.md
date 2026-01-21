# BigQuery Toolbox 🚀

A powerful Python-based toolbox for intelligent BigQuery data management with AI-powered search, automated data ingestion, and advanced SQL generation capabilities.

## DEMO 
### **(do not use in prod)**
https://bigquerytoolbox.streamlit.app/

Now featuring **Local Core** mode with direct Streamlit-to-Engine integration, eliminating the need for a separate WebSocket server.

## 🌟 Key Features

### 1. **Intelligent RAG & Search**
- **Vector Search**: Semantic search over unstructured data (PDFs, HTML) using Vertex AI Embeddings (`text-embedding-004`).
- **Hybrid Search**: Combines keyword search with vector similarity for precise retrieval.
- **Source Citations**: AI responses cite specific files and HTML tags/sections where information was found.

### 2. **AI-Powered Analytics (Text-to-SQL)**
- **Natural Language SQL**: Ask questions like "How many invoices were processed last month?" or "List the top 5 products".
- **BigQuery Dialect**: Generates valid BigQuery Standard SQL with `REPEATED` field handling (UNNEST).
- **Metadata Awareness**: The AI is aware of table schemas (column names, types, descriptions) and table statistics (row counts) for optimized query generation.
- **Traceability**: See the generated SQL, the raw result set, and the AI's interpretation.

### 3. **Smart Data Ingestion**
- **Document Processing**: Supports PDFs and HTML table parsing.
    - **DocAI Integration**: (Optional) Use Google Document AI for advanced OCR.
    - **PDF Parsing**: Robust extraction of text and tables, preserving column structure.
- **Chunking**: Intelligent content chunking with overlap for better context retention.
- **Graph Upload**: NetworkX graph conversion to BigQuery Node/Edge tables.
- **CSV/JSON**: Automated schema inference and batch upload with recursive retry logic for reliability.

### 4. **Modern UI/UX**
- **High Contrast Theme**: Clean, professional "Black & White" design for maximum readability.
- **Voice Interaction**: 
    - **Speech-to-Text**: Dictate your queries.
    - **Text-to-Speech**: Listen to AI responses.
- **Workflow Modes**: Manually override AI intent classification (SQL Only, Vector Only, Ingest Only) for testing or specific tasks.

### 5. **Robust Backend**
- **User Segregation**: Each user gets their own BigQuery dataset (derived from email) for complete data isolation.
- **Security**: Authentication via email/password (stored as hashed labels on datasets).
- **Error Recovery**: Automatic retries, batch splitting for large uploads, and graceful degradation if AI services are unavailable.

## 🚀 Getting Started

### Prerequisites

- Python 3.10+
- Google Cloud Project with the following APIs enabled:
    - BigQuery API
    - Vertex AI API (for Embeddings and Gemini)
    - (Optional) Document AI API

### Installation

1. **Clone and Install**
   ```bash
   git clone https://github.com/wired87/_bigquery_toolbox.git
   cd _bigquery_toolbox
   python -m venv venv
   source venv/bin/activate  # On Windows: .\venv\Scripts\activate
   pip install -r requirements.txt
   ```

2. **Credentials**
   - Place your Google Cloud Service Account JSON key in the root directory as `credentials.json`.

3. **Run the Application**
   ```bash
   # Run the Streamlit client (Local Core Mode)
   python -m streamlit run client_package/app.py
   ```

## 📚 Documentation

### Core Modules

- **`engine.py`**: The central brain. Orchestrates intent classification, tool routing (`SQLHandler`, `VectorHandler`, `IngestHandler`), and session management.
- **`bq_handler.py`**: Low-level BigQuery interactions. Handles connection, schema retrieval, efficient batch inserts, and upserts.
- **`ingestion_pipeline.py`**: Production-grade pipeline for processing files. Features extraction (PDFMiner/DocAI), chunking, embedding generation, and BQ loading.

### SQL Generation Logic

The toolbox uses a sophisticated prompt chain for SQL generation:
1. **Schema Retrieval**: Fetches detailed schema (types, modes, descriptions) and table stats.
2. **Analysis**: The AI serves as a "BigQuery Expert", writing valid SQL based on the user's intent.
3. **Execution**: The query is run safely against the user's dataset.
4. **Synthesis**: The results are interpreted back into natural language.

### Contributing

Contributions are welcome! Please submit Pull Requests for any improvements to the engine, UI, or documentation.

---

**Built with ❤️ for the BigQuery community**
