import pytest
from backend.agents.writing_agent import WritingAgent

class TestWritingAgent:
    @pytest.fixture
    def agent(self):
        return WritingAgent()

    def test_initialization(self, agent):
        assert agent is not None
