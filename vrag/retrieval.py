"""
Vertex AI RAG Retrieval and Generation
Direct retrieval and Gemini with RAG tool.
"""

import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


class VertexRetriever:
    """
    Vertex AI RAG retrieval and generation.
    Uses rag.retrieval_query for direct retrieval and GenerativeModel with Tool for RAG-augmented generation.
    """

    def __init__(self, config: "VRAGConfig"):
        from .config import VRAGConfig
        self.config = config if isinstance(config, VRAGConfig) else config

    def _ensure_vertex_init(self):
        import vertexai
        try:
            vertexai.init(project=self.config.project_id, location=self.config.location)
        except Exception as e:
            logger.warning("Vertex AI init: %s", e)

    def _build_retrieval_config(self):
        """Build RagRetrievalConfig."""
        from vertexai import rag
        return rag.RagRetrievalConfig(
            top_k=self.config.top_k,
            filter=rag.Filter(vector_distance_threshold=self.config.vector_distance_threshold),
        )

    def retrieval_query(
        self,
        corpus_name: str,
        text: str,
        rag_file_ids: Optional[List[str]] = None,
    ) -> Optional[object]:
        """
        Direct retrieval from corpus. Returns RAG response with contexts.
        """
        try:
            from vertexai import rag
            self._ensure_vertex_init()

            rag_resources = [rag.RagResource(rag_corpus=corpus_name, rag_file_ids=rag_file_ids or [])]
            response = rag.retrieval_query(
                rag_resources=rag_resources,
                text=text,
                rag_retrieval_config=self._build_retrieval_config(),
            )
            return response
        except Exception as e:
            logger.exception("Retrieval query failed: %s", e)
            return None

    def generate_with_rag(
        self,
        corpus_name: str,
        query: str,
        rag_file_ids: Optional[List[str]] = None,
    ) -> Optional[str]:
        """
        Generate response using Gemini with RAG retrieval tool.
        """
        try:
            from vertexai import rag
            from vertexai.generative_models import GenerativeModel, Tool
            self._ensure_vertex_init()

            rag_retrieval_config = self._build_retrieval_config()
            rag_resource = rag.RagResource(rag_corpus=corpus_name, rag_file_ids=rag_file_ids or [])
            retrieval_tool = Tool.from_retrieval(
                retrieval=rag.Retrieval(
                    source=rag.VertexRagStore(
                        rag_resources=[rag_resource],
                        rag_retrieval_config=rag_retrieval_config,
                    ),
                ),
            )
            model = GenerativeModel(
                model_name=self.config.generation_model,
                tools=[retrieval_tool],
            )
            response = model.generate_content(query)
            return response.text if response and response.text else None
        except Exception as e:
            logger.exception("RAG generation failed: %s", e)
            return None

    def retrieve_contexts(self, corpus_name: str, query: str) -> List[Dict[str, Any]]:
        """
        Retrieve contexts as a list of dicts for custom generation pipelines.
        """
        resp = self.retrieval_query(corpus_name, query)
        if not resp or not hasattr(resp, "contexts"):
            return []
        contexts = []
        for ctx in getattr(resp, "contexts", []) or []:
            if hasattr(ctx, "text"):
                contexts.append({"text": ctx.text})
            elif isinstance(ctx, dict):
                contexts.append(ctx)
        return contexts
