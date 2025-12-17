import os
from typing import List, Dict, Any
from rich.console import Console
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.document_loaders import PyPDFLoader, CSVLoader, UnstructuredImageLoader, TextLoader
from langchain_core.documents import Document

from models import KnowledgeNode

class FileProcessor:
    def __init__(self):
        self.console = Console()
        self.text_splitter_small = RecursiveCharacterTextSplitter(chunk_size=200, chunk_overlap=50)
        self.text_splitter_large = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=0)

    def process_file(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Process a file and return a list of rows for BigQuery using KnowledgeNode schema.
        Implements Hierarchical Chunking and Basic Categorization.
        """
        self.console.print(f"[dim]📄 Processing {os.path.basename(file_path)}...[/dim]")
        
        docs = self._load_file(file_path)
        if not docs:
            return []

        rows = []
        file_name = os.path.basename(file_path)
        
        # Basic Categorization based on extension (Placeholder for AI classification)
        category = "Document"
        if file_path.endswith(".csv"): category = "Data"
        elif file_path.endswith((".py", ".json", ".sql")): category = "Code"
        
        # 1. Create Large Chunks (Parents)
        large_chunks = self.text_splitter_large.split_documents(docs)
        
        for i, parent_doc in enumerate(large_chunks):
            parent_id = f"{file_name}_p{i}"
            
            # Create Parent Node
            parent_node = KnowledgeNode(
                id=parent_id,
                content=parent_doc.page_content,
                source_file=file_name,
                chunk_type="large",
                parent_id=None,
                page=parent_doc.metadata.get("page", 0),
                category=category,
                tags=[file_name.split('.')[1]] # Tag with extension
            )
            rows.append(parent_node.to_dict())
            
            # 2. Create Small Chunks (Children) from this Parent
            child_docs = self.text_splitter_small.split_text(parent_doc.page_content)
            
            for j, child_text in enumerate(child_docs):
                child_id = f"{parent_id}_c{j}"
                
                child_node = KnowledgeNode(
                    id=child_id,
                    content=child_text,
                    source_file=file_name,
                    chunk_type="small",
                    parent_id=parent_id,
                    page=parent_doc.metadata.get("page", 0),
                    category=category,
                    tags=["child"]
                )
                rows.append(child_node.to_dict())
                
        self.console.print(f"[green]✓ Generated {len(rows)} structured chunks from {file_name}[/green]")
        return rows

    def process_bytes(self, filename: str, content: bytes) -> List[Dict[str, Any]]:
        """
        Process in-memory file content and return structured rows.
        """
        self.console.print(f"[dim]📄 Processing in-memory file: {filename}...[/dim]")
        
        docs = self._load_bytes(filename, content)
        if not docs:
            return []

        rows = []
        
        # Basic Categorization
        category = "Document"
        if filename.endswith(".csv"): category = "Data"
        elif filename.endswith((".py", ".json", ".sql")): category = "Code"
        
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
                tags=[filename.split('.')[-1]]
            )
            rows.append(parent_node.to_dict())
            
            # 2. Create Small Chunks (Children)
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
                
        self.console.print(f"[green]✓ Generated {len(rows)} structured chunks from {filename}[/green]")
        return rows

    def _load_bytes(self, filename: str, content: bytes) -> List[Document]:
        import io
        try:
            if filename.lower().endswith(".pdf"):
                # Use pypdf directly with BytesIO
                try:
                    from pypdf import PdfReader
                    reader = PdfReader(io.BytesIO(content))
                    docs = []
                    for i, page in enumerate(reader.pages):
                        text = page.extract_text()
                        if text:
                            docs.append(Document(page_content=text, metadata={"page": i, "source": filename}))
                    return docs
                except ImportError:
                    self.console.print("[red]❌ pypdf not installed.[/red]")
                    return []
                    
            elif filename.lower().endswith(".csv"):
                # Use pandas or csv module
                try:
                    import pandas as pd
                    df = pd.read_csv(io.BytesIO(content))
                    text_content = df.to_string() # Simple representation
                    return [Document(page_content=text_content, metadata={"source": filename})]
                except ImportError:
                    return [Document(page_content=content.decode('utf-8', errors='ignore'), metadata={"source": filename})]
            
            else:
                # Treat as text
                text = content.decode("utf-8", errors="ignore")
                return [Document(page_content=text, metadata={"source": filename})]
                
        except Exception as e:
            self.console.print(f"[red]❌ Error loading bytes for {filename}: {e}[/red]")
            return []

    def _load_file(self, file_path: str) -> List[Document]:
        try:
            if file_path.endswith(".pdf"):
                return PyPDFLoader(file_path).load()
            elif file_path.endswith(".csv"):
                return CSVLoader(file_path).load()
            elif file_path.endswith((".jpg", ".png", ".jpeg")):
                # Requires 'unstructured' and 'opencv-python' usually, might fail if not installed
                # We'll try basic loader or skip
                try:
                    return UnstructuredImageLoader(file_path).load()
                except ImportError:
                    self.console.print("[yellow]⚠️  Image processing requires 'unstructured' and 'opencv-python'. Skipping.[/yellow]")
                    return []
            else:
                return TextLoader(file_path).load()
        except Exception as e:
            self.console.print(f"[red]❌ Error loading {file_path}: {e}[/red]")
            return []
