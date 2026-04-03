import os
from dotenv import load_dotenv

# Get the directory of the current file (project root)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load environment variables
load_dotenv()

# API Configuration
API_KEY = os.getenv("GOOGLE_API_KEY")
MODEL_ID = "gemini-3.1-pro-preview"

# Paths
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
