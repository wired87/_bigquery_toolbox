
import streamlit as st
from client_package.components import login, chat, sidebar

class StCollector:
    """
    Collects and renders components for the Streamlit app.
    """
    def __init__(self):
        pass

    def render(self):
        """
        Main render loop.
        """
        if st.session_state.auth_status:
            sidebar.render()
            chat.render()
        else:
            login.render()
