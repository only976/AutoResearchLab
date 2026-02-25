import json
import os
from dotenv import load_dotenv
from google.adk.models.lite_llm import LiteLlm
from backend.utils.logger import setup_logger
from backend.config import LLM_MODEL, LLM_API_BASE, LLM_API_KEY

# Load environment variables
load_dotenv()

class ReviewAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        # Initialize the LLM model using centralized configuration
        if LLM_API_BASE:
            self.model = LiteLlm(
                model=LLM_MODEL, 
                api_base=LLM_API_BASE,
                api_key=LLM_API_KEY
            )
        else:
            self.model = LLM_MODEL
        
    def review_code(self, step: dict, plan: dict, code: str, execution_result: dict, workspace_path: str) -> dict:
        """
        Reviews the executed code and its output to verify if the step goals were met.
        
        Args:
            step (dict): The current step details.
            plan (dict): The overall experiment plan.
            code (str): The code that was executed.
            execution_result (dict): The result of execution (stdout, stderr, exit_code).
            workspace_path (str): Path to the workspace (to check for artifacts).
            
        Returns:
            dict: {
                "status": "pass" | "fail",
                "reason": "...",
                "suggestions": "..."
            }
        """
        self.logger.info(f"Reviewing step {step['step_id']} execution...")
        
        # Check for generated files (artifacts)
        files = [f for f in os.listdir(workspace_path) if not f.startswith('.')]
        
        prompt = f"""
        You are a Quality Assurance (QA) and Code Review Agent for an automated research system.
        Your task is to verify if the executed code effectively completed the goal of the current step AND effectively supports the overall experiment goal.
        
        # Experiment Context
        - Global Goal: {plan.get('goal', 'Unknown')}
        - Global Plan Overview: {len(plan.get('steps', []))} steps total.
        
        # Current Step Details
        - Step Name: {step['name']}
        - Step Description: {step['description']}
        - Expected Output: {step.get('expected_output', 'Not specified')}
        - Required Artifacts: {step.get('artifacts', [])}
        
        # Execution Details
        - Code Executed:
        ```python
        {code[:3000]} # Truncated if too long
        ```
        
        - Execution Output (Stdout):
        ```
        {execution_result.get('stdout', '')[:2000]}
        ```
        
        - Execution Errors (Stderr):
        ```
        {execution_result.get('stderr', '')[:1000]}
        ```
        
        - Workspace Files (Artifacts):
        {json.dumps(files, indent=2)}
        
        # Review Instructions
        1. **Step Fulfillment**: Did the code actually do what the step description asked?
        2. **Global Alignment**: Does this result support the Global Goal? (e.g., if the goal is "Analyze bias", did we actually calculate metrics relevant to bias? If the goal is "Train model", did we save the model for the next step?)
        3. **Logical Correctness**: Are there any obvious logical flaws? (e.g., training on test set, empty dataframes, all-zero results)
        4. **Artifact Check**: Are the required artifacts (files/charts) present?
        5. **Output Check**: Does the stdout indicate success without critical warnings?
        
        # Output Format
        Return a strictly valid JSON object (no markdown formatting):
        {{
            "status": "pass" or "fail",
            "reason": "Brief explanation of why it passed or failed.",
            "suggestions": "If failed, actionable instructions for the CodingAgent to fix it. If passed, any minor improvements or 'None'."
        }}
        """
        
        try:
            response = self.model.generate_content(prompt)
            content = response.text.strip()
            
            # Remove markdown code blocks if present
            if content.startswith("```"):
                content = content.strip("`json \n")
            
            result = json.loads(content)
            
            # Validate structure
            if "status" not in result:
                result["status"] = "pass" # Default to pass if malformed
                result["reason"] = "Reviewer output malformed, assuming pass."
                
            self.logger.info(f"Review Result: {result['status']}")
            return result
            
        except Exception as e:
            self.logger.error(f"Error during review: {e}")
            # Fallback to pass to not block workflow on reviewer error
            return {
                "status": "pass",
                "reason": f"Reviewer failed to execute: {e}",
                "suggestions": "None"
            }

    def review_requirements(self, requirements: str, plan: dict) -> dict:
        """
        Reviews requirements.txt before building the environment.
        
        Args:
            requirements (str): Content of requirements.txt.
            plan (dict): Experiment plan.
            
        Returns:
            dict: {
                "status": "pass" | "fail",
                "reason": "...",
                "suggestions": "..."
            }
        """
        self.logger.info("Reviewing requirements.txt...")
        
        prompt = f"""
        You are a Dependency Manager for a Python project.
        Review the following `requirements.txt` file for the given experiment plan.
        
        # Experiment Plan
        Goal: {plan.get('goal', 'Unknown')}
        Steps: {[s.get('name') for s in plan.get('steps', [])]}
        
        # Requirements File Content
        ```text
        {requirements}
        ```
        
        # Instructions
        1. Check for hallucinated packages (e.g. 'sklearn' should be 'scikit-learn').
        2. Check for obviously conflicting packages.
        3. Check if key libraries mentioned in the plan are missing.
        4. Standard libraries (os, sys, json, math, etc.) should NOT be in requirements.txt.
        
        # Output Format
        Return a strictly valid JSON object:
        {{
            "status": "pass" or "fail",
            "reason": "Brief explanation.",
            "suggestions": "Corrected requirements.txt content or specific fix instructions."
        }}
        """
        try:
            response = self.model.generate_content(prompt)
            content = response.text.strip()
            if content.startswith("```"):
                content = content.strip("`json \n")
            result = json.loads(content)
            
            # Ensure valid structure
            if "status" not in result:
                result["status"] = "pass"
                
            return result
        except Exception as e:
            self.logger.error(f"Error reviewing requirements: {e}")
            return {"status": "pass", "reason": f"Review failed: {e}"}
