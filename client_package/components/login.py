"""Login component: BQ auth, then ensure RAG corpus in user metadata."""
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


def authenticate_user(email: str, password: str):
    """
    Handles BQ authentication.
    On success: engine.authenticate checks/creates RAG corpus and saves in user metadata.
    Returns (success: bool, message: str).
    """
    if not st.session_state.rag_core:
        return False, "System core not initialized."

    try:
        res = run_async(st.session_state.rag_core.authenticate(email, password))
        if res.get("success"):
            st.session_state.auth_status = True
            st.session_state.user_email = email
            return True, res.get("message", "Authenticated")
        return False, res.get("message", "Authentication failed")
    except Exception as e:
        return False, str(e)


def render():
    # Initialize login form key for re-init on failure
    if "login_form_key" not in st.session_state:
        st.session_state.login_form_key = 0

    # Show persisted error from previous failed attempt (then clear)
    if "login_error" in st.session_state:
        st.error(st.session_state.login_error)
        del st.session_state.login_error

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.title("🔒 Login to AI Core")

        # Unique key per failure to force form re-init (fixes "second try does nothing")
        form_key = st.session_state.login_form_key
        with st.form(key=f"login_form_{form_key}", clear_on_submit=False):
            email = st.text_input("Email", placeholder="admin@example.com", key=f"login_email_{form_key}")
            password = st.text_input("Password", type="password", key=f"login_password_{form_key}")
            submitted = st.form_submit_button("Sign In")

            if submitted:
                if not email or not password:
                    st.session_state.login_error = "Credentials required."
                    st.session_state.login_form_key += 1
                    st.rerun()
                else:
                    success, msg = authenticate_user(email, password)
                    if success:
                        st.success(msg)
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.session_state.login_error = msg
                        st.session_state.login_form_key += 1  # Force new form on next render
                        st.rerun()
