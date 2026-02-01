import os
import json
import uuid
import re
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.utils.logger import setup_logger
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY

load_dotenv()

class DataAnalysisAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        if LLM_API_BASE:
            self.model = LiteLlm(
                model=LLM_MODEL, 
                api_base=LLM_API_BASE,
                api_key=LLM_API_KEY
            )
        else:
            self.model = LLM_MODEL
        
    def generate_analysis_code(self, plan: dict, existing_files: list) -> str:
        """Generates Python code to visualize and summarize experiment results."""
        context_str = f"Experiment Title: {plan.get('title', 'Untitled')}\n"
        context_str += f"Goal: {plan.get('goal', 'Unknown')}\n"
        context_str += f"Available Files: {', '.join(existing_files)}\n"
        
        prompt = f"""
        You are a Data Science Expert. Your task is to write a Python script (`analysis.py`) to analyze the results of the experiment.
        
        CONTEXT:
        {context_str}
        
        REQUIREMENTS:
        1. Identify relevant data files (CSVs, JSONs) from the "Available Files" list.
        2. Load the data using pandas or json.
        3. Generate meaningful visualizations (matplotlib/seaborn) saved as PNG files.
           - Examples: Comparisons, trends, distributions.
           - Ensure titles and labels are clear.
        4. Calculate key metrics or summaries.
        5. IMPORTANT: The script MUST save a JSON file named `quantitative_summary.json` containing:
           - "metrics": Dictionary of calculated values.
           - "observations": List of text observations derived programmatically (e.g., "Algorithm A is 2x faster than B").
           - "generated_charts": List of filenames of charts generated.
        6. Return ONLY the Python code.
        """
        
        code = self._run_llm(prompt, "generate_analysis_code")
        
        # Clean up code blocks
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
            
        return code

    def fix_analysis_code(self, code: str, error_message: str, existing_files: list) -> str:
        """Fixes the analysis code based on error message."""
        prompt = f"""
        You are a Data Science Expert. The previous analysis script execution failed.
        
        CODE TO FIX:
        ```python
        {code}
        ```
        
        ERROR MESSAGE:
        {error_message}
        
        AVAILABLE FILES:
        {', '.join(existing_files)}
        
        TASK:
        1. Analyze the error (e.g., missing file, syntax error, library issue).
        2. Fix the code to handle the error (e.g., check file existence, use correct filenames, fix syntax).
        3. Ensure it still saves `quantitative_summary.json`.
        4. Return ONLY the fixed Python code.
        """
        
        code = self._run_llm(prompt, "fix_analysis_code")
        
        if "```python" in code:
            code = code.split("```python")[1].split("```")[0].strip()
        elif "```" in code:
            code = code.split("```")[1].split("```")[0].strip()
            
        return code

    def synthesize_conclusion(self, plan: dict, quantitative_summary: dict) -> dict:
        """Synthesizes a final conclusion based on the plan and quantitative analysis."""
        prompt = f"""
        You are a Principal Researcher. Synthesize a final conclusion for the experiment.
        
        EXPERIMENT PLAN:
        Title: {plan.get('title')}
        Goal: {plan.get('goal')}
        
        QUANTITATIVE RESULTS:
        {json.dumps(quantitative_summary, indent=2)}
        
        TASK:
        Generate a `conclusion.json` object with the following structure:
        {{
            "title": "Final Conclusion",
            "summary": "A concise executive summary of findings.",
            "key_findings": ["Finding 1", "Finding 2"],
            "evidence": {{
                "metrics": {{ ... key metrics ... }},
                "charts": ["list of chart files generated"]
            }},
            "recommendation": "Next steps or recommendations based on data."
        }}
        
        Return ONLY the JSON object.
        """
        
        response_text = self._run_llm(prompt, "synthesize_conclusion")
        try:
            # Extract JSON if wrapped in code blocks
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            return json.loads(response_text)
        except Exception as e:
            self.logger.error(f"Failed to parse conclusion JSON: {e}")
            return {
                "title": "Conclusion Generation Failed",
                "summary": "Could not parse agent response.",
                "raw_response": response_text
            }

    def _run_llm(self, prompt, task_name):
        self.logger.info(f"Running LLM for: {task_name}")
        agent = Agent(
            model=self.model,
            name="data_analysis_agent",
            instruction="You are a helpful Research Assistant."
        )
        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        
        events = runner.run(
            user_id="user",
            session_id=str(uuid.uuid4()),
            new_message=Content(role="user", parts=[Part(text=prompt)])
        )
        
        response = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    response += part.text
        return response
