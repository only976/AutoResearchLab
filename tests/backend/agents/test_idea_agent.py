import sys
import os
# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from backend.agents.idea_agent import IdeaAgent
from google.adk import Runner
from google.adk.sessions import InMemorySessionService
from google.genai.types import Content, Part

def test_generation():
    print("Initializing IdeaAgent...")
    try:
        agent_wrapper = IdeaAgent()
    except Exception as e:
        print(f"Failed to initialize agent: {e}")
        return

    scope = "Multi-agent reinforcement learning for autonomous driving in urban environments"
    print(f"Generating ideas for scope: {scope}")
    
    # Manually run with Runner to test
    try:
        runner = Runner(
            agent=agent_wrapper.agent,
            app_name="auto_research",
            session_service=InMemorySessionService(),
            auto_create_session=True
        )
        
        print("Starting runner...")
        
        events = runner.run(
            user_id="test_user", 
            session_id="test_session", 
            new_message=Content(role="user", parts=[Part(text=scope)])
        )
        
        final_text = ""
        for event in events:
            if event.content and event.content.parts:
                for part in event.content.parts:
                    if part.text:
                        print(f"Chunk: {part.text}")
                        final_text += part.text
        
        print("\n--- Final Text ---\n")
        print(final_text)
                 
    except Exception as e:
        print(f"Error during generation: {e}")

if __name__ == "__main__":
    test_generation()
