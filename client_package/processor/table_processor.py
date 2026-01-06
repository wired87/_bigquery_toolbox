from typing import List
from langchain_community.document_loaders import CSVLoader
from langchain_core.documents import Document
import io

from .base import BaseProcessor

class TableProcessor(BaseProcessor):
    def load_from_path(self, file_path: str) -> List[Document]:
        try:
            return CSVLoader(file_path).load()
        except Exception as e:
            self.console.print(f"[red]❌ Error loading CSV {file_path}: {e}[/red]")
            return []

    def load_from_bytes(self, filename: str, content: bytes) -> List[Document]:
        try:
            import pandas as pd
            df = pd.read_csv(io.BytesIO(content))
            text_content = df.to_string() # Simple representation
            return [Document(page_content=text_content, metadata={"source": filename})]
        except ImportError:
            # Fallback to plain text if pandas not available
            return [Document(page_content=content.decode('utf-8', errors='ignore'), metadata={"source": filename})]
        except Exception as e:
            self.console.print(f"[red]❌ Error loading CSV bytes for {filename}: {e}[/red]")
            return []
