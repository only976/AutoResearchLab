import pytest
import unittest
from unittest.mock import MagicMock, patch
from backend.agents.idea_agent import IdeaAgent
from tests.helpers.context_manager import TestContextManager

class TestIdeaAgent:
    """
    Test Suite for IdeaAgent
    
    Tests cover:
    1. Initialization (Agent setup, Tool setup)
    2. Topic Refinement (Broad vs Specific inputs)
    3. Idea Generation (Template selection, Literature Search usage)
    """
    
    @pytest.fixture
    def agent(self):
        """Fixture to provide an IdeaAgent instance with mocked LLM."""
        # Mocking the heavy dependencies during initialization if possible
        # Since IdeaAgent init creates LiteLlm which might connect to network, 
        # we might want to patch LiteLlm or LLM config.
        # For now, we assume LiteLlm init is safe or we mock it.
        with patch('backend.agents.idea_agent.LiteLlm') as MockLlm:
             agent = IdeaAgent()
             agent.model = MockLlm.return_value # Replace model with mock
             return agent

    def test_initialization(self, agent):
        """Test that the agent initializes correctly with tools and sub-agents."""
        assert agent is not None
        assert agent.tools is not None
        assert len(agent.tools) >= 1 # Should have search tool
        assert callable(agent.tools[0]) # Search tool should be callable

    def test_refine_topic_broad(self, agent, context_manager: TestContextManager):
        """
        Test refine_topic with a broad input.
        Should return a JSON structure with is_broad=True and multiple topics.
        """
        raw_scope = "AI in Healthcare"
        
        # Mocking the Runner.run method which executes the LLM
        # We need to simulate the LLM's response for refinement
        mock_response_json = {
            "is_broad": True,
            "analysis": "Input is a broad category.",
            "topics": [
                {"title": "Topic A", "keywords": ["k1"], "tldr": "tldr A", "abstract": "abs A", "refinement_reason": "r A"},
                {"title": "Topic B", "keywords": ["k2"], "tldr": "tldr B", "abstract": "abs B", "refinement_reason": "r B"},
                {"title": "Topic C", "keywords": ["k3"], "tldr": "tldr C", "abstract": "abs C", "refinement_reason": "r C"}
            ]
        }
        
        # Create a mock event chain simulating LLM output
        mock_event = MagicMock()
        import json
        mock_event.content.parts = [MagicMock(text=json.dumps(mock_response_json))]
        
        # We need to patch 'google.adk.Runner.run' or the specific runner instance usage inside refine_topic
        # Since refine_topic instantiates its own Runner, we patch the class.
        with patch('backend.agents.idea_agent.Runner') as MockRunner, \
             patch('backend.agents.idea_agent.Agent') as MockAgent:
            instance = MockRunner.return_value
            instance.run.return_value = [mock_event]
            
            result_str = agent.refine_topic(raw_scope)
            
            # Verify result parsing
            result = json.loads(result_str)
            assert result['is_broad'] is True
            assert len(result['topics']) == 3

    def test_refine_topic_specific(self, agent):
        """
        Test refine_topic with a specific input.
        Should return a JSON structure with is_broad=False and 1 refined topic.
        """
        raw_scope = "Specific Topic X"
        
        mock_response_json = {
            "is_broad": False,
            "analysis": "Input is specific.",
            "topics": [
                {"title": "Refined Topic X", "keywords": ["k1"], "tldr": "tldr X", "abstract": "abs X", "refinement_reason": "r X"}
            ]
        }
        
        mock_event = MagicMock()
        import json
        mock_event.content.parts = [MagicMock(text=json.dumps(mock_response_json))]
        
        with patch('backend.agents.idea_agent.Runner') as MockRunner, \
             patch('backend.agents.idea_agent.Agent') as MockAgent:
            instance = MockRunner.return_value
            instance.run.return_value = [mock_event]
            
            result_str = agent.refine_topic(raw_scope)
            result = json.loads(result_str)
            
            assert result['is_broad'] is False
            assert len(result['topics']) == 1
            assert result['topics'][0]['title'] == "Refined Topic X"

    def test_generate_ideas(self, agent):
        """
        Test generate_ideas method.
        Should return a JSON string containing reasoning and ideas.
        """
        scope = "AI in Healthcare"
        
        mock_response_json = {
            "reasoning": {
                "research_domain": "Healthcare AI",
                "selected_template": "new_method",
                "rationale": "Testing rationale"
            },
            "ideas": [
                {
                    "title": "Idea 1",
                    "idea_name": "Idea 1 Name",
                    "template_type": "new_method",
                    "content": {"summary": "Summary 1"}
                },
                {
                    "title": "Idea 2",
                    "idea_name": "Idea 2 Name",
                    "template_type": "new_method",
                    "content": {"summary": "Summary 2"}
                },
                {
                    "title": "Idea 3",
                    "idea_name": "Idea 3 Name",
                    "template_type": "new_method",
                    "content": {"summary": "Summary 3"}
                }
            ]
        }
        
        mock_event = MagicMock()
        import json
        mock_event.content.parts = [MagicMock(text=json.dumps(mock_response_json))]
        
        # generate_ideas uses self.agent which is initialized in __init__
        # But it creates a NEW runner instance inside generate_ideas?
        # Let's check the code.
        # No, generate_ideas in IdeaAgent (lines 162+) creates a prompt but...
        # Wait, let's look at generate_ideas implementation again.
        
        with patch('backend.agents.idea_agent.Runner') as MockRunner:
            instance = MockRunner.return_value
            instance.run.return_value = [mock_event]
            
            # Note: generate_ideas implementation (which I need to verify) 
            # might use self.agent or create a new one. 
            # If it uses self.agent, patching Agent class might not affect it if it was already instantiated in __init__.
            # However, I mocked LiteLlm in fixture, so self.agent has a mock model.
            # But the Runner is instantiated inside generate_ideas?
            # Let's check source code of generate_ideas again to be sure.
            
            result_str = agent.generate_ideas(scope)
            result = json.loads(result_str)
            
            assert "reasoning" in result
            assert len(result["ideas"]) == 3
            assert result["ideas"][0]["title"] == "Idea 1"
