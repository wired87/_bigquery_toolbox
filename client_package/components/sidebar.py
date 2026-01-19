
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

def render():
    with st.sidebar:
        st.title("🧰 Toolbox")
        st.warning(f"Logged in: {st.session_state.user_email}")
        
        st.subheader("🛠 Workflow Mode")
        mode = st.radio(
            "Select Operation Mode",
            ["Auto", "General", "SQL", "Vector", "Ingest"],
            index=0,
            key="workflow_mode_radio",
            help="Force a specific workflow or let AI decide (Auto)"
        )
        st.session_state.workflow_mode = mode

        st.divider()

        # Server Info
        with st.expander("System Status"):
            stats = st.session_state.rag_core.get_stats()
            st.write(stats)
 
        st.divider()
        
        # Function: Upload File
        st.subheader("📄 Upload File")
        uploaded_file = st.file_uploader(
            "Choose a file", 
            key=st.session_state.file_uploader_key
        )
        
        if uploaded_file:
            if st.button("Upload & Ingest"):
                with st.spinner("Uploading..."):
                    bytes_data = uploaded_file.getvalue()
                    
                    status_ph = st.empty()
                    async def status_cb(msg, step):
                        status_ph.caption(f"⚡ {step}: {msg}")

                    try:
                        # Use Engine IngestHandler directly
                        engine = st.session_state.rag_core.engine
                        res_msg = run_async(engine.ingest_handler.handle_file_upload(
                            uploaded_file.name,
                            bytes_data,
                            status_callback=status_cb
                        ))
                        st.success(res_msg)
                        # Increment key to clear uploader
                        st.session_state.file_uploader_key += 1
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"Upload failed: {e}")



        st.divider()
        if st.button("Logout"):
            st.session_state.auth_status = False
            st.session_state.messages = []
            st.rerun()
