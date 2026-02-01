import os
import uuid
from dotenv import load_dotenv
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.tools.scholar_search import OpenAlexSearchTool
from backend.templates.idea_templates import get_template_descriptions, get_template_schema, RESEARCH_TOPIC_SCHEMA
from backend.utils.logger import setup_logger
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY
import json

# Load environment variables
load_dotenv()

class IdeaAgent:
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
        
        # Initialize Tools
        self.scholar_tool = OpenAlexSearchTool()
        
        # Wrap the search method as a callable tool for ADK
        def search_literature(query: str) -> str:
            """
            Search for relevant scientific literature using OpenAlex.
            Args:
                query: The search query string.
            Returns:
                A formatted string containing paper titles, authors, and abstracts.
            """
            return self.scholar_tool.search(query)

        self.tools = [search_literature]

        # Initialize the ADK Agent
        # Dynamic instruction based on template will be injected in generate_ideas
        self.agent = Agent(
            model=self.model,
            name="idea_agent",
            description="An agent specialized in generating engineering research ideas.",
            instruction="", # Will be set dynamically
            tools=self.tools
        )

    def refine_topic(self, raw_scope: str) -> str:
        """
        Analyzes the user's raw research scope.
        If broad, generates 3 distinct research topics.
        If specific, refines it into 1 research topic.
        Returns a JSON string containing 'is_broad', 'analysis', and a list of 'topics'.
        """
        instruction = f"""
        You are a Senior Research Advisor.
        
        INPUT: "{raw_scope}"
        
        TASK:
        1. Analyze the specificity of the input.
           - "Broad": Any input that covers a CATEGORY rather than a specific INSTANCE, or lacks technical specificity.
             * Examples of BROAD: "Board games AI", "Low-memory AI", "Healthcare LLMs", "Optimization algorithms".
             * Even "Board games in low-memory" is BROAD because "Board games" is a category (could be Go, Chess, Gomoku, etc.).
           - "Specific": Input that targets a SINGLE specific instance (e.g., "Gomoku", "Llama-3") AND a specific problem context.
             * Examples of SPECIFIC: "Bitboard-based Gomoku AI for 2KB RAM microcontrollers", "Pruning Llama-3 for mobile devices".
        
        2. IF BROAD:
           - You MUST classify it as "is_broad": true.
           - Generate 3 DISTINCT, CONCRETE research topics.
           - CRITICAL: Do not just repeat the category. You must instantiate it. 
             * Bad: "AI for Board Game A", "AI for Board Game B".
             * Good: "Micro-Go: MCTS for 8-bit MCUs", "Connect-4 solver on FPGA", "Chess endgame tablebase compression".
        
        3. IF SPECIFIC:
           - Refine it into 1 professional research topic.
        
        OUTPUT SCHEMA (JSON):
        {{
            "is_broad": true/false,
            "analysis": "Brief explanation. If broad, explain which category needs instantiation.",
            "topics": [
                {json.dumps(RESEARCH_TOPIC_SCHEMA)}
            ]
        }}
        
        IMPORTANT:
        - Output ONLY valid JSON.
        - Do not include markdown formatting like ```json.
        """
        
        # Create a specialized agent for refinement (no tools needed) to avoid distraction
        refinement_agent = Agent(
            model=self.model,
            name="refinement_agent",
            description="Specialized agent for refining research topics.",
            instruction=instruction,
            tools=[] # No tools for this step
        )
        
        # Use a separate runner/session for refinement
        runner = Runner(
            agent=refinement_agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        
        self.logger.info(f"Refining topic: {raw_scope}")
        try:
            events = runner.run(
                user_id="user",
                session_id=str(uuid.uuid4()),
                new_message=Content(role="user", parts=[Part(text=f"Analyze and refine: {raw_scope}")])
            )
            
            final_text = ""
            for event in events:
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        if part.text:
                            final_text += part.text
                            
            # Clean up
            final_text = final_text.strip()
            if final_text.startswith("```json"): final_text = final_text[7:]
            if final_text.startswith("```"): final_text = final_text[3:]
            if final_text.endswith("```"): final_text = final_text[:-3]
            
            final_text = final_text.strip()
            
            if not final_text:
                raise ValueError("Empty response from model during refinement.")
            
            self.logger.info("Topic refinement successful")
            return final_text
            
        except Exception as e:
            self.logger.error(f"Refinement failed: {e}", exc_info=True)
            # Fallback: return a structure indicating failure but keeping flow alive
            return json.dumps({
                "is_broad": False,
                "analysis": f"Refinement failed ({str(e)}), treating as specific raw input.",
                "topics": [{
                    "title": "Raw Topic",
                    "keywords": ["General"],
                    "tldr": raw_scope,
                    "abstract": raw_scope,
                    "refinement_reason": "Automated refinement failed."
                }]
            })

    def generate_ideas(self, scope: str) -> str:
        """
        Generates research ideas based on the provided scope using dynamic templates.
        """
        # Step 1: Decide which template to use (Simplified: We let the LLM decide implicitly but enforce consistency)
        
        template_descriptions = get_template_descriptions()
        
        instruction = f"""
        You are an experienced AI researcher and Engineering Research Scientist who aims to propose high-impact research ideas resembling exciting grant proposals.
        Your goal is to generate novel, feasible, and valuable research ideas based on a given research scope.
        Each proposal should stem from a simple and elegant question, observation, or hypothesis.
        
        You have access to a literature search tool `search_literature`.
        
        AVAILABLE TEMPLATES:
        {template_descriptions}
        
        PROTOCOL:
        1. Analyze the user's research scope and SELECT ONE single template type that best fits the problem.
        2. PERFORM A LITERATURE SEARCH using `search_literature` to understand the state-of-the-art and identify gaps. You CANNOT skip this step.
        3. ITERATIVE REFINEMENT (MANDATORY 2 ROUNDS):
           - **Round 1 (Conceptualization)**: Draft initial ideas. Critique them: Are they generic? If an idea says "use Deep Learning", it is BAD. It must specify architecture (e.g., "Transformer with relative positional encoding"). Refine the drafts.
           - **Round 2 (Technical Deep Dive)**: Critique the refined drafts. Are the "implementation_steps" or "proposed_method" executable? Add specific algorithms, loss functions, datasets, or baselines. Ensure the "Key Insight" is non-trivial. Refine again.
        4. Based on the 2-round refinement, finalize 3 distinct research ideas.
        5. Output the final result as a JSON Object with two top-level keys: "reasoning" and "ideas".
        
        OUTPUT FORMAT (JSON):
        {{
            "reasoning": {{
                "research_domain": "The specific field (e.g. Computer Vision, Game AI)",
                "selected_template": "The ID of the template you selected (e.g. scientific_discovery)",
                "rationale": "A brief explanation of why this template fits the user's scope."
            }},
            "ideas": [
                {{
                   // This object must strictly follow the schema of the selected template, including "title", "idea_name", "template_type", and "content".
                }},
                ... (2 more ideas)
            ]
        }}
        
        IMPORTANT:
        - The output MUST be a VALID JSON Object (starting with {{ and ending with }}).
        - STRICTLY FORBIDDEN: Do not output any conversational text, introductions (e.g. "Here are the ideas"), or markdown code blocks (```json). JUST THE RAW JSON STRING.
        - Ensure "ideas" is a list containing exactly 3 objects.
        """
        
        # Update agent instruction
        self.agent.instruction = instruction
        
        prompt_text = f"""
        Research Scope: {scope}
        
        Please generate 3 high-quality research ideas. 
        First, search for literature. 
        Then, reflect on the quality and novelty of potential ideas.
        Finally, choose the ONE best template and generate the final JSON output.
        
        REQUIREMENTS:
        - Be specific. Avoid vague terms like "optimize" or "improve" without saying HOW.
        - Ensure the "technical_plan" or "method" details are actionable.
        - The content should be dense and informative, suitable for a research proposal.
        
        REMEMBER: Output ONLY the raw JSON string. No "Here is the output" prefix.
        """
        
        self.logger.info(f"Generating ideas for scope: {scope}")
        runner = Runner(
            agent=self.agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        
        final_text = ""
        try:
            events = runner.run(
                user_id="user", 
                session_id=str(uuid.uuid4()), 
                new_message=Content(role="user", parts=[Part(text=prompt_text)])
            )
            
            for event in events:
                # Debug: print event to see structure if needed
                # print(f"DEBUG EVENT: {event}")
                
                # Only collect text content from model responses, ignoring tool calls/outputs in the final stream
                if event.content and event.content.parts:
                    for part in event.content.parts:
                        # Check if part has text and is NOT a tool call
                        # Note: DeepSeek/LiteLLM might return tool calls as text with special tokens
                        if part.text:
                            # Heuristic to skip tool call logs that might leak into text
                            if "<\uff5ctool" in part.text or "<function>" in part.text:
                                continue
                            final_text += part.text
            
            self.logger.info("Idea generation execution finished")
            
        except Exception as e:
            # Handle potential runtime errors from event loop closure
            self.logger.error(f"Runner execution completed with potential warning: {e}", exc_info=True)
            if not final_text:
                raise e

        # Post-processing: Clean up potential markdown wrappers
        final_text = final_text.strip()
        if final_text.startswith("```json"):
            final_text = final_text[7:]
        if final_text.startswith("```"):
            final_text = final_text[3:]
        if final_text.endswith("```"):
            final_text = final_text[:-3]
        
        return final_text.strip()
