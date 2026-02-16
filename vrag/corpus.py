"""
Vertex AI RAG Corpus Manager
Create, list, and import files into RAG corpora.
"""

import logging
from typing import List, Optional, Union
from pathlib import Path

logger = logging.getLogger(__name__)


class CorpusManager:
    """
    Manages Vertex AI RAG corpora: create, list, import files.
    Supports GCS URIs and Google Drive links.
    """

    def __init__(self, config: "VRAGConfig"):
        from .config import VRAGConfig
        self.config = config if isinstance(config, VRAGConfig) else config

    def _ensure_vertex_init(self):
        """Initialize Vertex AI if not already done."""
        import vertexai
        try:
            vertexai.init(project=self.config.project_id, location=self.config.location)
        except Exception as e:
            logger.warning("Vertex AI init: %s", e)

    def create_corpus(
        self,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[object]:
        """
        Create a RAG corpus. Returns RagCorpus or None on failure.
        """
        try:
            from vertexai import rag
            self._ensure_vertex_init()

            backend_config = rag.RagVectorDbConfig(
                rag_embedding_model_config=self.config.to_rag_embedding_config()
            )
            corpus = rag.create_corpus(
                display_name=display_name or self.config.corpus_display_name,
                description=description or self.config.corpus_description,
                backend_config=backend_config,
            )
            logger.info("Created corpus: %s", corpus.name)
            return corpus
        except Exception as e:
            err_str = str(e).lower()
            if "allowlisted" in err_str or "us-central1" in err_str or "us-east1" in err_str or "us-east4" in err_str:
                logger.warning(
                    "Vertex RAG corpus creation failed (region restriction). "
                    "Set VRAG_LOCATION=europe-west4 or us-west1. See: "
                    "https://cloud.google.com/vertex-ai/generative-ai/docs/rag-engine/rag-overview#supported-regions"
                )
            else:
                logger.exception("Failed to create corpus: %s", e)
            return None

    def list_corpora(self) -> List[dict]:
        """List all RAG corpora in the project."""
        try:
            from vertexai import rag
            self._ensure_vertex_init()
            corpora = list(rag.list_corpora())
            return [
                {"name": c.name, "display_name": getattr(c, "display_name", ""), "description": getattr(c, "description", "")}
                for c in corpora
            ]
        except Exception as e:
            logger.exception("Failed to list corpora: %s", e)
            return []

    def get_corpus_name_by_display_name(self, display_name: str) -> Optional[str]:
        """Get corpus full resource name by display name."""
        for c in self.list_corpora():
            if c.get("display_name") == display_name:
                return c["name"]
        return None

    def import_files(
        self,
        corpus_name: str,
        paths: List[str],
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
        import_result_sink: Optional[str] = None,
    ) -> Optional[int]:
        """
        Import files into a corpus.
        paths: GCS URIs (gs://bucket/path) or Google Drive links.
        Returns count of imported files or None on failure.
        """
        try:
            from vertexai import rag
            self._ensure_vertex_init()

            transformation_config = rag.TransformationConfig(
                chunking_config=rag.ChunkingConfig(
                    chunk_size=chunk_size or self.config.chunk_size,
                    chunk_overlap=chunk_overlap or self.config.chunk_overlap,
                ),
            )
            result = rag.import_files(
                corpus_name=corpus_name,
                paths=paths,
                transformation_config=transformation_config,
                import_result_sink=import_result_sink,
                max_embedding_requests_per_min=self.config.max_embedding_requests_per_min,
            )
            logger.info("Imported files into %s", corpus_name)
            return result
        except Exception as e:
            logger.exception("Failed to import files: %s", e)
            return None

    def list_files(self, corpus_name: str) -> List[dict]:
        """List files in a corpus."""
        try:
            from vertexai import rag
            self._ensure_vertex_init()
            files = list(rag.list_files(parent=corpus_name))
            return [
                {"name": f.name, "display_name": getattr(f, "display_name", "")}
                for f in files
            ]
        except Exception as e:
            logger.exception("Failed to list files: %s", e)
            return []

    def upload_local_to_gcs_and_import(
        self,
        corpus_name: str,
        local_path: Union[str, Path],
        gcs_prefix: str = "vrag_uploads",
    ) -> Optional[int]:
        """
        Upload a local file to GCS and import into corpus.
        Requires VRAG_GCS_BUCKET to be set.
        """
        bucket = self.config.gcs_bucket
        if not bucket:
            logger.error("VRAG_GCS_BUCKET not set. Cannot upload local files.")
            return None

        try:
            from google.cloud import storage
            client = storage.Client(project=self.config.project_id)
            bucket_obj = client.bucket(bucket)
            local = Path(local_path)
            if not local.exists():
                logger.error("Local path does not exist: %s", local_path)
                return None
            blob_name = f"{gcs_prefix}/{local.name}"
            blob = bucket_obj.blob(blob_name)
            blob.upload_from_filename(str(local))
            gcs_uri = f"gs://{bucket}/{blob_name}"
            return self.import_files(corpus_name, [gcs_uri])
        except Exception as e:
            logger.exception("Upload + import failed: %s", e)
            return None
