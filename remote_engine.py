import os
import json
import asyncio
import logging
import websockets
import base64
from typing import Dict, Any, Optional

logger = logging.getLogger("remote_engine")

class RemoteEngine:
    def __init__(self, credentials_path: str = None, require_auth: bool = True, server_url: str = "http://localhost:8000"):
        self.server_url = os.getenv("SERVER_URL", server_url)
        # Adapt WS URL from HTTP URL
        if self.server_url.startswith("http"):
             self.ws_url = self.server_url.replace("http", "ws") + "/ws/chat/"
        else:
             self.ws_url = f"ws://{self.server_url}/ws/chat/"
             
        self.is_authenticated = False
        self.ws = None
        
    async def _connect_ws(self):
        if not self.ws or self.ws.closed:
            try:
                self.ws = await websockets.connect(self.ws_url)
                # Consume system welcome message
                # initial = await self.ws.recv() 
            except Exception as e:
                raise ConnectionError(f"Could not connect to server at {self.ws_url}: {e}")

    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        await self._connect_ws()
        
        # Consume welcome message if present (simple check)
        # In a real robust client we'd have a listening loop separately.
        # Here we just assume request-response lock-step for simplicity or read until we find what we want.
        
        auth_msg = {
            "action": "authenticate",
            "data": {
                "email": email,
                "password": password
            }
        }
        await self.ws.send(json.dumps(auth_msg))
        
        while True:
            response = await self.ws.recv()
            data = json.loads(response)
            if data.get("type") == "auth_result":
                if data.get("success"):
                    self.is_authenticated = True
                return data
            # Ignore statuses

    async def process_user_input(self, user_input: str, status_callback=None) -> Dict[str, Any]:
        if not self.ws: await self._connect_ws()
        
        msg = {
            "action": "chat",
            "data": {
                "message": user_input
            }
        }
        await self.ws.send(json.dumps(msg))
        
        final_result = None
        
        while True:
            try:
                response = await self.ws.recv()
                data = json.loads(response)
                
                resp_type = data.get("type")
                
                if resp_type == "status":
                    if status_callback:
                        await status_callback(data.get("message"), data.get("step"))
                elif resp_type == "response":
                    final_result = {
                        "intent": data.get("intent"),
                        "response_text": data.get("text"),
                        "traceability": data.get("traceability"),
                        "source_citation": data.get("citation")
                    }
                    break
                elif resp_type == "error":
                    final_result = {"response_text": f"Error: {data.get('message')}", "intent": "error"}
                    break
            except websockets.exceptions.ConnectionClosed:
                return {"response_text": "Server connection closed.", "intent": "error"}
                
        return final_result

    async def handle_file_upload(self, filename: str, content: bytes, status_callback=None, metadata: Optional[Dict[str, Any]] = None, ingestion_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Uploads file via WebSocket.
        """
        if not self.ws: await self._connect_ws()
        
        # Encode content
        b64_content = base64.b64encode(content).decode('utf-8')
        
        msg = {
            "action": "upload_file",
            "data": {
                "filename": filename,
                "content": b64_content,
                "metadata": metadata
            }
        }
        
        if status_callback: await status_callback(f"Uploading {filename} via WS...", "upload_ws")
        
        await self.ws.send(json.dumps(msg))
        
        while True:
            try:
                response = await self.ws.recv()
                data = json.loads(response)
                
                resp_type = data.get("type")
                
                if resp_type == "status":
                    if status_callback:
                        await status_callback(data.get("message"), data.get("step"))
                elif resp_type == "response" and data.get("intent") == "upload":
                    return data.get("text")
                elif resp_type == "error":
                    return f"Error: {data.get('message')}"
            except Exception as e:
                return f"Upload error: {e}"

    async def ingest_from_path(self, path_input: str, status_callback=None, ingestion_config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Client-side implementation of ingest_from_path.
        Walks local directory, uploads files to server via WS.
        """
        import os
        import re
        
        # Copied logic from engine.py for path extraction
        clean_input = path_input.replace("upload", "", 1).strip().strip('"\'')
        target_path = clean_input
        
        # Simple path check
        if not os.path.exists(target_path):
             path_match = re.search(r'(?:["\'])(.*?)(?:["\'])|(?:\s)((?:[a-zA-Z]:[\\/]|[.\\/])[^\s]+)', path_input)
             if path_match:
                 match = path_match.group(1) if path_match.group(1) else path_match.group(2)
                 if os.path.exists(match):
                    target_path = match
        
        if not target_path or not os.path.exists(target_path):
             return {
                "intent": "command_upload_by_path",
                "response_text": f"❌ Path not found: `{target_path or path_input}`."
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
                        relative_parent_dir = parts[0] if len(parts) > 1 else "root"
                        items_to_process.append((full_path, relative_parent_dir))
                    except ValueError:
                        items_to_process.append((full_path, "unknown"))

        processed_count = 0
        errors = []
        
        if status_callback: await status_callback(f"🚀 Found {len(items_to_process)} files. Uploading to server...", "start_ingest")
        
        for i, (fpath, parent_dir) in enumerate(items_to_process):
             fname = os.path.basename(fpath)
             if status_callback: await status_callback(f"[{i+1}/{len(items_to_process)}] Sending {fname}...", "process")
             
             try:
                 with open(fpath, "rb") as f:
                     content = f.read()
                 
                 metadata = {"relative_parent_dir": parent_dir}
                 msg = await self.handle_file_upload(fname, content, status_callback=None, metadata=metadata, ingestion_config=ingestion_config)
                 
                 if "❌" in msg or "failed" in msg.lower() or "Error" in msg:
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
