import pytest
from backend.agents.experiment_design_agent import ExperimentDesignAgent

class TestExperimentDesignAgent:
    @pytest.fixture
    def agent(self):
        return ExperimentDesignAgent()

    def test_initialization(self, agent):
        assert agent is not None
