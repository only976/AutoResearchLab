import pytest
import unittest
from unittest.mock import MagicMock, patch
from backend.agents.coding_agent import CodingAgent

class TestCodingAgent:
    """
    Test Suite for CodingAgent
    
    Tests cover:
    1. Code Generation (Prompt construction, LLM response handling)
    2. Code Fixing (Error handling loop)
    """

    @pytest.fixture
    def agent(self):
        with patch('backend.agents.coding_agent.LiteLlm') as MockLlm:
             agent = CodingAgent()
             agent.model = MockLlm.return_value 
             return agent

    def test_generate_code_success(self, agent):
        """Test successful code generation from a step description."""
        step = {
            "name": "Data Preprocessing",
            "description": "Load data.csv and clean null values.",
            "dependencies": [{"name": "pandas", "type": "python_package"}]
        }
        plan = {"title": "Test Experiment"}
        
        # Mock LLM response
        expected_code = "import pandas as pd\ndf = pd.read_csv('data.csv')\nprint('Done')"
        
        mock_event = MagicMock()
        mock_event.content.parts = [MagicMock(text=f"Here is the code:\n```python\n{expected_code}\n```")]
        
        with patch('backend.agents.coding_agent.Runner') as MockRunner, \
             patch('backend.agents.coding_agent.Agent') as MockAgent:
            instance = MockRunner.return_value
            instance.run.return_value = [mock_event]
            
            generated_code = agent.generate_code(step, plan)
            
            # The agent method _clean_code should strip markdown
            assert "import pandas as pd" in generated_code
            assert "```" not in generated_code

    def test_fix_code_loop(self, agent):
        """Test the fix_code method which attempts to repair broken code."""
        broken_code = "print(undefined_variable)"
        error_msg = "NameError: name 'undefined_variable' is not defined"
        
        fixed_code = "undefined_variable = 1\nprint(undefined_variable)"
        
        mock_event = MagicMock()
        mock_event.content.parts = [MagicMock(text=f"```python\n{fixed_code}\n```")]
        
        with patch('backend.agents.coding_agent.Runner') as MockRunner, \
             patch('backend.agents.coding_agent.Agent') as MockAgent:
            instance = MockRunner.return_value
            instance.run.return_value = [mock_event]
            
            result = agent.fix_code(broken_code, error_msg)
            
            assert "undefined_variable = 1" in result
