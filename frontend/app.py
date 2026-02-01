import streamlit as st
import sys
import os

# Add project root to sys.path to allow imports from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from components.kanban_board import render_kanban
from components.idea_generator import render_idea_generator
from components.experiment_dashboard import render_experiment_dashboard
from components.paper_writing import render_paper_writing
from backend.config import LLM_MODEL

def main():
    st.set_page_config(
        page_title="AutoResearchLab",
        page_icon="🔬",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # Custom CSS for better UI
    st.markdown("""
        <style>
        .main .block-container {
            padding-top: 2rem;
        }
        .stRadio > div {
            padding-top: 10px;
        }
        .breadcrumb {
            font-size: 0.9rem;
            color: #666;
            margin-bottom: 1rem;
            padding: 0.5rem 0;
            border-bottom: 1px solid #eee;
        }
        </style>
    """, unsafe_allow_html=True)

    # Initialize page state if not present
    if "page" not in st.session_state:
        st.session_state.page = "Dashboard"

    # Sidebar for navigation
    with st.sidebar:
        st.title("🔬 AutoResearchLab")
        st.caption("Automated Research Assistant")
        st.divider()
        
        st.markdown("### 📍 Navigation")
        
        options = ["Dashboard", "Idea Generator", "Experiment Lab", "Paper Drafting", "Chat Interface", "System Logs", "Configuration"]
        icons = {
            "Dashboard": "📊", 
            "Idea Generator": "💡", 
            "Experiment Lab": "🧪", 
            "Paper Drafting": "📝",
            "Chat Interface": "💬", 
            "System Logs": "📜", 
            "Configuration": "⚙️"
        }
        
        for option in options:
            # Highlight active page
            btn_type = "primary" if st.session_state.page == option else "secondary"
            if st.button(f"{icons.get(option, '📄')} {option}", key=f"nav_{option}", type=btn_type, width="stretch"):
                st.session_state.page = option
                st.rerun()
        
        st.divider()
        with st.expander("ℹ️ System Status", expanded=True):
            st.success("System Online")
            st.caption(f"Model: {LLM_MODEL}")

    page = st.session_state.page
    
    # Breadcrumbs UI
    st.markdown(f"""
    <div class="breadcrumb">
        <span>🏠 Home</span> &nbsp;/&nbsp; <span style="font-weight: 600; color: #333;">{page}</span>
    </div>
    """, unsafe_allow_html=True)

    if page == "Dashboard":
        render_kanban()
    elif page == "Idea Generator":
        render_idea_generator()
    elif page == "Experiment Lab":
        render_experiment_dashboard()
    elif page == "Paper Drafting":
        render_paper_writing()
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
