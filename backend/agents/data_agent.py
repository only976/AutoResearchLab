import os
import json
import uuid
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part
from google.adk.models.lite_llm import LiteLlm
from backend.utils.logger import setup_logger

load_dotenv()

class DataAgent:
    def __init__(self):
        self.logger = setup_logger(self.__class__.__name__)
        # Initialize Gemini API for experiment design generation
        self.gemini_api_key = os.getenv("GOOGLE_API_KEY")
        if not self.gemini_api_key:
            self.logger.warning("GOOGLE_API_KEY not found in environment variables.")
        
        # Also initialize DeepSeek model for other tasks
        self.model = LiteLlm(
            model="openai/Pro/deepseek-ai/DeepSeek-V3",
            api_base="https://api.siliconflow.cn/v1",
            api_key=os.getenv("SILICON_API_KEY")
        )

    def generate_experiment_design(self, idea_json_str: str) -> str:
        """
        Generates detailed experiment design JSON from a research idea.
        
        Args:
            idea_json_str: The research idea in JSON string format.
            
        Returns:
            String containing the generated experiment design in JSON format.
        """
        try:
            # 1. Parse upstream input JSON
            idea_data = json.loads(idea_json_str)
            
            # 2. Construct prompt for LLM
            prompt = f"""
            你是一个深度学习实验室的 AI 研究助理。请根据以下论文 Idea JSON，生成一份详细的实验设计 JSON。
            
            【输入 Idea 核心内容】:
            - 标题: {idea_data.get('idea', {}).get('title', 'Untitled')}
            - 创新点: {idea_data.get('idea', {}).get('innovation', 'Unknown')}
            - 基准模型: {idea_data.get('idea', {}).get('baselines', 'Unknown')}
            - 预期指标: {idea_data.get('idea', {}).get('success_metric', 'Unknown')}
            
            【输出要求】:
            1. 必须包含 'Datasets'：根据时间序列领域惯例，推荐 5 个常用数据集（如 ETT, Traffic, Electricity）。
            2. 必须包含 'Experimental_Group'：即本项目的完整模型配置。
            3. 必须包含 'Ablation_Groups'：针对 4 个创新点分别设计"剔除变量"。
            4. 必须包含 'Variables'：明确自变量（预测长度 96, 192, 336, 720）和因变量。
            5. 必须包含 'Expected_Output_Headers'：数组形式，给出结果数据表的列名。
            6. 格式：严格返回 JSON，不要有任何正文描述。
            """
            
            # 3. Call Gemini API
            self.logger.info("Generating experiment design via Gemini API")
            
            if not self.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured.")
            
            client = genai.Client(api_key=self.gemini_api_key)
            response = client.models.generate_content(
                model="gemini-3-flash-preview",
                contents=prompt,
                config={"response_mime_type": "application/json"}
            )
            
            self.logger.info("Experiment design generated successfully")
            return response.text
            
        except json.JSONDecodeError as e:
            self.logger.error(f"Failed to parse input JSON: {e}", exc_info=True)
            return json.dumps({
                "error": f"Invalid input JSON: {str(e)}",
                "datasets": [],
                "experimental_group": {},
                "ablation_groups": [],
                "variables": {},
                "expected_output_headers": []
            })
        except Exception as e:
            self.logger.error(f"Error generating experiment design: {e}", exc_info=True)
            return json.dumps({
                "error": f"Experiment design generation failed: {str(e)}",
                "datasets": [],
                "experimental_group": {},
                "ablation_groups": [],
                "variables": {},
                "expected_output_headers": []
            })

    def generate_data_collection_plan(self, experiment_design: dict) -> str:
        """
        Generates a data collection and sampling strategy based on experiment design.
        
        Args:
            experiment_design: The experiment design dictionary.
            
        Returns:
            String containing the data collection plan in JSON format.
        """
        self.logger.info(f"Generating data collection plan")
        
        context_str = f"Experiment Design:\n{json.dumps(experiment_design, indent=2)}\n"
        
        prompt = f"""
        You are a Data Science Expert. Based on the experiment design, generate a comprehensive data collection and sampling strategy.
        
        CONTEXT:
        {context_str}
        
        REQUIREMENTS:
        1. specify data sources and collection methods for each dataset.
        2. Define sampling strategies (train/val/test split ratios).
        3. Specify data preprocessing steps.
        4. Identify potential data quality issues and mitigation strategies.
        5. Return ONLY valid JSON with the following structure:
        {{
            "data_sources": [...],
            "sampling_strategy": {{...}},
            "preprocessing_steps": [...],
            "quality_checks": [...],
            "timeline": "..."
        }}
        """
        
        agent = Agent(
            model=self.model,
            name="data_agent_collector",
            instruction="You are a Data Science Expert."
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
                            response += part.text
            
            # Clean up JSON
            response = response.strip()
            if response.startswith("```json"):
                response = response[7:]
            if response.startswith("```"):
                response = response[3:]
            if response.endswith("```"):
                response = response[:-3]
            response = response.strip()
            
            return response
            
        except Exception as e:
            self.logger.error(f"Error generating data collection plan: {e}", exc_info=True)
            return json.dumps({
                "error": f"Data collection plan generation failed: {str(e)}",
                "data_sources": [],
                "sampling_strategy": {},
                "preprocessing_steps": [],
                "quality_checks": [],
                "timeline": ""
            })
