
import streamlit as st
import asyncio
import time
import pandas as pd

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


from client_package.speech_handler import SpeechHandler

# Initialize Speech Handler in Session State
if "speech_handler" not in st.session_state:
    st.session_state.speech_handler = SpeechHandler(input_enabled=True, output_enabled=True)

def render():
    st.title("💬 BigQuery AI Assistant")
    
    # --- Voice Controls ---
    col1, col2 = st.columns([1, 4])
    with col1:
        voice_mode = st.toggle("🔊 Read Aloud", value=False)
    
    voice_prompt = None
    with col2:
        if st.button("🎤 Voice Input"):
            with st.spinner("Listening..."):
                text = st.session_state.speech_handler.listen()
                if text:
                    voice_prompt = text
                    st.success(f"Heard: {text}")
                    time.sleep(1)
                else:
                    st.warning("No speech detected.")

    # Render History
    for msg in st.session_state.messages:
        role = msg["role"]
        with st.chat_message(role, avatar="🤖" if role == "assistant" else "👤"):
            st.markdown(msg["content"])
            if msg.get("query_result"):
                with st.expander("📊 Query Results", expanded=False):
                    st.dataframe(pd.DataFrame(msg["query_result"]))
            if msg.get("traceability"):
                 with st.expander("🔍 Traceability"):
                    st.json(msg["traceability"])
    
    # Handling Input (Voice OR Text)
    # Note: st.chat_input cannot be set programmatically easily.
    # We prioritize voice_prompt if it exists.
    
    prompt = st.chat_input("Ask about your data...")
    
    active_prompt = voice_prompt if voice_prompt else prompt

    if active_prompt:
        # 1. User Message
        st.session_state.messages.append({"role": "user", "content": active_prompt})
        
        # If it was a voice prompt, we need to explicitly render the user message now
        # (st.chat_input does it automatically differently? No, we always manual append)
        # But for persistent history we just loop above.
        # For the *current* turn, we should display it.
        
        # Actually, since we re-run on button click, the history loop above handles "past" messages.
        # But the NEW message needs to be shown.
        # Streamlit's chat_message block usually goes AFTER the specific input block.
        
        # IF voice_prompt was active, we are in the run where we have it.
        # We appended it. The loop above already ran? 
        # Yes, loop runs top to bottom. If we append NOW, it won't show in the loop above until NEXT rerun.
        # So we render it immediately below.
        
        # HOWEVER, the standard pattern is: Loop History -> Get Input -> Append -> Render New -> Rerun
        # But if we want it to persist, the next run handles it.
        # For immediate feedback:
        
        with st.chat_message("user", avatar="👤"):
            st.markdown(active_prompt)
            
        # 2. Assistant Response
        with st.chat_message("assistant", avatar="🤖"):
            resp_container = st.empty()
            status_container = st.empty()
            
            async def status_cb(msg, step):
                status_container.caption(f"⚙️ {msg}...")
            
            try:
                # Call Engine capabilities directly from Component
                # This replaces: result = run_async(st.session_state.rag_core.process(...))
                
                engine = st.session_state.rag_core.engine
                
                async def process_chat_logic(user_input, status_cb):
                    start_time = time.time()
                    
                    if not user_input.strip():
                        return {"response_text": "Please enter a message.", "intent": "none"}

                    # 1. Classify
                    await status_cb("🧠 Analyzing request...", "classify")
                    # Using engine's classify for now (shared util)
                    intent = await engine.classify_intent(user_input)
                    
                    # 2. Rewrite (if not ingest)
                    if intent not in ["upload_by_path", "command_upload_by_path"]:
                        await status_cb("🔄 Checking context...", "rewrite")
                        user_input = await engine.rewrite_user_input(user_input)
                    
                    # 3. Dispatch to Cases
                    # Import handlers which are initialized in engine (or import classes directly)
                    # For now, using engine's initialized handlers
                    
                    result = {
                        "intent": intent,
                        "response_text": "",
                        "source_citation": None,
                        "traceability": None
                    }
                    print("process_chat_logic result", result)
                    if intent == "query_similarity_search":
                        result = await engine.vector_handler.handle(user_input, status_cb)
                        
                    elif intent == "query_sql_generation":
                        result = await engine.sql_handler.handle(user_input, status_cb)
                            
                    elif intent == "upload_by_path":
                         # Chat-based ingest trigger
                        result = await engine.ingest_handler.handle(user_input, status_cb)

                    else:  # query_non_db_chat
                        result = await engine.general_handler.handle(user_input, status_cb)

                    # 4. History Saving (Component Logic)
                    if engine.current_user_email:
                         try:
                            engine.db.add_message(engine.current_user_email, "user", active_prompt) # Use original prompt
                            engine.db.add_message(engine.current_user_email, "assistant", result["response_text"])
                         except Exception:
                             pass
                    
                    return result

                # Run the async logic
                result = run_async(process_chat_logic(active_prompt, status_cb))
                
                status_container.empty() # Clear status
                
                # Debugging: View raw result
                with st.expander("Debug Result"):
                    st.json(result) 
                
                response_txt = result.get("response_text", "No response.")
                intent = result.get("intent", "unknown")
                
                # Check for errors in intent
                if intent == "error":
                    st.error(response_txt)
                else:
                    resp_container.markdown(response_txt)

                    # Append to history
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": response_txt,
                        "query_result": result.get("query_result"),
                        "traceability": result.get("traceability"),
                        "intent": intent
                    })
                    
                    # Show extra data immediately
                    if result.get("query_result"):
                        with st.expander("📊 Query Results", expanded=True):
                            st.dataframe(pd.DataFrame(result["query_result"]))
                    
                    if result.get("traceability"):
                        with st.expander("🔍 Traceability"):
                            st.json(result["traceability"])
                    
                    # TTS Handler
                    if voice_mode and st.session_state.speech_handler:
                        st.session_state.speech_handler.speak(response_txt)

            except Exception as e:
                status_container.empty()
                st.error(f"Processing Error: {e}")
                
        # Force Rerun to update history view properly
        if voice_prompt:
             st.rerun()
