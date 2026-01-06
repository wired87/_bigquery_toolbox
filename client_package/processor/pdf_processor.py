from typing import List
from langchain_community.document_loaders import PyPDFLoader
from langchain_core.documents import Document
import io

from .base import BaseProcessor

class PdfProcessor(BaseProcessor):
    def load_from_path(self, file_path: str) -> List[Document]:
        try:
            return PyPDFLoader(file_path).load()
        except Exception as e:
            self.console.print(f"[red]❌ Error loading PDF {file_path}: {e}[/red]")
            return []

    def load_from_bytes(self, filename: str, content: bytes) -> List[Document]:
        try:
            # Use pypdf directly with BytesIO
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
        except Exception as e:
            self.console.print(f"[red]❌ Error loading PDF bytes for {filename}: {e}[/red]")
            return []
