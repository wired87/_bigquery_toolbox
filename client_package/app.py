
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
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap');

    /* Global Reset & Background */
    .stApp {
        background-color: #000000 !important;
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Typography */
    h1, h2, h3, h4, h5, h6, p, li, span, div {
        color: #FFFFFF !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #050505 !important;
        border-right: 1px solid #1a1a1a;
    }
    section[data-testid="stSidebar"] * {
        color: #a0a0a0 !important;
    }

    /* Inputs */
    .stTextInput input, .stTextArea textarea, .stChatInput textarea {
        background-color: #0a0a0a !important;
        color: #FFFFFF !important;
        border: 1px solid #333 !important;
        border-radius: 8px !important;
        caret-color: #FFFFFF;
    }
    .stTextInput input:focus, .stTextArea textarea:focus, .stChatInput textarea:focus {
        border-color: #FFFFFF !important;
        box-shadow: none !important;
    }
    
    /* Buttons */
    .stButton button {
        background-color: #FFFFFF !important;
        color: #000000 !important;
        border: none !important;
        font-weight: 600 !important;
        border-radius: 6px !important;
        transition: all 0.2s ease;
    }
    .stButton button:hover {
        background-color: #e0e0e0 !important;
        transform: scale(1.02);
    }
    
    /* Chat Message Specifics - Classes injected in chat.py */
    .user-message {
        background-color: #FFFFFF;
        color: #000000 !important;
        padding: 1rem;
        border-radius: 12px;
        margin-bottom: 0.5rem;
        box-shadow: 0 2px 4px rgba(255,255,255,0.1);
    }
    
    .user-message * {
        color: #000000 !important;
    }

    .assistant-message {
        background-color: #0a0a0a;
        color: #FFFFFF !important;
        padding: 1rem;
        border: 1px solid #333;
        border-radius: 12px;
        margin-bottom: 0.5rem;
    }
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
