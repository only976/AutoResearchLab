import pytest
from backend.agents.data_analysis_agent import DataAnalysisAgent

class TestDataAnalysisAgent:
    @pytest.fixture
    def agent(self):
        return DataAnalysisAgent()

    def test_initialization(self, agent):
        assert agent is not None
