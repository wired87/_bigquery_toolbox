"""
VRAG Configuration
Environment and runtime settings for Vertex AI RAG Engine.
"""

import os
from dataclasses import dataclass, field
from typing import Optional, List

try:
    import dotenv
    dotenv.load_dotenv()
except ImportError:
    pass


@dataclass
class VRAGConfig:
    """Production-ready VRAG configuration."""

    project_id: Optional[str] = field(
        default_factory=lambda: os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
    )
    # RAG Engine: us-central1, us-east1, us-east4 are allowlisted for new projects.
    # Use europe-west4 (GA) or us-west1 (Preview) for non-allowlisted projects.
    location: str = field(
        default_factory=lambda: os.getenv("VRAG_LOCATION") or os.getenv("VERTEX_LOCATION", "europe-west4")
    )
    corpus_display_name: str = field(default_factory=lambda: os.getenv("VRAG_CORPUS_NAME", "bigquery_toolbox_corpus"))
    corpus_description: str = "Knowledge base for BigQuery AI Toolbox"
    embedding_model: str = "publishers/google/models/text-embedding-005"
    generation_model: str = "gemini-2.0-flash-001"
    top_k: int = 5
    chunk_size: int = 512
    chunk_overlap: int = 100
    max_embedding_requests_per_min: int = 1000
    vector_distance_threshold: float = 0.5
    gcs_bucket: Optional[str] = field(default_factory=lambda: os.getenv("VRAG_GCS_BUCKET"))
    use_vertex_rag: bool = field(
        default_factory=lambda: os.getenv("VRAG_USE_VERTEX", "true").lower() in ("true", "1", "yes")
    )

    def is_vertex_available(self) -> bool:
        """Check if Vertex RAG can be used (project + credentials)."""
        return bool(self.project_id)

    def to_rag_embedding_config(self):
        """Build RAG embedding config for Vertex AI SDK."""
        from vertexai import rag
        return rag.RagEmbeddingModelConfig(
            vertex_prediction_endpoint=rag.VertexPredictionEndpoint(
                publisher_model=self.embedding_model
            )
        )
