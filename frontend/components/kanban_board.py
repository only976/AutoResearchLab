import streamlit as st

def render_kanban():
    st.markdown("#### Agent Workflow Status")
    
    # Define columns for different stages
    col1, col2, col3, col4 = st.columns(4)
    
    stages = [
        {"name": "Idea Generation", "icon": "💡", "col": col1},
        {"name": "Code Execution", "icon": "⚙️", "col": col2},
        {"name": "Review & Eval", "icon": "🧐", "col": col3},
        {"name": "Paper Writing", "icon": "📝", "col": col4},
    ]

    # Mock data for demonstration
    # In a real app, this would come from the backend state
    tasks = {
        "Idea Generation": [{"title": "Generate Research Topic", "status": "completed"}, {"title": "Lit Review", "status": "in_progress"}],
        "Code Execution": [{"title": "Setup Sandbox", "status": "pending"}],
        "Review & Eval": [{"title": "Feasibility Check", "status": "pending"}],
        "Paper Writing": [{"title": "Draft Introduction", "status": "pending"}]
    }
    
    for stage in stages:
        with stage["col"]:
            st.subheader(f"{stage['icon']} {stage['name']}")
            st.divider()
            
            stage_tasks = tasks.get(stage["name"], [])
            if not stage_tasks:
                st.caption("No active tasks")
            
            for task in stage_tasks:
                status_color = "gray"
                if task["status"] == "completed":
                    status_color = "green"
                elif task["status"] == "in_progress":
                    status_color = "blue"
                elif task["status"] == "error":
                    status_color = "red"
                
                with st.container(border=True):
                    st.markdown(f"**{task['title']}**")
                    st.caption(f"Status: :{status_color}[{task['status'].upper()}]")
