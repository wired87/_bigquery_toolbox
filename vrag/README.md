# VRAG - Vertex AI RAG Pipeline

Production-ready RAG pipeline using Vertex AI RAG Engine with local process fallback.

## Overview

- **Primary**: Vertex AI RAG Engine (corpus, import files, retrieval, Gemini generation)
- **Fallback**: Local BigQuery KB + Gemini when Vertex RAG is unavailable

## Configuration

Set these environment variables (or use `.env`):

| Variable | Description | Default |
|----------|-------------|---------|
| `GOOGLE_CLOUD_PROJECT` / `GCP_PROJECT` | GCP project ID | (from credentials) |
| `VERTEX_LOCATION` | Vertex AI region | `us-central1` |
| `VRAG_CORPUS_NAME` | Corpus display name | `bigquery_toolbox_corpus` |
| `VRAG_GCS_BUCKET` | GCS bucket for local file uploads | - |
| `VRAG_USE_VERTEX` | Use Vertex RAG when available | `true` |

## Usage

### In Streamlit App

Vector/search queries automatically use VRAG:
1. Try Vertex RAG Engine (if corpus exists and project configured)
2. Fall back to local BigQuery KB + Gemini on failure

### Programmatic

```python
from vrag import VRAGPipeline, VRAGConfig
from engine import CoreEngine

engine = CoreEngine(credentials_path="credentials.toml")
config = VRAGConfig()
config.project_id = engine.pid
pipeline = VRAGPipeline(config=config, engine=engine)

result = await pipeline.handle("What is RAG?", status_callback=...)
```

### Corpus Management

```python
from vrag import CorpusManager, VRAGConfig

cm = CorpusManager(VRAGConfig())
corpus = cm.create_corpus(display_name="my_corpus")
cm.import_files(corpus.name, ["gs://my-bucket/docs/"])
```

## Files

- `config.py` - VRAG settings
- `corpus.py` - Create/list/import corpora
- `retrieval.py` - Vertex retrieval + generation
- `local_fallback.py` - Local BigQuery KB fallback
- `pipeline.py` - Unified pipeline (Vertex → local)
