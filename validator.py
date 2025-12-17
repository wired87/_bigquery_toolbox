from vertexai.generative_models import Tool, FunctionDeclaration
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Any, Dict
import re
import logging
import os
import threading
import time
import json

logger = logging.getLogger(__name__)

@dataclass
class ToolCase:
    """
    Unified definition of a Tool/UseCase.
    Combines the Intent Pattern with the Tool Definition.
    """
    key: str
    description: str
    pattern: str
    priority: int
    tools: Optional[Tool] = None
    tool_names: List[str] = field(default_factory=list)
    action: Optional[str] = None # Action identifier for LLM execution

class ToolRegistry:
    """
    Central repository for all Tools and intent patterns.
    """
    
    _validators: List['QueryValidator'] = []

    @staticmethod
    def _create_bq_tools() -> Tool:
        # Helper to create the actual Vertex AI Tool object
        list_datasets = FunctionDeclaration(name="list_datasets", description="List datasets", parameters={"type": "object", "properties": {}})
        list_tables = FunctionDeclaration(name="list_tables", description="List tables", parameters={"type": "object", "properties": {"dataset_id": {"type": "string"}}, "required": ["dataset_id"]})
        get_schema = FunctionDeclaration(name="get_table_schema", description="Get schema", parameters={"type": "object", "properties": {"table_id": {"type": "string"}}, "required": ["table_id"]})
        run_sql = FunctionDeclaration(name="run_sql_query", description="Run SQL", parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]})
        vector_search = FunctionDeclaration(name="vector_search", description="Vector Search", parameters={"type": "object", "properties": {"query_text": {"type": "string"}, "table_id": {"type": "string"}, "limit": {"type": "integer"}}, "required": ["query_text", "table_id"]})
        get_meta = FunctionDeclaration(name="get_table_metadata", description="Get Metadata", parameters={"type": "object", "properties": {"table_id": {"type": "string"}}, "required": ["table_id"]})
        
        return Tool(function_declarations=[list_datasets, list_tables, get_schema, run_sql, vector_search, get_meta])

    # HARDCODED UNIFIED ARSENAL
    ARSENAL: List[ToolCase] = [
        ToolCase(
            key="command_upload_by_path",
            description="Uploads files from local path",
            pattern=r"(?:upload\s+)(?:[\"']?)(?:[a-zA-Z]:[\\/]|[.\\/])",
            priority=100
        ),
        ToolCase(
            key="command_add_table",
            description="Add a new table",
            pattern=r"add\s+table|create\s+table",
            priority=90
        ),
        ToolCase(
            key="query_sql_generation", 
            description="Generate SQL",
            pattern=r"\b(sql|query|select|count|groupby|database|schema)\b",
            priority=80,
            tool_names=["run_sql_query", "get_table_schema"]
        ),
         ToolCase(
            key="query_similarity_search",
            description="Vector Search",
            pattern=r"\b(find|search|look for|similar|semantic)\b",
            priority=80,
            tool_names=["vector_search"]
        ),
        ToolCase(
            key="query_metadata",
            description="Table Metadata",
            pattern=r"\b(describe|info|metadata|columns|rows)\b",
            priority=70,
            tool_names=["get_table_metadata"]
        )
    ]

    @classmethod
    def get_all_cases(cls) -> List[ToolCase]:
        return cls.ARSENAL

    @classmethod
    def get_bq_tool_object(cls) -> Tool:
        return cls._create_bq_tools()
        
    @classmethod
    def register_validator(cls, validator: 'QueryValidator'):
        cls._validators.append(validator)

    @classmethod
    def start_env_scanner(cls):
        """
        Starts a background thread to scan environment variables for 'RELAY_' packages.
        """
        def scanner_loop():
            processed_keys = set()
            while True:
                try:
                    for key, value in os.environ.items():
                        if key.startswith("RELAY_") and key not in processed_keys:
                            try:
                                # Expecting JSON string configuration
                                # Format: {"key": "case_name", "pattern": "regex", "description": "desc", ...}
                                cfg = json.loads(value)
                                
                                new_case = ToolCase(
                                    key=cfg.get("key", key.lower()),
                                    description=cfg.get("description", "Dynamic Relay Case"),
                                    pattern=cfg.get("pattern", f"{key}"),
                                    priority=cfg.get("priority", 50),
                                    action=cfg.get("action")
                                )
                                
                                # Add to Arsenal
                                cls.ARSENAL.append(new_case)
                                processed_keys.add(key)
                                logger.info(f"🔌 Discovered Relay Package: {new_case.key}")
                                
                                # Update active validators
                                for v in cls._validators:
                                    v.register_case(new_case)
                                    
                            except json.JSONDecodeError:
                                logger.warning(f"Invalid JSON in {key}: {value}")
                            except Exception as e:
                                logger.error(f"Error loading {key}: {e}")
                                
                    time.sleep(5) # Scan interval
                except Exception as e:
                    logger.error(f"Scanner thread error: {e}")
                    time.sleep(5)

        t = threading.Thread(target=scanner_loop, daemon=True)
        t.start()
        logger.info("📡 RELAY Env Scanner started.")

class QueryValidator:
    """
    Validates user queries against registered ToolCases.
    """
    def __init__(self):
        self._cases: List[ToolCase] = []
        self.load_default_cases()
        ToolRegistry.register_validator(self)

    def register_case(self, case: ToolCase):
        """Register a new case."""
        self._cases.append(case)
        self._cases.sort(key=lambda x: x.priority, reverse=True)

    def load_default_cases(self):
        """Loads cases directly from the ToolRegistry Arsenal."""
        for case in ToolRegistry.get_all_cases():
            self.register_case(case)

    def validate(self, query: str) -> Optional[ToolCase]:
        """
        Returns the first matching ToolCase.
        """
        if not query or not query.strip():
            return None

        clean_query = query.strip()

        for case in self._cases:
            try:
                if re.search(case.pattern, clean_query, re.IGNORECASE):
                    return case
            except re.error as e:
                logger.error(f"Invalid regex for case {case.key}: {e}")
                continue
                
        return None
 
