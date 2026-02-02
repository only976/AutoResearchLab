import pytest
from backend.agents.data_agent import DataAgent

class TestDataAgent:
    @pytest.fixture
    def agent(self):
        return DataAgent()

    def test_initialization(self, agent):
        assert agent is not None
