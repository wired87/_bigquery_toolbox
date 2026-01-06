"""
Enhanced error handling utilities for clear, detailed exception reporting.
"""

import traceback
import sys
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


def format_exception_details(
    e: Exception,
    context: Optional[str] = None,
    include_traceback: bool = True,
    include_type: bool = True
) -> str:
    """
    Format exception with comprehensive details for debugging.
    
    Args:
        e: The exception object
        context: Optional context string (e.g., "Authentication", "File Upload")
        include_traceback: Whether to include full traceback
        include_type: Whether to include exception type
    
    Returns:
        Formatted error message string
    """
    parts = []
    
    # Header
    if context:
        parts.append(f"🔴 ERROR in {context}")
    else:
        parts.append("🔴 ERROR")
    
    # Exception type
    if include_type:
        parts.append(f"   Type: {type(e).__name__}")
    
    # Exception message
    error_msg = str(e)
    if error_msg:
        parts.append(f"   Message: {error_msg}")
    else:
        parts.append(f"   Message: (No message provided)")
    
    # Traceback
    if include_traceback:
        tb_lines = traceback.format_exception(type(e), e, e.__traceback__)
        tb_str = ''.join(tb_lines).strip()
        parts.append(f"   Traceback:\n{tb_str}")
    
    return "\n".join(parts)


def log_exception(
    e: Exception,
    context: Optional[str] = None,
    level: str = "error",
    include_traceback: bool = True
) -> str:
    """
    Log exception with full details and return formatted message.
    
    Args:
        e: The exception object
        context: Optional context string
        level: Log level ('debug', 'info', 'warning', 'error', 'critical')
        include_traceback: Whether to include full traceback
    
    Returns:
        Formatted error message (for returning to user)
    """
    # Format the full error message
    full_msg = format_exception_details(e, context, include_traceback, include_type=True)
    
    # Log it
    log_func = getattr(logger, level, logger.error)
    log_func(full_msg)
    
    # Return user-friendly version (without full traceback for cleaner UI)
    user_msg = format_exception_details(e, context, include_traceback=False, include_type=True)
    return user_msg


def create_error_response(
    e: Exception,
    context: Optional[str] = None,
    intent: str = "error",
    include_details: bool = True
) -> Dict[str, Any]:
    """
    Create standardized error response dictionary for API/CLI responses.
    
    Args:
        e: The exception object
        context: Optional context string
        intent: Intent type for response
        include_details: Whether to include detailed error info
    
    Returns:
        Dictionary with error response
    """
    # Log the exception with full details
    log_exception(e, context, level="error", include_traceback=True)
    
    # Create response
    response = {
        "intent": intent,
        "response_text": "",
        "error": True,
        "error_type": type(e).__name__
    }
    
    if include_details:
        # Include detailed information
        error_msg = str(e) if str(e) else "(No error message)"
        if context:
            response["response_text"] = f"❌ Error in {context}: {error_msg}"
        else:
            response["response_text"] = f"❌ Error: {error_msg}"
        
        response["error_details"] = {
            "type": type(e).__name__,
            "message": str(e),
            "context": context
        }
    else:
        # Simple user-friendly message
        if context:
            response["response_text"] = f"❌ An error occurred in {context}. Please check logs for details."
        else:
            response["response_text"] = "❌ An error occurred. Please check logs for details."
    
    return response


class DetailedExceptionLogger:
    """Context manager for detailed exception logging in code blocks."""
    
    def __init__(self, context: str, logger_instance: Optional[logging.Logger] = None):
        self.context = context
        self.logger = logger_instance or logger
    
    def __enter__(self):
        self.logger.debug(f"🔵 Entering: {self.context}")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Exception occurred
            error_msg = format_exception_details(
                exc_val,
                context=self.context,
                include_traceback=True,
                include_type=True
            )
            self.logger.error(error_msg)
        else:
            # Successful completion
            self.logger.debug(f"✅ Completed: {self.context}")
        
        # Don't suppress the exception
        return False


# Convenience function for try-except blocks
def safe_execute(func, context: str, default_return=None, log_level: str = "error"):
    """
    Execute a function with automatic exception handling and logging.
    
    Args:
        func: Function to execute (should be callable)
        context: Context string for error messages
        default_return: Value to return if exception occurs
        log_level: Log level for exceptions
    
    Returns:
        Function result or default_return if exception occurs
    """
    try:
        return func()
    except Exception as e:
        log_exception(e, context, level=log_level, include_traceback=True)
        return default_return
