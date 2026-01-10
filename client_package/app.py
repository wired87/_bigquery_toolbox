
import streamlit as st
import asyncio
import os
import sys
import pandas as pd
import time
import base64
from typing import Dict, Any, Optional

# --- path setup ---
# Add project root to python path to allow imports from root modules
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.append(project_root)

try:
    from engine import CoreEngine
    from rag.core import RAGCore
    # from server_config import GlobalServerConfig  <-- Removed
    # from ip_manager import ip_manager             <-- Removed
except ImportError as e:
    st.error(f"Failed to import core modules. Please run this app from the project root or ensure python path is correct.\nError: {e}")
    st.stop()

# --- Configuration ---
st.set_page_config(
    page_title="BigQuery AI Toolbox (Local Core)",
    page_icon="🧠",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'Get Help': 'mailto:support@example.com',
        'About': "# BigQuery AI Toolbox\nRunning in **Local Core** mode (No Websockets)"
    }
)

# --- Custom CSS ---
st.markdown("""
<style>
    .stApp { background-color: #0e1117; color: #e0e0e0; }
    h1, h2, h3 { font-family: 'Inter', sans-serif; color: #ffffff; }
    /* Chat styling */
    .user-msg { border-left: 4px solid #4CAF50; padding-left: 10px; }
    .bot-msg { border-left: 4px solid #2196F3; padding-left: 10px; }
</style>
""", unsafe_allow_html=True)


# --- Helper Functions ---
def run_async(coro):
    """Helper to run async code in Streamlit's sync environment."""
    try:
        return asyncio.run(coro)
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(coro, loop)
            return future.result()
        raise e

@st.cache_resource
def get_core_system():
    """
    Initialize the CoreEngine and RAGCore once.
    This replaces the 'get_engine' and 'connect' logic from the WebSocket consumer.
    """
    try:
        # Initialize CoreEngine
        with st.spinner("Initializing AI Core Engine..."):
            engine = CoreEngine(require_auth=True)
            
            # Initialize RAG Wrapper
            rag = RAGCore(engine)
            
            # GlobalServerConfig removed (Serverless mode)
                
            return rag
    except Exception as e:
        st.error(f"Critical Error Initializing Core: {e}")
        return None

# --- State Management ---
if "rag_core" not in st.session_state:
    st.session_state.rag_core = get_core_system()

if "messages" not in st.session_state:
    st.session_state.messages = []

if "auth_status" not in st.session_state:
    st.session_state.auth_status = False

if "user_email" not in st.session_state:
    st.session_state.user_email = None

if "file_uploader_key" not in st.session_state:
    st.session_state.file_uploader_key = 0


# --- Main App Logic ---
from client_package.st_collector import StCollector

def main():
    app = StCollector()
    app.render()

if __name__ == "__main__":
    main()
