"""
RAGWorkflow - Implements all methods from chat.py within a class.
Integrates with engine, user metadata, and Vertex AI RAG Engine.
Use for: login corpus check, file upload to corpus, RAG-based chat.
"""
import asyncio
import logging
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from google import genai
from google.genai.types import GenerateContentConfig, Retrieval, Tool, VertexRagStore

logger = logging.getLogger(__name__)

# Timeout for generate_response. Prevents "runs forever" hangs.
GENERATE_RESPONSE_TIMEOUT = float(os.environ.get("VRAG_RESPONSE_TIMEOUT", "75"))
DEFAULT_RAG_MODEL = os.environ.get("VRAG_GEN_MODEL", "gemini-2.0-flash-001")


class RAGWorkflow:
    """
    RAG workflow: User input -> Query corpus with defined Tool -> Response.

    Chat pipe: process_chat() -> generate_response() (genai Tool only).
    Ingestion logic kept for sidebar: upload_bytes_to_corpus, upload_file_to_corpus, etc.
    """

    def __init__(self, engine: Any, rag_core: Any = None):
        self.engine = engine
        self.rag_core = rag_core
        self._project_id: Optional[str] = getattr(engine, "pid", None)
        self._corpus_name: Optional[str] = None
        self._genai_client: Optional[Any] = None

    def _get_vrag_location(self) -> str:
        """Region where RAG corpus lives (must match corpus creation)."""
        try:
            from vrag.config import VRAGConfig
            return VRAGConfig().location
        except ImportError:
            return os.environ.get("VRAG_LOCATION", "europe-west4")

    def _get_genai_client(self):
        """Lazy-init genai Client for Vertex RAG. Location must match corpus region."""
        if self._genai_client is None:
            project = self._get_project_id()
            location = self._get_vrag_location()
            self._genai_client = genai.Client(
                vertexai=True,
                project=project,
                location=location,
            )
        return self._genai_client

    def _build_rag_retrieval_tool(
        self,
        corpus_name: str,
        similarity_top_k: int = 10,
        vector_distance_threshold: float = 0.5,
    ) -> Tool:
        """Build RAG retrieval Tool for the given corpus. Call per query request."""
        return Tool(
            retrieval=Retrieval(
                vertex_rag_store=VertexRagStore(
                    rag_corpora=[corpus_name],
                    similarity_top_k=similarity_top_k,
                    vector_distance_threshold=vector_distance_threshold,
                )
            )
        )

    def _get_project_id(self) -> Optional[str]:
        return self._project_id or getattr(self.engine, "pid", None) or os.environ.get("GOOGLE_CLOUD_PROJECT")

    def _get_corpus_name(self) -> Optional[str]:
        """Get user's corpus name from metadata or create if missing."""
        if self._corpus_name:
            return self._corpus_name
        dataset_id = getattr(self.engine, "current_dataset_id", None)
        if not dataset_id:
            return None
        auth = getattr(self.engine, "auth_manager", None)
        if not auth or not hasattr(auth, "get_metadata"):
            return None
        corpus_name = auth.get_metadata(dataset_id, "vertex_rag_corpus_id")
        if corpus_name:
            self._corpus_name = corpus_name
            return corpus_name
        # Ensure corpus exists (create + save to metadata)
        corpus_name = self.ensure_user_corpus()
        if corpus_name:
            self._corpus_name = corpus_name
        return corpus_name

    def ensure_user_corpus(self) -> Optional[str]:
        """Check/create RAG corpus and save in user's metadata table. Called on login."""
        try:
            from vrag.user_corpus import ensure_user_vertex_rag_corpus
            return ensure_user_vertex_rag_corpus(self.engine)
        except ImportError as e:
            logger.warning("VRAG not available for ensure_user_corpus: %s", e)
            return None

    def upload_file_to_corpus(
        self,
        file_path: str,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Optional[Any]:
        """Upload a single file to the user's RAG corpus. Supports all file types (PDF, text, etc)."""
        def _status(msg: str, step: str = ""):
            if status_callback:
                try:
                    status_callback(msg, step)
                except Exception:
                    pass
            logger.info("[RAGWorkflow] %s", msg)

        corpus_name = self._get_corpus_name()
        if not corpus_name:
            _status("No corpus; ensure login and corpus setup.", "error")
            return None

        path = Path(file_path)
        if not path.exists():
            _status(f"File not found: {file_path}", "error")
            return None

        try:
            from vrag.user_corpus import upsert_file_to_user_corpus
            ok = upsert_file_to_user_corpus(
                self.engine,
                str(path),
                display_name=display_name or path.name,
                status_callback=status_callback,
            )
            return ok
        except ImportError:
            _status("VRAG unavailable; use vrag package.", "error")
            return None

    def upload_bytes_to_corpus(
        self,
        filename: str,
        content: bytes,
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Optional[Any]:
        """Upload file content (bytes) to corpus. Writes to temp file then uploads."""
        with tempfile.NamedTemporaryFile(delete=False, suffix=Path(filename).suffix) as f:
            f.write(content)
            temp_path = f.name
        try:
            return self.upload_file_to_corpus(
                temp_path,
                display_name=filename,
                description=f"Uploaded {filename}",
                status_callback=status_callback,
            )
        finally:
            try:
                os.unlink(temp_path)
            except OSError:
                pass

    def import_files_from_gcs(
        self,
        gcs_uri: str,
        chunk_size: int = 1024,
        chunk_overlap: int = 100,
    ) -> Optional[Any]:
        """Import files from GCS bucket into the user's corpus."""
        corpus_name = self._get_corpus_name()
        if not corpus_name:
            return None
        try:
            from vrag.engine import VertexRAGEngine
            from vrag.config import VRAGConfig
            cfg = VRAGConfig()
            cfg.project_id = cfg.project_id or self._get_project_id()
            vrag = VertexRAGEngine(config=cfg, project_id=cfg.project_id)
            return vrag.import_files(corpus_name, [gcs_uri], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        except ImportError:
            return None

    def import_files_from_google_drive(self, folder_id: str, chunk_size: int = 512, chunk_overlap: int = 50) -> Optional[Any]:
        """Import files from Google Drive folder into the user's corpus."""
        corpus_name = self._get_corpus_name()
        if not corpus_name:
            return None
        try:
            from vrag.engine import VertexRAGEngine
            from vrag.config import VRAGConfig
            cfg = VRAGConfig()
            cfg.project_id = cfg.project_id or self._get_project_id()
            vrag = VertexRAGEngine(config=cfg, project_id=cfg.project_id)
            uri = f"https://drive.google.com/drive/folders/{folder_id}"
            return vrag.import_files(corpus_name, [uri], chunk_size=chunk_size, chunk_overlap=chunk_overlap)
        except ImportError:
            return None

    def direct_retrieval_query(
        self,
        query_text: str,
        top_k: int = 10,
        vector_distance_threshold: float = 0.5,
    ) -> Optional[Any]:
        """Perform direct context retrieval from the RAG corpus (no model)."""
        corpus_name = self._get_corpus_name()
        if not corpus_name:
            return None
        try:
            from vrag.engine import VertexRAGEngine
            from vrag.config import VRAGConfig
            cfg = VRAGConfig()
            cfg.project_id = cfg.project_id or self._get_project_id()
            vrag = VertexRAGEngine(config=cfg, project_id=cfg.project_id)
            return vrag.retrieval_query(corpus_name, query_text, top_k=top_k)
        except ImportError:
            return None

    def list_files(self) -> list:
        """List files in the user's RAG corpus. Returns list of dicts with 'name', 'display_name'."""
        corpus_name = self._get_corpus_name()
        if not corpus_name:
            return []
        try:
            from vrag.engine import VertexRAGEngine
            from vrag.config import VRAGConfig
            cfg = VRAGConfig()
            cfg.project_id = cfg.project_id or self._get_project_id()
            vrag = VertexRAGEngine(config=cfg, project_id=cfg.project_id)
            return vrag.list_files(corpus_name) or []
        except ImportError:
            return []

    def delete_file(self, rag_file_name: str) -> bool:
        """Delete a file from the RAG corpus by full resource name."""
        try:
            from vrag.engine import VertexRAGEngine
            from vrag.config import VRAGConfig
            cfg = VRAGConfig()
            cfg.project_id = cfg.project_id or self._get_project_id()
            vrag = VertexRAGEngine(config=cfg, project_id=cfg.project_id)
            return vrag.delete_file(rag_file_name)
        except ImportError:
            return False

    def build_rag_prompt(
        self,
        user_query: str,
        last_n_qa_pairs: int = 4,
        include_file_names: bool = True,
        token_usage: Optional[Dict[str, int]] = None,
        model_name: Optional[str] = None,
    ) -> str:
        """
        Generate a highly efficient RAG prompt for an LLM.
        Uses Vertex AI RAG engine: list_files (file names), chat history (last N Q&A),
        token usage. Compact format to minimize token cost.
        """
        sections: List[str] = []

        # 1. Corpus file names (vertexai.rag.list_files)
        if include_file_names:
            files = self.list_files()
            if files:
                names = [
                    (f.get("display_name") or f.get("name", "").split("/")[-1] or "file").strip()
                    for f in files
                ]
                names = [n for n in names if n]
                if names:
                    sections.append(f"[CORPUS] {', '.join(names)}")

        # 2. Last N Q&A pairs (engine.db chat history)
        session_id = getattr(self.engine, "current_user_email", None)
        if session_id:
            db = getattr(self.engine, "db", None)
            if db and hasattr(db, "get_recent_history"):
                limit = last_n_qa_pairs * 2
                history = db.get_recent_history(session_id, limit=limit)
                pairs: List[str] = []
                i = 0
                while i + 1 < len(history):
                    u, a = history[i], history[i + 1]
                    if u.get("role") == "user" and a.get("role") == "assistant":
                        q = (u.get("content") or "").strip()[:180]
                        ans = (a.get("content") or "").strip()[:250]
                        if q and ans:
                            pairs.append(f"Q:{q} A:{ans}")
                    i += 1
                if pairs:
                    recent = "; ".join(pairs[-last_n_qa_pairs:])
                    sections.append(f"[RECENT] {recent}")

        # 3. Token usage (from genai usage_metadata)
        if token_usage:
            inp = token_usage.get("input_tokens") or token_usage.get("prompt_tokens") or 0
            out = token_usage.get("output_tokens") or token_usage.get("candidates_tokens") or 0
            total = token_usage.get("total_tokens") or (inp + out)
            if total:
                sections.append(f"[USAGE] in={inp} out={out} tot={total}")

        # 4. Model
        if model_name:
            sections.append(f"[MODEL] {model_name}")

        header = " ".join(sections) if sections else ""
        if header:
            return f"{header}\n\n{user_query.strip()}"
        return user_query.strip()

    def _run_async(self, coro, timeout: float):
        """Run async coroutine with timeout. Works in sync context (Streamlit)."""
        wrapped = asyncio.wait_for(coro, timeout=timeout)
        try:
            return asyncio.run(wrapped)
        except RuntimeError:
            loop = asyncio.get_running_loop()
            return asyncio.run_coroutine_threadsafe(wrapped, loop).result(timeout=timeout + 10)

    async def process_chat(
        self,
        prompt: str,
        mode: str = "Auto",
        status_callback: Optional[Callable[[str, str], None]] = None,
    ) -> Dict[str, Any]:
        """
        Chat pipeline: User input -> Query RAG corpus with defined tool -> Response.
        Ingestion/SQL/vector logic kept for sidebar/future use, not in this pipe.
        """
        if not prompt.strip():
            return {"response_text": "Please enter a message.", "intent": "none"}
        return self.generate_response(prompt, status_callback=status_callback)

    def generate_response(
        self,
        prompt: str,
        status_callback: Optional[Callable[[str, str], None]] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        User input -> Query RAG corpus with defined Tool -> Response.
        No ingestion in pipe. Vrag/ingestion logic kept elsewhere for sidebar use.
        """
        result = {"response_text": "", "intent": "query_similarity_search", "traceability": None}
        t = timeout or GENERATE_RESPONSE_TIMEOUT

        corpus_name = self._get_corpus_name()
        if not corpus_name:
            result["response_text"] = "No RAG corpus. Please ensure you are logged in and corpus is set up."
            return result

        # Build Tool for this request (corpus resolved per query)
        rag_tool = self._build_rag_retrieval_tool(corpus_name)
        client = self._get_genai_client()

        # Use efficient RAG prompt with metadata (files, recent QA, model)
        full_prompt = self.build_rag_prompt(
            user_query=prompt,
            last_n_qa_pairs=4,
            include_file_names=True,
            token_usage=getattr(self, "_last_token_usage", None),
            model_name=DEFAULT_RAG_MODEL,
        )

        def _genai_generate():
            response = client.models.generate_content(
                model=DEFAULT_RAG_MODEL,
                contents=full_prompt,
                config=GenerateContentConfig(tools=[rag_tool]),
            )
            if response and hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                self._last_token_usage = {
                    "input_tokens": getattr(um, "prompt_token_count", None) or getattr(um, "promptTokenCount", None) or 0,
                    "output_tokens": getattr(um, "candidates_token_count", None) or getattr(um, "candidatesTokenCount", None) or 0,
                    "total_tokens": getattr(um, "total_token_count", None) or getattr(um, "totalTokenCount", None) or 0,
                }
            return response.text if response and response.text else ""

        try:
            if status_callback:
                status_callback("🔍 Querying RAG corpus...", "rag")
            text = _genai_generate()
            if text:
                result["response_text"] = text
                result["traceability"] = {"source": "genai_vertex_rag"}
                return result
            result["response_text"] = "No response from RAG model."
        except (asyncio.TimeoutError, TimeoutError) as e:
            logger.warning("RAG query timed out: %s", e)
            result["response_text"] = f"RAG query timed out after {t}s. Please try again."
            return result
        except Exception as e:
            logger.warning("RAG query failed: %s", e)
            result["response_text"] = f"RAG query failed: {e}. Please ensure corpus is ready."
            return result

        return result
