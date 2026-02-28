import os
import json
import uuid
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.utils.logger import setup_logger
from backend.config import get_llm_config

class WritingAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        cfg = get_llm_config()
        if cfg.get("api_base"):
            self.model = LiteLlm(
                model=cfg["model"],
                api_base=cfg["api_base"],
                api_key=cfg.get("api_key")
            )
        else:
            self.model = cfg["model"]
        
    def generate_paper(self, plan: dict, conclusion: dict, artifacts: list, format: str = "markdown") -> str:
        """Generates a research paper based on experiment data."""
        
        # Set up format-specific instructions
        if format.lower() == "latex":
            format_instruction = """Output the paper in LaTeX format.
Use standard LaTeX syntax with proper document structure.
Include placeholders for figures like \includegraphics{filename.png} where appropriate based on the available artifacts.
"""
        else:
            format_instruction = """Output the paper in Markdown format.
Use standard markdown headers (#, ##, ###).
Include placeholders for figures like `[Figure: filename.png]` where appropriate based on the available artifacts.
"""
        
        system_instruction = """You are an academic writing assistant. 
Your task is to write a comprehensive research paper based on the provided experiment plan, results, and conclusion.
The paper should follow standard academic structure:
1. Title
2. Abstract
3. Introduction (Background & Motivation)
4. Methodology (Experimental Setup)
5. Results (Key Findings & Evidence)
6. Discussion (Implications & Limitations)
7. Conclusion
8. References (Mocked if necessary, but strictly written according to APA format)

""" + format_instruction
        
        user_prompt = f"""
Experiment Title: {plan.get('title', 'Untitled')}
Goal: {plan.get('goal', 'N/A')}

Methodology Steps:
{json.dumps(plan.get('steps', []), indent=2)}

Conclusion & Findings:
{json.dumps(conclusion, indent=2)}

Available Artifacts (Figures/Tables):
{', '.join(artifacts)}

Please write the full paper.
"""

        agent = Agent(
            model=self.model,
            name="writing_agent",
            instruction=system_instruction
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
                new_message=Content(role="user", parts=[Part(text=user_prompt)])
            )
            
            response = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            response += part.text
                            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating paper: {e}", exc_info=True)
            return f"Error generating paper: {str(e)}"