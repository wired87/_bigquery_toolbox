
import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from collections import defaultdict

logger = logging.getLogger(__name__)

class ChatHistoryDB:
    """
    Session-based chat history manager.
    History is stored in memory and cleared when the session ends.
    """
    def __init__(self, db_path: str = None):
        """
        Initialize with in-memory storage.
        db_path parameter is kept for backward compatibility but ignored.
        """
        # In-memory storage: {session_id: [{"role": str, "content": str, "timestamp": datetime}]}
        self._sessions = defaultdict(list)
        print("Chat history initialized (session-based, in-memory)")

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to the session history."""
        try:
            message = {
                "role": role,
                "content": content,
                "timestamp": datetime.now()
            }
            self._sessions[session_id].append(message)
            logger.debug(f"Added {role} message to session {session_id}")
        except Exception as e:
            print(f"Failed to add message to history: {e}")

    def get_recent_history(self, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """
        Get recent history as a list of dicts.
        Limit 6 messages = 3 QA pairs.
        """
        try:
            session_messages = self._sessions.get(session_id, [])
            # Get last N messages
            recent = session_messages[-limit:] if len(session_messages) > limit else session_messages
            # Return only role and content (strip timestamp)
            return [{"role": msg["role"], "content": msg["content"]} for msg in recent]
        except Exception as e:
            print(f"Failed to get history: {e}")
            return []

    def get_formatted_history(self, session_id: str, limit: int = 6) -> str:
        """
        Get history formatted as a string for LLM context.
        """
        history = self.get_recent_history(session_id, limit)
        if not history:
            return ""
        
        formatted = []
        for msg in history:
            role_prefix = "User" if msg["role"] == "user" else "Assistant"
            formatted.append(f"{role_prefix}: {msg['content']}")
        
        return "\n".join(formatted)
    
    def clear_session(self, session_id: str):
        """
        Clear all history for a specific session.
        Called when user exits/quits.
        """
        if session_id in self._sessions:
            msg_count = len(self._sessions[session_id])
            del self._sessions[session_id]
            print(f"Cleared session {session_id} ({msg_count} messages)")
        else:
            logger.debug(f"Session {session_id} already empty")
    
    def get_session_count(self, session_id: str) -> int:
        """Get the number of messages in a session."""
        return len(self._sessions.get(session_id, []))
