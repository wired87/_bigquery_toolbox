"""Sidebar component: workflow mode, upload to RAG corpus, status, logout."""
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

        # VRAG Pipeline Status
        vrag = getattr(st.session_state.rag_core, "vrag_pipeline", None)
        if vrag:
            with st.expander("📚 Vertex RAG (VRAG)"):
                st.caption("Vertex RAG primary, local KB fallback")
                st.write("Status:", "Ready" if vrag.use_vertex_rag() else "Local only")

        st.divider()
        
        # Upload File - directly to user's RAG corpus (using RAGWorkflow from chat.py)
        st.subheader("📄 Upload to RAG Corpus")
        uploaded_file = st.file_uploader(
            "Choose a file (PDF, text, etc)",
            key=st.session_state.file_uploader_key,
            accept_multiple_files=False,
        )

        if uploaded_file:
            if st.button("Upload to Corpus"):
                with st.spinner("Uploading to RAG corpus..."):
                    bytes_data = uploaded_file.getvalue()
                    status_ph = st.empty()

                    def status_cb(msg: str, step: str = ""):
                        status_ph.caption(f"⚡ {step}: {msg}")

                    try:
                        from client_package.workflows import RAGWorkflow
                        engine = st.session_state.rag_core.engine
                        rag_workflow = RAGWorkflow(engine, st.session_state.rag_core)
                        ok = rag_workflow.upload_bytes_to_corpus(
                            uploaded_file.name,
                            bytes_data,
                            status_callback=status_cb,
                        )
                        if ok:
                            st.success(f"✅ Uploaded {uploaded_file.name} to RAG corpus")
                        else:
                            st.warning("Upload to RAG corpus failed.")
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
