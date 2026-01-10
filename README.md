# BigQuery Toolbox 🚀

A powerful Python-based toolbox for intelligent BigQuery data management with AI-powered search and automated data ingestion capabilities.

## 🌟 Features

### Core Functionality (run python cli.py)

#### 1. **Intelligent Data Ingestion**
- Automated CSV/JSON data upload to BigQuery
- Dynamic schema inference and table creation
- Smart batch processing with automatic retry logic
- Handles large datasets with configurable batch sizes
- Robust error handling with recursive batch splitting

#### 2. **AI-Powered Chat Interface**
- Natural language queries to your BigQuery data
- Intent classification for smart command routing
- Streaming AI responses powered by Google's Gemini
- Context-aware data analysis and insights
- Real-time data monitoring and collection

#### 3. **Advanced BigQuery Operations**
- **UPSERT Operations**: Merge data with conflict resolution
- **Schema Management**: Automatic column addition and type inference
- **Graph Support**: NetworkX graph upload to BigQuery (nodes & edges)
- **Batch Processing**: Intelligent batching to avoid query size limits
- **Type Safety**: Proper handling of STRING, INT64, FLOAT64, BOOL, ARRAY types

#### 4. **Data Search & Retrieval**
- Semantic search using embeddings
- Similarity-based content discovery
- Flexible query building
- Support for complex filters and conditions

### Key Components

#### `BQGroundZero`
Base class providing:
- Dataset management and creation
- Query execution with error handling
- Schema utilities and type conversion
- SQL query builders for common operations

#### `BQCore`
Extended functionality:
- Table existence checking
- Schema retrieval and updates
- Batch upload with recursive retry logic
- Column management (add, check, update)
- Intelligent error recovery

#### `BigQueryGraphHandler`
Specialized for graph data:
- NetworkX graph conversion
- Nodes and edges table management
- Automatic schema extraction
- Bulk column operations

## 🚀 Getting Started

### Prerequisites

```bash
# Python 3.8+
# Google Cloud credentials configured
# BigQuery API enabled
```

### Installation

```bash
# Clone the repository
git clone https://github.com/wired87/_bigquery_toolbox.git
cd _bigquery_toolbox

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

#### 1. **Google Cloud Platform Setup**

Before using this toolbox, you need to set up GCP credentials:

**Step 1: Create a Service Account**
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select your project (or create a new one)
3. Navigate to **IAM & Admin** > **Service Accounts**
4. Click **Create Service Account**
5. Enter a name (e.g., `bigquery-toolbox-sa`)
6. Grant the following roles:
   - `BigQuery Admin` (for full BigQuery access)
   - `BigQuery Data Editor` (minimum required for data operations)
   - `BigQuery Job User` (for running queries)

**Step 2: Create and Download Credentials**
1. Click on the created service account
2. Go to the **Keys** tab
3. Click **Add Key** > **Create new key**
4. Select **JSON** format
5. Click **Create** - the file will download automatically

**Step 3: Configure Credentials in Project**
1. Rename the downloaded file to `credentials.json`
2. Place it in the project root directory:
   ```
   _bigquery_toolbox/
   ├── credentials.json          ← Place your credentials file here
   ├── bq_handler.py
   ├── cli.py
   └── ...
   ```
3. **Important**: The file is already in `.gitignore` to prevent accidental commits

**Step 4: Set Environment Variable**

**On Linux/Mac:**
```bash
export GOOGLE_APPLICATION_CREDENTIALS="$(pwd)/credentials.json"
```

**On Windows (PowerShell):**
```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="$PWD\credentials.json"
```

**On Windows (CMD):**
```cmd
set GOOGLE_APPLICATION_CREDENTIALS=%CD%\credentials.json
```

**Permanent Setup (Optional):**
Add the environment variable to your shell profile:
- Linux/Mac: Add to `~/.bashrc` or `~/.zshrc`
- Windows: Set via System Properties > Environment Variables

#### 2. **Enable Required APIs**

Ensure the following APIs are enabled in your GCP project:
1. Go to **APIs & Services** > **Library**
2. Search and enable:
   - BigQuery API
   - BigQuery Storage API (for faster data access)
   - Vertex AI API (for AI chat features)

#### 3. **Verify Setup**

Test your credentials:
```bash
# Activate virtual environment
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Run a quick test
python -c "from google.cloud import bigquery; client = bigquery.Client(); print('✅ Credentials working!')"
```

### Usage

#### CLI Interface

```bash
# Start the AI-powered chat interface
python cli.py

