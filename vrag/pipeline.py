"""
VRAG Pipeline
Unified RAG pipeline: Vertex AI RAG primary, local processes as last fallback.
Uses VertexRAGEngine for production-ready Vertex operations.
"""

import asyncio
import logging
from typing import Optional, Callable, Any

from .config import VRAGConfig
from .corpus import CorpusManager
from .local_fallback import LocalRAGFallback

logger = logging.getLogger(__name__)


class VRAGPipeline:
    """
    Production-ready RAG pipeline:
    1. Try Vertex AI RAG Engine (corpus + retrieval + generation)
    2. Fallback to local BigQuery KB + Gemini on failure or when Vertex unavailable
    """

    def __init__(
        self,
        config: Optional[VRAGConfig] = None,
        engine: Optional[Any] = None,
    ):
        self.config = config or VRAGConfig()
        self.engine = engine
        if engine and hasattr(engine, "pid") and engine.pid and not self.config.project_id:
            self.config.project_id = engine.pid
        self.corpus_manager = CorpusManager(self.config)
        from .engine import VertexRAGEngine
        self.vrag_engine = VertexRAGEngine(config=self.config, project_id=self.config.project_id)
        self.local_fallback = LocalRAGFallback(engine) if engine else None
        self._corpus_name: Optional[str] = None
        self._corpus_create_failed: bool = False  # Avoid retrying create on every request

    def _resolve_corpus_name(self) -> Optional[str]:
        """
        Resolve corpus name for current user.
        Prefer user-specific corpus from METADATA (set on sign-in).
        Fallback to shared corpus or create if needed.
        """
        if not self.engine:
            return None
        dataset_id = getattr(self.engine, "current_dataset_id", None)
        auth_manager = getattr(self.engine, "auth_manager", None)
        if dataset_id and auth_manager and hasattr(auth_manager, "get_metadata"):
            corpus_name = auth_manager.get_metadata(dataset_id, "vertex_rag_corpus_id")
            if corpus_name:
                return corpus_name
        if self._corpus_name:
            return self._corpus_name
        if self._corpus_create_failed:
            return None  # Skip retry; fallback to local
        corpora = self.corpus_manager.list_corpora()
        for c in corpora:
            if c.get("display_name") == self.config.corpus_display_name:
                self._corpus_name = c["name"]
                return self._corpus_name
        corpus = self.corpus_manager.create_corpus()
        if corpus and hasattr(corpus, "name"):
            self._corpus_name = corpus.name
            return self._corpus_name
        self._corpus_create_failed = True
        return None

    def use_vertex_rag(self) -> bool:
        """Whether to attempt Vertex RAG (config allows and project set)."""
        return self.config.use_vertex_rag and self.config.is_vertex_available()

    async def handle(
        self,
        user_input: str,
        status_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Main entry: try Vertex RAG, fallback to local.
        """
        async def update_status(message: str, step: str = ""):
            if status_callback:
                await status_callback(message, step)

        result = {
            "intent": "query_similarity_search",
            "response_text": "",
            "source_citation": None,
            "traceability": None,
        }

        if self.use_vertex_rag():
            corpus_name = self._resolve_corpus_name()
            if corpus_name:
                try:
                    await update_status("🔍 Using Vertex RAG Engine...", "vertex")
                    text = await asyncio.to_thread(
                        self.vrag_engine.generate_with_rag,
                        corpus_name,
                        user_input,
                    )
                    if text:
                        result["response_text"] = text
                        result["traceability"] = {"source": "vertex_rag"}
                        return result
                except Exception as e:
                    logger.warning("Vertex RAG failed, falling back to local: %s", e)
                    await update_status("⚠️ Falling back to local RAG...", "fallback")

        if self.local_fallback and self.engine:
            return await self.local_fallback.handle(user_input, status_callback)

        result["response_text"] = (
            "RAG unavailable: Vertex RAG not configured and no local engine provided."
        )
        return result
