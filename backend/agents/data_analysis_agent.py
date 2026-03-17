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

load_dotenv()

class DataAnalysisAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        self.model = LiteLlm(
            model="openai/Pro/deepseek-ai/DeepSeek-V3", 
            api_base="https://api.siliconflow.cn/v1",
            api_key=os.getenv("SILICON_API_KEY")
        )
        
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
