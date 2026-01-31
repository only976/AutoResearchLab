import streamlit as st
import json
import os
import time
import subprocess
from backend.agents.experiment_design_agent import ExperimentDesignAgent
from backend.execution.feedback_manager import FeedbackManager
from backend.execution.experiment_runner import start_experiment_background, start_analysis_background
from backend.sandbox.docker_sandbox import DockerSandbox

def load_experiment(exp_id):
    """Loads an existing experiment from disk."""
    workspace_path = os.path.join("data", "experiments", exp_id)
    
    # Load Plan
    plan_file = os.path.join(workspace_path, "plan.json")
    refined_plan = None
    if os.path.exists(plan_file):
        try:
            with open(plan_file, "r") as f:
                refined_plan = json.load(f)
        except:
            pass
            
    # Load Status
    status_file = os.path.join(workspace_path, "status.json")
    status = "Initialized"
    
    if os.path.exists(status_file):
        try:
            with open(status_file, "r") as f:
                s_data = json.load(f)
                status_val = s_data.get("experiment_status", "unknown")
                if status_val == "running": status = "Running"
                elif status_val == "completed": status = "Completed"
                elif status_val == "failed": status = "Failed"
        except:
            pass

    st.session_state.current_experiment = {
        "id": exp_id,
        "idea": {"title": refined_plan.get("title", exp_id) if refined_plan else exp_id},
        "topic": {"query": "Loaded Experiment"}, 
        "status": status,
        "refined_plan": refined_plan
    }
    
    # Reset UI step based on status
    if status in ["Running", "Completed", "Failed"]:
        st.session_state.ui_step = 3
    elif refined_plan:
        st.session_state.ui_step = 2
    else:
        st.session_state.ui_step = 1

def get_experiment_options():
    exp_root = os.path.join("data", "experiments")
    options = []
    if os.path.exists(exp_root):
        for d in os.listdir(exp_root):
            path = os.path.join(exp_root, d)
            if os.path.isdir(path) and d.startswith("exp_"):
                # Get Time
                mtime = os.path.getmtime(path)
                time_str = time.strftime("%Y-%m-%d %H:%M", time.localtime(mtime))
                
                # Get Title
                title = "Untitled"
                try:
                    with open(os.path.join(path, "plan.json"), "r") as f:
                        plan = json.load(f)
                        title = plan.get("title", "Untitled")
                except:
                    pass
                
                label = f"{title} ({time_str})"
                options.append({"id": d, "label": label, "mtime": mtime})
    
    # Sort by time desc
    options.sort(key=lambda x: x["mtime"], reverse=True)
    return options

