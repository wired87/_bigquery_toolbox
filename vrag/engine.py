"""
Vertex AI RAG Engine - Production-ready wrapper
Implements all Vertex AI RAG Engine functionalities via official Python client.
Robust error handling, retries, and console/engine logging.
Local functionality used as last fallback.
"""

import logging
import os
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from .config import VRAGConfig
from pathlib import Path
from unittest.mock import patch

logger = logging.getLogger(__name__)

# Vertex RAG upload_file limit (bytes)
VRAG_UPLOAD_FILE_MAX_BYTES = 25 * 1024 * 1024  # 25 MB
DEFAULT_RETRY_ATTEMPTS = 2
DEFAULT_RETRY_DELAY_SEC = 2.0

# Scope required by Vertex RAG upload_file (rag_data.py uses auth.default() which may return limited scopes)
VRAG_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
VRAG_VERBOSE = os.environ.get("VRAG_VERBOSE", "true").lower() in ("true", "1", "yes")

# Configure VRAG logging based on env (increase terminal output when troubleshooting)
if VRAG_VERBOSE:
    logging.getLogger("vrag").setLevel(logging.DEBUG)
    logging.getLogger(__name__).setLevel(logging.DEBUG)


def _log_engine(msg: str, level: str = "info", verbose_only: bool = False) -> None:
    """Log to both module logger and console. Set verbose_only=True for debug details."""
    if verbose_only and not VRAG_VERBOSE:
        return
    log_fn = getattr(logger, level, logger.info)
    log_fn(msg)
    print(f"[VRAG] {msg}")


def _load_scoped_credentials():
    """
    Load service account credentials with cloud-platform scope.
    Workaround for vertexai.rag.rag_data.upload_file which ignores vertexai.init()
    credentials and uses auth.default() - often returning creds with insufficient scopes.
    See: https://github.com/googleapis/python-aiplatform/issues/6097
    """
    from google.oauth2 import service_account
    path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not path or not os.path.exists(path):
        _log_engine(f"No GOOGLE_APPLICATION_CREDENTIALS or file not found; auth.default will be used", "warning")
        return None
    try:
        creds = service_account.Credentials.from_service_account_file(
            path,
            scopes=[VRAG_CLOUD_PLATFORM_SCOPE],
        )
        _log_engine(f"Loaded SA credentials with {VRAG_CLOUD_PLATFORM_SCOPE} for upload_file", "debug", verbose_only=True)
        return creds
    except Exception as e:
        _log_engine(f"Failed to load scoped SA credentials: {e}", "warning")
        return None


def _safe_call(fn, *args, fallback=None, operation: str = "operation", **kwargs) -> Any:
    """Execute with retry and robust error handling. Returns fallback on failure."""
    last_err = None
    for attempt in range(1, DEFAULT_RETRY_ATTEMPTS + 1):
        try:
            _log_engine(f"VRAG {operation} attempt {attempt}/{DEFAULT_RETRY_ATTEMPTS}...", "debug", verbose_only=True)
            result = fn(*args, **kwargs)
            _log_engine(f"VRAG {operation} attempt {attempt} succeeded", "debug", verbose_only=True)
            return result
        except Exception as e:
            last_err = e
            err_detail = str(e)
            if "invalid_scope" in err_detail or "RefreshError" in err_detail:
                _log_engine(
                    f"VRAG {operation} attempt {attempt}/{DEFAULT_RETRY_ATTEMPTS} failed (OAuth scope): {e}. "
                    "Ensure GOOGLE_APPLICATION_CREDENTIALS points to SA with cloud-platform scope.",
                    "warning",
                )
            else:
                _log_engine(
                    f"VRAG {operation} attempt {attempt}/{DEFAULT_RETRY_ATTEMPTS} failed: {e}",
                    "warning",
                )
            if attempt < DEFAULT_RETRY_ATTEMPTS:
                _log_engine(f"VRAG retrying in {DEFAULT_RETRY_DELAY_SEC}s...", "debug", verbose_only=True)
                time.sleep(DEFAULT_RETRY_DELAY_SEC)
    _log_engine(f"VRAG {operation} failed after {DEFAULT_RETRY_ATTEMPTS} retries: {last_err}", "error")
    return fallback


