import time
import json
import os
import threading
import subprocess
from backend.execution.feedback_manager import FeedbackManager
from backend.sandbox.docker_sandbox import DockerSandbox
from backend.agents.coding_agent import CodingAgent
from backend.agents.data_analysis_agent import DataAnalysisAgent
from backend.utils.logger import setup_logger

class ExperimentRunner:
    def __init__(self, workspace_path, plan):
        self.workspace_path = workspace_path
        self.plan = plan
        self.log_file = os.path.join(workspace_path, "execution.log")
        self.fm = FeedbackManager(workspace_path)
        self.coding_agent = CodingAgent()
        self.data_agent = DataAnalysisAgent()
        self.logger = setup_logger(self.__class__.__name__)
        self.image_tag = None # Initialize image tag
        
    def log(self, message):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        entry = f"[{timestamp}] {message}\n"
        print(entry.strip()) # Also print to console
        
        # Write to experiment-specific execution log
        with open(self.log_file, "a") as f:
            f.write(entry)
            
        # Also log to system-wide logger
        self.logger.info(f"[{os.path.basename(self.workspace_path)}] {message}")

    def _init_workspace(self):
        """Initializes git and workspace."""
        if not os.path.exists(os.path.join(self.workspace_path, ".git")):
            self.log("Initializing Git repository...")
            try:
                subprocess.run(["git", "init"], cwd=self.workspace_path, check=False, stdout=subprocess.DEVNULL)
                with open(os.path.join(self.workspace_path, ".gitignore"), "w") as f:
                    f.write("__pycache__/\n*.pyc\nexecution.log\n.DS_Store\n")
                subprocess.run(["git", "add", "."], cwd=self.workspace_path, check=False, stdout=subprocess.DEVNULL)
                subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=self.workspace_path, check=False, stdout=subprocess.DEVNULL)
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

    def run_step(self, step, step_idx, total_steps):
        self._update_status(step_idx, total_steps, step['name'], "running", "Initializing step...")
        self.log(f"▶️ Starting Step {step['step_id']}: {step['name']}")
        self.log(f"   Description: {step['description']}")
        
        # 1. Pre-execution Feedback Check
        pending = self.fm.get_pending_feedback()
        if pending:
            self.log(f"🔔 INTERRUPT: Received {len(pending)} user feedback item(s).")
            for item in pending:
                self.log(f"   👤 User says ({item['type']}): \"{item['message']}\"")
                # In a real system, we would call LLM here to adjust the plan
                self.log(f"   🤖 Agent: Acknowledged. Integrating feedback into current context...")
                self.fm.mark_processed(item['id'])
                time.sleep(1) # Simulate processing time
        
        # 2. Code Generation
        self.log(f"🤖 Generating code for Step {step['step_id']}...")
        self._update_status(step_idx, total_steps, step['name'], "running", "Generating code...")
        
        # Get list of existing files for context (excluding hidden and common junk)
        existing_files = [f for f in os.listdir(self.workspace_path) 
                         if not f.startswith('.') and f not in ['execution.log', 'requirements.txt', '__pycache__']]
        
        try:
            code = self.coding_agent.generate_code(step, self.plan, existing_files)
        except Exception as e:
            self.log(f"❌ Error generating code: {e}")
            self._update_status(step_idx, total_steps, step['name'], "failed", f"Error generating code: {e}")
            raise e

        filename = f"step_{step['step_id']}.py"
        current_code = code
        max_retries = 3
        attempt_history = []
        
        # 3. Save Code locally (for Git tracking)
        self.log(f"💾 Saving code to {filename}...")
        with open(os.path.join(self.workspace_path, filename), "w") as f:
            f.write(current_code)
            
        # 4. Execute in Docker with Retry Loop
        for attempt in range(max_retries + 1):
            if attempt > 0:
                 self.log(f"🔄 Attempt {attempt}/{max_retries}: Fixing code...")
                 self._update_status(step_idx, total_steps, step['name'], "fixing", f"Attempt {attempt}/{max_retries}: Fixing code...")
                 
            self.log(f"🚀 Executing {filename} in Docker (Attempt {attempt+1})...")
            if attempt == 0:
                self._update_status(step_idx, total_steps, step['name'], "running", "Executing code...")
            
            sandbox = DockerSandbox()
            
            # We pass the code directly. DockerSandbox will write/overwrite the file in the mounted volume and run it.
            res = sandbox.run_code(current_code, self.workspace_path, filename, image_name=self.image_tag)
            
            if res["exit_code"] == 0:
                self.log(f"✅ Execution successful.")
                # Log output but truncate if too long
                stdout = res['stdout'].strip()
                if len(stdout) > 500:
                    self.log(f"Output (truncated):\n{stdout[:500]}...")
                else:
                    self.log(f"Output:\n{stdout}")
                    
                # 5. Git Commit
                self.log("📦 Commiting changes to Git...")
                try:
                    subprocess.run(["git", "add", "."], cwd=self.workspace_path, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    subprocess.run(["git", "commit", "-m", f"Completed Step {step['step_id']}: {step['name']}"], cwd=self.workspace_path, check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    self.log("Git commit successful.")
                except Exception as e:
                    self.log(f"⚠️ Git commit failed: {e}")
                
                self._update_status(step_idx, total_steps, step['name'], "completed", "Execution successful")
                self.log(f"✅ Step {step['step_id']} completed sequence.")
                return # Success, exit function
                
            else:
                # Failure
                output = res['stdout'] if res['stdout'] else res['stderr']
                self.log(f"❌ Execution failed (Attempt {attempt+1}). Error:\n{output[:200]}...")
                
                if attempt < max_retries:
                    # Try to fix
                    try:
                        self.log("🤖 Asking CodingAgent to fix the code...")
                        new_code = self.coding_agent.fix_code(
                            current_code, 
                            output, 
                            context=f"Step: {step['name']}\nDescription: {step['description']}",
                            previous_attempts=attempt_history
                        )
                        
                        # Add current failure to history for next attempt
                        attempt_history.append({"code": current_code, "error": output})
                        
                        current_code = new_code
                        # Save new code
                        self.log(f"💾 Saving fixed code to {filename}...")
                        with open(os.path.join(self.workspace_path, filename), "w") as f:
                            f.write(current_code)
                    except Exception as e:
                        self.log(f"⚠️ Failed to generate fix: {e}")
                        break # Stop retrying if fixer fails
                else:
                    # Final failure
                    error_msg = f"Execution failed after {max_retries} retries.\nLast Error: {output[:500]}"
                    self._update_status(step_idx, total_steps, step['name'], "failed", error_msg, experiment_status="failed")
                    raise Exception(f"Step {step['step_id']} execution failed.")

    def _build_environment(self, step_idx, total_steps):
        """Builds the custom Docker environment with dependencies."""
        self.log("🔨 Building experiment environment...")
        # Status update
        self._update_status(step_idx, total_steps, "Environment Setup", "running", "Building Docker environment...", experiment_status="running")
        
        sandbox = DockerSandbox()
        exp_id = os.path.basename(self.workspace_path)
        
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
            with open(os.path.join(self.workspace_path, filename), "w") as f:
                f.write(code)
                
            self.log("🚀 Running data preparation script...")
            sandbox = DockerSandbox()
            # Use the custom image we just built
            res = sandbox.run_code(code, self.workspace_path, filename, image_name=self.image_tag)
            
            if res["exit_code"] == 0:
                self.log(f"✅ Data preparation complete.\nOutput: {res['stdout'][:500]}")
            else:
                self.log(f"❌ Data preparation failed: {res['stderr']}")
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
        
        try:
            # 1. Generate Analysis Code
            existing_files = [f for f in os.listdir(self.workspace_path) 
                            if not f.startswith('.') and f not in ['execution.log', 'requirements.txt', '__pycache__']]
            
            code = self.data_agent.generate_analysis_code(self.plan, existing_files)
            
            filename = "final_analysis.py"
            with open(os.path.join(self.workspace_path, filename), "w") as f:
                f.write(code)
                
            self.log(f"🚀 Executing {filename} in Docker...")
            sandbox = DockerSandbox()
            # Use the custom image we built
            res = sandbox.run_code(code, self.workspace_path, filename, image_name=self.image_tag)
            
            if res["exit_code"] != 0:
                self.log(f"⚠️ Analysis script execution failed: {res['stderr']}")
                # We don't fail hard here, as we might still try to synthesize a conclusion from what we have
            else:
                self.log("✅ Analysis script executed successfully.")
                if len(res['stdout']) > 200:
                    self.log(f"Output: {res['stdout'][:200]}...")
                else:
                    self.log(f"Output: {res['stdout']}")

            # 2. Synthesize Conclusion
            self._update_status(step_idx, total_steps, "Conclusion Synthesis", "running", "Synthesizing findings...", experiment_status="running")
            
            # Load quantitative summary if exists
            summary_path = os.path.join(self.workspace_path, "quantitative_summary.json")
            quantitative_data = {}
            if os.path.exists(summary_path):
                try:
                    with open(summary_path, "r") as f:
                        quantitative_data = json.load(f)
                except:
                    pass
            
            conclusion = self.data_agent.synthesize_conclusion(self.plan, quantitative_data)
            
            # Save conclusion
            with open(os.path.join(self.workspace_path, "conclusion.json"), "w") as f:
                json.dump(conclusion, f, indent=2)
                
            self.log("✅ Conclusion synthesized and saved to conclusion.json")
            
        except Exception as e:
            self.log(f"❌ Error during analysis phase: {e}")
            # Don't fail the whole experiment

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
