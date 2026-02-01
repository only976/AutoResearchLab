import streamlit as st
import sys
import os
import json
import uuid
import datetime

# Add project root to sys.path to allow imports from backend
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from backend.agents.idea_agent import IdeaAgent
from backend.templates.idea_templates import get_template_schema
from backend.utils.snapshot_manager import save_snapshot, list_snapshots, load_snapshot

def render_idea_card(idea, index, unique_key_prefix, topic=None):
    """Renders a single research idea based on its template type."""
    # Robust field extraction (handling potential case sensitivity or nesting issues)
    title = idea.get('title') or idea.get('Title') or idea.get('idea_name') or 'Untitled'
    template_type = idea.get('template_type') or idea.get('template_id') or 'scientific_discovery' # Default to general if missing
    idea_id = idea.get('idea_name') or idea.get('Name') or 'N/A'
    
    # Use a container for better isolation and to avoid DOM sync issues
    with st.container(border=True):
        st.markdown(f"### 💡 Idea {index + 1}: {title}")
        
        # Display Topic Context inside the idea card as requested
        if topic:
            st.markdown(f"**📍 Context:** {topic.get('title', 'Untitled')}")
            with st.expander("📄 View Research Scope", expanded=False):
                st.caption(f"**Keywords:** {', '.join(topic.get('keywords', []))}")
                st.info(f"**TL;DR:** {topic.get('tldr', '')}")
                st.markdown(f"**Abstract:**\n{topic.get('abstract', '')}")
            st.divider()
        
        # Common metadata
        st.caption(f"Template: {template_type} | ID: {idea_id}")
        
        # Handle content extraction: could be in 'content' key or flat in the root
        content = idea.get('content')
        if not content:
            # If no 'content' key, assume flat structure and exclude metadata keys
            content = {k: v for k, v in idea.items() if k not in ['title', 'Title', 'template_type', 'template_id', 'idea_name', 'Name']}
        
        # Retrieve schema to determine field order and labels
        schema = get_template_schema(template_type)
        schema_content = schema.get('content', {})
        
        # Determine the order of keys: first from schema, then any extras in content
        ordered_keys = list(schema_content.keys())
        extra_keys = [k for k in content.keys() if k not in ordered_keys]
        all_keys = ordered_keys + extra_keys
        
        # Dynamic rendering based on content fields
        for key in all_keys:
            if key not in content:
                continue
                
            value = content[key]
            formatted_key = key.replace('_', ' ').title()
            
            if isinstance(value, list):
                st.markdown(f"**{formatted_key}**")
                for item in value:
                    if isinstance(item, dict):
                         # Handle complex objects like risks_and_mitigations
                         # Avoid dynamic st.columns which can cause DOM sync issues
                         formatted_items = [f"- **{k.replace('_', ' ').title()}**: {v}" for k, v in item.items()]
                         st.markdown("\n".join(formatted_items))
                    else:
                        st.markdown(f"- {item}")
            elif isinstance(value, dict):
                st.markdown(f"**{formatted_key}**")
                st.json(value)
            else:
                st.markdown(f"**{formatted_key}**: {value}")
        
        # Action Buttons
        st.divider()
        col1, col2 = st.columns([1, 3])
        with col1:
            if st.button("🧪 Start Experiment", key=f"{unique_key_prefix}_start_btn", type="primary"):
                # Generate Unique Experiment ID
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                short_id = str(uuid.uuid4())[:8]
                exp_id = f"exp_{timestamp}_{short_id}"
                
                st.session_state.current_experiment = {
                    "id": exp_id,
                    "idea": idea,
                    "topic": topic,
                    "status": "Initialized"
                }
                st.session_state.page = "Experiment Lab"
                st.rerun()

