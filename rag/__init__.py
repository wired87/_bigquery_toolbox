"""
RAG Package - Retrieval Augmented Generation Core
Wraps all chat logic and exposes globally accessible API
"""

from .core import RAGCore
from .global_registry import GlobalRAGRegistry

# Global singleton instance
__all__ = ['RAGCore', 'GlobalRAGRegistry', 'get_rag_instance']

def get_rag_instance():
    """Get the global RAG instance"""
    return GlobalRAGRegistry.get_instance()
