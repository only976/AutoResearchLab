import time
import json
import os
import threading
import subprocess
import re
from backend.execution.feedback_manager import FeedbackManager
from backend.sandbox.docker_sandbox import DockerSandbox
from backend.agents.coding_agent import CodingAgent
from backend.agents.data_analysis_agent import DataAnalysisAgent
from backend.agents.review_agent import ReviewAgent
from backend.utils.logger import setup_logger

class ExperimentRunner:
    def __init__(self, workspace_path, plan):
        self.workspace_path = workspace_path
        self.plan = plan
        self.log_file = os.path.join(workspace_path, "execution.log")
        self.fm = FeedbackManager(workspace_path)
        self.coding_agent = CodingAgent()
        self.data_agent = DataAnalysisAgent()
        self.review_agent = ReviewAgent()
        self.logger = setup_logger(self.__class__.__name__)
        self.image_tag = None # Initialize image tag
        
        # Iteration Control
        self.max_iterations = 50
        self.current_iterations = 0
        self._load_iteration_state()

    def _load_iteration_state(self):
        """Loads iteration state from status.json if exists."""
        status_path = os.path.join(self.workspace_path, "status.json")
        if os.path.exists(status_path):
            try:
                with open(status_path, "r") as f:
                    data = json.load(f)
                    self.current_iterations = data.get("current_iterations", 0)
                    self.max_iterations = data.get("max_iterations", 50)
            except:
                pass

    def _save_iteration_state(self):
        """Saves current iteration state to status.json."""
        status_path = os.path.join(self.workspace_path, "status.json")
        data = {}
        if os.path.exists(status_path):
            try:
                with open(status_path, "r") as f:
                    data = json.load(f)
            except:
                pass
        
        data["current_iterations"] = self.current_iterations
        data["max_iterations"] = self.max_iterations
        
        with open(status_path, "w") as f:
            json.dump(data, f, indent=2)

    def _check_and_wait_for_limit(self):
        """Checks if iteration limit is reached and waits for user approval."""
        while self.current_iterations >= self.max_iterations:
            self.log(f"⏸️ Iteration limit reached ({self.current_iterations}/{self.max_iterations}). Waiting for user approval...")
            
            # Update status to paused
            status_path = os.path.join(self.workspace_path, "status.json")
            if os.path.exists(status_path):
                with open(status_path, "r") as f:
                    data = json.load(f)
                data["status"] = "paused"
                data["message"] = f"Iteration limit reached ({self.max_iterations}). Please extend to continue."
                with open(status_path, "w") as f:
                    json.dump(data, f, indent=2)
            
            # Wait loop
            time.sleep(5)
            
            # Check if limit has been increased (by frontend modifying status.json or via reload)
            self._load_iteration_state()
            
            if self.current_iterations < self.max_iterations:
                self.log(f"▶️ Resuming execution. Limit extended to {self.max_iterations}.")
                # Restore running status
                if os.path.exists(status_path):
                    with open(status_path, "r") as f:
                        data = json.load(f)
                    data["status"] = "running"
                    with open(status_path, "w") as f:
                        json.dump(data, f, indent=2)
                break

    def _commit_structured(self, step_id, attempt, plan, scheme, result, decision, output=None):
        """Creates a git commit with structured metadata."""
        message = f"Step {step_id}: Attempt {attempt} - {result}\n\n"
        
        metadata = {
            "step": step_id,
            "attempt": attempt,
            "plan": plan,
            "scheme": scheme,
            "result": result,
            "decision": decision,
            "timestamp": time.time()
        }
        
        message += f"METADATA_START\n{json.dumps(metadata, indent=2)}\nMETADATA_END\n"
        
        if output:
            message += f"\nOUTPUT_PREVIEW:\n{output[:500]}..."
            
        self._run_git_cmd(["add", "."])
        self._run_git_cmd(["commit", "--allow-empty", "-m", message])

    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        print(entry.strip()) # Also print to console
        
        # Write to experiment-specific execution log
        with open(self.log_file, "a") as f:
            f.write(entry)
            
        # Also log to system-wide logger
        self.logger.info(f"[{os.path.basename(self.workspace_path)}] {message}")

    def _sanitize_filename(self, text):
        """Converts text to a safe filename."""
        s = re.sub(r'[^\w\s-]', '', text.lower())
        return re.sub(r'[-\s]+', '_', s).strip('-_') + ".py"

    def _run_git_cmd(self, args, check=False):
        """Helper to run git commands in workspace."""
        try:
            result = subprocess.run(
                ["git"] + args, 
                cwd=self.workspace_path, 
                check=check, 
                stdout=subprocess.PIPE, 
                stderr=subprocess.PIPE,
                text=True
            )
            return result.returncode == 0
        except subprocess.CalledProcessError as e:
            self.log(f"Git command failed: git {' '.join(args)}\n{e.stderr}")
            return False

    def _init_workspace(self):
        """Initializes git and workspace."""
        if not os.path.exists(os.path.join(self.workspace_path, ".git")):
            self.log("Initializing Git repository...")
            try:
                subprocess.run(["git", "init"], cwd=self.workspace_path, check=False, stdout=subprocess.DEVNULL)
                # Configure git user for this repo
                self._run_git_cmd(["config", "user.email", "agent@autoresearchlab.ai"])
                self._run_git_cmd(["config", "user.name", "AutoResearch Agent"])
                
                with open(os.path.join(self.workspace_path, ".gitignore"), "w") as f:
                    f.write("__pycache__/\n*.pyc\nexecution.log\n.DS_Store\n")
                
                self._run_git_cmd(["add", "."])
                self._run_git_cmd(["commit", "-m", "Initial commit"])
                self._run_git_cmd(["branch", "-M", "main"]) # Ensure branch is main
                self.log("Git repository initialized.")
            except Exception as e:
                self.log(f"Warning: Git init failed: {e}")
        
        # Save plan to disk for persistence
        with open(os.path.join(self.workspace_path, "plan.json"), "w") as f:
            json.dump(self.plan, f, indent=2)

    def _setup_dependencies(self):
        """Prepares requirements.txt for Docker."""
        self.log("Analyzing dependencies...")
        steps = self.plan.get("steps", [])
        pip_packages = set()
        
        # Common standard library modules to ignore
        std_lib_modules = {
            "abc", "argparse", "array", "asyncio", "base64", "binascii", "bisect", "builtins",
            "calendar", "cmath", "collections", "contextlib", "copy", "csv", "datetime",
            "decimal", "difflib", "enum", "errno", "fnmatch", "functools", "gc", "glob",
            "hashlib", "heapq", "hmac", "html", "http", "importlib", "inspect", "io",
            "itertools", "json", "logging", "math", "mmap", "multiprocessing", "netrc",
            "numbers", "operator", "os", "pathlib", "pickle", "platform", "pprint",
            "profile", "pstats", "queue", "random", "re", "select", "shlex", "shutil",
            "signal", "socket", "sqlite3", "ssl", "stat", "statistics", "string", "struct",
            "subprocess", "sys", "tempfile", "textwrap", "threading", "time", "timeit",
            "tokenize", "traceback", "types", "typing", "unittest", "urllib", "uuid",
            "warnings", "weakref", "xml", "zipfile", "zlib"
        }

        for step in steps:
            for dep in step.get("dependencies", []):
                if dep.get("type") == "python_package" and dep.get("status") == "auto_installable":
                    name = dep.get("name").strip()
                    # Filter out common hallucinations or built-ins
                    if name.lower() in ["typing", "typing module", "typing_module", "python standard library", "standard library", "built-in"] or name in std_lib_modules:
                        continue
                    pip_packages.add(name)
        
        if pip_packages:
            # Always add standard analysis libraries for the analysis phase
            pip_packages.add("pandas")
            pip_packages.add("matplotlib")
            pip_packages.add("seaborn")
            
            req_path = os.path.join(self.workspace_path, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("\n".join(pip_packages))
            self.log(f"Created requirements.txt with: {', '.join(pip_packages)}")
        else:
            # Even if no plan dependencies, we need analysis libs
            pip_packages = {"pandas", "matplotlib", "seaborn"}
            req_path = os.path.join(self.workspace_path, "requirements.txt")
            with open(req_path, "w") as f:
                f.write("\n".join(pip_packages))
            self.log(f"Created requirements.txt with default analysis libraries: {', '.join(pip_packages)}")
            
    def _update_status(self, step_idx, total_steps, current_step_name, status, details=None, experiment_status="running"):
        """Updates the status.json file for frontend monitoring."""
        status_file = os.path.join(self.workspace_path, "status.json")
        data = {
            "experiment_status": experiment_status,
            "current_step": step_idx + 1,
            "total_steps": total_steps,
            "step_name": current_step_name,
            "status": status, # "running", "completed", "failed", "fixing"
            "details": details or "",
            "last_updated": time.time()
        }
        with open(status_file, "w") as f:
            json.dump(data, f)

    def _get_git_graph(self):
        """Returns the git graph for context."""
        try:
            res = subprocess.run(
                ["git", "log", "--oneline", "--graph", "--all", "-n", "20"], 
                cwd=self.workspace_path, 
                capture_output=True, 
                text=True
            )
            return res.stdout
        except:
            return "(Git graph unavailable)"

    def run_step(self, step, step_idx, total_steps):
        self._update_status(step_idx, total_steps, step['name'], "running", "Initializing step...")
        self.log(f"▶️ Starting Step {step['step_id']}: {step['name']}")
        self.log(f"   Description: {step['description']}")
        
        # Ensure we start from a stable main state
        self._run_git_cmd(["checkout", "main"])
        
        step_slug = self._sanitize_filename(step['name']).replace('.py', '')
        filename = self._sanitize_filename(step['name'])
        
        # 1. Pre-execution Feedback Check
        pending = self.fm.get_pending_feedback()
        if pending:
            self.log(f"🔔 INTERRUPT: Received {len(pending)} user feedback item(s).")
            for item in pending:
                self.log(f"   👤 User says ({item['type']}): \"{item['message']}\"")
                self.log(f"   🤖 Agent: Acknowledged. Integrating feedback into current context...")
                self.fm.mark_processed(item['id'])
                time.sleep(1) 
        
        current_code = None
        max_retries = 3
        attempt_history = []
        
        # DFS-style Retry Loop
        for attempt in range(max_retries + 1):
            # Check Iteration Limit
            self._check_and_wait_for_limit()
            
            # Increment global iteration
            self.current_iterations += 1
            self._save_iteration_state()
            
            attempt_label = f"Attempt {attempt+1}"
            branch_name = f"step-{step['step_id']}-{step_slug}-try-{attempt+1}"
            
            self.log(f"🌿 Branching: {branch_name} ({attempt_label}) (Global Iteration: {self.current_iterations})")
            
            # Always start from main (Clean State)
            self._run_git_cmd(["checkout", "main"])
            self._run_git_cmd(["checkout", "-b", branch_name])
            
            # 2. Code Generation / Fixing
            plan_desc = f"Execute Step {step['step_id']}"
            scheme_desc = "Initial Code Generation"
            
            if attempt == 0:
                self.log(f"🤖 Generating code for Step {step['step_id']}...")
                self._update_status(step_idx, total_steps, step['name'], "running", "Generating code...")
                
                existing_files = [f for f in os.listdir(self.workspace_path) 
                                if not f.startswith('.') and f not in ['execution.log', 'requirements.txt', '__pycache__']]
                try:
                    current_code = self.coding_agent.generate_code(step, self.plan, existing_files)
                    scheme_desc = "Generated new code based on plan"
                except Exception as e:
                    self.log(f"❌ Error generating code: {e}")
                    raise e
            else:
                self.log(f"🔄 {attempt_label}: Refinining code based on previous failure...")
                self._update_status(step_idx, total_steps, step['name'], "fixing", f"{attempt_label}: Fixing code...")
                
                plan_desc = f"Fix Step {step['step_id']} Failure"
                scheme_desc = "Refine code based on error log and git history"
                
                # We use the code from the PREVIOUS attempt (which failed) as the base to fix
                # Note: current_code currently holds the *failed* code from the loop bottom
                last_error = attempt_history[-1]['error']
                
                git_graph = self._get_git_graph()
                context_str = f"Step: {step['name']}\nDescription: {step['description']}\n\nGit Tree Context:\n{git_graph}"
                
                try:
                    current_code = self.coding_agent.fix_code(
                        current_code, 
                        last_error, 
                        context=context_str,
                        previous_attempts=attempt_history
                    )
                except Exception as e:
                    self.log(f"⚠️ Failed to generate fix: {e}")
                    break
            
            # 3. Save Code
            self.log(f"💾 Saving code to {filename}...")
            with open(os.path.join(self.workspace_path, filename), "w") as f:
                f.write(current_code)
                
            # Git Commit: "Attempt Start" -> We will commit result at the end instead to keep it cleaner?
            # User wants "Plan", "Scheme", "Result", "Decision".
            # We can't commit result before running.
            # But we can commit "Plan/Scheme" now?
            # Let's do ONE commit per attempt at the END, containing everything.
            # But if it crashes hard, we lose the code record in git.
            # Safe bet: Commit "Start" now, then "Result" later?
            # User said "form of structure... plan... result...".
            # If we commit twice, the tree gets deep.
            # Let's commit ONCE after execution with all info.
            
            # 4. Execute
            self.log(f"🚀 Executing {filename} in Docker ({attempt_label})...")
            if attempt == 0:
                self._update_status(step_idx, total_steps, step['name'], "running", "Executing code...")
            
            sandbox = DockerSandbox()
            res = sandbox.run_code(current_code, self.workspace_path, filename, image_name=self.image_tag)
            
            # Review Phase
            if res["exit_code"] == 0:
                self.log(f"🧐 Reviewing execution results...")
                try:
                    review_res = self.review_agent.review_code(step, self.plan, current_code, res, self.workspace_path)
                    if review_res['status'] != 'pass':
                        self.log(f"❌ Review Failed: {review_res['reason']}")
                        res["exit_code"] = 1
                        # Append review feedback to stderr so it's treated as an error log
                        res["stderr"] = f"Review Agent Rejected Result:\nReason: {review_res['reason']}\nSuggestions: {review_res['suggestions']}\n\n" + res.get('stderr', '')
                    else:
                        self.log(f"✅ Review Passed.")
                except Exception as e:
                    self.log(f"⚠️ Review check failed: {e}")

            if res["exit_code"] == 0:
                # SUCCESS
                self.log(f"✅ Execution successful.")
                stdout = res['stdout'].strip()
                log_out = stdout[:500] + "..." if len(stdout) > 500 else stdout
                self.log(f"Output:\n{log_out}")
                
                # Commit Success with Structured Info
                self._commit_structured(
                    step_id=step['step_id'],
                    attempt=attempt+1,
                    plan=plan_desc,
                    scheme=scheme_desc,
                    result="Success",
                    decision="Merge to main",
                    output=stdout
                )
                
                # Merge to main
                self.log(f"twisted_rightwards_arrows Merging {branch_name} into main...")
                self._run_git_cmd(["checkout", "main"])
                self._run_git_cmd(["merge", branch_name])
                
                self._update_status(step_idx, total_steps, step['name'], "completed", "Execution successful")
                return
                
            else:
                # FAILURE
                output = res['stdout'] if res['stdout'] else res['stderr']
                self.log(f"❌ Execution failed ({attempt_label}). Error:\n{output[:200]}...")
                
                # Decide next step
                decision = "Retry with fix" if attempt < max_retries else "Abort (Max retries reached)"
                
                # Commit Failure with Structured Info
                self._commit_structured(
                    step_id=step['step_id'],
                    attempt=attempt+1,
                    plan=plan_desc,
                    scheme=scheme_desc,
                    result="Failed",
                    decision=decision,
                    output=output
                )
                
                # Add to history for next branch to see
                attempt_history.append({"code": current_code, "error": output})
                
                # We DO NOT merge. We leave this branch dangling (or part of the tree history).
                # The loop continues -> Next iteration will checkout main and start a NEW branch.
                
                if attempt == max_retries:
                    error_msg = f"Execution failed after {max_retries + 1} attempts.\nLast Error: {output[:500]}"
                    self._update_status(step_idx, total_steps, step['name'], "failed", error_msg, experiment_status="failed")
                    raise Exception(f"Step {step['step_id']} execution failed.")

    def _build_environment(self, step_idx, total_steps):
        """Builds the custom Docker environment with dependencies."""
        self.log("🔨 Building experiment environment...")
        # Status update
        self._update_status(step_idx, total_steps, "Environment Setup", "running", "Building Docker environment...", experiment_status="running")
        
        sandbox = DockerSandbox()
        exp_id = os.path.basename(self.workspace_path)
        
        # Pre-Build Review
        req_path = os.path.join(self.workspace_path, "requirements.txt")
        if os.path.exists(req_path):
            with open(req_path, "r") as f:
                current_reqs = f.read()
            
            self.log("🧐 Reviewing requirements.txt before build...")
            review_res = self.review_agent.review_requirements(current_reqs, self.plan)
            
            if review_res['status'] == 'fail':
                self.log(f"⚠️ Requirements review failed: {review_res['reason']}")
                self.log(f"🛠️ Applying suggested fixes...")
                
                # If suggestion looks like a full file content, use it directly
                # Otherwise, we might need to ask CodingAgent to apply it.
                # For simplicity, if suggestions are short instructions, we ask CodingAgent.
                # If it's a list of packages, we might just overwrite.
                # Let's ask CodingAgent to fix it based on suggestions.
                
                try:
                    new_reqs = self.coding_agent.resolve_environment_error(
                        current_reqs, 
                        f"Reviewer rejected requirements: {review_res['reason']}\nSuggestions: {review_res['suggestions']}"
                    )
                    with open(req_path, "w") as f:
                        f.write(new_reqs)
                    self.log("✅ Applied requirements fixes.")
                except Exception as e:
                    self.log(f"⚠️ Failed to apply requirements fixes: {e}. Proceeding with original...")

        max_retries = 3
        attempt_history = []
        for attempt in range(max_retries + 1):
            try:
                self.image_tag = sandbox.build_experiment_image(exp_id, self.workspace_path)
                if self.image_tag:
                     self.log(f"✅ Environment built successfully: {self.image_tag}")
                     return # Success
                else:
                     # This usually means no requirements.txt, which is fine
                     self.image_tag = sandbox.image_name
                     return

            except Exception as e:
                self.log(f"⚠️ Environment build failed (Attempt {attempt+1}/{max_retries+1}): {e}")
                
                if attempt < max_retries:
                    self.log("🤖 Asking CodingAgent to fix requirements.txt...")
                    req_path = os.path.join(self.workspace_path, "requirements.txt")
                    if os.path.exists(req_path):
                        with open(req_path, "r") as f:
                            current_reqs = f.read()
                        
                        error_msg = str(e)
                        
                        # Get git history context
                        try:
                            res = subprocess.run(["git", "log", "--oneline", "--graph", "-n", "5"], cwd=self.workspace_path, capture_output=True, text=True)
                            error_msg += f"\n\nGit History (Recent):\n{res.stdout}"
                        except:
                            pass
                        
                        try:
                            new_reqs = self.coding_agent.resolve_environment_error(
                                current_reqs, 
                                error_msg,
                                previous_attempts=attempt_history
                            )
                            
                            # Add to history
                            attempt_history.append({"requirements": current_reqs, "error": error_msg})
                            
                            with open(req_path, "w") as f:
                                f.write(new_reqs)
                            self.log("Updated requirements.txt. Retrying build...")
                        except Exception as agent_error:
                             self.log(f"❌ Failed to resolve environment error: {agent_error}")
                             raise e
                    else:
                        self.log("No requirements.txt found but build failed. Cannot fix.")
                        raise e
                else:
                    self.log("❌ Failed to resolve environment issues after retries.")
                    raise e

    def _prepare_data(self, step_idx, total_steps):
        """Prepares necessary datasets or pre-computations."""
        self.log("📊 Checking for data preparation requirements...")
        self._update_status(step_idx, total_steps, "Data Preparation", "running", "Preparing datasets...", experiment_status="running")
        
        # Git: Ensure clean slate
        self._run_git_cmd(["checkout", "main"])
        # Use timestamp to avoid collision if retrying
        timestamp = int(time.time())
        branch_name = f"phase-data-prep-{timestamp}"
        self._run_git_cmd(["checkout", "-b", branch_name])
        
        # Create a dummy step for data prep to use CodingAgent
        dummy_step = {
            "step_id": "setup",
            "name": "Data Preparation",
            "description": "Check experiment requirements and generate a Python script 'setup_data.py' to download necessary public datasets or generate synthetic data. If no specific data is needed, just print 'No data setup needed'.",
            "dependencies": []
        }
        
        try:
            existing_files = [f for f in os.listdir(self.workspace_path) 
                            if not f.startswith('.') and f not in ['execution.log', 'requirements.txt', '__pycache__']]
            
            code = self.coding_agent.generate_code(dummy_step, self.plan, existing_files)
            
            filename = "setup_data.py"
            self.log(f"💾 Saving data prep code to {filename}...")
            with open(os.path.join(self.workspace_path, filename), "w") as f:
                f.write(code)
                
            # Git Commit
            self._run_git_cmd(["add", "."])
            self._run_git_cmd(["commit", "-m", "Generated setup_data.py"])
                
            self.log("🚀 Running data preparation script...")
            sandbox = DockerSandbox()
            # Use the custom image we just built
            res = sandbox.run_code(code, self.workspace_path, filename, image_name=self.image_tag)
            
            if res["exit_code"] == 0:
                self.log(f"✅ Data preparation complete.\nOutput: {res['stdout'][:500]}")
                
                # Git Success
                self._run_git_cmd(["add", "."])
                self._run_git_cmd(["commit", "--allow-empty", "-m", "Data Preparation Success"])
                self._run_git_cmd(["checkout", "main"])
                self._run_git_cmd(["merge", branch_name])
            else:
                self.log(f"❌ Data preparation failed: {res['stderr']}")
                
                # Git Fail
                self._run_git_cmd(["add", "."])
                self._run_git_cmd(["commit", "--allow-empty", "-m", "Data Preparation Failed"])
                raise Exception(f"Data preparation failed: {res['stderr']}")
                
        except Exception as e:
            self.log(f"⚠️ Data preparation step encountered error: {e}")
            # Depending on severity, we might want to stop. 
            # For now, we assume it's critical if it failed.
            raise e

    def _perform_analysis(self, step_idx, total_steps):
        """Generates analysis code and synthesizes conclusion."""
        self.log("📈 Starting Data Analysis & Conclusion Synthesis...")
        self._update_status(step_idx, total_steps, "Data Analysis", "running", "Generating analysis code...", experiment_status="running")
        
        # Git: Ensure clean slate
        self._run_git_cmd(["checkout", "main"])
        timestamp = int(time.time())
        branch_name = f"phase-analysis-{timestamp}"
        self._run_git_cmd(["checkout", "-b", branch_name])
        
        # Retry loop for Analysis Code & Conclusion
        max_retries = 3
        current_code = ""
        execution_success = False
        
        try:
            for attempt in range(max_retries):
                self.log(f"🔄 Analysis & Conclusion Attempt {attempt + 1}/{max_retries}")
                
                # 1. Generate/Fix Analysis Code
                existing_files = [f for f in os.listdir(self.workspace_path) 
                                if not f.startswith('.') and f not in ['execution.log', 'requirements.txt', '__pycache__']]
                
                if attempt == 0:
                    current_code = self.data_agent.generate_analysis_code(self.plan, existing_files)
                else:
                    self.log("🛠️ Fixing analysis code...")
                    # We need the error from the PREVIOUS iteration.
                    # It is stored in 'last_error' variable from the continue block
                    pass
                
                filename = "final_analysis.py"
                with open(os.path.join(self.workspace_path, filename), "w") as f:
                    f.write(current_code)
                
                # Git Commit Code
                self._run_git_cmd(["add", "."])
                self._run_git_cmd(["commit", "-m", f"Analysis Code Attempt {attempt+1}"])
                    
                self.log(f"🚀 Executing {filename} in Docker (Attempt {attempt+1})...")
                sandbox = DockerSandbox()
                res = sandbox.run_code(current_code, self.workspace_path, filename, image_name=self.image_tag)
                
                if res["exit_code"] != 0:
                    self.log(f"⚠️ Analysis failed: {res['stderr']}")
                    last_error = res['stderr']
                    
                    # Git Commit Failure
                    self._run_git_cmd(["add", "."])
                    self._run_git_cmd(["commit", "--allow-empty", "-m", f"Analysis Failed: {last_error[:50]}..."])
                    
                    # Prepare for next attempt
                    if attempt < max_retries - 1:
                         current_code = self.data_agent.fix_analysis_code(current_code, last_error, existing_files)
                    continue
                else:
                    self.log("✅ Analysis script executed successfully.")
                    if len(res['stdout']) > 200:
                        self.log(f"Output: {res['stdout'][:200]}...")
                    else:
                        self.log(f"Output: {res['stdout']}")
                    
                    # Check if output files were actually created (quantitative_summary.json)
                    if not os.path.exists(os.path.join(self.workspace_path, "quantitative_summary.json")):
                        self.log("⚠️ quantitative_summary.json missing. Treating as logical failure.")
                        last_error = "Script ran but did not generate 'quantitative_summary.json'. Check file paths."
                        
                        self._run_git_cmd(["add", "."])
                        self._run_git_cmd(["commit", "--allow-empty", "-m", "Analysis Missing Output"])
                        
                        if attempt < max_retries - 1:
                            current_code = self.data_agent.fix_analysis_code(current_code, last_error, existing_files)
                        continue
                    
                    # 2. Synthesize Conclusion (Inside Loop now)
                    self.log("🧠 Synthesizing findings to check for validity...")
                    
                    # Load quantitative summary
                    summary_path = os.path.join(self.workspace_path, "quantitative_summary.json")
                    quantitative_data = {}
                    if os.path.exists(summary_path):
                        with open(summary_path, "r") as f:
                            quantitative_data = json.load(f)
                    
                    conclusion = self.data_agent.synthesize_conclusion(self.plan, quantitative_data)
                    
                    # Check for failure indications in conclusion
                    summary_text = conclusion.get("summary", "").lower()
                    if "insufficient data" in summary_text or "failed" in summary_text or not conclusion.get("key_findings"):
                        self.log("⚠️ Conclusion indicates experiment failure (insufficient data/results).")
                        last_error = f"Analysis script ran, but the conclusion was: {summary_text}. Please fix the script to extract meaningful data."
                        
                        self._run_git_cmd(["add", "."])
                        self._run_git_cmd(["commit", "--allow-empty", "-m", "Conclusion: Insufficient Data"])
                        
                        if attempt < max_retries - 1:
                            current_code = self.data_agent.fix_analysis_code(current_code, last_error, existing_files)
                        continue
                    
                    # Success!
                    self.log("✅ Conclusion verified.")
                    
                    # Save conclusion
                    with open(os.path.join(self.workspace_path, "conclusion.json"), "w") as f:
                        json.dump(conclusion, f, indent=2)
                        
                    self._run_git_cmd(["add", "."])
                    self._run_git_cmd(["commit", "--allow-empty", "-m", "Analysis Success & Conclusion"])
                    execution_success = True
                    break
            
            if not execution_success:
                raise Exception("Analysis failed after max retries (Code Error or Insufficient Data).")

            # Merge to main
            self._run_git_cmd(["checkout", "main"])
            self._run_git_cmd(["merge", branch_name])
            
        except Exception as e:
            self.log(f"❌ Error during analysis phase: {e}")
            # Ensure status is updated to failed
            self._update_status(step_idx, total_steps, "Analysis Error", "failed", str(e), experiment_status="failed")
            # Don't re-raise to crash the runner, just end.
            return

    def run(self):
        # Clear log
        with open(self.log_file, "w") as f:
            f.write(f"Experiment initialized at {self.workspace_path}\n")
            
        self._init_workspace()
        self._setup_dependencies()
        
        try:
            steps = self.plan.get("steps", [])
            # Include Setup, Data Prep, and Analysis in total steps
            total = len(steps) + 3
            self.log(f"Plan contains {total} steps (including setup and analysis).")

            # New Phases
            self._build_environment(0, total)
            self._prepare_data(1, total)
            
            for i, step in enumerate(steps):
                self.run_step(step, i + 2, total)
                time.sleep(1) # Pause between steps
            
            # Perform Analysis
            self._perform_analysis(total-1, total)

            self.log("🎉 All steps executed successfully. Experiment finished.")
            self._update_status(total-1, total, "Experiment Completed", "completed", "Experiment finished.", experiment_status="completed")
            
        except Exception as e:
            self.log(f"❌ Error during execution: {str(e)}")
            self._update_status(0, 0, "Execution Error", "failed", str(e), experiment_status="failed")

    def run_analysis_only(self):
        """Runs only the analysis and conclusion synthesis phase."""
        try:
            self.log("🔄 Starting Manual Analysis & Conclusion Generation...")
            
            # Ensure sandbox is ready (get image tag)
            sandbox = DockerSandbox()
            exp_id = os.path.basename(self.workspace_path)
            # Try to guess the image tag based on convention
            self.image_tag = f"autoresearchlab/exp_{exp_id.lower()}"
            
            # Check if image exists, if not, try to build it
            image_exists = False
            try:
                sandbox.client.images.get(self.image_tag)
                self.log(f"✅ Found existing environment: {self.image_tag}")
                image_exists = True
            except:
                pass
                
            if not image_exists:
                self.log(f"⚠️ Environment image {self.image_tag} not found. Rebuilding...")
                self._build_environment(-1, 1)
            
            # Perform Analysis
            self._perform_analysis(1, 1)
            
            self.log("🎉 Analysis completed successfully.")
            self._update_status(1, 1, "Analysis Completed", "completed", "Manual analysis finished.", experiment_status="completed")
            
        except Exception as e:
            self.log(f"❌ Error during manual analysis: {str(e)}")
            self._update_status(0, 1, "Analysis Error", "failed", str(e), experiment_status="failed")

def start_experiment_background(workspace_path, plan):
    """Starts the experiment runner in a background thread."""
    runner = ExperimentRunner(workspace_path, plan)
    thread = threading.Thread(target=runner.run, daemon=True)
    thread.start()
    return thread

def start_analysis_background(workspace_path, plan):
    """Starts the analysis only in a background thread."""
    runner = ExperimentRunner(workspace_path, plan)
    thread = threading.Thread(target=runner.run_analysis_only, daemon=True)
    thread.start()
    return thread
