import os
import json
import re
import uuid
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.utils.logger import setup_logger
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY

# Load environment variables
load_dotenv()

class CodingAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        # Initialize the LLM model using SiliconFlow configuration
        # Using the same configuration as ExperimentDesignAgent for consistency
        if LLM_API_BASE:
            self.model = LiteLlm(
                model=LLM_MODEL, 
                api_base=LLM_API_BASE,
                api_key=LLM_API_KEY
            )
        else:
            self.model = LLM_MODEL
        
    def generate_code(self, step: dict, plan: dict, context_files: list = None) -> str:
        """
        Generates Python code for a specific experiment step.
        
        Args:
            step: The current step dictionary from the plan.
            plan: The full experiment plan (for context).
            context_files: List of previously generated files (names only).
            
        Returns:
            String containing the executable Python code.
        """
        
        step_name = step.get('name', 'Unknown Step')
        step_desc = step.get('description', '')
        step_deps = step.get('dependencies', [])
        
        context_str = f"Experiment Plan: {plan.get('title', 'Untitled')}\n"
        context_str += f"Current Step: {step_name}\n"
        context_str += f"Description: {step_desc}\n"
        
        if step_deps:
            deps_list = [d.get('name') for d in step_deps if d.get('type') == 'python_package']
            context_str += f"Required Dependencies: {', '.join(deps_list)}\n"
            
        if context_files:
            context_str += f"Existing Files in Workspace: {', '.join(context_files)}\n"

        prompt = f"""
        You are an expert Python Research Engineer. Your task is to write a Python script to execute the current step of a research experiment.
        
        CONTEXT:
        {context_str}
        
        REQUIREMENTS:
        1. Write a COMPLETE, executable Python script.
        2. The script should perform the task described in the step.
        3. If this step produces data, save it to files (e.g., .csv, .json, .png) in the current directory.
        4. If this step relies on previous data, assume it exists in the current directory (check if file exists before reading).
        5. Include basic error handling (try/except) and print informative messages to stdout.
        6. Do NOT use placeholder comments like "# implement logic here". Write the actual logic.
        7. If the step is abstract (e.g., "Analyze results"), write code that would perform that analysis on the expected data.
        8. RETURN ONLY THE CODE. Use Markdown code blocks if necessary, but I will extract the content.
        
        PYTHON CODE:
        """
        
        self.logger.info(f"Generating code for step: {step_name}")
        
        # Create execution agent
        agent = Agent(
            model=self.model,
            name="coding_agent_exec",
            instruction="You are an expert Python Research Engineer."
        )

        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )

        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=prompt)])
            )
            
            response = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                         if part.text:
                             # Skip tool call artifacts if any
                             if "<\uff5ctool" in part.text or "<function>" in part.text:
                                continue
                             response += part.text

            self.logger.info(f"LLM Response received (length: {len(response)})")
            return self._clean_code(response)
        except Exception as e:
            self.logger.error(f"Error generating code: {e}", exc_info=True)
            return f"# Error generating code: {str(e)}\nprint('Error generating code')"

    def fix_code(self, code: str, error_message: str, context: str = "", previous_attempts: list = None) -> str:
        """
        Fixes the provided Python code based on the error message.
        """
        self.logger.info("Attempting to fix code...")
        
        history_section = ""
        if previous_attempts:
            history_section = "HISTORY OF PREVIOUS FAILED ATTEMPTS:\n"
            for i, attempt in enumerate(previous_attempts):
                history_section += f"--- Attempt {i+1} ---\n"
                # limit code length in history to avoid massive prompts, but keep enough context
                prev_code = attempt.get('code', '')
                if len(prev_code) > 2000:
                    prev_code = prev_code[:2000] + "\n... (truncated)"
                
                history_section += f"Code:\n```python\n{prev_code}\n```\n"
                history_section += f"Error:\n{attempt.get('error', 'Unknown Error')}\n\n"

        prompt = f"""
        You are an expert Python Research Engineer. The following code execution failed.
        
        CODE TO FIX:
        ```python
        {code}
        ```
        
        CURRENT ERROR MESSAGE:
        {error_message}
        
        {history_section}
        
        ADDITIONAL CONTEXT:
        {context}
        
        TASK:
        1. Analyze the error and fix the code.
        2. Return the COMPLETE fixed code.
        3. Do not assume any external fixes (like installing packages) unless you can solve it by importing correctly or using alternatives.
        4. If it's a syntax error, fix it. If it's a runtime error, add checks or fix logic.
        5. REVIEW THE HISTORY: Avoid repeating mistakes from previous attempts.
        
        FIXED PYTHON CODE:
        """
        
        # Create execution agent
        agent = Agent(
            model=self.model,
            name="coding_agent_fixer",
            instruction="You are an expert Python Research Engineer."
        )

        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )

        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=prompt)])
            )
            
            response = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                         if part.text:
                             # Skip tool call artifacts if any
                             if "<\uff5ctool" in part.text or "<function>" in part.text:
                                continue
                             response += part.text

            self.logger.info(f"Fix Response received (length: {len(response)})")
            return self._clean_code(response)
        except Exception as e:
            self.logger.error(f"Error fixing code: {e}", exc_info=True)
            return code # Return original code if fix fails

    def resolve_environment_error(self, requirements: str, error_log: str, previous_attempts: list = None) -> str:
        """
        Analyzes environment build errors and fixes requirements.txt.
        
        Args:
            requirements: The content of requirements.txt
            error_log: The build error log/output
            previous_attempts: List of dicts with 'requirements' and 'error' from prior failures
            
        Returns:
            The fixed requirements.txt content
        """
        self.logger.info("Attempting to resolve environment error...")
        
        history_section = ""
        if previous_attempts:
            history_section = "HISTORY OF PREVIOUS FAILED ATTEMPTS:\n"
            for i, attempt in enumerate(previous_attempts):
                history_section += f"--- Attempt {i+1} ---\n"
                history_section += f"Requirements:\n```\n{attempt.get('requirements', '')}\n```\n"
                history_section += f"Error:\n{attempt.get('error', 'Unknown Error')}\n\n"

        prompt = f"""
        You are an expert DevOps/Python Engineer. The Docker environment build failed due to dependency issues.
        
        CURRENT REQUIREMENTS.TXT:
        ```
        {requirements}
        ```
        
        ERROR LOG:
        {error_log}
        
        {history_section}
        
        TASK:
        1. Analyze the error (e.g., version conflict, package not found, build error).
        2. Fix the requirements list.
        3. Return ONLY the content of the new requirements.txt. NO conversational text.
        4. If a package is causing issues and is not critical, remove it or relax the version.
        5. REVIEW HISTORY: Do not repeat identical failed requirements.
        
        NEW REQUIREMENTS.TXT CONTENT:
        """
        
        agent = Agent(
            model=self.model,
            name="coding_agent_env_fixer",
            instruction="You are an expert DevOps Engineer. Output ONLY valid requirements.txt content."
        )

        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )

        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=prompt)])
            )
            
            response = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                         if part.text:
                             if "<\uff5ctool" in part.text or "<function>" in part.text:
                                continue
                             response += part.text
            
            self.logger.info(f"Env Fix Response received (length: {len(response)})")
            
            # Clean response
            content = response.strip()
            # Check for code blocks first
            code_block_pattern = r"```(?:txt|text)?(.*?)```"
            matches = re.findall(code_block_pattern, response, re.DOTALL)
            if matches:
                content = max(matches, key=len).strip()
            
            # Extra validation: filter out non-requirement lines
            final_lines = []
            for line in content.split('\n'):
                line = line.strip()
                # Skip empty lines
                if not line: 
                    continue
                # Keep comments
                if line.startswith('#'):
                    final_lines.append(line)
                    continue
                # Must start with alphanumeric (package name)
                if re.match(r'^[a-zA-Z0-9]', line):
                    final_lines.append(line)
            
            return "\n".join(final_lines)
            
        except Exception as e:
            self.logger.error(f"Error resolving env error: {e}", exc_info=True)
            return requirements # Return original if fix fails

    def _clean_code(self, response: str) -> str:
        """Extracts code from Markdown blocks if present."""
        # Check for markdown code blocks
        code_block_pattern = r"```python(.*?)```"
        matches = re.findall(code_block_pattern, response, re.DOTALL)
        
        if matches:
            # Return the longest code block found (usually the main script)
            return max(matches, key=len).strip()
        
        # Fallback: Check for generic code blocks
        code_block_pattern_generic = r"```(.*?)```"
        matches_generic = re.findall(code_block_pattern_generic, response, re.DOTALL)
        if matches_generic:
            return max(matches_generic, key=len).strip()
            
        # If no blocks, assume raw text is code (risky but necessary fallback)
        return response.strip()
