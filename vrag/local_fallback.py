"""
Local RAG Fallback
Uses engine's BigQuery vector search + Gemini when Vertex RAG is unavailable.
"""

import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class LocalRAGFallback:
    """
    Local RAG implementation using CoreEngine's vector_search and chat_session.
    Used when Vertex AI RAG Engine is not configured or fails.
    """

    def __init__(self, engine: Any):
        """
        Args:
            engine: CoreEngine instance (must have vector_search, chat_session, tools, handle_model_response).
        """
        self.engine = engine

    async def handle(
        self,
        user_input: str,
        status_callback: Optional[Callable] = None,
    ) -> dict:
        """
        Handle vector search query using local BigQuery KB + Gemini.
        Same interface as VectorHandler.handle.
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

        if not self.engine.chat_session:
            result["response_text"] = "⚠️ AI features unavailable. Cannot perform vector search."
            return result

        try:
            import asyncio
            await update_status("🔍 Performing local vector search...", "search")
            response = await asyncio.to_thread(
                self.engine.chat_session.send_message,
                f"User wants to find items: {user_input}. Use vector_search tool if appropriate. Default table is 'KB'.",
                tools=[self.engine.tools],
            )
            await update_status("✨ Generating response...", "generate")
            result["response_text"] = await self.engine.handle_model_response(response)
            logger.info("Local RAG completed (%d chars)", len(result["response_text"]))
        except Exception as e:
            try:
                from error_handler import log_exception
                log_exception(e, "Local RAG Fallback")
            except ImportError:
                logger.exception("Local RAG Fallback failed")
            await update_status(f"❌ Local search failed: {type(e).__name__}", "error")
            result["response_text"] = f"Search failed: {str(e)}"

        return result
