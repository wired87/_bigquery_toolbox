import json
import asyncio
import os
import traceback
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings

# Import CoreEngine (Assuming it is in the python path or adjust imports)
# The user's structure has engine.py in the root. 
# We might need to adjust python path or imports.
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from engine import CoreEngine
    from ip_manager import ip_manager
    from rag import RAGCore, GlobalRAGRegistry
    from server_config import GlobalServerConfig
    from error_handler import log_exception, create_error_response
except ImportError:
    # Fallback or error logging
    CoreEngine = None
    ip_manager = None
    RAGCore = None
    GlobalRAGRegistry = None
    GlobalServerConfig = None
    log_exception = None
    create_error_response = None

def safe_json_serialize(obj, max_results=100):
    """
    Safely serialize objects to JSON by converting non-serializable types.
    Returns a JSON-safe version of the object.
    """
    from datetime import datetime, date
    import decimal
    import copy
    
    def convert_value(value):
        """Recursively convert non-serializable types"""
        if isinstance(value, (datetime, date)):
            return value.isoformat()
        elif isinstance(value, decimal.Decimal):
            return float(value)
        elif isinstance(value, dict):
            return {k: convert_value(v) for k, v in value.items()}
        elif isinstance(value, (list, tuple)):
            return [convert_value(item) for item in value]
        elif hasattr(value, '__dict__') and not isinstance(value, (str, int, float, bool, type(None))):
            return str(value)
        return value
    
    try:
        # Deep copy to avoid modifying original
        obj_copy = copy.deepcopy(obj)
        
        # Limit query results size
        if isinstance(obj_copy, dict) and 'query_result' in obj_copy:
            results = obj_copy.get('query_result')
            if results and isinstance(results, list):
                if len(results) > max_results:
                    print(f"⚠️ Truncating query_result from {len(results)} to {max_results} rows")
                    obj_copy['query_result'] = results[:max_results]
                    obj_copy['result_truncated'] = True
                    obj_copy['total_rows'] = len(results)
                
                # Convert all values in query results
                obj_copy['query_result'] = [convert_value(row) for row in obj_copy['query_result']]
        
        # Convert the entire object
        converted = convert_value(obj_copy)
        
        # Test serialization
        json_str = json.dumps(converted)
        size_mb = len(json_str) / (1024 * 1024)
        if size_mb > 5:
            print(f"⚠️ Large JSON payload: {size_mb:.2f}MB")
        
        return converted
    except Exception as e:
        print(f"❌ JSON conversion failed: {e}")
        traceback.print_exc()
        return {
            "type": "error",
            "message": f"Failed to prepare response: {str(e)}"
        }

class BQToolboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        import time
        client_ip = self.scope.get('client', ['unknown'])[0]
        print(f"🔌 New WebSocket connection attempt from {client_ip}...")
        
        if ip_manager and ip_manager.is_blocked(client_ip):
            print(f"🚫 Blocked connection attempt from {client_ip}")
            if ip_manager: ip_manager.log_access(client_ip, "WS /ws/chat/", blocked=True)
            await self.accept() 
            await self.send_json({"type": "error", "message": "Your IP is blocked."})
            await self.close()
            return

        if ip_manager: ip_manager.log_access(client_ip, "WS /ws/chat/", blocked=False)
        
        # Connection tracking
        self.engine = None
        self.rag_core = None
        self.authenticated = False
        self.email = None
        self.connected_at = time.time()
        self.request_count = 0
        self.client_ip = client_ip
        
        await self.accept()
        print(f"✅ Connection accepted for {client_ip} (lazy engine init).")
        
        # Gather server configuration
        server_info = {}
        if GlobalServerConfig and GlobalServerConfig.is_initialized():
            server_info = GlobalServerConfig.get_info()
        
        # Send initial connection message with server info
        await self.send_json({
            "type": "system",
            "message": "Connected to BigQuery AI Toolbox. Please authenticate.",
            "server_info": server_info
        })
        
        # Register RELAY listener for this connection
        if GlobalRAGRegistry and GlobalRAGRegistry.is_initialized():
            GlobalRAGRegistry.register_relay_listener(self.relay_notification_callback)
            
            # Send all already discovered RELAY packages
            discovered = GlobalRAGRegistry.get_discovered_relays()
            if discovered:
                await self.send_json({
                    "type": "relay_modules_initial",
                    "modules": discovered,
                    "count": len(discovered)
                })
                print(f"📡 Sent {len(discovered)} RELAY modules to {client_ip}")

    async def get_engine(self):
        if not self.engine and CoreEngine:
            print("⚙️ Initializing CoreEngine (lazy)...")
            try:
                self.engine = await asyncio.to_thread(CoreEngine, require_auth=True)
                print("✅ CoreEngine initialized.")
                
                # Initialize RAG Core wrapper
                if RAGCore:
                    self.rag_core = RAGCore(self.engine)
                    
                    # Register with global registry if not already done
                    if GlobalRAGRegistry and not GlobalRAGRegistry.is_initialized():
                        GlobalRAGRegistry.initialize(self.rag_core)
                        print("✅ RAG Core registered globally.")
                    
            except Exception as e:
                print(f"❌ Failed to initialize CoreEngine: {e}")
                traceback.print_exc()
        return self.engine
    
    async def relay_notification_callback(self, relay_info: dict):
        """
        Callback for RELAY package discovery notifications
        Sends real-time updates to the frontend
        """
        try:
            await self.send_json({
                "type": "relay_module_discovered",
                "module": relay_info,
                "message": f"🔌 New module available: {relay_info.get('description', relay_info.get('key'))}"
            })
            print(f"📡 Sent RELAY notification to {self.client_ip}: {relay_info.get('key')}")
        except Exception as e:
            print(f"❌ Failed to send RELAY notification: {e}")


    async def receive_json(self, content):
        """
        Handle incoming messages.
        Expected format: { "action": "...", "data": ... }
        """
        print(f"📥 Received message: {content.get('action')}")
        action = content.get("action")
        data = content.get("data", {})
        
        engine = await self.get_engine()
        if not engine:
            await self.send_json({"type": "error", "message": "Engine not initialized on server (check credentials)."})
            return

        try:
            # --- AUTH ENTICATION ---
            if action == "authenticate":
                email = data.get("email")
                password = data.get("password")
                
                await self.send_status("Authenticating...", "auth")
                auth_res = await self.engine.authenticate(email, password)
                
                if auth_res["success"]:
                    self.authenticated = True
                    self.email = email
                    await self.send_json({
                        "type": "auth_result",
                        "success": True, 
                        "message": auth_res['message'],
                        "dataset_id": auth_res.get('dataset_id')
                    })
                else:
                    await self.send_json({
                        "type": "auth_result", 
                        "success": False, 
                        "message": auth_res['message']
                    })
                return

            # --- REQUIRE AUTHENTICATION FOR OTHER ACTIONS ---
            if not self.authenticated:
                await self.send_json({"type": "error", "message": "Authentication required. Send 'authenticate' action."})
                return

            # --- CHAT / QUERY ---
            if action == "chat":
                user_input = data.get("message", "")
                if not user_input.strip():
                    await self.send_json({
                        "type": "error",
                        "message": "Empty message received. Please send a valid query."
                    })
                    return
                
                # Callback for status updates
                async def status_callback(msg, step):
                    await self.send_status(msg, step)

                print(f"🚀 Processing chat request from {self.email}: '{user_input[:50]}...'")
                
                try:
                    # Use RAG Core if available, otherwise fallback to engine
                    if self.rag_core:
                        result = await self.rag_core.process(
                            user_input, 
                            status_callback=status_callback,
                            context={'user_email': self.email, 'client_ip': self.client_ip}
                        )
                    else:
                        result = await self.engine.process_user_input(user_input, status_callback=status_callback)
                    
                    print(f"✅ Chat request completed. Intent: {result.get('intent')}")
                except Exception as proc_error:
                    # Log with full details
                    if log_exception:
                        error_msg = log_exception(proc_error, f"Processing chat from {self.email}")
                    else:
                        print(f"❌ ERROR in process_user_input: {proc_error}")
                        traceback.print_exc()
                    
                    # Send error to client
                    await self.send_json({
                        "type": "error",
                        "message": f"Processing failed: {type(proc_error).__name__}: {str(proc_error)}"
                    })
                    return  # Don't re-raise, we've handled it
                
                self.request_count += 1  # Track requests
                
                print(f"📤 Preparing response (intent: {result.get('intent')})")
                
                # Safely serialize response
                response_data = safe_json_serialize({
                    "type": "response",
                    "intent": result.get("intent"),
                    "text": result.get("response_text"),
                    "query_result": result.get("query_result"),  # Add query results for table display
                    "traceability": result.get("traceability"),
                    "citation": result.get("source_citation")
                })
                
                print(f"📡 Sending response to client...")
                try:
                    await self.send_json(response_data)
                    print(f"✅ Response sent successfully")
                except Exception as send_error:
                    if log_exception:
                        log_exception(send_error, f"Sending response to {self.email}")
                    else:
                        print(f"❌ Failed to send response: {send_error}")
                        traceback.print_exc()
                    
                    try:
                        await self.send_json({
                            "type": "error",
                            "message": f"Failed to send response: {str(send_error)}"
                        })
                    except:
                        pass  # Connection might be dead
            
            # --- DIRECT COMMANDS ---
            elif action == "ingest":
                 # Trigger ingestion on server path (if applicable)
                 path = data.get("path", "data_dir")
                 config = data.get("config", {})
                 
                 async def status_callback(msg, step):
                    await self.send_status(msg, step)
                    
                 res = await self.engine.ingest_from_path(path, status_callback=status_callback, ingestion_config=config)
                 await self.send_json({
                     "type": "response",
                     "intent": "ingest",
                     "text": res.get("response_text")
                 })
                 
            elif action == "batch_upsert":
                 # Direct insertion of rows processed by client
                 table_id = data.get("table_id", "KB")
                 rows = data.get("rows", [])
                 upsert = data.get("upsert", True)
                 
                 if not rows:
                     await self.send_json({"type": "error", "message": "No rows provided for upsert"})
                     return
                 
                 print(f"📥 Received batch upsert: {len(rows)} rows for table '{table_id}'")
                 
                 async def status_callback(msg, step):
                    await self.send_status(msg, step)
                 
                 try:
                     await status_callback(f"Inserting {len(rows)} rows into BigQuery table '{table_id}'...", "upsert")
                     
                     # Call engine method
                     result = await self.engine.upsert_data(table_id, rows, upsert=upsert)
                     
                     await self.send_json({
                         "type": "response",
                         "intent": "batch_upsert",
                         "text": f"✅ Successfully inserted {result.get('count')} rows into {table_id}",
                         "count": result.get("count")
                     })
                     
                 except Exception as e:
                     error_msg = f"Upsert failed: {str(e)}"
                     print(f"❌ {error_msg}")
                     if log_exception: log_exception(e, "Batch Upsert")
                     await self.send_json({
                         "type": "error",
                         "message": error_msg
                     })

            elif action == "upload_file":
                # Expecting name and content (base64 or similar? raw bytes usually hard in JSON)
                # DRF/Channels usually handles text/binary frames. receive_json implies text.
                # Client might need to send base64 encoded content for 'data'
                import base64
                
                filename = data.get("filename")
                b64_content = data.get("content")
                
                if filename and b64_content:
                    file_bytes = base64.b64decode(b64_content)
                    
                    async def status_callback(msg, step):
                        await self.send_status(msg, step)

                    res_msg = await self.engine.handle_file_upload(filename, file_bytes, status_callback=status_callback)
                    
                    await self.send_json({
                        "type": "response",
                        "intent": "upload",
                        "text": res_msg
                    })

            elif action == "check_duplicates":
                filenames = data.get("filenames", [])
                existing = await self.engine.get_existing_filenames()
                duplicates = [f for f in filenames if f in existing]
                
                await self.send_json({
                    "type": "duplicate_check_result",
                    "duplicates": duplicates
                })
            
            elif action == "get_server_info":
                # Return current server configuration
                server_info = {}
                if GlobalServerConfig and GlobalServerConfig.is_initialized():
                    server_info = GlobalServerConfig.get_info()
                
                # Also include RELAY modules
                relay_modules = []
                if GlobalRAGRegistry and GlobalRAGRegistry.is_initialized():
                    relay_modules = GlobalRAGRegistry.get_discovered_relays()
                
                # Get RAG stats if available
                rag_stats = {}
                if self.rag_core:
                    rag_stats = self.rag_core.get_stats()
                
                await self.send_json({
                    "type": "server_info_result",
                    "server_info": server_info,
                    "relay_modules": relay_modules,
                    "relay_count": len(relay_modules),
                    "rag_stats": rag_stats
                })

            elif action == "ping":
                # Application-level keepalive to reset idle timers
                await self.send_json({"type": "pong"})

            else:
                print(f"⚠️ Unknown or missing action received: {action}")
                await self.send_json({
                    "type": "error",
                    "message": f"Unknown action: {action}" if action else "Missing 'action' field in request"
                })


        except asyncio.TimeoutError:
            print(f"⏰ Timeout processing action: {action}")
            traceback.print_exc()
            try:
                await self.send_json({
                    "type": "error",
                    "message": "Request timed out. The operation took too long. Please try a simpler query or contact support."
                })
            except:
                pass  # Connection might be dead
        except Exception as e:
            error_msg = str(e)
            print(f"❌ Error processing action '{action}': {error_msg}")
            traceback.print_exc()
            try:
                await self.send_json({
                    "type": "error",
                    "message": f"Server error: {error_msg}"
                })
            except:
                print("❌ Failed to send error message - connection may be closed")

    async def send_status(self, message, step):
        await self.send_json({
            "type": "status",
            "message": message,
            "step": step
        })
    
    async def disconnect(self, close_code):
        """Handle WebSocket disconnection with detailed logging"""
        import time
        duration = time.time() - getattr(self, 'connected_at', time.time())
        client_ip = getattr(self, 'client_ip', 'unknown')
        email = getattr(self, 'email', 'unauthenticated')
        request_count = getattr(self, 'request_count', 0)
        
        # Human-readable close codes
        close_reason = {
            1000: "Normal closure",
            1001: "Going away",
            1002: "Protocol error",
            1003: "Unsupported data",
            1006: "Abnormal closure (no close frame)",
            1007: "Invalid payload",
            1008: "Policy violation",
            1009: "Message too big",
            1011: "Server error"
        }.get(close_code, f"Unknown ({close_code})")
        
        print(f"🔌 WebSocket DISCONNECTED")
        print(f"   Client: {client_ip} ({email})")
        print(f"   Reason: {close_reason}")
        print(f"   Duration: {duration:.1f}s")
        print(f"   Requests processed: {request_count}")
        
        if close_code not in [1000, 1001]:  # Not normal closure
            print(f"   ⚠️ ABNORMAL DISCONNECTION - investigating required!")
