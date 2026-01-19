import logging
import asyncio
import os
import re
import glob
from typing import Dict, Any, Optional, Set, List
from error_handler import log_exception

logger = logging.getLogger(__name__)

class IngestHandler:
    def __init__(self, engine):
        self.engine = engine

    async def handle(self, user_input: str, status_callback=None) -> Dict[str, Any]:
        """
        Handles the workflow for 'upload_by_path' intent.
        """
        async def update_status(message, step=""):
            if status_callback: await status_callback(message, step)

        result = {
            "intent": "upload_by_path",
            "response_text": "",
            "source_citation": None,
            "traceability": None
        }

        print("📂 Processing file upload")
        await update_status("📂 Detecting path and starting ingestion...", "ingest")
        
        try:
            # Call internal method instead of engine's
            ingest_res = await self.ingest_from_path(user_input, status_callback)
            print("ingest_res", ingest_res)
            result["response_text"] = ingest_res.get("response_text", "Ingestion started.")
            if "traceability" in ingest_res:
                result["traceability"] = ingest_res["traceability"]
            print("✅ File upload completed")
            
        except Exception as e:
            log_exception(e, "File Upload")
            await update_status(f"❌ Upload failed", "error")
            result["response_text"] = f"Upload failed: {str(e)}"

        return result

    async def ingest_from_path(
            self,
            path_input: str,
            status_callback=None, 
            ingestion_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Ingests files from a given path (file or directory).
        Auto-detects recursive directories and extracts 'relative parent directory' metadata.
        """
        
        # 1. Path Extraction Logic (Robust)
        target_path = path_input.strip().strip('"\'')
        
        # Strip common keywords
        for kw in ["upsert", "upload", "ingest", "data", "from"]:
            pattern = re.compile(f'^{kw}\\s+', re.IGNORECASE)
            target_path = pattern.sub('', target_path).strip()
        
        if not os.path.exists(target_path):
             path_match = re.search(r'(?:["\'])(.*?)(?:["\'])|(?:\s)((?:[a-zA-Z]:[\\/]|[.\\/])[^\s]+)', path_input)
             if path_match:
                 match = path_match.group(1) if path_match.group(1) else path_match.group(2)
                 if os.path.exists(match):
                    target_path = match
        
        if not target_path or not os.path.exists(target_path):
            potential_path = path_input.split()[-1].strip('"\'')
            if os.path.exists(potential_path):
                target_path = potential_path
        
        if not target_path or not os.path.exists(target_path):
             return {
                "intent": "command_upload_by_path",
                "response_text": f"❌ Path not found: `{target_path or path_input}`. Please check the path and try again."
             }

        abs_path = os.path.abspath(target_path)
        items_to_process = [] 

        if status_callback: await status_callback(f"📂 Scanning `{abs_path}`...", "scan")
        
        if os.path.isfile(abs_path):
            items_to_process.append((abs_path, "root"))
        else:
            for root, dirs, files in os.walk(abs_path):
                for file in files:
                    full_path = os.path.join(root, file)
                    try:
                        rel_path = os.path.relpath(full_path, abs_path)
                        parts = rel_path.split(os.sep)
                        if len(parts) > 1:
                            relative_parent_dir = parts[0]
                        else:
                            relative_parent_dir = "root"
                        items_to_process.append((full_path, relative_parent_dir))
                    except ValueError:
                        items_to_process.append((full_path, "unknown"))

        if not items_to_process:
             return {
                "intent": "command_upload_by_path",
                "response_text": f"⚠️ No files found in `{abs_path}`."
             }

        processed_count = 0
        errors = []
        
        if status_callback: await status_callback(f"🚀 Found {len(items_to_process)} files. Starting ingestion...", "start_ingest")
        
        for i, (fpath, parent_dir) in enumerate(items_to_process):
             fname = os.path.basename(fpath)
             if status_callback: await status_callback(f"[{i+1}/{len(items_to_process)}] Processing {fname} (Parent: {parent_dir})...", "process")
             
             try:
                 with open(fpath, "rb") as f:
                     content = f.read()
                 
                 metadata = {"relative_parent_dir": parent_dir}
                 msg = await self.handle_file_upload(fname, content, status_callback=None, metadata=metadata, ingestion_config=ingestion_config)
                 
                 if "❌" in msg:
                     errors.append(f"{fname}: {msg}")
                 else:
                     processed_count += 1
                     
             except Exception as e:
                 errors.append(f"{fname}: {str(e)}")
        
        report = f"✅ Successfully processed {processed_count}/{len(items_to_process)} files from `{abs_path}`."
        if errors:
            report += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
            
        return {
             "intent": "command_upload_by_path",
             "response_text": report
        }

    async def handle_file_upload(self, filename: str, content: bytes, status_callback=None, metadata: Optional[Dict[str, Any]] = None, ingestion_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Processes an uploaded file via Production Pipeline.
        """
        async def update_status(message: str, step: str = ""):
            if status_callback: await status_callback(message, step)

        TEMP_STORE = "temp_store"
        if not os.path.exists(TEMP_STORE): os.makedirs(TEMP_STORE)
        temp_file_path = os.path.join(TEMP_STORE, filename)

        print(f"📂 Handling file upload: {filename} ({len(content)} bytes)")
        
        try:
            with open(temp_file_path, "wb") as f:
                f.write(content)
            
            from ingestion_pipeline import ProductionIngestionPipeline, PipelineConfig
            
            defaults = {"chunk_size": 200, "chunk_overlap": 50, "use_docai": True}
            if ingestion_config: defaults.update(ingestion_config)
            
            config = PipelineConfig(
                chunk_size=defaults["chunk_size"],
                chunk_overlap=defaults["chunk_overlap"],
                use_docai=defaults["use_docai"],
                dataset_id=self.engine.current_dataset_id,
                table_id=getattr(self.engine, 'current_table_id', 'KB')
            )
            pipeline = ProductionIngestionPipeline(config)
            
            await update_status(f"🚀 Initializing extraction for {filename}...", "extract")
            result_message = await pipeline.run_pipeline_for_bytes(
                filename,
                content,
                status_callback=update_status,
                metadata=metadata
            )

            # Post-ingestion verification
            try:
                table_id = getattr(self.engine, 'current_table_id', 'KB')
                query = f"SELECT COUNT(*) as count FROM `{self.engine.bqclient.project}.{self.engine.current_dataset_id}.{table_id}` WHERE file_id = '{filename}'"
                results = self.engine.bqclient.query(query).result()
                for row in results:
                    return f"✅ {result_message} (Verified: {row.count} rows)"
            except Exception as e:
                print("Err", e)
            
            msg = f"✅ {result_message}"
            if filename.lower().endswith(".pdf"):
                msg += f"\n\n🔗 [View Knowledge Graph](/graphs/{filename}_graph.html)"
            return msg
            
        except Exception as e:
            print(f"Upload failed: {e}")
            return f"❌ Upload failed: {str(e)}"
        
        finally:
            if os.path.exists(temp_file_path):
                try: os.remove(temp_file_path)
                except: pass

    def ingest_data(self, data_dir: str = "./data_dir"):
        """Sync wrapper for mass ingestion, usually called from CLI."""
        if not os.path.exists(data_dir): return

        files = glob.glob(os.path.join(data_dir, "*"))
        if not files: return

        print(f"📂 Found {len(files)} files to ingest...")
        
        async def run_batch():
            for f in files:
                fname = os.path.basename(f)
                with open(f, "rb") as fo:
                    content = fo.read()
                msg = await self.handle_file_upload(fname, content)
                print(f"   {fname}: {msg}")

        try:
             loop = asyncio.get_event_loop()
             if loop.is_running(): asyncio.create_task(run_batch())
             else: loop.run_until_complete(run_batch())
        except RuntimeError:
             asyncio.run(run_batch())