def render_experiment_dashboard():
    st.header("🧪 Experiment Lab")
    
    # --- Persistence / Load ---
    with st.expander("📂 Load Experiment History", expanded=False):
        opts = get_experiment_options()
        if opts:
             # Create a mapping for selectbox
             opt_map = {f"{o['label']} [{o['id']}]": o['id'] for o in opts}
             selected_label = st.selectbox("Select Experiment", options=list(opt_map.keys()))
             
             if st.button("📂 Load Selected"):
                 exp_id = opt_map[selected_label]
                 load_experiment(exp_id)
                 st.rerun()
        else:
             st.info("No history found.")
    
    if "current_experiment" not in st.session_state or not st.session_state.current_experiment:
        st.info("No active experiment. Go to 'Idea Generator' to start one.")
        return

    experiment = st.session_state.current_experiment
    idea = experiment.get("idea", {})
    topic = experiment.get("topic", {})
    status = experiment.get("status", "Initialized")
    refined_plan = experiment.get("refined_plan")
    
    # Define Workspace Path
    exp_id = experiment.get("id", "temp_experiment")
    workspace_path = os.path.abspath(os.path.join("data", "experiments", exp_id))

    # Header
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.subheader(f"Experiment: {idea.get('title', 'Untitled')}")
            st.caption(f"ID: {experiment.get('id', 'N/A')}")
        with col2:
            st.metric("Status", status)

    # State Management for Steps
    if "ui_step" not in st.session_state:
        st.session_state.ui_step = 1

    has_plan = refined_plan is not None
    is_running = status == "Running"

    # Auto-advance logic based on external state changes
    if not has_plan:
        st.session_state.ui_step = 1
    elif is_running:
        st.session_state.ui_step = 3
    elif st.session_state.ui_step == 1 and has_plan:
        # Just finished generating plan
        st.session_state.ui_step = 2

    # --- Step 1: Plan Generation ---
    step1_expanded = (st.session_state.ui_step == 1)
    with st.expander("1️⃣ Plan Generation", expanded=step1_expanded):
        if not has_plan:
            st.write("Generate a detailed experiment plan based on the selected idea.")
            if st.button("📝 Generate Plan", type="primary"):
                with st.spinner("Agent is designing the experiment details..."):
                     design_agent = ExperimentDesignAgent()
                     plan_str = design_agent.refine_plan(idea, topic)
                     try:
                        plan_data = json.loads(plan_str)
                        st.session_state.current_experiment["refined_plan"] = plan_data
                        st.session_state.current_experiment["status"] = "Plan Ready"
                        st.session_state.ui_step = 2
                        st.rerun()
                     except Exception as e:
                        st.error(f"Failed to parse plan: {e}")
        else:
            st.success("✅ Plan Generated")
            st.markdown(f"**Goal:** {refined_plan.get('goal', 'N/A')}")
            if st.button("Show Plan Details"):
                 st.json(refined_plan)

    # --- Step 2: Environment & Risk Check ---
    # Always visible if plan exists, but collapsed if running
    if has_plan:
        step2_expanded = (st.session_state.ui_step == 2)
        with st.expander("2️⃣ Environment & Risk Check", expanded=step2_expanded):
            # Risk Analysis
            all_issues = refined_plan.get("issues", [])
            blockers = [i for i in all_issues if i.get("severity", "blocking") == "blocking"]
            warnings = [i for i in all_issues if i.get("severity") == "warning"]
            
            # Dependencies Analysis
            all_deps_check = []
            for step in refined_plan.get("steps", []):
                all_deps_check.extend(step.get("dependencies", []))
            manual_deps = [d for d in all_deps_check if d.get("status") == "manual_intervention_required"]
            
            can_execute = True
            
            # Display Status
            col_risk1, col_risk2 = st.columns([2, 1])
            with col_risk1:
                if blockers or manual_deps:
                    st.error(f"⛔ {len(blockers) + len(manual_deps)} Blocking Issues Detected")
                    can_execute = False
                elif warnings:
                    st.warning(f"⚠️ {len(warnings)} Warnings (Non-blocking)")
                else:
                    st.success("✅ No Blocking Issues")
            
            # Resolution Interface
            if all_issues or manual_deps:
                st.markdown("#### Risk Resolution")
                with st.container(border=True):
                    risk_feedback = st.text_area("Feedback to Agent (e.g., 'I have the data')", key="risk_fb")
                    if st.button("🤖 Agent: Re-evaluate Plan"):
                        if risk_feedback:
                            with st.spinner("Agent is re-evaluating risks..."):
                                 design_agent = ExperimentDesignAgent()
                                 new_plan_str = design_agent.process_feedback(refined_plan, risk_feedback)
                                 try:
                                    new_plan = json.loads(new_plan_str)
                                    st.session_state.current_experiment["refined_plan"] = new_plan
                                    st.success("Plan updated!")
                                    st.rerun()
                                 except Exception as e:
                                    st.error(f"Failed to update plan: {e}")

            st.divider()
            
            # Environment Checks
            st.markdown("#### Environment Checks")
            col_sys1, col_sys2, col_sys3 = st.columns(3)
            
            # Docker
            try:
                sandbox = DockerSandbox()
                docker_ok = sandbox.client is not None
            except:
                docker_ok = False
            col_sys1.metric("Docker", "Running" if docker_ok else "Missing", delta="✅" if docker_ok else "❌")
            
            # Git
            git_ok = os.path.exists(os.path.join(workspace_path, ".git"))
            col_sys2.metric("Git Repo", "Ready" if git_ok else "Pending", delta="✅" if git_ok else "⚪")
            
            # Requirements
            req_path = os.path.join(workspace_path, "requirements.txt")
            req_ok = os.path.exists(req_path)
            col_sys3.metric("Dependencies", "Ready" if req_ok else "Pending", delta="✅" if req_ok else "⚪")
            
            if not docker_ok:
                st.error("Docker is required for execution.")
                can_execute = False

            # Force Execute Option
            if (blockers or manual_deps or not docker_ok) and not can_execute:
                 if st.checkbox("✅ Force Execute (I accept all risks)", value=False, key="force_exec"):
                     can_execute = True

            st.markdown("---")
            if st.button("➡️ Proceed to Execution", disabled=not can_execute, type="primary"):
                st.session_state.ui_step = 3
                st.rerun()

    # --- Step 3: Code Execution ---
    if has_plan:
        step3_expanded = (st.session_state.ui_step == 3)
        with st.expander("3️⃣ Code Execution", expanded=step3_expanded):
            
            # Execution Controls
            col_ctrl1, col_ctrl2, col_ctrl3 = st.columns([1, 1, 2])
            
            with col_ctrl1:
                if status != "Running":
                    label = "🔄 Retry Execution" if status == "Failed" else "▶️ Start Execution"
                    if st.button(label, type="primary"):
                        st.session_state.current_experiment["status"] = "Running"
                        start_experiment_background(workspace_path, refined_plan)
                        st.rerun()
                else:
                    st.info("🚀 Experiment is Running...")

            with col_ctrl2:
                if st.button("⏹️ Stop", disabled=(status != "Running")):
                    st.session_state.current_experiment["status"] = "Stopped"
                    st.rerun()
            
            with col_ctrl3:
                 if st.button("🗑️ Reset Experiment"):
                    st.session_state.current_experiment = None
                    st.session_state.ui_step = 1
                    st.rerun()

            st.divider()
            
            # --- PROGRESS TRACKER ---
            st.markdown("### 📊 Progress Tracker")
            status_file = os.path.join(workspace_path, "status.json")
            
            if os.path.exists(status_file):
                try:
                    with open(status_file, "r") as f:
                        status_data = json.load(f)
                    
                    # Progress Bar
                    curr = status_data.get("current_step", 0)
                    total = status_data.get("total_steps", 1)
                    if total == 0: total = 1
                    
                    if curr <= 0:
                        display_progress = 0.0
                        step_text = "Setting up Environment..."
                    else:
                        display_progress = min(curr / total, 1.0)
                        step_text = f"Step {curr} of {total}"
                        
                    st.progress(display_progress, text=step_text)
                    
                    # Status Details
                    s_status = status_data.get("status", "unknown")
                    exp_status = status_data.get("experiment_status", "running")
                    s_name = status_data.get("step_name", "")
                    s_details = status_data.get("details", "")
                    
                    # Sync backend status to frontend session state
                    if exp_status == "failed" and status == "Running":
                        st.session_state.current_experiment["status"] = "Failed"
                        st.rerun()
                    elif exp_status == "completed" and status == "Running":
                        st.session_state.current_experiment["status"] = "Completed"
                        st.rerun()
                    
                    st.markdown(f"**Current Step:** {s_name}")
                    
                    if s_status == "running":
                        st.info(f"🔄 {s_details}")
                        if status == "Running":
                            time.sleep(2)
                            st.rerun()
                    elif s_status == "fixing":
                        st.warning(f"🛠️ {s_details}")
                        if status == "Running":
                            time.sleep(2)
                            st.rerun()
                    elif s_status == "completed":
                        st.success(f"✅ {s_details}")
                        if status == "Running":
                            time.sleep(1)
                            st.rerun()
                    elif s_status == "failed":
                        st.error(f"❌ {s_details}")
                        if status == "Running":
                            time.sleep(2)
                            st.rerun()
                        
                except Exception as e:
                    st.caption(f"Error reading status: {e}")
            else:
                st.caption("Waiting for execution to start...")
                if status == "Running":
                    time.sleep(2)
                    st.rerun()

            # --- HUMAN FEEDBACK ---
            st.divider()
            st.markdown("### 🗣️ Human Feedback (Runtime)")
            fb_col1, fb_col2 = st.columns([3, 1])
            with fb_col1:
                feedback_msg = st.text_input("Message", key="fb_msg", placeholder="Guidance for the agent...")
            with fb_col2:
                feedback_type = st.selectbox("Type", ["Suggestion", "Risk", "Correction"], key="fb_type")
            
            if st.button("📨 Send Feedback"):
                if feedback_msg:
                    fm = FeedbackManager(workspace_path)
                    fm.add_feedback(feedback_type.lower(), feedback_msg)
                    st.success("Feedback queued.")
                else:
                    st.warning("Empty message.")

            # --- GIT HISTORY ---
            st.divider()
            st.markdown("### 📜 Project History (Git)")
            if os.path.exists(os.path.join(workspace_path, ".git")):
                 try:
                     res = subprocess.run(
                         ["git", "log", "--pretty=format:%h|%s|%cr|%an", "-n", "10"], 
                         cwd=workspace_path, 
                         stdout=subprocess.PIPE, 
                         text=True
                     )
                     if res.returncode == 0 and res.stdout:
                         commits = []
                         for line in res.stdout.strip().split('\n'):
                             parts = line.split('|')
                             if len(parts) == 4:
                                 commits.append({
                                     "Commit": parts[0], 
                                     "Message": parts[1], 
                                     "Time": parts[2],
                                     "Author": parts[3]
                                 })
                         st.dataframe(
                             commits, 
                             column_config={
                                 "Commit": st.column_config.TextColumn("ID", width="small"),
                                 "Message": st.column_config.TextColumn("Action", width="large"),
                                 "Time": st.column_config.TextColumn("When", width="medium"),
                             },
                             hide_index=True,
                             use_container_width=True
                         )
                     else:
                         st.caption("No history yet.")
                 except Exception as e:
                     st.error(f"Error reading history: {e}")
            else:
                 st.caption("History not available yet.")

            # --- RESULTS / ARTIFACTS ---
            st.divider()
            st.markdown("### 📂 Artifacts & Results")
            
            artifact_files = []
            if os.path.exists(workspace_path):
                for f in os.listdir(workspace_path):
                    # Exclude system files, logs, and directories
                    if f in ["status.json", "plan.json", "requirements.txt", ".gitignore", "user_feedback.json", "Dockerfile.exp"] or f.startswith(".") or f.endswith(".log") or os.path.isdir(os.path.join(workspace_path, f)):
                        continue
                    artifact_files.append(f)
            
            if artifact_files:
                selected_artifact = st.selectbox("View Artifact", sorted(artifact_files), key="artifact_select")
                file_path = os.path.join(workspace_path, selected_artifact)
                
                try:
                    if selected_artifact.lower().endswith(('.png', '.jpg', '.jpeg')):
                        st.image(file_path, caption=selected_artifact)
                    elif selected_artifact.lower().endswith('.csv'):
                        import pandas as pd
                        st.dataframe(pd.read_csv(file_path))
                    elif selected_artifact.lower().endswith(('.json', '.txt', '.log', '.py', '.md')):
                        with open(file_path, "r") as f:
                            st.code(f.read())
                    else:
                        st.info(f"File type not supported for preview: {selected_artifact}")
                except Exception as e:
                    st.error(f"Error reading file: {e}")
            else:
                st.caption("No artifacts generated yet.")

            # --- DEBUG LOGS (Hidden) ---
            with st.expander("🔍 Debug Logs (Optional)"):
                log_path = os.path.join(workspace_path, "execution.log")
                if os.path.exists(log_path):
                     with open(log_path, "r") as f:
                         logs = f.read()
                     st.code(logs, language="text")
                     if status == "Running":
                         if st.button("🔄 Refresh Logs"):
                             st.rerun()

        # --- CONCLUSION ---
        st.divider()
        col_conc_header, col_conc_btn = st.columns([3, 1])
        with col_conc_header:
            st.markdown("### 🏆 Final Conclusion")
        with col_conc_btn:
            # Only allow regeneration if not running
            if status != "Running":
                if st.button("🔄 Regenerate", help="Run only the analysis and conclusion synthesis phase"):
                        st.session_state.current_experiment["status"] = "Running"
                        start_analysis_background(workspace_path, refined_plan)
                        st.rerun()

        conclusion_path = os.path.join(workspace_path, "conclusion.json")
        if os.path.exists(conclusion_path):
            try:
                with open(conclusion_path, "r") as f:
                    conclusion = json.load(f)
                
                st.info(f"**{conclusion.get('title', 'Conclusion')}**")
                st.write(conclusion.get("summary", ""))
                
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**Key Findings:**")
                    for finding in conclusion.get("key_findings", []):
                        st.markdown(f"- {finding}")
                        
                with c2:
                    st.markdown("**Recommendation:**")
                    st.write(conclusion.get("recommendation", "None"))
                    
                if "evidence" in conclusion:
                    with st.expander("📊 Evidence & Metrics"):
                        st.json(conclusion["evidence"])
                        
            except Exception as e:
                st.error(f"Error reading conclusion: {e}")
        else:
            st.info("No conclusion generated yet.")
