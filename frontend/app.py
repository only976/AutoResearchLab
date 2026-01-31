import streamlit as st
import sys
import os

# Add project root to sys.path to allow imports from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from components.kanban_board import render_kanban
from components.idea_generator import render_idea_generator

def main():
    st.set_page_config(
        page_title="AutoResearchLab",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    st.title("🔬 AutoResearchLab")
    st.markdown("### Multi-Agent LLM System for Automating Engineering Research Workflows")

    # Sidebar for navigation
    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Go to", ["Dashboard", "Idea Generator", "Chat Interface", "System Logs", "Configuration"])

    if page == "Dashboard":
        render_kanban()
    elif page == "Idea Generator":
        render_idea_generator()
    elif page == "Chat Interface":
        st.header("Chat with Agents")
        st.info("Chat interface will be implemented here.")
    elif page == "System Logs":
        st.header("System Logs")
        st.info("Log viewer will be implemented here.")
    elif page == "Configuration":
        st.header("System Configuration")
        st.info("Configuration settings will be implemented here.")

if __name__ == "__main__":
    main()
