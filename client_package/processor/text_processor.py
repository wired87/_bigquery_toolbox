from typing import List
from langchain_community.document_loaders import TextLoader
from langchain_core.documents import Document

from .base import BaseProcessor

class TextProcessor(BaseProcessor):
    def load_from_path(self, file_path: str) -> List[Document]:
        try:
            return TextLoader(file_path, autodetect_encoding=True).load()
        except Exception as e:
            self.console.print(f"[red]❌ Error loading Text {file_path}: {e}[/red]")
            return []

    def load_from_bytes(self, filename: str, content: bytes) -> List[Document]:
        try:
            text = content.decode("utf-8", errors="ignore")
            return [Document(page_content=text, metadata={"source": filename})]
        except Exception as e:
            self.console.print(f"[red]❌ Error loading Text bytes for {filename}: {e}[/red]")
            return []
