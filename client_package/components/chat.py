"""
Chat component - RAG-based chat using RAGWorkflow from chat.py.
Replaces previous intent-based logic with corpus retrieval + generation.
"""

import streamlit as st
import asyncio
import time
import pandas as pd


# Max time for chat processing (prevents indefinite hangs)
CHAT_PROCESS_TIMEOUT = 90


def run_async(coro, timeout: float = CHAT_PROCESS_TIMEOUT):
    """Helper to run async code in Streamlit's sync environment. Applies timeout to prevent hangs."""
    wrapped = asyncio.wait_for(coro, timeout=timeout)
    try:
        return asyncio.run(wrapped)
    except RuntimeError as e:
        if "This event loop is already running" in str(e):
            loop = asyncio.get_running_loop()
            future = asyncio.run_coroutine_threadsafe(wrapped, loop)
            return future.result(timeout=timeout + 10)
        raise e
    except asyncio.TimeoutError:
        raise TimeoutError(f"Chat processing timed out after {timeout}s")


def render():
    st.title("💬 BigQuery AI Assistant (RAG)")

    # Render message history
    for msg in st.session_state.messages:
        role = msg["role"]
        with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
            css_class = "user-message" if role == "user" else "assistant-message"
            st.markdown(f'<div class="{css_class}">{msg["content"]}</div>', unsafe_allow_html=True)
            if msg.get("query_result"):
                with st.expander("📊 Query Results", expanded=False):
                    st.dataframe(pd.DataFrame(msg["query_result"]))
            if msg.get("traceability"):
                with st.expander("🔍 Traceability"):
                    st.json(msg["traceability"])

    prompt = st.chat_input("Ask about your data...")
    if not prompt:
        return

    # 1. User message
    print(f"\n[USER] {prompt}")
    st.session_state.messages.append({"role": "user", "content": prompt})

    with st.chat_message("user", avatar="👤"):
        st.markdown(f'<div class="user-message">{prompt}</div>', unsafe_allow_html=True)

    # 2. Assistant response - use RAGWorkflow (chat.py logic)
    with st.chat_message("assistant", avatar="🤖"):
        resp_container = st.empty()
        status_container = st.empty()

        def status_cb(msg: str, step: str = ""):
            print(f"[{step.upper()}] {msg}")
            status_container.caption(f"⚙️ {msg}...")

        try:
            from client_package.workflows import RAGWorkflow
            rag_core = st.session_state.rag_core
            workflow = RAGWorkflow(rag_core.engine, rag_core)
            mode = st.session_state.get("workflow_mode", "Auto")

            result = run_async(workflow.process_chat(prompt, mode=mode, status_callback=status_cb))
            status_container.empty()

            response_txt = result.get("response_text", "No response.")
            intent = result.get("intent", "unknown")

            engine = rag_core.engine
            if engine.current_user_email:
                try:
                    engine.db.add_message(engine.current_user_email, "user", prompt)
                    engine.db.add_message(engine.current_user_email, "assistant", response_txt)
                except Exception:
                    pass

            if intent == "error":
                st.error(response_txt)
            else:
                print(f"[ASSISTANT] {response_txt}")
                resp_container.markdown(
                    f'<div class="assistant-message">{response_txt}</div>',
                    unsafe_allow_html=True,
                )
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response_txt,
                    "query_result": result.get("query_result"),
                    "traceability": result.get("traceability"),
                    "intent": intent,
                })
                if result.get("query_result"):
                    with st.expander("📊 Query Results", expanded=True):
                        st.dataframe(pd.DataFrame(result["query_result"]))
                if result.get("traceability"):
                    with st.expander("🔍 Traceability"):
                        st.json(result["traceability"])
        except (asyncio.TimeoutError, TimeoutError):
            status_container.empty()
            st.error(f"Request timed out after {CHAT_PROCESS_TIMEOUT}s. Try a shorter query.")
        except Exception as e:
            status_container.empty()
            st.error(f"Processing Error: {e}")
