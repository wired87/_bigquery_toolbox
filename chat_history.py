
import sqlite3
import json
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class ChatHistoryDB:
    def __init__(self, db_path: str = "chat_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize the SQLite database schema."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to init chat history DB: {e}")

    def add_message(self, session_id: str, role: str, content: str):
        """Add a message to the history."""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO history (session_id, role, content) VALUES (?, ?, ?)",
                (session_id, role, content)
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error(f"Failed to add message to history: {e}")

    def get_recent_history(self, session_id: str, limit: int = 6) -> List[Dict[str, str]]:
        """
        Get recent history as a list of dicts.
        Limit 6 messages = 3 QA pairs.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # Get last N *descending*, then reverse
            cursor.execute(
                "SELECT role, content FROM history WHERE session_id = ? ORDER BY id DESC LIMIT ?",
                (session_id, limit)
            )
            rows = cursor.fetchall()
            conn.close()
            
            history = [{"role": row["role"], "content": row["content"]} for row in rows]
            return history[::-1] # Return in chronological order
        except Exception as e:
            logger.error(f"Failed to get history: {e}")
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
