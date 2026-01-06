"""
Global RAG Registry - Singleton pattern for global access
"""

import logging
from typing import Optional, Dict, Any, List, Callable
import threading

logger = logging.getLogger(__name__)


class GlobalRAGRegistry:
    """
    Global singleton registry for RAG Core
    Provides thread-safe access to RAG instance
    Also manages RELAY package notifications
    """
    
    _instance: Optional['RAGCore'] = None
    _lock = threading.Lock()
    _relay_listeners: List[Callable] = []
    _discovered_relays: List[Dict[str, Any]] = []
    
    @classmethod
    def initialize(cls, rag_core):
        """
        Initialize the global RAG instance
        
        Args:
            rag_core: RAGCore instance
        """
        with cls._lock:
            if cls._instance is not None:
                logger.warning("RAG Registry already initialized. Replacing instance.")
            cls._instance = rag_core
            logger.info("🌍 Global RAG Registry initialized")
    
    @classmethod
    def get_instance(cls):
        """Get the global RAG instance"""
        with cls._lock:
            if cls._instance is None:
                raise RuntimeError("RAG Registry not initialized. Call initialize() first.")
            return cls._instance
    
    @classmethod
    def is_initialized(cls) -> bool:
        """Check if registry is initialized"""
        return cls._instance is not None
    
    @classmethod
    def register_relay_listener(cls, callback: Callable):
        """
        Register a callback to be notified when new RELAY packages are discovered
        
        Args:
            callback: Async function that accepts (relay_info: Dict[str, Any])
        """
        with cls._lock:
            if callback not in cls._relay_listeners:
                cls._relay_listeners.append(callback)
                logger.info(f"📡 Registered RELAY listener: {callback.__name__}")
    
    @classmethod
    async def notify_relay_discovered(cls, relay_info: Dict[str, Any]):
        """
        Notify all listeners about a newly discovered RELAY package
        
        Args:
            relay_info: Dictionary with relay package information
        """
        with cls._lock:
            cls._discovered_relays.append(relay_info)
            listeners = cls._relay_listeners.copy()
        
        logger.info(f"🔌 Broadcasting RELAY discovery: {relay_info.get('key')}")
        
        # Notify all listeners asynchronously
        for listener in listeners:
            try:
                await listener(relay_info)
            except Exception as e:
                logger.error(f"Error notifying listener {listener.__name__}: {e}")
    
    @classmethod
    def get_discovered_relays(cls) -> List[Dict[str, Any]]:
        """Get all discovered RELAY packages"""
        with cls._lock:
            return cls._discovered_relays.copy()
    
    @classmethod
    def clear_relay_listeners(cls):
        """Clear all RELAY listeners"""
        with cls._lock:
            cls._relay_listeners.clear()
            logger.info("Cleared all RELAY listeners")
