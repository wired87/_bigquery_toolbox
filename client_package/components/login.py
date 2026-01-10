
import streamlit as st
import time
import asyncio

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

def authenticate_user(email, password):
    """Handles authentication."""
    if not st.session_state.rag_core:
        st.error("System core not initialized.")
        return False

    try:
        res = run_async(st.session_state.rag_core.authenticate(email, password))
        if res.get("success"):
            st.session_state.auth_status = True
            st.session_state.user_email = email
            # Initialize engine session logic if needed
            return True, res.get("message")
        else:
            return False, res.get("message")
    except Exception as e:
        return False, str(e)

def render():
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Login to AI Core")
        
        with st.form("login"):
            email = st.text_input("Email", placeholder="admin@example.com")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Sign In")
            
            if submitted:
                if not email or not password:
                    st.error("Credentials required.")
                else:
                    success, msg = authenticate_user(email, password)
                    if success:
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error(msg)
        
        st.info("Debugging? Try `admin@example.com` / `admin123` if configured.")
