import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# LLM Configuration
# Option 1: DeepSeek (via SiliconFlow)
# LLM_MODEL = "openai/Pro/deepseek-ai/DeepSeek-V3"
# LLM_API_BASE = "https://api.siliconflow.cn/v1"
# LLM_API_KEY = os.getenv("SILICON_API_KEY")

# Option 2: Google Gemini (Native)
# To use Gemini, uncomment the lines below and comment out Option 1
LLM_MODEL = "gemini-3-flash-preview"
LLM_API_BASE = None
LLM_API_KEY = os.getenv("GOOGLE_API_KEY")
