import streamlit as st
import os
import json
import pandas as pd

from backend.agents.writing_agent import WritingAgent

def render_paper_writing():
    st.title("📝 Paper Drafting")
    
    # 1. Select Experiment
    # Go up 3 levels from frontend/components/paper_writing.py -> root -> data/experiments
    # Current file: /Users/only976/code/AutoResearchLab/frontend/components/paper_writing.py
    # .. -> components
    # .. -> frontend
    # .. -> root
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    experiments_dir = os.path.join(root_dir, "data", "experiments")
    
    if not os.path.exists(experiments_dir):
        st.info("No experiments found.")
        return

    experiments = [d for d in os.listdir(experiments_dir) if os.path.isdir(os.path.join(experiments_dir, d))]
    experiments.sort(reverse=True) # Newest first
    
    if not experiments:
        st.info("No experiments found.")
        return
        
    selected_exp = st.selectbox("Select Experiment to Draft Paper For", experiments)
    exp_path = os.path.join(experiments_dir, selected_exp)
    
    # 2. Load Data
    status_path = os.path.join(exp_path, "status.json")
    plan_path = os.path.join(exp_path, "plan.json")
    conclusion_path = os.path.join(exp_path, "conclusion.json")
    
    # Check data availability
    data_status = {
        "Status": os.path.exists(status_path),
        "Plan": os.path.exists(plan_path),
        "Conclusion": os.path.exists(conclusion_path),
        "Artifacts": len([f for f in os.listdir(exp_path) if f.endswith(('.png', '.csv'))]) > 0
    }
    
    with st.expander("💾 Data Availability Check", expanded=True):
        cols = st.columns(4)
        for i, (k, v) in enumerate(data_status.items()):
            cols[i].metric(k, "Available" if v else "Missing", delta="✅" if v else "❌")
            
    if not data_status["Conclusion"]:
        st.warning("⚠️ Conclusion data is missing. Please run the experiment analysis first.")
    
    # 3. Draft Editor / Preview
    st.divider()
    
    # Load content
    plan_data = {}
    if data_status["Plan"]:
        try:
            with open(plan_path) as f: plan_data = json.load(f)
        except: pass
            
    conclusion_data = {}
    if data_status["Conclusion"]:
        try:
            with open(conclusion_path) as f: conclusion_data = json.load(f)
        except: pass
            
    # Auto-fill content
    default_title = plan_data.get("title", "Untitled Research")
    default_abstract = conclusion_data.get("summary", "No summary available.")
    
    # Layout
    st.header(f"Draft: {default_title}")
    
    # AI Generation
    if st.button("🤖 Generate Draft with AI", type="primary"):
        if not data_status["Conclusion"]:
             st.error("Cannot generate draft without conclusion.")
        else:
             with st.spinner("AI is writing your paper (this may take a minute)..."):
                 try:
                     agent = WritingAgent()
                     artifacts = [f for f in os.listdir(exp_path) if f.endswith(('.png', '.jpg', '.csv'))]
                     draft = agent.generate_paper(plan_data, conclusion_data, artifacts)
                     st.session_state[f"paper_draft_{selected_exp}"] = draft
                     st.success("Draft generated!")
                 except Exception as e:
                     st.error(f"Generation failed: {e}")
    
    tab1, tab2, tab3, tab4 = st.tabs(["📄 Content Editor", "📊 Figures & Data", "📥 Export", "🤖 AI Full Draft"])
    
    with tab1:
        st.text_area("Title", value=default_title, height=68, key="paper_title")
        st.text_area("Abstract", value=default_abstract, height=150, key="paper_abstract")
        
        # Methodology from Plan
        method_text = "The experiment followed these steps:\n"
        for step in plan_data.get("steps", []):
            method_text += f"- {step.get('description', '')}\n"
        st.text_area("Methodology", value=method_text, height=200, key="paper_method")
        
        # Results from Conclusion
        results_text = "Key Findings:\n"
        for finding in conclusion_data.get("key_findings", []):
            results_text += f"- {finding}\n"
        st.text_area("Results", value=results_text, height=200, key="paper_results")
        
        st.text_area("Discussion", value=conclusion_data.get("recommendation", ""), height=150, key="paper_discussion")

    with tab2:
        st.info("Select artifacts to include in the paper.")
        artifacts = [f for f in os.listdir(exp_path) if f.endswith(('.png', '.jpg', '.csv'))]
        if artifacts:
            for art in artifacts:
                c1, c2 = st.columns([1, 3])
                with c1:
                    st.checkbox(f"Include {art}", value=True, key=f"inc_{art}")
                with c2:
                    if art.endswith('.csv'):
                        try:
                            st.dataframe(pd.read_csv(os.path.join(exp_path, art)), height=150)
                        except:
                            st.caption("Error reading CSV")
                    else:
                        st.image(os.path.join(exp_path, art), width=300)
        else:
            st.caption("No visual artifacts found.")

    with tab3:
        st.button("📄 Generate PDF (Placeholder)")
        st.button("💾 Save Draft (Placeholder)")

    with tab4:
        draft_content = st.session_state.get(f"paper_draft_{selected_exp}", "")
        if draft_content:
            st.markdown(draft_content)
            st.download_button("Download Markdown", draft_content, file_name="paper.md")
        else:
            st.info("Click 'Generate Draft with AI' above to create a full paper draft.")
