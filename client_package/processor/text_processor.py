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

    def process_bytes(self, filename: str, content: bytes, category:str) -> List[Document]:
        try:
            text = content.decode("utf-8", errors="ignore")
            return [Document(page_content=text, metadata={"source": filename,"category":category})]
        except Exception as e:
            self.console.print(f"[red]❌ Error loading Text bytes for {filename}: {e}[/red]")
            return []
