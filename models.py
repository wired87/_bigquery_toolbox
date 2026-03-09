from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from datetime import datetime

class KnowledgeNode(BaseModel):
    """
    Represents a single unit of knowledge (chunk) in the system.
    Enforces a strict schema for BigQuery ingestion.
    """
    id: str = Field(..., description="Unique identifier for the chunk")
    content: str = Field(..., description="The actual text content")
    source_file: str = Field(..., description="Name of the source file")
    chunk_type: str = Field(..., description="'large' (parent) or 'small' (child)")
    parent_id: Optional[str] = Field(None, description="ID of the parent chunk if applicable")
    page: int = Field(0, description="Page number in original document")
    
    # New Data Categorization Fields
    category: str = Field("General", description="High-level category (e.g., 'Finance', 'Tech')")
    tags: List[str] = Field(default_factory=list, description="List of specific tags")
    
    # Metadata
    ingested_at: str = Field(default_factory=lambda: datetime.now())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for BigQuery insertion"""
        return self.model_dump()
