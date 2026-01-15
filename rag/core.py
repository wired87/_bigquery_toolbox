"""
RAG Core - Unified Chat Logic
Wraps all engine operations for efficient processing
"""

import asyncio
import logging
from typing import Dict, Any, Optional, Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class RAGConfig:
    """Configuration for RAG operations"""
    timeout_classification: float = 30.0
    timeout_search: float = 90.0
    timeout_sql: float = 120.0
    timeout_chat: float = 60.0
    max_retry_attempts: int = 2
    enable_history_rewrite: bool = True


class RAGCore:
    """
    Unified RAG Core that wraps all chat logic
    Provides efficient, centralized processing for all user queries
    """
    
    def __init__(self, engine, config: Optional[RAGConfig] = None):
        """
        Initialize RAG Core with engine instance
        
        Args:
            engine: CoreEngine instance
            config: Optional RAG configuration
        """
        self.engine = engine
        self.config = config or RAGConfig()
        self.active_requests = {}
        self.request_counter = 0
        
        print("✅ RAG Core initialized")
    
    async def process(
        self,
        user_input: str,
        status_callback: Optional[Callable] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main processing method for all user inputs
        
        Args:
            user_input: User's query/command
            status_callback: Optional callback for status updates
            context: Optional context (user_id, session_id, etc.)
            
        Returns:
            Dict with response and metadata
        """
        request_id = self._generate_request_id()
        self.active_requests[request_id] = {
            'input': user_input,
            'status': 'processing',
            'context': context
        }
        
        try:
            # Delegate to engine
            result = await self.engine.process_user_input(
                user_input,
                status_callback=status_callback
            )
            
            # Add RAG metadata
            result['request_id'] = request_id
            result['processed_by'] = 'RAG Core'
            
            self.active_requests[request_id]['status'] = 'completed'
            return result
            
        except Exception as e:
            print(f"RAG processing failed: {e}")
            self.active_requests[request_id]['status'] = 'failed'
            return {
                'intent': 'error',
                'response_text': f"Processing failed: {str(e)}",
                'request_id': request_id,
                'error': str(e)
            }
        finally:
            # Cleanup after a delay
            await asyncio.sleep(300)  # Keep for 5 minutes
            self.active_requests.pop(request_id, None)
    
    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user through engine"""
        return await self.engine.authenticate(email, password)
    
    async def handle_file_upload(
        self,
        filename: str,
        content: bytes,
        status_callback: Optional[Callable] = None,
        metadata: Optional[Dict[str, Any]] = None,
        ingestion_config: Optional[Dict[str, Any]] = None
    ) -> str:
        """Handle file upload through engine"""
        return await self.engine.handle_file_upload(
            filename, content, status_callback, metadata, ingestion_config
        )
    
    async def get_existing_filenames(self):
        """Get existing filenames from engine"""
        return await self.engine.get_existing_filenames()
    
    def get_active_requests(self) -> Dict[str, Any]:
        """Get all active requests"""
        return self.active_requests.copy()
    
    def _generate_request_id(self) -> str:
        """Generate unique request ID"""
        self.request_counter += 1
        return f"req_{self.request_counter}"
    
    def get_stats(self) -> Dict[str, Any]:
        """Get RAG core statistics"""
        return {
            'active_requests': len(self.active_requests),
            'total_processed': self.request_counter,
            'engine_authenticated': self.engine.is_authenticated,
            'current_user': self.engine.current_user_email
        }
