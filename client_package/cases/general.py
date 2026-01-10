
import logging
import asyncio
import prompts
from error_handler import log_exception

logger = logging.getLogger(__name__)

class GeneralHandler:
    def __init__(self, engine):
        self.engine = engine

    async def handle(self, user_input: str, status_callback=None):
        """
        Handles general non-DB chat queries (e.g. platform help).
        """
        async def update_status(message, step=""):
            if status_callback: await status_callback(message, step)

        result = {
            "intent": "query_non_db_chat",
            "response_text": "",
            "source_citation": None,
            "traceability": None
        }

        logger.info("💬 Starting platform help workflow")
        await update_status(f"💬 Assisting with platform help...", "chat")
        
        help_prompt = prompts.get_platform_help_prompt(user_input)
        
        try:
            response = await asyncio.wait_for(
                self.engine.chat_session.send_message_async(help_prompt),
                timeout=60.0
            )
            result["response_text"] = response.text
            logger.info(f"✅ Platform help response received ({len(response.text)} chars)")
            
        except asyncio.TimeoutError:
            error_msg = "Platform help request TIMED OUT after 60s"
            logger.error(error_msg)
            await update_status("⏰ Response timed out", "error")
            result["response_text"] = "I apologize, but I'm taking too long to respond. Please try rephrasing your question or ask about specific features."
            
        except Exception as e:
            logger.error(f"❌ Error in general chat: {e}")
            await update_status(f"❌ Error: {type(e).__name__}", "error")
            result["response_text"] = f"I encountered an error: {str(e)}. Please try again or ask a different question."

        await update_status("✅ Complete!", "done")
        return result