def render_idea_generator():
    st.header("💡 Research Idea Generator")
    st.markdown("Enter your research scope below. The Agent will analyze its specificity and automatically generate targeted proposals.")

    if "step" not in st.session_state:
        st.session_state.step = "input"
    if "results" not in st.session_state:
        st.session_state.results = None
    if "refinement_data" not in st.session_state:
        st.session_state.refinement_data = None

    # Snapshot Loader
    with st.expander("📂 Load Saved Session", expanded=False):
        snapshots = list_snapshots()
        if not snapshots:
            st.info("No saved snapshots found.")
        else:
            col_snap, col_load = st.columns([3, 1])
            with col_snap:
                selected_snapshot = st.selectbox("Select Snapshot", snapshots, label_visibility="collapsed")
            with col_load:
                if st.button("Load", width="stretch"):
                    data = load_snapshot(selected_snapshot)
                    if data:
                        st.session_state.refinement_data = data.get("refinement_data")
                        st.session_state.results = data.get("results")
                        st.session_state.step = "done" # Jump to results
                        st.toast(f"Loaded snapshot: {selected_snapshot}")
                        st.rerun()
                    else:
                        st.error("Failed to load snapshot.")

    # Step 1: Input
    scope = st.text_area("Research Scope / Topic", 
                         placeholder="e.g., 'Gomoku AI' (Broad) or 'Multi-agent RL for autonomous driving' (Specific)", 
                         height=100,
                         key="scope_input")

    if st.button("Generate Ideas", type="primary"):
        if not scope:
            st.warning("Please enter a research scope first.")
        else:
            # Reset state
            st.session_state.results = []
            st.session_state.refinement_data = None
            
            with st.status("🚀 Agent is working...", expanded=True) as status:
                try:
                    agent = IdeaAgent()
                    
                    # 1. Refinement
                    status.write("🔍 Analyzing research scope specificity...")
                    refined_json = agent.refine_topic(scope)
                    refinement_data = json.loads(refined_json)
                    st.session_state.refinement_data = refinement_data
                    
                    topics = refinement_data.get("topics", [])
                    is_broad = refinement_data.get("is_broad", False)
                    analysis = refinement_data.get("analysis", "")
                    
                    if is_broad:
                        status.write(f"🌐 Broad topic detected. Generating ideas for {len(topics)} distinct directions...")
                    else:
                        status.write(f"🎯 Specific topic detected. Refining and generating ideas...")
                    
                    # 2. Generation Loop
                    results = []
                    for i, topic in enumerate(topics):
                        status.write(f"⚡ Brainstorming for direction {i+1}: {topic.get('title', 'Untitled')}...")
                        
                        rich_context = f"Title: {topic.get('title')}\nAbstract: {topic.get('abstract')}"
                        ideas_json_str = agent.generate_ideas(rich_context)
                        
                        try:
                            ideas_data = json.loads(ideas_json_str)
                        except json.JSONDecodeError:
                            ideas_data = {"error": "Failed to parse JSON", "raw": ideas_json_str}
                            
                        results.append({
                            "topic": topic,
                            "ideas_data": ideas_data
                        })
                    
                    st.session_state.results = results
                    st.session_state.step = "done"
                    status.update(label="✅ All tasks completed!", state="complete", expanded=False)
                    st.rerun()
                    
                except Exception as e:
                    st.error(f"An error occurred: {e}")
                    status.update(label="❌ Error occurred", state="error")

    # Step 3: Display Results
    if st.session_state.step == "done" and st.session_state.results:
        st.divider()
        
        ref_data = st.session_state.refinement_data
        if ref_data.get("is_broad"):
            st.info(f"ℹ️ **Broad Topic Detected**: {ref_data.get('analysis')}\n\nWe explored {len(st.session_state.results)} distinct research directions for you.")
            
            # Use tabs for multiple topics
            tabs = st.tabs([f"{i+1}. {r['topic'].get('title', 'Untitled')}" for i, r in enumerate(st.session_state.results)])
            
            for i, tab in enumerate(tabs):
                with tab:
                    result = st.session_state.results[i]
                    render_single_result(result["topic"], result["ideas_data"], f"broad_res_{i}")
        else:
            st.success(f"🎯 **Specific Topic Refined**: {ref_data.get('analysis')}")
            result = st.session_state.results[0]
            render_single_result(result["topic"], result["ideas_data"], "specific_res_0")
            
        st.divider()
        col1, col2 = st.columns([1, 5])
        with col1:
            if st.button("🔄 Start Over"):
                st.session_state.step = "input"
                st.session_state.results = None
                st.session_state.refinement_data = None
                st.rerun()
        with col2:
            if st.button("💾 Save Snapshot"):
                filename = save_snapshot(st.session_state.refinement_data, st.session_state.results)
                st.toast(f"Session saved to {filename}")

def render_single_result(topic, response_data, unique_key_prefix):
    """Helper to render one topic and its ideas."""
    
    # Render Reasoning
    if isinstance(response_data, dict) and "reasoning" in response_data:
        reasoning = response_data["reasoning"]
        with st.expander("🧠 Agent Reasoning", expanded=True):
            col1, col2 = st.columns(2)
            with col1:
                st.markdown(f"**Domain:** {reasoning.get('research_domain', 'N/A')}")
            with col2:
                st.markdown(f"**Template:** `{reasoning.get('selected_template', 'N/A')}`")
            st.markdown(f"**Rationale:** {reasoning.get('rationale', 'N/A')}")
            
    # Render Ideas
    ideas_list = response_data.get("ideas", []) if isinstance(response_data, dict) else response_data
    if isinstance(ideas_list, list):
        for i, idea in enumerate(ideas_list):
            render_idea_card(idea, i, f"{unique_key_prefix}_idea_{i}", topic)
    else:
        st.warning("No structured ideas found.")
        st.json(response_data)
