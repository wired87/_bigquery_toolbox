"""
User-scoped Vertex AI RAG Corpus
Ensures each user has a corpus in metadata; creates and saves if missing.
Upserts uploaded files to the user's Vertex RAG corpus.
"""

import logging
import os
from pathlib import Path
from typing import Optional, Any, Callable

logger = logging.getLogger(__name__)

METADATA_KEY_CORPUS_ID = "vertex_rag_corpus_id"

# Vertex RAG upload_file max size (25 MB)
VRAG_UPLOAD_MAX_BYTES = 25 * 1024 * 1024


def ensure_user_vertex_rag_corpus(engine: Any) -> Optional[str]:
    """
    On sign-in: check METADATA for vertex_rag_corpus_id.
    If not present, create a Vertex AI RAG corpus for the user and save to METADATA.
    Returns corpus full resource name, or None on failure.
    """
    dataset_id = getattr(engine, "current_dataset_id", None)
    if not dataset_id:
        logger.warning("No current_dataset_id; cannot ensure user corpus")
        return None

    auth_manager = getattr(engine, "auth_manager", None)
    if not auth_manager or not hasattr(auth_manager, "get_metadata"):
        logger.warning("AuthManager missing get_metadata; cannot ensure user corpus")
        return None

    # Check if corpus already in metadata
    corpus_name = auth_manager.get_metadata(dataset_id, METADATA_KEY_CORPUS_ID)
    if corpus_name:
        logger.info("User %s already has Vertex RAG corpus", dataset_id)
        return corpus_name

    # Create corpus and save to metadata
    try:
        from .config import VRAGConfig
        from .corpus import CorpusManager

        config = VRAGConfig()
        config.project_id = config.project_id or getattr(engine, "pid", None)
        if not config.project_id:
            logger.warning("No project_id; cannot create Vertex RAG corpus")
            return None

        manager = CorpusManager(config)
        display_name = f"toolbox_{dataset_id}"[:63]  # Vertex display_name limit
        corpus = manager.create_corpus(
            display_name=display_name,
            description=f"RAG corpus for user {dataset_id}",
        )
        if not corpus or not hasattr(corpus, "name"):
            logger.warning(
                "Vertex RAG corpus creation failed for %s. Using local KB. "
                "Set VRAG_LOCATION=europe-west4 if region-restricted.",
                dataset_id,
            )
            return None

        corpus_name = corpus.name
        ok = auth_manager.set_metadata(dataset_id, METADATA_KEY_CORPUS_ID, corpus_name)
        if ok:
            logger.info("Created and saved Vertex RAG corpus for user %s: %s", dataset_id, corpus_name)
        else:
            logger.warning("Corpus created but failed to save to METADATA")

        return corpus_name
    except Exception as e:
        logger.warning(
            "ensure_user_vertex_rag_corpus failed for %s: %s. Using local KB.",
            dataset_id,
            str(e),
        )
        return None


def upsert_file_to_user_corpus(
    engine: Any,
    local_path: str,
    display_name: Optional[str] = None,
    status_callback: Optional[Callable[[str, str], None]] = None,
) -> bool:
    """
    Upsert an uploaded file to the user's Vertex AI RAG corpus.
    Uses rag.upload_file for files <= 25MB; for larger files uses GCS+import if bucket configured.
    Returns True if upsert succeeded, False otherwise. Failures are logged; does not raise.
    """
    def _status(msg: str, step: str = ""):
        logger.info("[VRAG upsert] %s", msg)
        print(f"[VRAG] {msg}")
        if status_callback:
            try:
                status_callback(msg, step)
            except Exception:
                pass

    dataset_id = getattr(engine, "current_dataset_id", None)
    if not dataset_id:
        logger.warning("[VRAG] No current_dataset_id; cannot upsert to corpus")
        return False

    auth_manager = getattr(engine, "auth_manager", None)
    if not auth_manager or not hasattr(auth_manager, "get_metadata"):
        logger.warning("[VRAG] AuthManager missing; cannot upsert to corpus")
        return False

    corpus_name = auth_manager.get_metadata(dataset_id, METADATA_KEY_CORPUS_ID)
    if not corpus_name:
        _status("No Vertex RAG corpus for user; ensuring one exists...", "vrag_setup")
        corpus_name = ensure_user_vertex_rag_corpus(engine)
    if not corpus_name:
        _status("Vertex RAG corpus unavailable; skipping upsert", "vrag_skip")
        return False

    path = Path(local_path)
    if not path.exists():
        logger.error("[VRAG] upsert_file: path not found: %s", local_path)
        return False

    size = path.stat().st_size
    disp = display_name or path.name

    try:
        import os
        creds_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "NOT SET")
        logger.info("[VRAG upsert] GOOGLE_APPLICATION_CREDENTIALS=%s (exists=%s)", creds_path, os.path.exists(creds_path) if creds_path != "NOT SET" else False)

        from .engine import VertexRAGEngine
        from .config import VRAGConfig

        config = VRAGConfig()
        config.project_id = config.project_id or getattr(engine, "pid", None)
        vrag = VertexRAGEngine(config=config, project_id=config.project_id)

        if size <= VRAG_UPLOAD_MAX_BYTES:
            _status(f"Upserting to Vertex RAG: {disp} ({size / 1024:.1f} KB)", "vrag_upload")
            rag_file = vrag.upload_file(
                corpus_name=corpus_name,
                path=path,
                display_name=disp,
                description=f"Uploaded from BigQuery Toolbox",
            )
            if rag_file:
                _status(f"Vertex RAG upsert OK: {disp}", "vrag_done")
                return True
            _status(f"Vertex RAG upload failed for {disp}; local KB is primary", "vrag_fallback")
            return False

        # Larger file: use GCS + import if bucket configured
        bucket = getattr(config, "gcs_bucket", None) or os.getenv("VRAG_GCS_BUCKET")
        if not bucket:
            _status(
                f"File {disp} exceeds 25MB; set VRAG_GCS_BUCKET for large file support. Skipping Vertex RAG.",
                "vrag_skip",
            )
            return False

        _status(f"Uploading {disp} to GCS for Vertex RAG import...", "vrag_gcs")
        from google.cloud import storage
        client = storage.Client(project=config.project_id)
        bucket_obj = client.bucket(bucket)
        blob_name = f"vrag_uploads/{dataset_id}/{disp}"
        blob = bucket_obj.blob(blob_name)
        blob.upload_from_filename(str(path))
        gcs_uri = f"gs://{bucket}/{blob_name}"
        _status(f"Importing {gcs_uri} into Vertex RAG...", "vrag_import")
        count = vrag.import_files(corpus_name, [gcs_uri])
        if count is not None:
            _status(f"Vertex RAG import OK: {disp}", "vrag_done")
            return True
        _status(f"Vertex RAG import failed for {disp}", "vrag_fallback")
        return False

    except ImportError as e:
        logger.warning("[VRAG] Vertex RAG engine not available: %s", e)
        _status("Vertex RAG not available; using local KB only", "vrag_fallback")
        return False
    except Exception as e:
        logger.exception("[VRAG] upsert_file_to_user_corpus failed: %s", e)
        _status(f"Vertex RAG upsert failed: {e}; local KB is primary", "vrag_fallback")
        return False
