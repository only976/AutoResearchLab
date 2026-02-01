import os
import json
import uuid
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.utils.logger import setup_logger
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY

load_dotenv()

class WritingAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        if LLM_API_BASE:
            self.model = LiteLlm(
                model=LLM_MODEL, 
                api_base=LLM_API_BASE,
                api_key=LLM_API_KEY
            )
        else:
            # Use native model (e.g. Gemini) if API base is not provided
            self.model = LLM_MODEL
        
    def generate_paper(self, plan: dict, conclusion: dict, artifacts: list) -> str:
        """Generates a research paper based on experiment data."""
        
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
8. References (Mocked if necessary)

Output the paper in Markdown format.
Use standard markdown headers (#, ##, ###).
Include placeholders for figures like `[Figure: filename.png]` where appropriate based on the available artifacts.
"""
        
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
