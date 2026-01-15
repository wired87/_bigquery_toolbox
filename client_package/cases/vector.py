
import logging
import asyncio
from error_handler import log_exception

logger = logging.getLogger(__name__)

class VectorHandler:
    def __init__(self, engine):
        self.engine = engine

    async def handle(self, user_input: str, status_callback=None):
        """
        Handles vector similarity search queries.
        """
        async def update_status(message, step=""):
            if status_callback: await status_callback(message, step)

        result = {
            "intent": "query_similarity_search",
            "response_text": "",
            "source_citation": None,
            "traceability": None
        }

        print("📊 Starting vector search workflow")
        await update_status("🔍 Performing vector search...", "search")
        
        logger.debug(f"Calling Gemini for vector search with tools (timeout: 90s)...")
        
        try:
            response = await asyncio.wait_for(
                self.engine.chat_session.send_message_async(
                    f"User wants to find items: {user_input}. Use vector_search tool if appropriate. Default table is 'KB'.",
                    tools=[self.engine.tools]
                ),
                timeout=90.0
            )
            await update_status("✨ Generating response...", "generate")
            result["response_text"] = await self.engine.handle_model_response(response)
            print(f"✅ Vector search completed ({len(result['response_text'])} chars)")
            
        except asyncio.TimeoutError:
            error_msg = "Vector search TIMED OUT after 90s"
            print(error_msg)
            await update_status("⏰ Search timed out", "error")
            result["response_text"] = "The search operation timed out. Please try a more specific query."
            
        except Exception as e:
            log_exception(e, "Vector Search")
            await update_status(f"❌ Search failed: {type(e).__name__}", "error")
            result["response_text"] = f"Search failed: {str(e)}"

        return result
