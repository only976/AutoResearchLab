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

# Load environment variables
load_dotenv()

class ExperimentDesignAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        # Initialize the LLM model using SiliconFlow configuration
        if LLM_API_BASE:
            self.model = LiteLlm(
                model=LLM_MODEL, 
                api_base=LLM_API_BASE,
                api_key=LLM_API_KEY
            )
        else:
            self.model = LLM_MODEL
        
    def refine_plan(self, idea: dict, topic: dict = None) -> str:
        """
        Takes a research idea and refines it into a detailed, executable experiment plan.
        
        Args:
            idea: The research idea dictionary (from IdeaAgent).
            topic: The research topic dictionary (optional context).
            
        Returns:
            JSON string containing the detailed experiment plan.
        """
        
        # Construct context string
        context_str = f"Research Idea Title: {idea.get('title', 'Untitled')}\n"
        if topic:
            context_str += f"Topic Context: {topic.get('title', '')} - {topic.get('tldr', '')}\n"
        
        # Extract existing plan/content based on template structure
        content = idea.get('content', {})
        if not content:
            # Fallback for flat structure
            content = idea
            
        context_str += f"\nIdea Content:\n{json.dumps(content, indent=2)}\n"

        instruction = """
        You are a Principal Research Engineer and System Architect.
        
        TASK:
        You are given a research idea and a high-level plan. Your goal is to convert this into a **Detailed, Executable Experiment Plan**.
        
        REQUIREMENTS:
        1. **Step Analysis & Refinement**: 
           - Break down the experiment into clear, sequential steps (Environment Setup -> Data Prep -> Implementation -> Training/Experiment -> Evaluation).
           - Ensure each step is concrete. "Implement algorithm" is bad. "Implement MCTS with UCB1 in Python using numpy" is good.
        
        2. **Technical Details**:
           - For each step, provide specific technical implementation details (e.g., specific algorithms, architectural choices, file formats).
        
        3. **Dependency Analysis**:
           - Identify ALL external dependencies required for each step.
           - Classify them into types: "python_package", "dataset", "paper", "system_tool" (e.g., docker, cuda), "other".
           - **CRITICAL**: Assess availability. 
             - **"auto_installable"**: DEFAULT for almost all software/data. Includes pip packages, system tools (apt/brew), public git repos, public datasets, and standard APIs.
             - **"manual_intervention_required"**: ONLY for:
               1. **Proprietary/Private Data** not available publicly.
               2. **Physical Hardware** constraints (e.g., "Requires Robot Arm", "Requires 1000 GPUs").
               3. **Impossible Software** (e.g., "Requires Windows-only app on Linux server").
             - **Rule of Thumb**: If it is code or data that *can* be downloaded/installed (even if complex), mark it as **"auto_installable"**.

        4. **Feasibility Check**:
           - Flag issues in the 'issues' list.
           - Use 'severity': "blocking" for hard blockers (impossible hardware/laws).
           - Use 'severity': "warning" for soft risks (high cost, long runtime, potential ambiguity).
           - **Do NOT** flag software configuration complexity or missing libraries as issues.
           
        OUTPUT SCHEMA (JSON):
        {
            "experiment_name": "Short name for the experiment",
            "goal": "Main objective of this experiment",
            "steps": [
                {
                    "step_id": 1,
                    "name": "Concise Step Name",
                    "description": "Detailed description of what to do",
                    "technical_details": "Specific implementation logic, math, or design patterns",
                    "dependencies": [
                        {
                            "name": "e.g., numpy", 
                            "type": "python_package", 
                            "reason": "For matrix operations",
                            "status": "auto_installable" // OR "manual_intervention_required"
                        }
                    ],
                    "artifacts": ["expected_output_file.py", "model_weights.pth", "plot.png"]
                }
            ],
            "issues": [
                {
                    "type": "dependency_missing" // OR "resource_constraint" OR "ambiguity",
                    "severity": "blocking", // OR "warning"
                    "description": "Description of the problem (e.g., 'Dataset X is proprietary')",
                    "action_required": "What the user needs to do (e.g., 'Manually download dataset to /data/')"
                }
            ]
        }
        
        IMPORTANT:
        - Output ONLY valid JSON.
        - Do not include markdown formatting like ```json.
        """
        
        agent = Agent(
            model=self.model,
            name="experiment_design_agent",
            description="Refines research ideas into executable plans.",
            instruction=instruction,
            tools=[]
        )
        
        runner = Runner(
            agent=agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        
        self.logger.info(f"Refining plan for idea: {idea.get('title')}")
        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=f"Refine this experiment plan:\n\n{context_str}")])
            )
            
            final_text = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final_text += part.text
            
            self.logger.info("Plan refinement completed successfully")
            
            # Clean up JSON
            final_text = final_text.strip()
            if final_text.startswith("```json"): final_text = final_text[7:]
            if final_text.startswith("```"): final_text = final_text[3:]
            if final_text.endswith("```"): final_text = final_text[:-3]
            final_text = final_text.strip()
            
            return final_text
            
        except Exception as e:
            self.logger.error(f"Plan refinement failed: {e}", exc_info=True)
            return json.dumps({
                "error": f"Plan refinement failed: {str(e)}",
                "steps": []
            })

    def process_feedback(self, current_plan: dict, user_feedback: str) -> str:
        """
        Updates the experiment plan based on user feedback to resolve/downgrade issues.
        """
        context_str = f"Current Plan:\n{json.dumps(current_plan, indent=2)}\n\nUser Feedback:\n{user_feedback}\n"
        
        instruction = """
        You are a Principal Research Engineer.
        
        TASK:
        Analyze the user's feedback regarding the current experiment plan's issues.
        Update the 'issues' list in the plan based on the feedback.
        
        RULES:
        1. If the user accepts a risk or provides a workaround, DOWNGRADE the issue severity from 'blocking' to 'warning' or REMOVE it if fully resolved.
        2. If the user provides new information (e.g., "I have the dataset"), REMOVE the dependency issue AND update the corresponding dependency status in 'steps' to 'auto_installable'.
        3. Do NOT remove steps unless explicitly asked.
        4. Maintain the rest of the plan structure exactly.
        
        OUTPUT SCHEMA (JSON):
        Same as input plan schema.
        """
        
        agent = Agent(
            model=self.model,
            name="experiment_design_agent_feedback",
            description="Updates plan based on feedback.",
            instruction=instruction,
            tools=[]
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
                new_message=Content(role="user", parts=[Part(text=f"Update this plan based on feedback:\n\n{context_str}")])
            )
            
            final_text = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final_text += part.text
            
            # Clean up JSON
            final_text = final_text.strip()
            if final_text.startswith("```json"): final_text = final_text[7:]
            if final_text.startswith("```"): final_text = final_text[3:]
            if final_text.endswith("```"): final_text = final_text[:-3]
            final_text = final_text.strip()
            
            return final_text
            
        except Exception as e:
            return json.dumps({
                "error": f"Feedback processing failed: {str(e)}",
                "steps": []
            })
