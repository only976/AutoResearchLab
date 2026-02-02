import pytest
from backend.agents.review_agent import ReviewAgent

class TestReviewAgent:
    @pytest.fixture
    def agent(self):
        return ReviewAgent()

    def test_initialization(self, agent):
        assert agent is not None
