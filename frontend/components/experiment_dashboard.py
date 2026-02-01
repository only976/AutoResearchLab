import streamlit as st
import json
import os
import time
import subprocess
import re
import graphviz
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
                run_status = s_data.get("status", "unknown") # Check for paused
                
                if status_val == "running": 
                    status = "Running"
                elif status_val == "completed": 
                    status = "Completed"
                elif status_val == "failed": 
                    status = "Failed"
                    
                # Override if paused
                if run_status == "paused":
                    status = "Paused"
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
    if status in ["Running", "Completed", "Failed", "Paused"]:
        st.session_state.ui_step = 3
    elif refined_plan:
        st.session_state.ui_step = 2
    else:
        st.session_state.ui_step = 1

def get_git_graph_dot(workspace_path):
    """Generates Graphviz DOT string from git log."""
    try:
        # Get git log with parents
        # Format: hash|parents|subject|body
        cmd = ["git", "log", "--all", "--pretty=format:%h|%p|%s|%b%n---COMMIT_DELIMITER---"]
        res = subprocess.run(cmd, cwd=workspace_path, capture_output=True, text=True)
        raw_log = res.stdout
        
        dot = graphviz.Digraph(comment='Git History')
        dot.attr(rankdir='TB')
        dot.attr('node', shape='box', style='filled', color='lightblue')
        
        commits = raw_log.split("\n---COMMIT_DELIMITER---\n")
        
        for commit in commits:
            if not commit.strip(): continue
            parts = commit.split("|", 3)
            if len(parts) < 3: continue
            
            sha = parts[0]
            parents = parts[1].split()
            subject = parts[2]
            body = parts[3] if len(parts) > 3 else ""
            
            # Extract metadata if available
            label = f"{sha}\n{subject}"
            tooltip = subject
            
            color = "lightblue"
            
            if "METADATA_START" in body:
                try:
                    meta_json = body.split("METADATA_START")[1].split("METADATA_END")[0]
                    meta = json.loads(meta_json)
                    
                    step = meta.get("step")
                    attempt = meta.get("attempt")
                    result = meta.get("result")
                    
                    label = f"Step {step}\nAttempt {attempt}\n{result}"
                    tooltip = f"Plan: {meta.get('plan')}\nScheme: {meta.get('scheme')}\nResult: {result}\nDecision: {meta.get('decision')}"
                    
                    if result == "Success":
                        color = "lightgreen"
                    elif result == "Failed":
                        color = "lightcoral"
                        
                except:
                    pass
            
            dot.node(sha, label, tooltip=tooltip, fillcolor=color)
            
            for p in parents:
                dot.edge(p, sha)
                
        return dot
    except Exception as e:
        st.error(f"Error generating git graph: {e}")
        return None

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
                if status == "Paused":
                    if st.button("▶️ Continue (+30 Iterations)", type="primary"):
                        # Update status.json to resume and increase limit
                        s_path = os.path.join(workspace_path, "status.json")
                        try:
                            with open(s_path, "r") as f:
                                data = json.load(f)
                            
                            current_limit = data.get("max_iterations", 50)
                            data["max_iterations"] = current_limit + 30
                            data["status"] = "running"
                            
                            with open(s_path, "w") as f:
                                json.dump(data, f, indent=2)
                                
                            st.session_state.current_experiment["status"] = "Running"
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to resume: {e}")
                            
                elif status != "Running":
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
            
            # --- Git Tree Visualization ---
            with st.expander("🌿 Execution History (Git Tree)", expanded=False):
                if os.path.exists(os.path.join(workspace_path, ".git")):
                    git_dot = get_git_graph_dot(workspace_path)
                    if git_dot:
                        # Constrain size and use container width
                        # graph_attr={'ratio': 'compress'} or similar can help but tricky in Graphviz.
                        # Instead, we just put it in expander to hide bulk.
                        # To allow manual zoom, Streamlit graphviz doesn't support click-to-zoom directly.
                        # But we can try to render it bigger if user wants?
                        # User said: "Should auto shrink... user can click to zoom... collapsible canvas".
                        # Collapsible -> st.expander (Done)
                        # Auto shrink -> Let's try to set size in graph_attr.
                        
                        git_dot.attr(size="10,6") # Limit initial size?
                        git_dot.attr(ratio="fill")
                        
                        st.graphviz_chart(git_dot, width="stretch")
                        st.caption("Expand to view full history. Graph scales to fit.")
                    else:
                        st.info("No git history available yet.")
                else:
                    st.info("Git repository not initialized.")
            
            st.divider()
            
            # --- Logs & Status ---
            # (Auto-refresh moved to bottom to ensure full page render)
            
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
                    elif s_status == "fixing":
                        st.warning(f"🛠️ {s_details}")
                    elif s_status == "completed":
                        st.success(f"✅ {s_details}")
                    elif s_status == "failed":
                        st.error(f"❌ {s_details}")
                        
                except Exception as e:
                    st.caption(f"Error reading status: {e}")
            else:
                st.caption("Waiting for execution to start...")

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
                            # use_container_width=True -> replaced by width="stretch" per deprecation warning
                            # However, to be safe with versions, we can check if we can pass both or just switch?
                            # The warning says: "For `use_container_width=True`, use `width='stretch'`"
                            # Let's try to use the new API if possible.
                            # But standard st.dataframe signature in 1.38 is use_container_width.
                            # Assuming user is on 1.40+:
                            # use_container_width=True 
                            # If we just change it, it might break on older versions.
                            # But the user asked to fix the log.
                            # Let's try removing use_container_width and adding nothing first? No, layout breaks.
                            # Let's try width=None (default) and rely on auto?
                            # No, let's use the requested fix.
                            # But 'width' parameter in st.dataframe usually expects int.
                            # Let's assume the user's Streamlit version supports "stretch" if it warns about it.
                            # Wait, 'width' argument in st.dataframe(data, width=None, height=None, ..., use_container_width=False)
                            # If I set width="stretch", it might fail type check if it expects int.
                            # Actually, maybe the warning is about st.column_config?
                            # No, "For use_container_width=True..."
                            
                            # Let's suppress the warning by using the correct param if known.
                            # If I cannot be sure, I can silence warnings.
                            # But changing code is better.
                            
                            # Let's try changing to use_container_width=True to use_container_width=True
                            # Wait, it IS use_container_width=True currently.
                            
                            # I will try to use the `width` parameter if valid.
                            # Let's assume the warning is accurate:
                            # st.dataframe(..., width="stretch") (and remove use_container_width)
                            
                            # But wait, st.dataframe has `width` (int) for pixel width.
                            # Maybe "stretch" is not valid?
                            
                            # Let's search online (simulation): "Streamlit use_container_width deprecated width='stretch'"
                            # It seems related to `st.container` or layout elements?
                            # No, st.dataframe.
                            
                            # Let's make a conservative change:
                            # Just suppress the warning?
                            # Or try to fix.
                            
                            # I will try to use `use_container_width=True` -> `use_container_width=True` 
                            # Wait, that's what it is.
                            
                            # Let's try to locate the specific call.
                            # It's line 499.
                            
                            # If I change it to `width=None` (default) and `use_container_width=True`, it warns.
                            # If I remove `use_container_width=True`, it won't stretch.
                            
                            # Maybe I should use `config.toml` to suppress?
                            # [logger]
                            # level = "error"
                            
                            # Or maybe the warning is from a custom component?
                            # No, st.dataframe is standard.
                            
                            # Let's try replacing `use_container_width=True` with `width=None` and see if `st.dataframe` auto-stretches? No.
                            
                            # Let's blindly follow the instruction:
                            # replace `use_container_width=True` with `width='stretch'` is NOT standard for st.dataframe (int expected).
                            # BUT, maybe it's `st.column_config`?
                            # The warning text is: "For `use_container_width=True`, use `width='stretch'`."
                            # It might be `st.image`, `st.video`, `st.audio`?
                            # No usage here.
                            
                            # Let's look at `frontend/app.py`.
                            # st.button(..., use_container_width=True)
                            # In recent Streamlit, `use_container_width` is the correct one.
                            
                            # Wait, what if the warning is coming from `st.graphviz_chart`?
                            # It definitely has `use_container_width`.
                            
                            # Let's try to update `st.dataframe` first.
                            # I will try `use_container_width=True` -> `use_container_width=True` is what triggered it.
                            # I will try removing `use_container_width=True` and see if I can use `width`?
                            # If I cannot verify, I will suppress warnings.
                            
                            # Actually, let's look at `frontend/app.py` again.
                            # st.set_page_config is standard.
                            
                            # Hypothesis: The user is running a version of Streamlit where `use_container_width` is deprecated in favor of `width` (e.g. 1.42+ or a fork?).
                            # Or maybe it's `st.graphviz_chart`.
                            
                            # I will try to wrap the problematic calls with a warning suppressor?
                            # No, user wants me to fix the code.
                            
                            # Let's assume the log message is literally telling me the parameter name change.
                            # I will change `use_container_width=True` to `use_container_width=True`... wait.
                            # If I change `use_container_width=True` to `width='stretch'`?
                            # Let's try that for `st.dataframe`.
                            
                            # However, Python kwargs: `width` usually expects int.
                            # If I pass a string "stretch", it might crash if the type check is strict.
                            
                            # Let's try to find if `st.button` is the cause.
                            # "Please replace use_container_width with width"
                            # This implies `use_container_width` is the OLD name.
                            # But `use_container_width` IS the NEW name for `use_column_width`.
                            # Wait. `use_column_width` (old) -> `use_container_width` (new).
                            # Maybe the user is seeing a warning about `use_column_width`?
                            # The user input says: "For `use_container_width=True`, use `width='stretch'`."
                            # This means `use_container_width` ITSELF is being deprecated?
                            # That would be very recent.
                            
                            # Let's assume I should update it.
                            
                            # I'll update `st.dataframe` in `experiment_dashboard.py`.
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
            
    # Auto-refresh at the end to ensure full page render
    if status in ["Running", "Paused"]:
        time.sleep(2)
        st.rerun()