# You'll be prompted for:
# 1. Knowledge Base Name (table name)
# 2. Natural language queries about your data
```

#### Programmatic Usage

```python
from bq_handler import BQCore

# Initialize handler
bq = BQCore(dataset_id="IDB")

# Insert/Upsert data
rows = [
    {"id": "1", "name": "Product A", "price": 99.99},
    {"id": "2", "name": "Product B", "price": 149.99}
]
bq.bq_insert("products", rows, upsert=True)

# Query data
results = bq.run_query("SELECT * FROM `project.IDB.products`", conv_to_dict=True)
print(results)
```

#### Graph Upload Example

```python
from bq_handler import BigQueryGraphHandler
import networkx as nx

# Create a graph
G = nx.Graph()
G.add_node(1, name="Node A", type="person")
G.add_node(2, name="Node B", type="company")
G.add_edge(1, 2, relationship="works_at")

# Upload to BigQuery
handler = BigQueryGraphHandler()
handler.upload_graph(G)
```

## 🔧 Technical Highlights

### String Escaping Fix
The toolbox includes a robust SQL string escaping mechanism that properly handles:
- Backslashes (`\`)
- Single quotes (`'`)
- Special characters
- Unicode content
- Nested JSON structures

```python
def sql_escape_string(self, s):
    """Escape a string for use in BigQuery SQL."""
    if s is None:
        return "NULL"
    s = str(s).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"
```

### Batch Processing Strategy
- Default batch size: 200 rows
- Automatic splitting on failure
- Recursive retry logic
- Debug query logging for troubleshooting

### Error Recovery
- Syntax error detection and logging
- Failed query saved to `failed_query_debug.sql`
- Graceful degradation to single-row inserts
- Detailed error messages with row content

## 📊 Use Cases

1. **E-commerce Product Catalogs**
   - Ingest product data from multiple sources
   - AI-powered product search and recommendations
   - Price tracking and analysis

2. **Knowledge Bases**
   - Document storage with embeddings
   - Semantic search capabilities
   - Content similarity analysis

3. **Graph Analytics**
   - Social network analysis
   - Relationship mapping
   - Network visualization data prep

4. **Data Warehousing**
   - ETL pipeline integration
   - Automated schema evolution
   - Data quality monitoring

## 🛠 TODO List

### High Priority

#### Web Server Integration
- [ ] **Load Admin Specific Data**
  - [ ] Load help emails and contact info from `.env`
  - [ ] Ensure sensitive admin configuration is decoupled from code

- [ ] **REST API Server**
  - [ ] FastAPI/Flask backend
  - [ ] Authentication & authorization (OAuth2, API keys)
  - [ ] Rate limiting and quota management
  - [ ] Swagger/OpenAPI documentation
  - [ ] WebSocket support for real-time updates

- [ ] **API Endpoints**
  - [ ] `POST /api/v1/tables/{table_id}/insert` - Bulk insert
  - [ ] `POST /api/v1/tables/{table_id}/upsert` - Upsert operations
  - [ ] `GET /api/v1/tables/{table_id}/query` - Query execution
  - [ ] `GET /api/v1/tables` - List all tables
  - [ ] `POST /api/v1/chat` - AI chat interface
  - [ ] `POST /api/v1/search` - Semantic search
  - [ ] `GET /api/v1/schema/{table_id}` - Get table schema
  - [ ] `POST /api/v1/graph/upload` - Graph upload

- [ ] **Web Dashboard**
  - [ ] React/Vue.js frontend
  - [ ] Real-time data monitoring
  - [ ] Query builder interface
  - [ ] Schema visualizer
  - [ ] AI chat interface
  - [ ] Data preview and exploration
  - [ ] Performance metrics and analytics

