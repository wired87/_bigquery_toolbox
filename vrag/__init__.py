"""
VRAG - Vertex AI RAG Pipeline
Production-ready RAG using Vertex AI RAG Engine with local process fallback.
"""

from .config import VRAGConfig
from .pipeline import VRAGPipeline
from .corpus import CorpusManager
from .retrieval import VertexRetriever
from .engine import VertexRAGEngine
from .local_fallback import LocalRAGFallback
from .user_corpus import ensure_user_vertex_rag_corpus, upsert_file_to_user_corpus

__all__ = [
    "VRAGConfig",
    "VRAGPipeline",
    "CorpusManager",
    "VertexRetriever",
    "VertexRAGEngine",
    "LocalRAGFallback",
    "ensure_user_vertex_rag_corpus",
    "upsert_file_to_user_corpus",
]