class VertexRAGEngine:
    """
    Production-ready Vertex AI RAG Engine wrapper.
    All operations use robust error handling; failures return None/empty with logging.
    """

    def __init__(self, config: Optional["VRAGConfig"] = None, project_id: Optional[str] = None):
        from .config import VRAGConfig
        self.config = config or VRAGConfig()
        self.config.project_id = project_id or self.config.project_id
        self._init_done = False

    def _ensure_init(self) -> bool:
        """Initialize Vertex AI with explicit credentials. Returns False on failure."""
        if self._init_done:
            return True
        try:
            import vertexai
            creds = _load_scoped_credentials()
            if creds:
                vertexai.init(
                    project=self.config.project_id,
                    location=self.config.location,
                    credentials=creds,
                )
                _log_engine("Vertex AI initialized with explicit SA credentials (cloud-platform scope)")
            else:
                vertexai.init(project=self.config.project_id, location=self.config.location)
                _log_engine("Vertex AI initialized (using default credentials)")
            self._init_done = True
            return True
        except Exception as e:
            _log_engine(f"Vertex AI init failed: {e}", "error")
            return False

    # --- Corpus operations ---

    def create_corpus(
        self,
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Any]:
        """Create a RAG corpus."""
        def _create():
            from vertexai import rag
            backend_config = rag.RagVectorDbConfig(
                rag_embedding_model_config=self.config.to_rag_embedding_config()
            )
            return rag.create_corpus(
                display_name=display_name or self.config.corpus_display_name,
                description=description or self.config.corpus_description,
                backend_config=backend_config,
            )

        if not self._ensure_init():
            return None
        corpus = _safe_call(_create, fallback=None, operation="create_corpus")
        if corpus:
            _log_engine(f"Created corpus: {getattr(corpus, 'name', corpus)}")
        return corpus

    def get_corpus(self, corpus_name: str) -> Optional[Any]:
        """Get corpus metadata."""
        def _get():
            from vertexai import rag
            return rag.get_corpus(name=corpus_name)

        if not self._ensure_init():
            return None
        return _safe_call(_get, fallback=None, operation="get_corpus")

    def list_corpora(self) -> List[Dict[str, Any]]:
        """List all corpora."""
        def _list():
            from vertexai import rag
            corpora = list(rag.list_corpora())
            return [
                {
                    "name": c.name,
                    "display_name": getattr(c, "display_name", ""),
                    "description": getattr(c, "description", ""),
                }
                for c in corpora
            ]

        if not self._ensure_init():
            return []
        result = _safe_call(_list, fallback=[], operation="list_corpora")
        _log_engine(f"Listed {len(result)} corpora")
        return result

    def delete_corpus(self, corpus_name: str) -> bool:
        """Delete a corpus."""
        def _delete():
            from vertexai import rag
            rag.delete_corpus(name=corpus_name)

        if not self._ensure_init():
            return False
        ok = _safe_call(_delete, fallback=False, operation="delete_corpus")
        if ok is not False:
            _log_engine(f"Deleted corpus: {corpus_name}")
            return True
        return False

    # --- File operations ---

    def upload_file(
        self,
        corpus_name: str,
        path: Union[str, Path],
        display_name: Optional[str] = None,
        description: Optional[str] = None,
    ) -> Optional[Any]:
        """
        Upload a local file to RAG corpus. Max 25 MB.
        Returns RagFile or None.
        Uses auth.default monkeypatch to fix invalid_scope (rag_data ignores vertexai.init credentials).
        """
        path = Path(path)
        if not path.exists():
            _log_engine(f"upload_file: path not found: {path}", "error")
            return None
        size = path.stat().st_size
        _log_engine(f"upload_file: {path.name} ({size / 1024:.1f} KB) -> corpus", "info")
        if size > VRAG_UPLOAD_FILE_MAX_BYTES:
            _log_engine(
                f"upload_file: file {path.name} exceeds 25MB ({size / 1e6:.1f} MB); use GCS+import for larger files",
                "warning",
            )
            return None

        def _upload():
            from vertexai import rag
            scoped_creds = _load_scoped_credentials()
            project_id = self.config.project_id

            def _patched_auth_default(scopes=None, quota_project_id=None, request=None, *args, **kwargs):
                if scoped_creds and project_id:
                    return scoped_creds, project_id
                import google.auth
                return google.auth.default(
                    scopes=scopes, quota_project_id=quota_project_id, request=request, *args, **kwargs
                )

            # rag_data.upload_file calls auth.default() internally; patch to use SA with cloud-platform scope
            with patch("vertexai.rag.rag_data.auth.default", side_effect=_patched_auth_default):
                _log_engine(f"upload_file: calling rag.upload_file (patched auth)", "debug", verbose_only=True)
                return rag.upload_file(
                    corpus_name=corpus_name,
                    path=str(path),
                    display_name=display_name or path.name,
                    description=description or f"Uploaded {path.name}",
                )

        if not self._ensure_init():
            return None
        rag_file = _safe_call(_upload, fallback=None, operation="upload_file")
        if rag_file:
            _log_engine(f"Uploaded {path.name} to corpus successfully")
        return rag_file

    def import_files(
        self,
        corpus_name: str,
        paths: List[str],
        chunk_size: Optional[int] = None,
        chunk_overlap: Optional[int] = None,
    ) -> Optional[int]:
        """Import files from GCS or Drive URIs."""
        def _import():
            from vertexai import rag
            cfg = rag.TransformationConfig(
                chunking_config=rag.ChunkingConfig(
                    chunk_size=chunk_size or self.config.chunk_size,
                    chunk_overlap=chunk_overlap or self.config.chunk_overlap,
                ),
            )
            return rag.import_files(
                corpus_name=corpus_name,
                paths=paths,
                transformation_config=cfg,
                max_embedding_requests_per_min=self.config.max_embedding_requests_per_min,
            )

        if not self._ensure_init():
            return None
        result = _safe_call(_import, fallback=None, operation="import_files")
        if result is not None:
            _log_engine(f"Imported files into corpus (count: {result})")
        return result

    def list_files(self, corpus_name: str) -> List[Dict[str, Any]]:
        """List files in a corpus."""
        def _list():
            from vertexai import rag
            files = list(rag.list_files(corpus_name=corpus_name))
            return [
                {"name": f.name, "display_name": getattr(f, "display_name", "")}
                for f in files
            ]

        if not self._ensure_init():
            return []
        return _safe_call(_list, fallback=[], operation="list_files")

    def delete_file(self, rag_file_name: str) -> bool:
        """Delete a RAG file by full resource name."""
        def _delete():
            from vertexai import rag
            rag.delete_file(name=rag_file_name)

        if not self._ensure_init():
            return False
        ok = _safe_call(_delete, fallback=False, operation="delete_file")
        if ok is not False:
            _log_engine(f"Deleted RAG file: {rag_file_name}")
            return True
        return False

    # --- Retrieval & generation ---

    def retrieval_query(
        self,
        corpus_name: str,
        text: str,
        top_k: Optional[int] = None,
    ) -> Optional[Any]:
        """Direct retrieval from corpus."""
        def _retrieve():
            from vertexai import rag
            cfg = rag.RagRetrievalConfig(
                top_k=top_k or self.config.top_k,
                filter=rag.Filter(vector_distance_threshold=self.config.vector_distance_threshold),
            )
            return rag.retrieval_query(
                rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
                text=text,
                rag_retrieval_config=cfg,
            )

        if not self._ensure_init():
            return None
        return _safe_call(_retrieve, fallback=None, operation="retrieval_query")

    def generate_with_rag(
        self,
        corpus_name: str,
        query: str,
    ) -> Optional[str]:
        """Generate response using Gemini with RAG retrieval tool."""
        def _generate():
            from vertexai import rag
            from vertexai.generative_models import GenerativeModel, Tool
            cfg = rag.RagRetrievalConfig(
                top_k=self.config.top_k,
                filter=rag.Filter(vector_distance_threshold=self.config.vector_distance_threshold),
            )
            tool = Tool.from_retrieval(
                retrieval=rag.Retrieval(
                    source=rag.VertexRagStore(
                        rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
                        rag_retrieval_config=cfg,
                    ),
                ),
            )
            model = GenerativeModel(model_name=self.config.generation_model, tools=[tool])
            response = model.generate_content(query)
            return response.text if response and response.text else None

        if not self._ensure_init():
            return None
        return _safe_call(_generate, fallback=None, operation="generate_with_rag")
