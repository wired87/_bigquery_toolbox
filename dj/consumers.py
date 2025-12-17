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
except ImportError:
    # Fallback or error logging
    CoreEngine = None
    ip_manager = None

class BQToolboxConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.engine = None
        self.authenticated = False
        self.email = None
        
        # Initialize Engine with require_auth=True
        # We handle auth in the WS loop
        if CoreEngine:
            self.engine = CoreEngine(require_auth=True)
            
        await self.accept()
        await self.send_json({
            "type": "system",
            "message": "Connected to BigQuery AI Toolbox. Please authenticate."
        })

    async def disconnect(self, close_code):
        pass

    async def receive_json(self, content):
        """
        Handle incoming messages.
        Expected format: { "action": "...", "data": ... }
        """
        action = content.get("action")
        data = content.get("data", {})
        
        if not self.engine:
            await self.send_json({"type": "error", "message": "Engine not initialized on server."})
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
                if not user_input.strip(): return
                
                # Check for client-side commands passed through WS?
                # e.g. /upload
                # If the user sends "/upload path", the engine's ingest_from_path will try to read SERVER LOCAL path.
                
                # Callback for status updates
                async def status_callback(msg, step):
                    await self.send_status(msg, step)

                result = await self.engine.process_user_input(user_input, status_callback=status_callback)
                
                await self.send_json({
                    "type": "response",
                    "intent": result.get("intent"),
                    "text": result.get("response_text"),
                    "traceability": result.get("traceability"),
                    "citation": result.get("source_citation")
                })
            
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

        except Exception as e:
            traceback.print_exc()
            await self.send_json({"type": "error", "message": str(e)})

    async def send_status(self, message, step):
        await self.send_json({
            "type": "status",
            "message": message,
            "step": step
        })
