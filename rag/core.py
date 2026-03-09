"""
RAG Core - Minimal container for engine and VRAG pipeline.
All chat logic (routing, SQL, Ingest, RAG, upload, fallback) lives in RAGWorkflow.
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class RAGConfig:
    """Configuration for RAG operations."""
    timeout_classification: float = 30.0
    timeout_search: float = 90.0
    timeout_sql: float = 120.0
    timeout_chat: float = 60.0
    max_retry_attempts: int = 2
    enable_history_rewrite: bool = True


class RAGCore:
    """
    Minimal container: holds engine and vrag_pipeline.
    Chat logic (process_chat, upload, RAG) is in RAGWorkflow.
    """

    def __init__(self, engine, config: Optional[RAGConfig] = None):
        self.engine = engine
        self.config = config or RAGConfig()
        self.vrag_pipeline = None  # Set by app after init
        print("✅ RAG Core initialized")

    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user through engine."""
        return await self.engine.authenticate(email, password)

    def get_stats(self) -> Dict[str, Any]:
        """Basic stats for sidebar."""
        return {
            "engine_authenticated": self.engine.is_authenticated,
            "current_user": self.engine.current_user_email,
        }