#### Enhanced Data Tools
- [ ] **Data Validation**
  - [ ] Schema validation before insert
  - [ ] Data type checking and coercion
  - [ ] Custom validation rules
  - [ ] Duplicate detection

- [ ] **Data Transformation**
  - [ ] Built-in ETL pipelines
  - [ ] Data cleaning utilities
  - [ ] Format converters (CSV, JSON, Parquet, Avro)
  - [ ] Column mapping and renaming

- [ ] **Advanced Search**
  - [ ] Full-text search integration
  - [ ] Faceted search
  - [ ] Aggregation queries
  - [ ] Custom ranking algorithms

### Medium Priority

#### Monitoring & Observability
- [ ] **Logging & Metrics**
  - [ ] Structured logging (JSON format)
  - [ ] Query performance tracking
  - [ ] Cost monitoring and alerts
  - [ ] Error rate tracking
  - [ ] Integration with Prometheus/Grafana

- [ ] **Alerting**
  - [ ] Failed query notifications
  - [ ] Schema change alerts
  - [ ] Cost threshold warnings
  - [ ] Data quality alerts

#### Performance Optimization
- [ ] **Caching Layer**
  - [ ] Redis integration for query results
  - [ ] Schema caching
  - [ ] Embedding cache for search

- [ ] **Query Optimization**
  - [ ] Query plan analysis
  - [ ] Automatic index suggestions
  - [ ] Partition management
  - [ ] Clustering recommendations

#### Security & Compliance
- [ ] **Access Control**
  - [ ] Row-level security
  - [ ] Column-level encryption
  - [ ] Audit logging
  - [ ] GDPR compliance tools (data deletion, export)

- [ ] **Data Governance**
  - [ ] Data lineage tracking
  - [ ] Metadata management
  - [ ] Data catalog integration

### Low Priority

#### Additional Features
- [ ] **Multi-Cloud Support**
  - [ ] AWS Redshift adapter
  - [ ] Snowflake integration
  - [ ] Azure Synapse support

- [ ] **Advanced Analytics**
  - [ ] Built-in ML model training
  - [ ] Anomaly detection
  - [ ] Trend analysis
  - [ ] Forecasting utilities

- [ ] **Collaboration Tools**
  - [ ] Shared queries and dashboards
  - [ ] Team workspaces
  - [ ] Query versioning
  - [ ] Comments and annotations

- [ ] **Data Export**
  - [ ] Scheduled exports
  - [ ] Multiple format support
  - [ ] Cloud storage integration (GCS, S3)
  - [ ] Email reports

#### Developer Experience
- [ ] **CLI Enhancements**
  - [ ] Interactive query builder
  - [ ] Auto-completion
  - [ ] Query history
  - [ ] Configuration profiles

- [ ] **SDK Development**
  - [ ] JavaScript/TypeScript SDK
  - [ ] Python package on PyPI
  - [ ] Go client library
  - [ ] Documentation site

- [ ] **Testing & Quality**
  - [ ] Unit test coverage >80%
  - [ ] Integration tests
  - [ ] Performance benchmarks
  - [ ] Load testing suite

## 📝 Recent Fixes

### BigQuery Syntax Error Resolution
**Issue**: String values with special characters (quotes, backslashes) caused syntax errors in MERGE queries.

**Solution**: Implemented `sql_escape_string()` method that properly escapes strings for BigQuery SQL, replacing the problematic `json.dumps()` approach.

**Impact**: 
- ✅ Handles strings with quotes, backslashes, newlines
- ✅ Reduced query generation overhead
- ✅ Improved error recovery with debug logging
- ✅ More reliable batch processing

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License.

## 🔗 Links

- **Repository**: https://github.com/wired87/_bigquery_toolbox
- **Issues**: https://github.com/wired87/_bigquery_toolbox/issues
- **Documentation**: Coming soon

## 💡 Support

For questions and support, please open an issue on GitHub.

---

**Built with ❤️ for the BigQuery community**
