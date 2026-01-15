import os
import json
import asyncio
import logging
import websockets
import base64
from typing import Dict, Any, Optional, List

# Local imports for client-side processing
try:
    from file_processor import FileProcessor
except ImportError:
    FileProcessor = None  # Fallback if dependencies missing


try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not available

logger = logging.getLogger("remote_engine")

class RemoteEngine:
    def __init__(self, credentials_path: str = "credentials.json", require_auth: bool = True, server_url: str = "http://localhost:8000"):
        self.server_url = os.getenv("SERVER_URL", server_url)
        env_ws_url = os.getenv("WS_URL")
        
        if env_ws_url:
            self.ws_url = env_ws_url
            if "/ws/chat/" not in self.ws_url:
                if self.ws_url.endswith("/"):
                    self.ws_url += "ws/chat/"
                else:
                    self.ws_url += "/ws/chat/"
        elif self.server_url.startswith("http"):
             self.ws_url = self.server_url.replace("http", "ws") + "/ws/chat/"
        else:
             self.ws_url = f"ws://{self.server_url}/ws/chat/"
             
        self.is_authenticated = False
        self.ws = None
        self.email = None
        self.password = None
        self.session_id = None  # Track session ID for history
        
        # Keepalive mechanism
        self._keepalive_task = None
        self._keepalive_running = False
        self._ws_lock = asyncio.Lock()  # Protect WebSocket operations
        
        # Local Processor
        self.processor = None
        if FileProcessor:
            try:
                self.processor = FileProcessor()
            except Exception as e:
                print(f"Could not init local FileProcessor: {e}")
    
    def clear_history(self):
        """
        Clear session history (remote sessions handled server-side).
        This is a no-op for RemoteEngine as history is managed on the server.
        """
        print("History clearing (remote session - managed server-side)")
    
    async def _keepalive_loop(self):
        """
        Background task that sends periodic pings to keep the WebSocket connection alive.
        Uses the built-in websockets ping/pong mechanism.
        """
        print("🔄 Keepalive task started")
        self._keepalive_running = True
        
        while self._keepalive_running:
            try:
                await asyncio.sleep(15)  # Ping every 15 seconds
                
                if self.ws and not self.ws.closed:
                    async with self._ws_lock:
                        # 1. Protocol Ping (TCP/WS level)
                        pong_waiter = await self.ws.ping()
                        await asyncio.wait_for(pong_waiter, timeout=10.0)
                        
                        # 2. Application Ping (Daphne/Channels level to prevent idle timeout)
                        # We don't necessarily need to wait for response, just sending it is enough update activity
                        await self.ws.send(json.dumps({"action": "ping"}))
                        
                        logger.debug("💓 Keepalive ping successful (Protocol + App)")
                else:
                    logger.debug("⚠️ WebSocket not connected, skipping keepalive ping")
                    
            except asyncio.TimeoutError:
                print("⏰ Keepalive ping timeout - connection may be stale")
            except asyncio.CancelledError:
                print("🛑 Keepalive task cancelled")
                break
            except Exception as e:
                print(f"⚠️ Keepalive ping failed: {e}")
                # Don't break - let the connection be detected as dead on next actual use
                
        print("🔄 Keepalive task stopped")
        
    def _stop_keepalive(self):
        """Stop the keepalive background task."""
        self._keepalive_running = False
        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            logger.debug("🛑 Keepalive task cancelled")
        
    async def is_connected(self) -> bool:
        """
        Check if the WebSocket connection is alive and healthy.
        Returns True if connected and responsive, False otherwise.
        """
        if not self.ws or self.ws.closed:
            return False
        
        try:
            # Quick ping test to verify connection is responsive
            pong = await self.ws.ping()
            await asyncio.wait_for(pong, timeout=2.0)
            return True
        except Exception:
            return False
        
    
    async def _connect_ws(self):
        # Check if we have an open connection
        is_alive = False
        if self.ws:
            try:
                # Try a quick ping to see if it's healthy
                await asyncio.wait_for(self.ws.ping(), timeout=2.0)
                is_alive = True
            except Exception as e:
                print("self.ws.ping() failed:", e)
                is_alive = False

        if not is_alive:
            # Priority: WS_URL from Env
            if os.getenv("WS_URL"):
                try:
                    logger.debug(f"🔌 Connecting to configured WS_URL: {self.ws_url}")
                    self.ws = await asyncio.wait_for(
                        websockets.connect(
                            self.ws_url, 
                            max_size=120 * 1024 * 1024,
                            ping_interval=20,
                            ping_timeout=45,
                            close_timeout=1000
                        ),
                        timeout=60.0
                    )
                    print(f"✅ Connected to WebSocket at {self.ws_url}")
                    
                    # Update server_url approximation
                    if "://" in self.ws_url:
                        base = self.ws_url.split("/ws/")[0]
                        self.server_url = base.replace("ws", "http")

                    # Start keepalive task
                    if self._keepalive_task is None or self._keepalive_task.done():
                        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
                    
                    # Auto-re-authenticate
                    if self.email and self.password:
                         # Run in background or await if possible, but here we are in connect.
                         # The loop version calls await, so we do too.
                         try:
                             await self.authenticate(self.email, self.password)
                         except:
                             pass
                    
                    return

                except Exception as e:
                     raise ConnectionError(f"Could not connect to Env-defined WS_URL ({self.ws_url}): {e}")

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
                            ping_interval=20,  # More frequent keepalive
                            ping_timeout=45,   # Longer timeout for network delays
                            close_timeout=1000
                        ),
                        timeout=60.0  # Quick timeout per port
                    )
                    
                    # Connection successful!
                    self.ws_url = ws_url
                    self.server_url = f"http://127.0.0.1:{port}"
                    print(f"✅ Connected to WebSocket at {ws_url}")
                    connected = True
                    
                    # Start keepalive task to maintain connection
                    if self._keepalive_task is None or self._keepalive_task.done():
                        self._keepalive_task = asyncio.create_task(self._keepalive_loop())
                        logger.debug("🔄 Started keepalive background task")
                    
                    # Auto-re-authenticate if we have credentials
                    if self.email and self.password:
                        print("🔄 Re-authenticating session...")
                        try:
                            await self.authenticate(self.email, self.password)
                        except Exception as e:
                            print(f"Re-authentication failed: {e}")
                    
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

    async def authenticate(self, email: str, password: str, status_callback=None) -> Dict[str, Any]:
        await self._connect_ws()
        
        # Consume welcome message if present (simple check)
        # In a real robust client we'd have a listening loop separately.
        # Here we just assume request-response lock-step for simplicity or read until we find what we want.
        
        self.email = email
        self.password = password
        
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
            resp_type = data.get("type")
            
            if resp_type == "auth_result":
                if data.get("success"):
                    self.is_authenticated = True
                return data
            elif resp_type == "error":
                return {"success": False, "message": data.get("message", "Unknown error")}
            elif resp_type == "status":
                if status_callback:
                    await status_callback(data.get("message"), data.get("step"))
            # Ignore other types like 'system'

    async def process_user_input(self, user_input: str, status_callback=None, confirm_callback=None) -> Dict[str, Any]:
        if not self.ws: await self._connect_ws()

        # Intercept local path commands (upsert, ingest, upload)
        if any(kw in user_input.lower() for kw in ["upload", "ingest", "upsert"]) and \
           any(p in user_input.lower() for p in ["/", "\\", "c:", "./", "../", "dir", "path"]):
            print(f"Intercepted local ingestion command: {user_input}")
            return await self.ingest_from_path(user_input, status_callback, confirm_callback=confirm_callback)
        
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
                # Add timeout to prevent indefinite waiting (90s for long AI operations)
                response = await asyncio.wait_for(self.ws.recv(), timeout=90.0)
                data = json.loads(response)
                
                resp_type = data.get("type")
                
                if resp_type == "status":
                    if status_callback:
                        await status_callback(data.get("message"), data.get("step"))
                elif resp_type == "response":
                    final_result = {
                        "intent": data.get("intent"),
                        "response_text": data.get("text"),
                        "query_result": data.get("query_result"),  # Include query results for table display
                        "traceability": data.get("traceability"),
                        "source_citation": data.get("citation")
                    }
                    break
                elif resp_type == "error":
                    final_result = {"response_text": f"Error: {data.get('message')}", "intent": "error"}
                    break
            except asyncio.TimeoutError:
                print("Timeout waiting for server response (90s)")
                return {"response_text": "Server response timeout. The operation may still be processing.", "intent": "error"}
            except websockets.exceptions.ConnectionClosed as e:
                print(f"WebSocket connection closed: {e}")
                return {"response_text": "Server connection closed.", "intent": "error"}
                
        return final_result

    async def check_duplicates(self, filenames: list[str]) -> List[str]:
        """
        Asks the server to check which of these filenames already exist.
        """
        if not self.ws: await self._connect_ws()
        
        msg = {
            "action": "check_duplicates",
            "data": {
                "filenames": filenames
            }
        }
        await self.ws.send(json.dumps(msg))
        
        try:
            response = await self.ws.recv()
            data = json.loads(response)
            if data.get("type") == "duplicate_check_result":
                return data.get("duplicates", [])
        except Exception as e:
            print(f"Duplicate check failed: {e}")
            
        return []

    async def handle_file_upload(self, filename: str, content: bytes, status_callback=None, metadata: Optional[Dict[str, Any]] = None, ingestion_config: Optional[Dict[str, Any]] = None) -> str:
        """
        Uploads file via WebSocket with retry logic.
        """
        attempts = 0
        max_attempts = 2
        
        while attempts < max_attempts:
            attempts += 1
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
            
            if status_callback: await status_callback(f"Uploading {filename} (Attempt {attempts})...", "upload_ws")
            
            try:
                await self.ws.send(json.dumps(msg))
                
                while True:
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
            except (websockets.exceptions.ConnectionClosed, ConnectionError) as e:
                print(f"⚠️ Connection lost during upload of {filename}. Attempt {attempts}/{max_attempts}. Error: {e}")
                self.ws = None # Force reconnect
                if attempts >= max_attempts:
                    return f"Upload failed after {max_attempts} attempts: {e}"
                await asyncio.sleep(1) # Small delay before retry
            except Exception as e:
                return f"Upload error: {e}"



    async def _send_upsert_batch(self, rows: List[Dict[str, Any]], table_id: str = "KB") -> str:
        """
        Sends a batch of pre-processed rows to the server for direct upsertion.
        """
        if not self.ws: await self._connect_ws()
        
        msg = {
            "action": "batch_upsert",
            "data": {
                "table_id": table_id,
                "rows": rows,
                "upsert": True
            }
        }
        
        await self.ws.send(json.dumps(msg))
        
        # Wait for response
        try:
            while True:
                response = await asyncio.wait_for(self.ws.recv(), timeout=60.0)
                data = json.loads(response)
                resp_type = data.get("type")
                
                if resp_type == "response" and data.get("intent") == "batch_upsert":
                    return data.get("text")
                elif resp_type == "error":
                    return f"Server Error: {data.get('message')}"
                # Ignore status updates here or handle check? 
                # Ideally we let status callback handler deal with status messages if we could, 
                # but receiving loop here blocks.
                
        except asyncio.TimeoutError:
             return "Error: Timeout waiting for upsert confirmation."
        except Exception as e:
             return f"Error sending batch: {e}"

    async def ingest_from_path(self, path_input: str, status_callback=None, ingestion_config: Optional[Dict[str, Any]] = None, confirm_callback=None) -> Dict[str, Any]:
        """
        Client-side implementation of ingestion.
        Walks local directory, processes files LOCALLY, and upserts data to BigQuery via Server.
        """
        import os
        import re
        
        # 0. Check for processor
        if not self.processor:
             return {
                 "intent": "command_upload_by_path",
                 "response_text": "❌ Client-side processing not available. Please ensure dependencies (langchain, pypdf, etc.) are installed."
             }
        
        # 1. Path Extraction Logic (Robust)
        target_path = path_input.strip().strip('"\'')
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
                "response_text": f"❌ Local path not found: `{target_path or path_input}`. Please check the path and try again."
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
                    items_to_process.append((full_path, "root"))

        if not items_to_process:
             return {"intent": "command_upload_by_path", "response_text": f"⚠️ No files found in `{abs_path}`."}

        # 2. LOCAL PROCESSING & UPSERT
        processed_count = 0
        errors = []
        all_rows = []
        
        if status_callback: await status_callback(f"🚀 Found {len(items_to_process)} files. Processing locally...", "start_process")
        
        for i, (fpath, parent_dir) in enumerate(items_to_process):
             fname = os.path.basename(fpath)
             if status_callback: await status_callback(f"[{i+1}/{len(items_to_process)}] Processing {fname}...", "process")
             
             try:
                 # Local extraction - Run in executor to prevent loop blocking (vital for keepalive)
                 loop = asyncio.get_running_loop()
                 rows = await loop.run_in_executor(None, self.processor.process_file, fpath)
                 
                 if rows:
                     all_rows.extend(rows)
                     processed_count += 1
             except Exception as e:
                 errors.append(f"{fname}: {str(e)}")

        # 3. SEND TO SERVER
        if all_rows:
            total_rows = len(all_rows)
            if status_callback: await status_callback(f"📤 Uploading {total_rows} extracted chunks to BigQuery...", "upload")
            
            # Batch sending
            batch_size = 200
            failed_batches = 0
            
            for i in range(0, total_rows, batch_size):
                batch = all_rows[i:i+batch_size]
                if status_callback: await status_callback(f"Uploading batch {i//batch_size + 1}/{(total_rows + batch_size - 1)//batch_size}...", "upload_batch")
                
                res = await self._send_upsert_batch(batch, table_id="KB")
                if isinstance(res, str) and ("Error" in res or "fail" in res.lower()):
                    errors.append(f"Batch {i}: {res}")
                    failed_batches += 1
            
            if failed_batches == 0:
                report = f"✅ Successfully processed {processed_count} files and upserted {total_rows} chunks."
            else:
                report = f"⚠️ Processed {processed_count} files, but {failed_batches} upload batches failed."
        else:
            report = f"⚠️ Processed {processed_count} files but found no extractable content."
            
        if errors:
            report += f"\n\n⚠️ Errors ({len(errors)}):\n" + "\n".join(errors[:5])
        
        return {
             "intent": "command_upload_by_path",
             "response_text": report
        }
    
    async def close(self):
        """
        Gracefully close the WebSocket connection and cleanup resources.
        """
        print("🔌 Closing WebSocket connection...")
        
        # Stop keepalive task first
        self._stop_keepalive()
        
        # Close WebSocket connection
        if self.ws and not self.ws.closed:
            try:
                await self.ws.close()
                print("✅ WebSocket connection closed")
            except Exception as e:
                print(f"⚠️ Error closing WebSocket: {e}")
        
        self.ws = None
        self.is_authenticated = False
    
    def __del__(self):
        """
        Destructor to ensure cleanup when object is garbage collected.
        """
        if self._keepalive_task and not self._keepalive_task.done():
            self._stop_keepalive()
