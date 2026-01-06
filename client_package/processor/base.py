from typing import List, Dict, Any, Optional
from rich.console import Console
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

from ..models import KnowledgeNode

class BaseProcessor:
    def __init__(self):
        self.console = Console()
        self.text_splitter_small = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=50)
        self.text_splitter_large = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)

    def load_from_path(self, file_path: str) -> List[Document]:
        """Override this to load documents from a file path."""
        raise NotImplementedError

    def load_from_bytes(self, filename: str, content: bytes) -> List[Document]:
        """Override this to load documents from bytes."""
        raise NotImplementedError

    def process_path(self, file_path: str, category: str = "Document") -> List[Dict[str, Any]]:
        docs = self.load_from_path(file_path)
        if not docs:
            return []
        
        # Default filename extraction
        import os
        filename = os.path.basename(file_path)
        
        return self._structure_docs(docs, filename, category)

    def process_bytes(self, filename: str, content: bytes, category: str = "Document") -> List[Dict[str, Any]]:
        docs = self.load_from_bytes(filename, content)
        if not docs:
            return []
            
        return self._structure_docs(docs, filename, category)

    def _structure_docs(self, docs: List[Document], filename: str, category: str) -> List[Dict[str, Any]]:
        """
        Common logic to split documents into large/small chunks and wrap in KnowledgeNodes.
        """
        rows = []
        
        # 1. Create Large Chunks (Parents)
        large_chunks = self.text_splitter_large.split_documents(docs)
        
        for i, parent_doc in enumerate(large_chunks):
            parent_id = f"{filename}_p{i}"
            
            # Create Parent Node
            parent_node = KnowledgeNode(
                id=parent_id,
                content=parent_doc.page_content,
                source_file=filename,
                chunk_type="large",
                parent_id=None,
                page=parent_doc.metadata.get("page", 0),
                category=category,
                tags=[filename.split('.')[-1]] if '.' in filename else []
            )
            rows.append(parent_node.to_dict())
            
            # 2. Create Small Chunks (Children) from this Parent
            child_docs = self.text_splitter_small.split_text(parent_doc.page_content)
            
            for j, child_text in enumerate(child_docs):
                child_id = f"{parent_id}_c{j}"
                
                child_node = KnowledgeNode(
                    id=child_id,
                    content=child_text,
                    source_file=filename,
                    chunk_type="small",
                    parent_id=parent_id,
                    page=parent_doc.metadata.get("page", 0),
                    category=category,
                    tags=["child"]
                )
                rows.append(child_node.to_dict())
                
        return rows
