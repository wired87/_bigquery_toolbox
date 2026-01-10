import os
import json
import logging
import websockets
import base64
import asyncio
from typing import Dict, Any, Optional

try:
    import ray
except ImportError:
    ray = None

logger = logging.getLogger("interactor")

class Interactor:
    def __init__(self, agent_name: str = "bq_agent", require_auth: bool = True):
        self.agent_name = agent_name
        self.require_auth = require_auth
        self.domain = os.getenv("DOMAIN", "localhost:8000")
        self.ws = None
        self.is_authenticated = False
        self.urls = []

    async def _get_urls_from_agent(self):
        """
        Retrieve a list of URLs from the BQ agent via Ray.
        """
        if ray:
            try:
                # Attempt to connect to Ray if not already connected
                if not ray.is_initialized():
                    # In a cloud cli context, we might expect 'auto' or a specific address
                    # For now we try 'auto' but catch errors if no cluster is found
                    try:
                        ray.init(address="auto", ignore_reinit_error=True)
                    except Exception:
                        pass 

                if ray.is_initialized():
                    try:
                        agent = ray.get_actor(self.agent_name)
                        # We assume the agent has a 'get_urls' method
                        fetched_urls = await agent.get_urls.remote()
                        if isinstance(fetched_urls, list):
                            self.urls = fetched_urls
                            return
                    except ValueError:
                         logger.warning(f"Actor {self.agent_name} not found.")
                    except Exception as e:
                         logger.warning(f"Error communicating with Ray actor: {e}")
            except Exception as e:
                logger.warning(f"Ray check failed: {e}")

        # Fallback to constructing URL from domain
        # If urls list is still empty, we use the domain from .env
        logger.info("Using domain from .env for connection.")
        if "localhost" in self.domain or "127.0.0.1" in self.domain:
             base = f"ws://{self.domain}"
        else:
             base = f"wss://{self.domain}"
             
        self.urls = [f"{base}/ws/chat/"]


    async def _connect_ws(self):
        # Port jumping: Try ports 8000-8010 sequentially
        last_error = None
        connected = False
        
        for port in range(8000, 8011):
            try:
                # Construct WebSocket URL for this port
                ws_url = f"ws://127.0.0.1:{port}/ws/chat/"
                
                logger.debug(f"🔌 Attempting connection to {ws_url}...")
                
                # Try to connect with timeout
                self.ws = await asyncio.wait_for(
                    websockets.connect(
                        ws_url,
                        max_size=120 * 1024 * 1024,  # 120MB
                        ping_interval=30,
                        ping_timeout=30,
                        close_timeout=10
                    ),
                    timeout=2.0  # Quick timeout per port
                )
                
                # Connection successful!
                logger.info(f"✅ Connected to WebSocket at {ws_url}")
                self.domain = f"127.0.0.1:{port}"
                connected = True
                break  # Exit loop on success
                
            except asyncio.TimeoutError:
                last_error = f"Connection timeout on port {port}"
                logger.debug(f"⏱️  Timeout on port {port}, trying next...")
                continue
            except (ConnectionRefusedError, OSError) as e:
                last_error = f"Connection refused on port {port}"
                logger.debug(f"❌ Port {port} refused, trying next...")
                continue
            except Exception as e:
                last_error = str(e)
                logger.debug(f"⚠️  Error on port {port}: {e}, trying next...")
                continue
        
        # If no connection was established, raise an error
        if not connected:
            error_msg = (
                f"Could not connect to server on any port (8000-8010). "
                f"Please ensure the server is running. Last error: {last_error}"
            )
            raise ConnectionError(error_msg)


    async def authenticate(self, email: str, password: str) -> Dict[str, Any]:
        if not self.ws or self.ws.closed:
            await self._connect_ws()
        
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

    def check_auth(self):
        if self.require_auth and not self.is_authenticated:
            raise PermissionError("User not authenticated.")

    async def process_user_input(self, user_input: str, status_callback=None) -> Dict[str, Any]:
        self.check_auth()
        if not self.ws or self.ws.closed: await self._connect_ws()
        
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
        self.check_auth()
        if not self.ws or self.ws.closed: await self._connect_ws()
        
        b64_content = base64.b64encode(content).decode('utf-8')
        
        msg = {
            "action": "upload_file",
            "data": {
                "filename": filename,
                "content": b64_content,
                "metadata": metadata,
                "ingestion_config": ingestion_config
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
        self.check_auth()
        import os
        for char in ['"', "'"]:
            path_input = path_input.replace(char, "")
        path_input = path_input.strip()

        # Handle "upload <path>" case if passed directly
        if path_input.lower().startswith("upload "):
            path_input = path_input[7:].strip()
            
        abs_path = os.path.abspath(path_input)
        
        if not os.path.exists(abs_path):
             return {
                "intent": "command_upload_by_path",
                "response_text": f"❌ Path not found: `{path_input}`"
             }

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
        
        report = f"✅ Successfully processed {processed_count}/{len(items_to_process)} files."
        if errors:
            report += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
        
        return {
             "intent": "command_upload_by_path",
             "response_text": report
        }
